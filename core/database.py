"""
Database layer — Supabase (PostgreSQL in cloud).
Free tier: 500MB, accessible from anywhere (laptop + server).
Falls back to SQLite for local dev if SUPABASE_URL not set.

Supabase setup:
  1. supabase.com → New project → free tier
  2. Settings → API → copy URL + anon key → paste in .env
  3. SQL Editor → run schema from data/supabase_schema.sql
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.config import DB_PATH

# ── Detect mode ───────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

_supabase_client = None


def _get_supabase():
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


# ── SQLite fallback (local dev) ───────────────────────────────

def _sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Initialize database. Supabase: prints schema instructions. SQLite: creates tables."""
    if USE_SUPABASE:
        print("[DB] Using Supabase (cloud PostgreSQL)")
        schema_path = Path("data/supabase_schema.sql")
        if schema_path.exists():
            print(f"[DB] Run schema in Supabase SQL Editor: {schema_path}")
        return

    print("[DB] Using SQLite (local fallback)")
    with _sqlite_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
            status              TEXT DEFAULT 'pending',
            topic               TEXT,
            topic_score         REAL,
            template_used       TEXT,
            script_path         TEXT,
            audio_path          TEXT,
            video_path          TEXT,
            thumbnail_path      TEXT,
            metadata_json       TEXT,
            youtube_video_id    TEXT,
            preview_url         TEXT,
            publish_time        DATETIME,
            supervisor_approved INTEGER DEFAULT 0,
            human_approved      INTEGER DEFAULT 0,
            rejection_reason    TEXT,
            policy_flags        TEXT DEFAULT '[]',
            retry_count         INTEGER DEFAULT 0,
            completed_at        DATETIME
        );

        CREATE TABLE IF NOT EXISTS video_analytics (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id                  INTEGER REFERENCES jobs(id),
            youtube_video_id        TEXT,
            pulled_at               DATETIME DEFAULT CURRENT_TIMESTAMP,
            views                   INTEGER DEFAULT 0,
            impressions             INTEGER DEFAULT 0,
            ctr                     REAL DEFAULT 0,
            avg_view_duration_sec   INTEGER DEFAULT 0,
            avg_view_percentage     REAL DEFAULT 0,
            likes                   INTEGER DEFAULT 0,
            comments                INTEGER DEFAULT 0,
            subscribers_gained      INTEGER DEFAULT 0,
            estimated_revenue_usd   REAL DEFAULT 0,
            rpm                     REAL DEFAULT 0,
            cpm                     REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS topic_performance (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_category  TEXT UNIQUE,
            template_used   TEXT,
            avg_ctr         REAL DEFAULT 0,
            avg_avd_pct     REAL DEFAULT 0,
            avg_rpm         REAL DEFAULT 0,
            video_count     INTEGER DEFAULT 0,
            last_updated    DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS policy_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id          INTEGER REFERENCES jobs(id),
            agent_name      TEXT,
            check_time      DATETIME DEFAULT CURRENT_TIMESTAMP,
            passed          INTEGER,
            violations      TEXT DEFAULT '[]',
            action_taken    TEXT
        );

        CREATE TABLE IF NOT EXISTS used_topics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            topic       TEXT UNIQUE,
            used_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)


# ── Universal DB operations (Supabase or SQLite) ──────────────

def create_job(topic: str, topic_score: float, template: str) -> int:
    data = {
        "topic":        topic,
        "topic_score":  topic_score,
        "template_used": template,
        "status":       "pending",
    }
    if USE_SUPABASE:
        sb = _get_supabase()
        res = sb.table("jobs").insert(data).execute()
        return res.data[0]["id"]
    else:
        with _sqlite_conn() as conn:
            cur = conn.execute(
                "INSERT INTO jobs (topic, topic_score, template_used, status) VALUES (?,?,?,?)",
                (topic, topic_score, template, "pending")
            )
            return cur.lastrowid


def update_job(job_id: int, fields: dict) -> None:
    if not fields:
        return
    if USE_SUPABASE:
        _get_supabase().table("jobs").update(fields).eq("id", job_id).execute()
    else:
        with _sqlite_conn() as conn:
            cols = ", ".join(f"{k} = ?" for k in fields)
            vals = list(fields.values()) + [job_id]
            conn.execute(f"UPDATE jobs SET {cols} WHERE id = ?", vals)


def get_job(job_id: int) -> Optional[dict]:
    if USE_SUPABASE:
        res = _get_supabase().table("jobs").select("*").eq("id", job_id).execute()
        return res.data[0] if res.data else None
    else:
        with _sqlite_conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None


def get_pending_human_review() -> Optional[dict]:
    if USE_SUPABASE:
        res = (
            _get_supabase().table("jobs")
            .select("*").eq("status", "human_review")
            .order("created_at", desc=True).limit(1).execute()
        )
        return res.data[0] if res.data else None
    else:
        with _sqlite_conn() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE status = 'human_review' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None


def get_jobs_by_status(status: str) -> list:
    if USE_SUPABASE:
        res = (
            _get_supabase().table("jobs")
            .select("*").eq("status", status)
            .order("created_at", desc=True).execute()
        )
        return res.data or []
    else:
        with _sqlite_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC", (status,)
            ).fetchall()
            return [dict(r) for r in rows]


def get_recent_completed_jobs(limit: int = 10) -> list:
    if USE_SUPABASE:
        res = (
            _get_supabase().table("jobs")
            .select("*").eq("status", "live")
            .order("completed_at", desc=True).limit(limit).execute()
        )
        return res.data or []
    else:
        with _sqlite_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = 'live' ORDER BY completed_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]


def log_policy_check(job_id: int, agent_name: str, passed: bool, violations: list, action: str) -> None:
    data = {
        "job_id":       job_id,
        "agent_name":   agent_name,
        "passed":       passed,
        "violations":   json.dumps(violations),
        "action_taken": action,
    }
    if USE_SUPABASE:
        _get_supabase().table("policy_log").insert(data).execute()
    else:
        with _sqlite_conn() as conn:
            conn.execute(
                "INSERT INTO policy_log (job_id, agent_name, passed, violations, action_taken) VALUES (?,?,?,?,?)",
                (job_id, agent_name, int(passed), json.dumps(violations), action)
            )


def mark_topic_used(topic: str) -> None:
    if USE_SUPABASE:
        try:
            _get_supabase().table("used_topics").insert({"topic": topic}).execute()
        except Exception:
            pass  # duplicate — ignore
    else:
        with _sqlite_conn() as conn:
            conn.execute("INSERT OR IGNORE INTO used_topics (topic) VALUES (?)", (topic,))


def is_topic_used(topic: str) -> bool:
    if USE_SUPABASE:
        res = (
            _get_supabase().table("used_topics")
            .select("id").ilike("topic", topic).limit(1).execute()
        )
        return bool(res.data)
    else:
        with _sqlite_conn() as conn:
            row = conn.execute(
                "SELECT id FROM used_topics WHERE LOWER(topic) = LOWER(?)", (topic,)
            ).fetchone()
            return row is not None


def get_used_topics(limit: int = 50) -> list[str]:
    if USE_SUPABASE:
        res = (
            _get_supabase().table("used_topics")
            .select("topic").order("used_at", desc=True).limit(limit).execute()
        )
        return [r["topic"] for r in (res.data or [])]
    else:
        with _sqlite_conn() as conn:
            rows = conn.execute(
                "SELECT topic FROM used_topics ORDER BY used_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [r["topic"] for r in rows]


def save_analytics(job_id: int, video_id: str, data: dict) -> None:
    row = {
        "job_id":                   job_id,
        "youtube_video_id":         video_id,
        "views":                    data.get("views", 0),
        "impressions":              data.get("impressions", 0),
        "ctr":                      data.get("ctr", 0),
        "avg_view_duration_sec":    data.get("avg_view_duration_sec", 0),
        "avg_view_percentage":      data.get("avg_view_percentage", 0),
        "likes":                    data.get("likes", 0),
        "comments":                 data.get("comments", 0),
        "subscribers_gained":       data.get("subscribers_gained", 0),
        "estimated_revenue_usd":    data.get("estimated_revenue_usd", 0),
        "rpm":                      data.get("rpm", 0),
        "cpm":                      data.get("cpm", 0),
    }
    if USE_SUPABASE:
        _get_supabase().table("video_analytics").insert(row).execute()
    else:
        with _sqlite_conn() as conn:
            conn.execute(
                """INSERT INTO video_analytics
                   (job_id, youtube_video_id, views, impressions, ctr,
                    avg_view_duration_sec, avg_view_percentage, likes, comments,
                    subscribers_gained, estimated_revenue_usd, rpm, cpm)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                tuple(row.values())
            )


def get_channel_stats() -> dict:
    if USE_SUPABASE:
        sb = _get_supabase()
        jobs_res = sb.table("jobs").select("id", count="exact").eq("status", "live").execute()
        analytics_res = sb.table("video_analytics").select(
            "views, ctr, avg_view_percentage, subscribers_gained, estimated_revenue_usd"
        ).execute()
        rows = analytics_res.data or []
        total_views  = sum(r.get("views", 0) for r in rows)
        avg_ctr      = sum(r.get("ctr", 0) for r in rows) / max(len(rows), 1)
        avg_avd      = sum(r.get("avg_view_percentage", 0) for r in rows) / max(len(rows), 1)
        total_subs   = sum(r.get("subscribers_gained", 0) for r in rows)
        total_rev    = sum(r.get("estimated_revenue_usd", 0) for r in rows)
        return {
            "total_videos":        jobs_res.count or 0,
            "total_views":         total_views,
            "avg_ctr":             round(avg_ctr, 2),
            "avg_avd_pct":         round(avg_avd, 1),
            "total_subs_gained":   total_subs,
            "total_revenue_usd":   round(total_rev, 2),
        }
    else:
        with _sqlite_conn() as conn:
            total = conn.execute("SELECT COUNT(*) as n FROM jobs WHERE status='live'").fetchone()["n"]
            a = conn.execute(
                "SELECT SUM(views),AVG(ctr),AVG(avg_view_percentage),"
                "SUM(subscribers_gained),SUM(estimated_revenue_usd) FROM video_analytics"
            ).fetchone()
            return {
                "total_videos":      total,
                "total_views":       a[0] or 0,
                "avg_ctr":           round(a[1] or 0, 2),
                "avg_avd_pct":       round(a[2] or 0, 1),
                "total_subs_gained": a[3] or 0,
                "total_revenue_usd": round(a[4] or 0, 2),
            }


def get_topic_performance_history() -> list:
    if USE_SUPABASE:
        res = (
            _get_supabase().table("topic_performance")
            .select("*").order("avg_ctr", desc=True).execute()
        )
        return res.data or []
    else:
        with _sqlite_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM topic_performance ORDER BY avg_ctr DESC"
            ).fetchall()
            return [dict(r) for r in rows]


def get_conn():
    """Raw SQLite connection — used by analytics agent for complex queries."""
    if USE_SUPABASE:
        raise RuntimeError("Use Supabase client directly for complex queries")
    return _sqlite_conn()
