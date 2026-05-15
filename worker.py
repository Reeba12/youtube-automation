"""
Local worker — runs on your laptop.
Polls Supabase for approved jobs → runs heavy pipeline locally:
  script → voiceover → avatar → video → thumbnail → upload

Railway handles: research, scheduling, notifications, analytics.
Laptop handles: script writing, TTS, avatar animation, video assembly.

Run: .venv\Scripts\python.exe worker.py
Keep running in background while you work.
"""

import asyncio
import sys
import time

sys.path.insert(0, ".")

from core.database import get_jobs_by_status, update_job
from core.logger import get_logger
from core.notification import send

log = get_logger("worker", "system")

POLL_INTERVAL_SEC = 60   # check Supabase every 60 seconds


async def process_job(job: dict) -> None:
    job_id = job["id"]
    log.info(f"[Job {job_id}] Picked up — starting local pipeline")
    update_job(job_id, {"status": "running"})

    try:
        import json
        from agents.orchestrator import run_pipeline
        await run_pipeline(job_id)
    except Exception as e:
        log.error(f"[Job {job_id}] Pipeline error: {e}", exc_info=True)
        update_job(job_id, {"status": "failed"})
        await send(f"Pipeline failed for job {job_id}: {e}", title="Worker Error", tags=["warning"])


async def main():
    log.info("Local worker started — polling Supabase for approved jobs")
    await send("Local worker online. Ready to process approved jobs.", title="Worker Started", tags=["computer"])

    while True:
        try:
            # Check for topic_approved jobs (need full pipeline)
            approved = get_jobs_by_status("topic_approved")
            for job in approved:
                log.info(f"Found approved job {job['id']}: {job['topic']}")
                asyncio.create_task(process_job(job))

            # Check for scheduling jobs (human approved video — schedule publish)
            scheduling = get_jobs_by_status("scheduling")
            for job in scheduling:
                log.info(f"Scheduling job {job['id']}")
                from agents.scheduler_agent import SchedulerAgent
                asyncio.create_task(
                    SchedulerAgent().schedule(job["id"], job["youtube_video_id"])
                )

        except Exception as e:
            log.error(f"Worker poll error: {e}")

        await asyncio.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    asyncio.run(main())
