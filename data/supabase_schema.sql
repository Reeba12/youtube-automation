-- YouTube Automation System — Supabase Schema
-- Run this in: supabase.com → your project → SQL Editor → New query → paste → Run
-- Safe to re-run (IF NOT EXISTS). One-time setup.

-- Jobs: full pipeline lifecycle per video
CREATE TABLE IF NOT EXISTS jobs (
    id                  BIGSERIAL PRIMARY KEY,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    status              TEXT DEFAULT 'pending',
    topic               TEXT,
    topic_score         FLOAT,
    template_used       TEXT,
    script_path         TEXT,
    audio_path          TEXT,
    video_path          TEXT,
    thumbnail_path      TEXT,
    metadata_json       TEXT,
    youtube_video_id    TEXT,
    preview_url         TEXT,
    publish_time        TIMESTAMPTZ,
    supervisor_approved BOOLEAN DEFAULT FALSE,
    human_approved      BOOLEAN DEFAULT FALSE,
    rejection_reason    TEXT,
    policy_flags        TEXT DEFAULT '[]',
    retry_count         INTEGER DEFAULT 0,
    completed_at        TIMESTAMPTZ
);

-- Per-video analytics (pulled daily)
CREATE TABLE IF NOT EXISTS video_analytics (
    id                      BIGSERIAL PRIMARY KEY,
    job_id                  BIGINT REFERENCES jobs(id),
    youtube_video_id        TEXT,
    pulled_at               TIMESTAMPTZ DEFAULT NOW(),
    views                   INTEGER DEFAULT 0,
    impressions             INTEGER DEFAULT 0,
    ctr                     FLOAT DEFAULT 0,
    avg_view_duration_sec   INTEGER DEFAULT 0,
    avg_view_percentage     FLOAT DEFAULT 0,
    likes                   INTEGER DEFAULT 0,
    comments                INTEGER DEFAULT 0,
    subscribers_gained      INTEGER DEFAULT 0,
    estimated_revenue_usd   FLOAT DEFAULT 0,
    rpm                     FLOAT DEFAULT 0,
    cpm                     FLOAT DEFAULT 0
);

-- Topic performance for Research Agent scoring
CREATE TABLE IF NOT EXISTS topic_performance (
    id              BIGSERIAL PRIMARY KEY,
    topic_category  TEXT UNIQUE,
    template_used   TEXT,
    avg_ctr         FLOAT DEFAULT 0,
    avg_avd_pct     FLOAT DEFAULT 0,
    avg_rpm         FLOAT DEFAULT 0,
    video_count     INTEGER DEFAULT 0,
    last_updated    TIMESTAMPTZ DEFAULT NOW()
);

-- Policy check audit log
CREATE TABLE IF NOT EXISTS policy_log (
    id              BIGSERIAL PRIMARY KEY,
    job_id          BIGINT REFERENCES jobs(id),
    agent_name      TEXT,
    check_time      TIMESTAMPTZ DEFAULT NOW(),
    passed          BOOLEAN,
    violations      TEXT DEFAULT '[]',
    action_taken    TEXT
);

-- Topics already used (Research Agent avoids repeats)
CREATE TABLE IF NOT EXISTS used_topics (
    id          BIGSERIAL PRIMARY KEY,
    topic       TEXT UNIQUE,
    used_at     TIMESTAMPTZ DEFAULT NOW()
);

-- NOTE: RLS disabled — this is a private backend, not a public app.
-- Only your service_role key can access it.
-- If you want RLS, add: ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
-- then add policies. For now, tables are accessible via service_role key only.
