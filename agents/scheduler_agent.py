"""
Scheduler Agent — makes video public at optimal time after human approval.
Optimal: Tuesday–Thursday, 12pm–3pm EST (US finance audience peak).
Uses YouTube API scheduledStartTime via privacyStatus=private + publishAt.
"""

from datetime import datetime, timedelta

import pytz
from googleapiclient.discovery import build

from agents.base import advance_job
from core.config import UPLOAD_DAY, UPLOAD_HOUR_EST
from core.database import update_job
from core.logger import get_logger
from core.notification import send_published

log = get_logger("scheduler_agent", "system")

EST = pytz.timezone("US/Eastern")

# Best publish days + times for US finance audience
OPTIMAL_DAYS = ["tuesday", "wednesday", "thursday"]
OPTIMAL_HOUR = UPLOAD_HOUR_EST  # 13 = 1pm EST from config


class SchedulerAgent:

    async def schedule(self, job_id: int, video_id: str) -> None:
        log.info(f"[Job {job_id}] Scheduling video {video_id} for public publish")

        publish_time = self._find_next_slot()
        log.info(f"[Job {job_id}] Scheduling for: {publish_time.strftime('%A %b %d at %I:%M %p EST')}")

        from agents.upload_agent import UploadAgent
        yt = UploadAgent()._get_youtube()

        try:
            # Set to private + publishAt = scheduled public
            yt.videos().update(
                part="status",
                body={
                    "id": video_id,
                    "status": {
                        "privacyStatus": "private",
                        "publishAt":     publish_time.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    },
                },
            ).execute()

            update_job(job_id, {
                "status":       "scheduled",
                "publish_time": publish_time.isoformat(),
            })

            # Notify human
            from core.database import get_job
            job = get_job(job_id)
            meta_str = job["metadata_json"] or "{}"
            import json
            meta = json.loads(meta_str)
            title = meta.get("title", "Video")

            await send_published(
                title=title,
                publish_time=publish_time.strftime("%A %b %d at %I:%M %p EST"),
                url=f"https://youtu.be/{video_id}",
            )
            log.info(f"[Job {job_id}] Scheduled successfully")

        except Exception as e:
            log.error(f"[Job {job_id}] Scheduling failed: {e}")
            update_job(job_id, {"status": "schedule_failed"})

    def _find_next_slot(self) -> datetime:
        """Find next optimal publish slot (Tue/Wed/Thu, 1pm EST)."""
        now = datetime.now(EST)
        candidate = now.replace(hour=OPTIMAL_HOUR, minute=0, second=0, microsecond=0)

        # If today is optimal day and time hasn't passed yet, use today
        # Otherwise advance to next optimal day
        for _ in range(14):  # check up to 2 weeks ahead
            day_name = candidate.strftime("%A").lower()
            if day_name in OPTIMAL_DAYS and candidate > now + timedelta(hours=2):
                return candidate
            candidate += timedelta(days=1)
            candidate = candidate.replace(hour=OPTIMAL_HOUR, minute=0, second=0)

        # Fallback: tomorrow at 1pm EST
        return (now + timedelta(days=1)).replace(hour=OPTIMAL_HOUR, minute=0, second=0)
