"""
Notification system — ntfy.sh (free, no bot setup).
Sends alerts to your phone via ntfy app.
Action buttons in notifications for approve/reject.

Setup:
  1. Install ntfy app on phone
  2. Subscribe to topic: yt-automatiom
  3. Set NTFY_TOPIC=yt-automatiom in .env
  4. Done — no tokens, no bot, no chat ID needed
"""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

NTFY_TOPIC   = os.getenv("NTFY_TOPIC", "yt-automatiom")
NTFY_SERVER  = os.getenv("NTFY_SERVER", "https://ntfy.sh")
NTFY_URL     = f"{NTFY_SERVER}/{NTFY_TOPIC}"

# Callback hooks set by orchestrator
_callbacks: dict = {
    "approve_topic":  None,   # callable(topic: dict)
    "approve_video":  None,   # callable(job_id: int)
    "reject_video":   None,   # callable(job_id: int, reason: str)
}

# Pending state
_state: dict = {
    "pending_topics":  [],    # list of topic dicts
    "pending_job_id":  None,  # job_id awaiting approval
    "paused":          False,
}

from core.logger import get_logger
log = get_logger("notification", "system")


# ── Core send function ────────────────────────────────────────

def send(
    message: str,
    title: str = "YT Automation",
    priority: str = "default",
    tags: list | None = None,
    actions: list | None = None,
    attach: str | None = None,
) -> None:
    """
    Send ntfy notification.
    actions format: [{"action": "http", "label": "Approve", "url": "...", "method": "POST"}]
    """
    headers = {
        "Title":    title,
        "Priority": priority,
    }
    if tags:
        headers["Tags"] = ",".join(tags)
    if actions:
        # Use 'view' type — opens URL in phone browser (GET request)
        # Works with any tunnel including LocalX
        headers["Actions"] = "; ".join(
            f"view, {a['label']}, {a['url']}"
            for a in actions
        )
    if attach:
        headers["Attach"] = attach

    try:
        r = requests.post(
            NTFY_URL,
            data=message.encode("utf-8", errors="replace"),
            headers={k: v.encode("latin-1", errors="replace").decode("latin-1") for k, v in headers.items()},
            timeout=10,
        )
        if r.status_code != 200:
            log.warning(f"ntfy send failed: {r.status_code} {r.text}")
        else:
            log.info(f"ntfy sent: {title}")
    except Exception as e:
        log.error(f"ntfy error: {e}")


def send_alert(message: str) -> None:
    send(message, title="ALERT", priority="high", tags=["warning"])


# ── Action server (receives button taps from ntfy) ────────────

class _ActionHandler(BaseHTTPRequestHandler):
    """Tiny HTTP server that receives ntfy action button callbacks."""

    def do_GET(self):
        self._handle()

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def _handle(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/approve_topic":
            idx = int(params.get("idx", ["0"])[0])
            topics = _state["pending_topics"]
            if 0 <= idx < len(topics):
                chosen = topics[idx]
                _state["pending_topics"] = []
                cb = _callbacks.get("approve_topic")
                if cb:
                    threading.Thread(target=cb, args=(chosen,), daemon=True).start()
                self._respond(f"Topic approved: {chosen['title']}")
                send(f"Pipeline starting for: {chosen['title']}", title="Topic Approved", tags=["white_check_mark"])
            else:
                self._respond("Invalid topic index")

        elif parsed.path == "/approve_video":
            job_id = _state.get("pending_job_id")
            if job_id:
                from core.database import update_job
                update_job(job_id, {"human_approved": 1, "status": "scheduling"})
                _state["pending_job_id"] = None
                cb = _callbacks.get("approve_video")
                if cb:
                    threading.Thread(target=cb, args=(job_id,), daemon=True).start()
                self._respond("Video approved")
                send("Video approved! Scheduling...", title="Approved", tags=["white_check_mark"])
            else:
                self._respond("No video pending")

        elif parsed.path == "/reject_video":
            job_id = _state.get("pending_job_id")
            reason = params.get("reason", ["No reason given"])[0]
            if job_id:
                from core.database import update_job
                update_job(job_id, {
                    "human_approved": 0,
                    "rejection_reason": reason,
                    "status": "failed"
                })
                _state["pending_job_id"] = None
                cb = _callbacks.get("reject_video")
                if cb:
                    threading.Thread(target=cb, args=(job_id, reason), daemon=True).start()
                self._respond("Video rejected")
                send(f"Video rejected: {reason}", title="Rejected", tags=["x"])
            else:
                self._respond("No video pending")

        elif parsed.path == "/pause":
            _state["paused"] = True
            self._respond("Pipeline paused")
            send("Pipeline paused", title="Paused", tags=["pause_button"])

        elif parsed.path == "/resume":
            _state["paused"] = False
            self._respond("Pipeline resumed")
            send("Pipeline resumed", title="Resumed", tags=["arrow_forward"])

        else:
            self._respond("Unknown action", status=404)

    def _respond(self, msg: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        html = f"<html><body style='font-family:sans-serif;padding:40px;text-align:center'><h2>{msg}</h2><p>You can close this tab.</p></body></html>"
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        pass  # suppress default HTTP logs


def start_action_server(port: int = 5055) -> None:
    """Start action server in background thread."""
    server = HTTPServer(("0.0.0.0", port), _ActionHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    log.info(f"ntfy action server running on port {port}")


def get_action_url(path: str, params: dict | None = None) -> str:
    """Build action URL. For local: localhost. For deployed: your server IP/domain."""
    base = os.getenv("ACTION_BASE_URL", "http://localhost:5055")
    url  = f"{base}{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    return url


# ── High-level notification helpers ──────────────────────────

async def send_topics_notification(topics: list, cb_approve: Callable) -> None:
    _state["pending_topics"] = topics
    _callbacks["approve_topic"] = cb_approve

    actions = []
    lines = ["Pick a topic:\n"]
    for i, t in enumerate(topics[:5]):
        lines.append(f"{i+1}. [{t['score']}] {t['title']}\n   {t.get('trend_momentum','')}")
        if i < 3:
            actions.append({
                "label":  f"Pick {i+1}",
                "url":    get_action_url("/approve_topic", {"idx": i}),
                "method": "POST",
            })

    send(
        message="\n".join(lines),
        title="Topics Ready - Pick One",
        priority="high",
        tags=["clipboard"],
        actions=actions,
    )


def send_video_review(
    job_id: int,
    preview_url: str,
    metadata: dict,
    policy_ok: bool,
    cb_approve: Callable,
    cb_reject: Callable,
) -> None:
    _state["pending_job_id"] = job_id
    _callbacks["approve_video"] = cb_approve
    _callbacks["reject_video"]  = cb_reject

    policy_txt = "All policy checks passed" if policy_ok else "Policy warnings — check preview"
    msg = (
        f"Title: {metadata.get('title','N/A')}\n"
        f"Duration: ~{metadata.get('duration_min','?')} min\n"
        f"Policy: {policy_txt}\n"
        f"Preview: {preview_url}"
    )

    send(
        message=msg,
        title="Video Ready - Approve?",
        priority="high",
        tags=["movie_camera"],
        actions=[
            {"label": "Approve", "url": get_action_url("/approve_video"), "method": "POST"},
            {"label": "Reject",  "url": get_action_url("/reject_video", {"reason": "rejected_by_human"}), "method": "POST"},
        ],
    )


def send_published(title: str, publish_time: str, url: str) -> None:
    send(
        f"Title: {title}\nPublishes: {publish_time}\nLink: {url}",
        title="Video Scheduled",
        tags=["rocket"],
    )


def send_weekly_report(report: str) -> None:
    send(report, title="Weekly Channel Report", tags=["bar_chart"])


def is_paused() -> bool:
    return _state["paused"]


def register_callbacks(
    on_approve_topic: Callable,
    on_approve_video: Callable,
    on_reject_video: Callable,
) -> None:
    _callbacks["approve_topic"] = on_approve_topic
    _callbacks["approve_video"] = on_approve_video
    _callbacks["reject_video"]  = on_reject_video
