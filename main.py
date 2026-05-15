"""
Entry point — starts Telegram bot + APScheduler cron jobs.

IMPORTANT: Run from inside .venv (Python 3.11), NOT system Python 3.14.

Windows:
  .venv\\Scripts\\activate
  python main.py

Or directly:
  .venv\\Scripts\\python.exe main.py
"""

import asyncio
import logging
import signal
import sys

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from core.config import UPLOAD_DAY, UPLOAD_HOUR_EST
from core.database import init_db
from core.logger import get_logger
from core.notification import send, start_action_server

log = get_logger("main", "system")
EST = pytz.timezone("US/Eastern")

# ── Cron jobs ─────────────────────────────────────────────────

async def job_research():
    """Monday 8am EST — Research Agent finds 5 topics, sends to Telegram."""
    from core.notification import is_paused
    if is_paused():
        log.info("Pipeline paused — skipping research job")
        return
    log.info("CRON: Starting research job")
    from agents.research_agent import ResearchAgent
    agent = ResearchAgent()
    await agent.run()


async def job_check_topic_approved():
    """Monday 9am EST — Start pipeline if topic was approved."""
    from core.notification import is_paused
    if is_paused():
        return
    from core.database import get_jobs_by_status
    pending = get_jobs_by_status("topic_approved")
    if not pending:
        log.info("No approved topic yet — waiting")
        return
    job = pending[0]
    log.info(f"Topic approved — starting full pipeline for job {job['id']}")
    from agents.orchestrator import run_pipeline
    asyncio.create_task(run_pipeline(job["id"]))


async def job_analytics_daily():
    """Daily 9am EST — Pull analytics for all live videos."""
    log.info("CRON: Running daily analytics pull")
    from agents.analytics_agent import AnalyticsAgent
    agent = AnalyticsAgent()
    await agent.run_daily()


async def job_weekly_report():
    """Sunday 6pm EST — Generate weekly insight report → Telegram."""
    log.info("CRON: Generating weekly report")
    from agents.analytics_agent import AnalyticsAgent
    agent = AnalyticsAgent()
    await agent.run_weekly_report()


async def job_check_human_approval():
    """Every 5 min — Check if human approved video → trigger scheduling."""
    from core.database import get_jobs_by_status
    scheduling = get_jobs_by_status("scheduling")
    for job in scheduling:
        log.info(f"Human approved job {job['id']} — scheduling publish")
        from agents.scheduler_agent import SchedulerAgent
        agent = SchedulerAgent()
        await agent.schedule(job["id"], job["youtube_video_id"])


# ── Scheduler setup ───────────────────────────────────────────

def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=EST)

    # Research: Monday 8am EST
    scheduler.add_job(
        job_research,
        CronTrigger(day_of_week="mon", hour=8, minute=0, timezone=EST),
        id="research", replace_existing=True
    )

    # Check topic approval: Monday 9am EST
    scheduler.add_job(
        job_check_topic_approved,
        CronTrigger(day_of_week="mon", hour=9, minute=0, timezone=EST),
        id="check_topic", replace_existing=True
    )

    # Daily analytics: 9am EST every day
    scheduler.add_job(
        job_analytics_daily,
        CronTrigger(hour=9, minute=0, timezone=EST),
        id="analytics_daily", replace_existing=True
    )

    # Weekly report: Sunday 6pm EST
    scheduler.add_job(
        job_weekly_report,
        CronTrigger(day_of_week="sun", hour=18, minute=0, timezone=EST),
        id="weekly_report", replace_existing=True
    )

    # Poll for human approval: every 5 min
    scheduler.add_job(
        job_check_human_approval,
        "interval",
        minutes=5,
        id="check_approval", replace_existing=True
    )

    return scheduler


# ── Graceful shutdown ─────────────────────────────────────────

def handle_shutdown(scheduler: AsyncIOScheduler, loop: asyncio.AbstractEventLoop):
    log.info("Shutdown signal received — stopping...")
    scheduler.shutdown(wait=False)
    loop.stop()


# ── Main ──────────────────────────────────────────────────────

def _validate_env() -> None:
    """Fail fast with clear message if required keys missing."""
    from core.config import ANTHROPIC_API_KEY
    import os
    missing = []
    if not ANTHROPIC_API_KEY:              missing.append("ANTHROPIC_API_KEY")
    if not os.getenv("NTFY_TOPIC"):        missing.append("NTFY_TOPIC")
    if missing:
        print(f"\nERROR: Missing required .env keys: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in your API keys.")
        sys.exit(1)


async def main():
    _validate_env()
    log.info("=" * 60)
    log.info("YouTube Automation System starting up")
    log.info("=" * 60)

    # Init DB
    init_db()
    log.info("Database initialized")

    # Start scheduler
    scheduler = build_scheduler()
    scheduler.start()
    log.info("Scheduler started — cron jobs registered")

    # Start ntfy action server (receives approve/reject button taps)
    start_action_server(port=5055)
    log.info("ntfy action server started on port 5055")

    send(
        "YouTube Automation System Online!\n"
        "Research runs Monday 8am EST.\n"
        "You will receive topic options to pick from.",
        title="System Started",
        tags=["white_check_mark"],
    )

    # Register shutdown handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_shutdown, scheduler, loop)
        except NotImplementedError:
            pass  # Windows doesn't support add_signal_handler for all signals

    log.info("System fully operational. Press Ctrl+C to stop.")

    try:
        await asyncio.Event().wait()  # run forever
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        log.info("Shutting down gracefully...")
        scheduler.shutdown(wait=False)
        log.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
