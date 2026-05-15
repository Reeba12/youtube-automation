"""
Analytics Agent — pulls YouTube Analytics API data daily.
Tracks: CTR, AVD, RPM, subs, revenue per video.
Generates weekly insight report via Claude → Telegram.
Feeds performance data back to Research Agent topic scoring.
"""

import json
import pickle
from datetime import datetime, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from agents.base import claude, advance_job
from core.config import YOUTUBE_CLIENT_SECRETS_PATH, YOUTUBE_TOKEN_PATH
from core.database import (
    get_recent_completed_jobs, get_channel_stats,
    save_analytics, get_topic_performance_history,
)
from core.logger import get_logger
from core.notification import send_weekly_report

log = get_logger("analytics_agent", "system")

ANALYTICS_SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]

METRICS = ",".join([
    "views", "estimatedMinutesWatched", "averageViewDuration",
    "averageViewPercentage", "subscribersGained", "likes", "comments",
    "shares", "estimatedRevenue", "estimatedAdRevenue",
    "impressions", "impressionClickThroughRate",
])


class AnalyticsAgent:

    def __init__(self):
        self._yt_analytics = None
        self._yt_data      = None

    def _get_clients(self):
        if self._yt_analytics:
            return self._yt_analytics, self._yt_data

        creds = None
        token_path = Path(YOUTUBE_TOKEN_PATH)
        if token_path.exists():
            with open(token_path, "rb") as f:
                creds = pickle.load(f)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())

        self._yt_analytics = build("youtubeAnalytics", "v2", credentials=creds)
        self._yt_data      = build("youtube", "v3", credentials=creds)
        return self._yt_analytics, self._yt_data

    async def run_daily(self) -> None:
        """Pull analytics for all live videos — runs daily 9am EST."""
        log.info("Analytics Agent: daily pull starting")
        jobs = get_recent_completed_jobs(limit=30)
        if not jobs:
            log.info("No live videos yet")
            return

        analytics, _ = self._get_clients()
        today     = datetime.utcnow().date()
        start_date = (today - timedelta(days=30)).isoformat()
        end_date   = today.isoformat()

        for job in jobs:
            video_id = job["youtube_video_id"]
            if not video_id:
                continue
            try:
                data = self._pull_video_analytics(analytics, video_id, start_date, end_date)
                if data:
                    save_analytics(job["id"], video_id, data)
                    log.info(f"Analytics saved for video {video_id}: CTR={data.get('ctr',0):.1f}%")
            except Exception as e:
                log.warning(f"Analytics pull failed for {video_id}: {e}")

        # Update topic performance table
        self._update_topic_performance()
        log.info("Analytics Agent: daily pull complete")

    async def run_weekly_report(self) -> None:
        """Generate weekly insight report → Telegram. Runs Sunday 6pm EST."""
        log.info("Analytics Agent: generating weekly report")
        stats  = get_channel_stats()
        history = get_topic_performance_history()
        jobs   = get_recent_completed_jobs(limit=10)

        report = self._generate_report(stats, history, jobs)
        await send_weekly_report(report)
        log.info("Weekly report sent to Telegram")

    # ── Analytics pull ────────────────────────────────────────

    def _pull_video_analytics(
        self,
        analytics,
        video_id: str,
        start_date: str,
        end_date: str,
    ) -> dict:
        try:
            resp = analytics.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics=METRICS,
                filters=f"video=={video_id}",
                dimensions="video",
            ).execute()

            rows = resp.get("rows", [])
            if not rows:
                return {}

            row = rows[0]
            cols = [h["name"] for h in resp.get("columnHeaders", [])]
            vals = dict(zip(cols, row))

            return {
                "views":                  int(vals.get("views", 0)),
                "avg_view_duration_sec":  int(vals.get("averageViewDuration", 0)),
                "avg_view_percentage":    round(float(vals.get("averageViewPercentage", 0)), 1),
                "subscribers_gained":     int(vals.get("subscribersGained", 0)),
                "likes":                  int(vals.get("likes", 0)),
                "comments":               int(vals.get("comments", 0)),
                "estimated_revenue_usd":  round(float(vals.get("estimatedRevenue", 0)), 2),
                "rpm":                    round(
                    float(vals.get("estimatedRevenue", 0)) /
                    max(int(vals.get("views", 1)), 1) * 1000, 2
                ),
                "impressions":            int(vals.get("impressions", 0)),
                "ctr":                    round(float(vals.get("impressionClickThroughRate", 0)) * 100, 2),
            }
        except Exception as e:
            log.warning(f"Analytics query error for {video_id}: {e}")
            return {}

    def _update_topic_performance(self) -> None:
        """Update topic_performance table from latest analytics."""
        from core.database import get_conn
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT j.topic, va.ctr, va.avg_view_percentage, va.rpm
                FROM video_analytics va
                JOIN jobs j ON va.job_id = j.id
                WHERE va.ctr > 0
            """).fetchall()

            for row in rows:
                topic_lower = (row["topic"] or "").lower()
                category = (
                    "investing"     if any(w in topic_lower for w in ["invest", "stock", "fund", "market"]) else
                    "business"      if any(w in topic_lower for w in ["business", "entrepreneur"]) else
                    "tax"           if "tax" in topic_lower else
                    "real_estate"   if "real estate" in topic_lower else
                    "passive_income" if "passive" in topic_lower else
                    "budgeting"     if any(w in topic_lower for w in ["budget", "save", "debt"]) else
                    "general_finance"
                )
                conn.execute("""
                    INSERT INTO topic_performance (topic_category, avg_ctr, avg_avd_pct, avg_rpm, video_count)
                    VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(topic_category) DO UPDATE SET
                        avg_ctr     = (avg_ctr * video_count + ?) / (video_count + 1),
                        avg_avd_pct = (avg_avd_pct * video_count + ?) / (video_count + 1),
                        avg_rpm     = (avg_rpm * video_count + ?) / (video_count + 1),
                        video_count = video_count + 1,
                        last_updated = CURRENT_TIMESTAMP
                """, (
                    category, row["ctr"], row["avg_view_percentage"], row["rpm"],
                    row["ctr"], row["avg_view_percentage"], row["rpm"],
                ))

    # ── Weekly report generation ──────────────────────────────

    def _generate_report(self, stats: dict, history: list, jobs: list) -> str:
        # Find best and worst video this week
        best = max(jobs, key=lambda j: j.get("ctr", 0), default=None) if jobs else None
        worst = min(jobs, key=lambda j: j.get("ctr", 99), default=None) if jobs else None

        jobs_data = [
            {
                "topic": j["topic"],
                "ctr":   round(j.get("ctr", 0) or 0, 1),
                "avd":   round(j.get("avg_view_percentage", 0) or 0, 1),
                "rpm":   round(j.get("rpm", 0) or 0, 2),
                "subs":  j.get("subscribers_gained", 0) or 0,
            }
            for j in jobs[:5]
        ]

        prompt = f"""
You are a YouTube channel analyst. Generate a concise weekly report for Telegram (max 400 words).

CHANNEL STATS:
{json.dumps(stats, indent=2)}

RECENT VIDEO PERFORMANCE (last 5):
{json.dumps(jobs_data, indent=2)}

TOPIC CATEGORY PERFORMANCE:
{json.dumps([dict(h) for h in history[:5]], indent=2)}

TARGETS: CTR >5%, AVD >50%, RPM >$4/1K views

Write the report in this format:
📊 Week Summary
- Best video: [title] (CTR X%, AVD X%)
- Worst video: [title] (why it underperformed)
- Channel: +X subs this week | Est. revenue: $X

📈 What's Working
[2-3 bullet points — specific observations]

⚠️ What to Fix
[2-3 bullet points — specific action items]

🎯 Next Week Recommendation
- Topic type: [specific recommendation]
- Template: [A/B/C and why]
- Title style: [what worked]

YPP Progress: X/1000 subs | X/4000 watch hours
"""
        try:
            return claude(prompt, max_tokens=600, temperature=0.5)
        except Exception as e:
            log.warning(f"Report generation error: {e}")
            return (
                f"📊 Weekly Stats\n"
                f"Videos: {stats['total_videos']} | "
                f"Views: {stats['total_views']:,}\n"
                f"CTR: {stats['avg_ctr']}% | AVD: {stats['avg_avd_pct']}%\n"
                f"Revenue: ${stats['total_revenue_usd']}"
            )
