"""
Orchestrator — LangGraph state machine connecting all agents.
Pipeline: research → script → voiceover → avatar → video →
          thumbnail → seo → supervisor_review → upload → human_review →
          schedule → analytics
Crash recovery: SQLite checkpointing resumes from last completed node.
"""

import asyncio
import json
from typing import TypedDict, Optional, Literal

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from core.config import DB_PATH
from core.database import get_job, update_job
from core.logger import get_logger
from core.notification import send_alert, is_paused
from core.policy_checker import final_audit

log = get_logger("orchestrator", "system")


# ── Pipeline state ────────────────────────────────────────────

class PipelineState(TypedDict):
    job_id:             int
    topic:              dict
    template:           str
    metadata_json:      str           # JSON string — metadata accumulates here
    script:             str
    script_path:        str
    audio_path:         str
    avatar_path:        Optional[str]
    video_path:         str
    thumbnail_path:     str
    metadata:           dict
    youtube_video_id:   str
    preview_url:        str
    duration_sec:       float
    policy_violations:  list
    supervisor_ok:      bool
    human_approved:     bool
    rejection_reason:   str
    retry_count:        int
    error:              Optional[str]


# ── Node functions ────────────────────────────────────────────

def node_script(state: PipelineState) -> PipelineState:
    log.info(f"[Job {state['job_id']}] Node: script")
    from agents.script_agent import ScriptAgent
    return ScriptAgent().run(state)


def node_voiceover(state: PipelineState) -> PipelineState:
    log.info(f"[Job {state['job_id']}] Node: voiceover")
    from agents.voiceover_agent import VoiceoverAgent
    return VoiceoverAgent().run(state)


def node_avatar(state: PipelineState) -> PipelineState:
    log.info(f"[Job {state['job_id']}] Node: avatar")
    from agents.avatar_agent import AvatarAgent
    return AvatarAgent().run(state)


def node_video(state: PipelineState) -> PipelineState:
    log.info(f"[Job {state['job_id']}] Node: video")
    from agents.video_agent import VideoAgent
    return VideoAgent().run(state)


def node_thumbnail(state: PipelineState) -> PipelineState:
    log.info(f"[Job {state['job_id']}] Node: thumbnail")
    from agents.thumbnail_agent import ThumbnailAgent
    return ThumbnailAgent().run(state)


def node_seo(state: PipelineState) -> PipelineState:
    log.info(f"[Job {state['job_id']}] Node: seo")
    from agents.seo_agent import SEOAgent
    return SEOAgent().run(state)


def node_supervisor_review(state: PipelineState) -> PipelineState:
    """Final policy gate before sending to human."""
    job_id = state["job_id"]
    log.info(f"[Job {job_id}] Node: supervisor_review")

    result = final_audit(state)
    violations = result.get("violations", [])

    if result["passed"]:
        log.info(f"[Job {job_id}] Supervisor: APPROVED ✅")
        state["supervisor_ok"] = True
        state["policy_violations"] = []
    else:
        log.warning(f"[Job {job_id}] Supervisor: REJECTED ❌ — {violations}")
        state["supervisor_ok"] = False
        state["policy_violations"] = violations
        asyncio.create_task(
            send_alert(f"Supervisor rejected job {job_id}:\n" + "\n".join(violations))
        )

    return state


async def node_upload(state: PipelineState) -> PipelineState:
    """Upload as unlisted + wait for human Telegram approval."""
    job_id = state["job_id"]
    log.info(f"[Job {job_id}] Node: upload (unlisted)")

    from agents.upload_agent import UploadAgent
    agent = UploadAgent()

    async def on_approve(jid: int):
        update_job(jid, {"human_approved": 1, "status": "scheduling"})
        log.info(f"[Job {jid}] Human approved via Telegram")

    async def on_reject(jid: int, reason: str):
        update_job(jid, {"human_approved": 0, "rejection_reason": reason, "status": "failed"})
        log.warning(f"[Job {jid}] Human rejected: {reason}")

    return await agent.run(state, on_approve, on_reject)


def node_human_review(state: PipelineState) -> PipelineState:
    """
    Polling node — checks if human has approved/rejected.
    LangGraph will call this repeatedly (via conditional edge loop)
    until human_approved or rejection_reason is set.
    """
    job_id = state["job_id"]
    job = get_job(job_id)
    if not job:
        return state

    if job["human_approved"] == 1:
        state["human_approved"] = True
        log.info(f"[Job {job_id}] Human approval confirmed")
    elif job["rejection_reason"]:
        state["human_approved"] = False
        state["rejection_reason"] = job["rejection_reason"]
        log.warning(f"[Job {job_id}] Human rejected: {job['rejection_reason']}")

    return state


async def node_schedule(state: PipelineState) -> PipelineState:
    job_id   = state["job_id"]
    video_id = state["youtube_video_id"]
    log.info(f"[Job {job_id}] Node: schedule")
    from agents.scheduler_agent import SchedulerAgent
    await SchedulerAgent().schedule(job_id, video_id)
    update_job(job_id, {"status": "live"})
    return state


def node_failure(state: PipelineState) -> PipelineState:
    """Handle failure — determine retry target or stop."""
    job_id  = state["job_id"]
    retries = state.get("retry_count", 0) + 1
    state["retry_count"] = retries

    violations = state.get("policy_violations", [])
    reason     = state.get("rejection_reason", "")
    error      = state.get("error", "")
    combined   = " ".join(violations) + " " + reason + " " + error

    log.warning(f"[Job {job_id}] Failure handler (attempt {retries}) — {combined[:100]}")

    if retries >= 3:
        log.error(f"[Job {job_id}] 3 retries exhausted — stopping pipeline")
        asyncio.create_task(
            send_alert(
                f"⛔ Job {job_id} failed after 3 retries.\n"
                f"Last error: {combined[:200]}\n"
                f"Manual intervention required."
            )
        )
        update_job(job_id, {"status": "failed_manual_required"})

    return state


# ── Routing functions ─────────────────────────────────────────

def route_after_node(state: PipelineState) -> Literal["failure", "continue"]:
    """Generic: if error set → failure, else continue."""
    if state.get("error") or state.get("policy_violations"):
        return "failure"
    return "continue"


def route_supervisor(state: PipelineState) -> Literal["upload", "failure"]:
    return "upload" if state.get("supervisor_ok") else "failure"


def route_human_review(state: PipelineState) -> Literal["schedule", "failure", "wait"]:
    if state.get("human_approved") is True:
        return "schedule"
    elif state.get("rejection_reason"):
        return "failure"
    return "wait"  # not decided yet — loop back


def route_failure(
    state: PipelineState,
) -> Literal["script", "voiceover", "video", "thumbnail", "seo", "end"]:
    if state.get("retry_count", 0) >= 3:
        return "end"
    error = (state.get("error", "") + " " + " ".join(state.get("policy_violations", []))).lower()
    if "script"     in error: return "script"
    if "audio"      in error: return "voiceover"
    if "thumbnail"  in error: return "thumbnail"
    if "seo"        in error or "metadata" in error: return "seo"
    return "video"   # default retry


# ── Graph builder ─────────────────────────────────────────────

def build_pipeline() -> StateGraph:
    g = StateGraph(PipelineState)

    # Register all nodes
    g.add_node("script",            node_script)
    g.add_node("voiceover",         node_voiceover)
    g.add_node("avatar",            node_avatar)
    g.add_node("video",             node_video)
    g.add_node("thumbnail",         node_thumbnail)
    g.add_node("seo",               node_seo)
    g.add_node("supervisor_review", node_supervisor_review)
    g.add_node("upload",            node_upload)
    g.add_node("human_review",      node_human_review)
    g.add_node("schedule",          node_schedule)
    g.add_node("failure",           node_failure)

    # Entry
    g.set_entry_point("script")

    # Linear edges (with error check after each)
    for src, dst in [
        ("script",    "voiceover"),
        ("voiceover", "avatar"),
        ("avatar",    "video"),
        ("video",     "thumbnail"),
        ("thumbnail", "seo"),
        ("seo",       "supervisor_review"),
    ]:
        g.add_conditional_edges(
            src,
            route_after_node,
            {"continue": dst, "failure": "failure"},
        )

    # Supervisor → upload or failure
    g.add_conditional_edges(
        "supervisor_review",
        route_supervisor,
        {"upload": "upload", "failure": "failure"},
    )

    # Upload → human review
    g.add_conditional_edges(
        "upload",
        route_after_node,
        {"continue": "human_review", "failure": "failure"},
    )

    # Human review → schedule | failure | wait (loop)
    g.add_conditional_edges(
        "human_review",
        route_human_review,
        {"schedule": "schedule", "failure": "failure", "wait": "human_review"},
    )

    g.add_edge("schedule", END)

    # Failure → retry specific node or END
    g.add_conditional_edges(
        "failure",
        route_failure,
        {
            "script":    "script",
            "voiceover": "voiceover",
            "video":     "video",
            "thumbnail": "thumbnail",
            "seo":       "seo",
            "end":       END,
        },
    )

    # SQLite checkpointing — crash recovery
    memory = SqliteSaver.from_conn_string(str(DB_PATH))
    return g.compile(checkpointer=memory)


# ── Entry point ───────────────────────────────────────────────

async def run_pipeline(job_id: int) -> None:
    """Called by main.py scheduler when topic is approved."""
    job = get_job(job_id)
    if not job:
        log.error(f"Job {job_id} not found")
        return

    if is_paused():
        log.info(f"Pipeline paused — job {job_id} queued")
        return

    meta = json.loads(job["metadata_json"] or "{}")
    topic_data = meta.get("topic_data", {"title": job["topic"]})

    initial_state: PipelineState = {
        "job_id":           job_id,
        "topic":            topic_data,
        "template":         job["template_used"] or "A",
        "metadata_json":    job["metadata_json"] or "{}",
        "script":           "",
        "script_path":      "",
        "audio_path":       "",
        "avatar_path":      None,
        "video_path":       "",
        "thumbnail_path":   "",
        "metadata":         meta,
        "youtube_video_id": "",
        "preview_url":      "",
        "duration_sec":     0,
        "policy_violations": [],
        "supervisor_ok":    False,
        "human_approved":   False,
        "rejection_reason": "",
        "retry_count":      0,
        "error":            None,
    }

    pipeline = build_pipeline()
    config   = {"configurable": {"thread_id": str(job_id)}}

    log.info(f"[Job {job_id}] Pipeline starting — topic: {topic_data.get('title', '')}")
    update_job(job_id, {"status": "running"})

    try:
        async for event in pipeline.astream(initial_state, config=config):
            node = list(event.keys())[0]
            log.info(f"[Job {job_id}] Completed node: {node}")
    except Exception as e:
        log.error(f"[Job {job_id}] Pipeline crashed: {e}", exc_info=True)
        update_job(job_id, {"status": "crashed"})
        await send_alert(f"Pipeline crashed for job {job_id}:\n{e}")
