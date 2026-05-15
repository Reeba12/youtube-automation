# YouTube Automation System — Complete Build Plan v3
# AI Engineer Reference Document
# Last Updated: May 2026
# Stack: LangGraph + Claude API + 100% Free/Open Source tools

---

## PROJECT OVERVIEW

**Goal:** Fully automated YouTube channel (Finance + Business niche)
**Human time required:** ~20 min/week (topic approval + final video approval)
**Target:** Passive income $2,000–$8,000/month at scale
**Upload schedule:** 1 long-form/week + 2-3 Shorts repurposed from it
**Audience:** English-speaking, US/UK/Canada, 25-40 years old
**Monetization path:** YPP (1K subs + 4K hours) → AdSense + Affiliate

---

## WHY TELEGRAM? (Answer to your question)

**Short answer:** Telegram is free, instant, works on phone, has bot API.

**Full reasoning:**
- You have 9-5 job. System runs while you work. You need alerts on phone.
- Telegram Bot API = free, no subscription, works anywhere
- Bot sends you: topic options Monday morning, final video for approval, weekly revenue report
- You reply `/approve` from phone = video goes live. That's it.
- **Alternatives considered:**
  - Email: slow, goes to spam, no interactive commands
  - WhatsApp: no bot API
  - Discord: more complex setup, overkill for 1 user
  - SMS: costs money per message
- Telegram = best free option for phone-based approval workflow

---

## WHY DATABASE? (Yes we need it)

**Without DB:** Pipeline crashes at 2am after 40 min of video rendering → lose all work → restart from scratch.

**With SQLite DB:**
- Pipeline crashes → resumes from exact step it failed
- Topic history → Research Agent never repeats same topic
- Analytics history → system learns what works on YOUR channel
- Job queue → track every video: created → scripted → rendered → approved → live
- Audit log → every policy check recorded (protection if YouTube ever questions channel)

**SQLite specifically:** Zero setup, single file, built into Python. No server, no Docker, no config. Perfect for 1 video/week scale.

---

## THE "NOT AI-LOOKING" PROBLEM — Deep Analysis

YouTube does NOT scan script text for AI. It detects PATTERNS:

| AI Pattern Signal | Our Fix |
|---|---|
| Same video template every week | 3 rotating templates (A/B/C), random variation in structure |
| Identical B-roll style every video | Mix: stock footage + animated charts + text overlays + screen recordings |
| Robotic TTS with no variation | Kokoro TTS with SSML tags: pace changes, emphasis, pauses |
| Stock footage + voice = nothing else | Add custom animated intros per section, data visualizations |
| Every video same exact length | Vary: 10min, 13min, 15min, 8min — not always 12:00 exactly |
| No engagement signals | Strong CTA script: question in first 30 sec drives comments |
| Zero personality in voice | Kokoro voice + prosody control = natural cadence |
| Script sounds like Wikipedia | Two-pass humanization + real opinion + contrarian takes |
| Same music every video | 5 royalty-free tracks, rotate randomly |
| Thumbnail always same layout | 3 thumbnail templates, rotate |

**What actually matters for monetization review:**
1. Human editorial judgment present → our Script Agent uses real data + strong opinions
2. Not mass-produced → 1 video/week maximum, never automated beyond that
3. Transforms content → we analyze data, don't just narrate it
4. Original perspective → Supervisor Agent enforces unique angle per video

---

## COMPLETE FREE/OPEN SOURCE TECH STACK

```
CATEGORY          TOOL                    WHY                              COST
─────────────────────────────────────────────────────────────────────────────
Language          Python 3.11+            Best AI/ML ecosystem             Free
─────────────────────────────────────────────────────────────────────────────
AI Brain          Anthropic Claude API    Best reasoning, policy checks,   Paid API
                  (claude-sonnet-4-6)     script writing, analysis         ~$15-25/mo
─────────────────────────────────────────────────────────────────────────────
Orchestration     LangGraph               Explicit state machine. Full     Free (library)
                  + APScheduler           control over pipeline steps.     Free
                                          Debug each step individually.
                                          Industry standard for prod.
                                          APScheduler handles cron.
─────────────────────────────────────────────────────────────────────────────
Voice/TTS         Kokoro TTS              #1 HuggingFace TTS Arena.        Free (local)
                  (kokoro-onnx)           82M params, runs on CPU.
                                          Apache 2.0 license.
                                          350MB download, zero API cost.
─────────────────────────────────────────────────────────────────────────────
Video Assembly    FFmpeg + MoviePy        Industry standard. Powers        Free
                                          YouTube itself. MIT license.
─────────────────────────────────────────────────────────────────────────────
Captions          OpenAI Whisper          MIT license, runs locally,       Free (local)
                  (local)                 word-level timestamps.
─────────────────────────────────────────────────────────────────────────────
Stock Footage     Pexels API              Free, commercial use OK,         Free
                                          HD footage, REST API.
─────────────────────────────────────────────────────────────────────────────
Charts/Graphs     Matplotlib + Plotly     Generate from raw API data.      Free
                                          Never screenshot Bloomberg.
─────────────────────────────────────────────────────────────────────────────
Thumbnails        Pillow + OpenCV         Extract best video frame,        Free
                  (frame extraction)      add text/logo overlay.
                                          No AI image gen needed.
                                          Simpler + faster + no GPU.
─────────────────────────────────────────────────────────────────────────────
Financial Data    Alpha Vantage           Stock/market data, free tier     Free
                  World Bank API          GDP/inflation/unemployment        Free (no key)
                  NewsAPI                 Business headlines               Free tier
─────────────────────────────────────────────────────────────────────────────
Trend Research    pytrends                Google Trends, no key needed     Free
                  PRAW                    Reddit API, MIT license          Free
─────────────────────────────────────────────────────────────────────────────
Upload/Schedule   YouTube Data API v3     Official Google API.             Free quota
                                          10K units/day = 6 uploads/day.
                                          We do 1/week. Never hit limit.
─────────────────────────────────────────────────────────────────────────────
Analytics         YouTube Analytics API   Official. Pulls CTR, RPM,        Free
                                          AVD, revenue per video.
─────────────────────────────────────────────────────────────────────────────
Notifications     python-telegram-bot     Free bot API. Phone alerts.      Free
                                          MIT license. You approve
                                          videos from phone.
─────────────────────────────────────────────────────────────────────────────
Database          SQLite (stdlib)         Built into Python. Zero setup.   Free
                                          Single file. Crash recovery.
─────────────────────────────────────────────────────────────────────────────
Music             YouTube Audio Library   Royalty-free. Safe for YPP.      Free
                  + Pixabay Music         Both allow commercial use.
─────────────────────────────────────────────────────────────────────────────
Hosting           Your PC (local)         Free while building/testing      Free
                  OR Railway              $5/mo for 24/7 cloud             $5/mo
─────────────────────────────────────────────────────────────────────────────

TOTAL COST: ~$15-25/mo (Claude API only)
```

---

## FOLDER STRUCTURE

```
youtube-automation/
│
├── agents/
│   ├── orchestrator.py        # Master Claude Agent SDK orchestrator
│   ├── research_agent.py      # Topic research sub-agent
│   ├── script_agent.py        # Two-pass script writing sub-agent
│   ├── voiceover_agent.py     # Kokoro TTS sub-agent
│   ├── video_agent.py         # FFmpeg assembly sub-agent
│   ├── thumbnail_agent.py     # Frame extraction + Pillow sub-agent
│   ├── seo_agent.py           # Metadata + SEO sub-agent
│   ├── upload_agent.py        # YouTube API upload sub-agent
│   ├── scheduler_agent.py     # Publish scheduling sub-agent
│   └── analytics_agent.py     # Performance tracking sub-agent
│
├── core/
│   ├── policy_checker.py      # Policy gate — used by ALL agents
│   ├── notification.py        # Telegram bot (replaced telegram_bot.py)
│   ├── database.py            # SQLite — job queue + logs + analytics
│   ├── config.py              # All API keys + settings (loads .env)
│   └── logger.py              # Structured JSON logging per agent
│
├── data/
│   ├── YOUTUBE_POLICY_REFERENCE.md   # Policy bible — loaded at startup
│   ├── channel_persona.txt           # Voice/tone definition for scripts
│   ├── music/                        # Pre-downloaded royalty-free tracks
│   └── fonts/                        # Montserrat Bold, Impact for thumbnails
│
├── temp/                      # Auto-cleaned after each job
│   └── {job_id}/
│       ├── audio.wav
│       ├── video_raw.mp4
│       └── thumbnail_raw.jpg
│
├── output/                    # Final approved videos (keep 90 days)
│   └── {job_id}/
│       ├── final_video.mp4
│       └── thumbnail.jpg
│
├── logs/                      # Per-job logs
│   └── {job_id}.json
│
├── data/analytics.db          # SQLite database file
├── requirements.txt
├── .env                       # API keys — NEVER commit this
├── main.py                    # Entry point + APScheduler cron setup
└── SYSTEM_PLAN.md
```

---

## DATABASE SCHEMA (SQLite)

```sql
-- Every video job: full lifecycle tracking
CREATE TABLE jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    status              TEXT DEFAULT 'pending',
    -- Status values:
    -- pending → researching → scripting → voiceover → video
    -- → thumbnail → seo → supervisor_review → uploading
    -- → human_review → scheduled → live → failed
    topic               TEXT,
    topic_score         REAL,
    template_used       TEXT,           -- A, B, or C
    script_path         TEXT,
    audio_path          TEXT,
    video_path          TEXT,
    thumbnail_path      TEXT,
    metadata_json       TEXT,           -- title, desc, tags as JSON
    youtube_video_id    TEXT,
    preview_url         TEXT,           -- unlisted link sent to human
    publish_time        DATETIME,
    supervisor_approved INTEGER DEFAULT 0,
    human_approved      INTEGER DEFAULT 0,
    rejection_reason    TEXT,
    policy_flags        TEXT,           -- JSON array of violations
    retry_count         INTEGER DEFAULT 0,
    completed_at        DATETIME
);

-- Per-video analytics pulled daily
CREATE TABLE video_analytics (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id                  INTEGER REFERENCES jobs(id),
    youtube_video_id        TEXT,
    pulled_at               DATETIME,
    views                   INTEGER,
    impressions             INTEGER,
    ctr                     REAL,       -- target >5%
    avg_view_duration_sec   INTEGER,
    avg_view_percentage     REAL,       -- target >50%
    likes                   INTEGER,
    comments                INTEGER,
    subscribers_gained      INTEGER,
    estimated_revenue_usd   REAL,
    rpm                     REAL,
    cpm                     REAL
);

-- Topic performance: Research Agent uses this to score future topics
CREATE TABLE topic_performance (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_category  TEXT,       -- "investing", "business", "tax", etc.
    template_used   TEXT,       -- A, B, C
    avg_ctr         REAL,
    avg_avd_pct     REAL,
    avg_rpm         REAL,
    video_count     INTEGER DEFAULT 0,
    last_updated    DATETIME
);

-- Every policy check logged (audit trail)
CREATE TABLE policy_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER REFERENCES jobs(id),
    agent_name      TEXT,
    check_time      DATETIME DEFAULT CURRENT_TIMESTAMP,
    passed          INTEGER,    -- 0 or 1
    violations      TEXT,       -- JSON array of strings
    action_taken    TEXT        -- "continued", "retried", "blocked"
);

-- Used topics — never repeat
CREATE TABLE used_topics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    topic       TEXT UNIQUE,
    used_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## AGENT ARCHITECTURE (LangGraph State Machine)

LangGraph models the pipeline as a directed graph. Each node = one agent function.
State dict passes between nodes. Edges = conditional routing (pass/fail/retry).

```python
# orchestrator.py — LangGraph pipeline

from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

# ── Shared pipeline state ─────────────────────────────────────────────────────
class PipelineState(TypedDict):
    job_id:             int
    topic:              dict
    template:           str
    script:             str
    script_path:        str
    audio_path:         str
    video_path:         str
    thumbnail_path:     str
    metadata:           dict
    youtube_video_id:   str
    preview_url:        str
    policy_violations:  list
    supervisor_ok:      bool
    human_approved:     bool
    rejection_reason:   str
    retry_count:        int
    error:              Optional[str]

# ── Graph definition ──────────────────────────────────────────────────────────
def build_pipeline() -> StateGraph:
    graph = StateGraph(PipelineState)

    # Register nodes (each is a Python function)
    graph.add_node("research",          research_agent.run)
    graph.add_node("script",            script_agent.run)
    graph.add_node("voiceover",         voiceover_agent.run)
    graph.add_node("video",             video_agent.run)
    graph.add_node("thumbnail",         thumbnail_agent.run)
    graph.add_node("seo",               seo_agent.run)
    graph.add_node("supervisor_review", supervisor_agent.run)
    graph.add_node("upload_unlisted",   upload_agent.upload_unlisted)
    graph.add_node("human_review",      human_review_node)   # waits for Telegram /approve
    graph.add_node("schedule_publish",  scheduler_agent.run)
    graph.add_node("handle_failure",    failure_handler)

    # Linear edges (no branching)
    graph.add_edge("script",     "voiceover")
    graph.add_edge("voiceover",  "video")
    graph.add_edge("video",      "thumbnail")
    graph.add_edge("thumbnail",  "seo")
    graph.add_edge("seo",        "supervisor_review")

    # Conditional: supervisor passes or fails
    graph.add_conditional_edges(
        "supervisor_review",
        lambda s: "pass" if s["supervisor_ok"] else "fail",
        {"pass": "upload_unlisted", "fail": "handle_failure"}
    )

    graph.add_edge("upload_unlisted", "human_review")

    # Conditional: human approves or rejects
    graph.add_conditional_edges(
        "human_review",
        lambda s: "approved" if s["human_approved"] else "rejected",
        {"approved": "schedule_publish", "rejected": "handle_failure"}
    )

    graph.add_edge("schedule_publish", END)

    # Failure handler — retry specific failed step or stop
    graph.add_conditional_edges(
        "handle_failure",
        route_retry,
        {
            "retry_script":     "script",
            "retry_voiceover":  "voiceover",
            "retry_video":      "video",
            "retry_thumbnail":  "thumbnail",
            "retry_seo":        "seo",
            "stop":             END,
        }
    )

    graph.set_entry_point("research")

    # SQLite checkpointing — crash recovery built-in
    memory = SqliteSaver.from_conn_string("data/analytics.db")
    return graph.compile(checkpointer=memory)


def route_retry(state: PipelineState) -> str:
    """Decide which node to retry based on what failed."""
    if state["retry_count"] >= 3:
        return "stop"
    violations = state.get("policy_violations", [])
    reason = state.get("rejection_reason", "")
    combined = " ".join(violations) + " " + reason
    if "script"     in combined: return "retry_script"
    if "audio"      in combined: return "retry_voiceover"
    if "thumbnail"  in combined: return "retry_thumbnail"
    if "seo"        in combined or "metadata" in combined: return "retry_seo"
    return "retry_video"
```

**Why LangGraph over Claude Agent SDK:**
- Full explicit control over every pipeline step
- SQLite checkpointing = automatic crash recovery mid-pipeline
- Easy to debug — run any single node in isolation
- Conditional routing = smart retry of only failed step (not whole pipeline)
- Standard library — massive community, well-documented
- Works perfectly with `anthropic` Python SDK for Claude calls

---

## AGENT 1: RESEARCH AGENT

**Purpose:** Find best topic this week. Score 5 options and present to human.

**Data Sources:**
```python
SOURCES = {
    "google_trends": pytrends → finance/business keywords, US geo, last 7 days
    "reddit":        PRAW → r/personalfinance, r/entrepreneur, r/investing (hot posts)
    "newsapi":       business/finance headlines, English, US, last 48 hours
    "youtube":       YouTube Data API → search finance topics, sort by viewCount/7days
    "alpha_vantage": market movers this week (top gainers/losers = content opportunity)
}
```

**Scoring Formula:**
```
Topic Score = 
  trend_momentum (0-30)     ← Google Trends rise % this week
+ search_demand (0-25)      ← YouTube competitor avg view count proxy
+ low_competition (0-25)    ← few videos + low views = opportunity
+ cpm_alignment (0-20)      ← investing/tax/business > general finance > news
+ history_bonus (0-10)      ← similar past topic performed well on OUR channel
- repeat_penalty (-50)      ← topic used in last 90 days → immediate disqualify
```

**Output to Telegram:**
```
📋 TOPICS THIS WEEK (pick one):

1. [Score: 87] "Why Index Funds Fail 90% of Investors"
   Trend: +340% this week | Competition: Medium | CPM: $18-35
   Angle: Most miss the behavior gap, not the fund itself
   
2. [Score: 79] "The Hidden Cost of Keeping Money in Savings"  
   Trend: +210% (inflation news) | Competition: Low | CPM: $20-40
   Angle: Real inflation-adjusted loss over 5 years with actual numbers

3-5: ...

Reply: /approve_topic 1
```

**Policy Check #1:**
- Topic not on banned list (pump-and-dump, guaranteed returns, scams)
- No YMYL violation (no direct investment advice framing in title)
- Not repeated from used_topics table

---

## AGENT 2: SCRIPT AGENT — Human-Like Writing

**Purpose:** Write script that passes human inspection. No AI patterns.

**Why it won't look AI-generated:**

1. **Real data woven as personal discoveries, not recitations**
   - BAD: "According to Alpha Vantage data, markets returned 10.4%..."
   - GOOD: "I pulled the numbers on this. Going back 20 years — 10.4% average annual return. That sounds great. Until you see what the average investor actually got."

2. **Three rotating templates** — algorithm never sees same format twice
   - Template A: Myth Buster ("Everyone says X. They're wrong.")
   - Template B: Data Story ("This one number explains everything.")
   - Template C: Insider Reveal ("Most people don't know this exists.")

3. **Humanization pass** — second Claude call specifically to:
   - Break sentences >18 words into 2
   - Add false starts: "Now look —", "Here's what nobody tells you —"
   - Add 1 self-correction per section: "...actually scratch that, better example..."
   - Vary rhythm: 3 short. Then longer. Very short.
   - Replace ALL formal transitions

4. **Strong opinion** — not neutral. Takes a clear stance.
   - Not: "Some experts think X while others believe Y"
   - Yes: "The experts are wrong. Here's why."

5. **Financial disclaimer** spoken naturally at ~1:30 mark:
   - "Quick note before we go further — this is education, not advice. Do your own research."

**Script Agent Prompt (Pass 1 — Draft):**
```
You are a YouTube scriptwriter for a finance/business channel targeting US audience.

PERSONA: Direct, slightly contrarian, speaks like smart friend not textbook.
Catchphrase style: "Here's what the numbers actually show"

TOPIC: {topic}
TEMPLATE: {template_name} — {template_structure}
REAL DATA: {live_api_data}
COMPETITOR ANGLES TO AVOID: {top_5_existing_videos_on_topic}

Write {word_count}-word script. Target: 12-14 min video.

MANDATORY RULES:
- First sentence must create FOMO (fear of missing out on knowledge)
- Take strong stance. No both-sides neutrality.
- Weave data into story — never list statistics
- "you" and "your money" — speak directly to viewer
- Add [DISCLAIMER] marker at ~1:30: natural, not fearful
- End each section with teaser to next

BANNED WORDS/PHRASES:
furthermore, additionally, in conclusion, as we can see,
"in today's video", "without further ado", "let's dive in",
"it's important to note", "in summary", "to wrap things up"

OUTPUT FORMAT:
[00:00] SECTION NAME
script text
[KEY QUOTE]: most shareable single line
```

**Script Agent Prompt (Pass 2 — Humanize):**
```
This script was AI-generated. Make it completely undetectable as AI.

ORIGINAL: {draft}

MANDATORY CHANGES:
1. Every sentence >18 words → split into 2
2. Add 2 false starts per section ("Now look —" / "And here's the thing —")
3. Add 1 self-correction per section ("...actually let me rephrase that...")  
4. Turn 3 statistics into personal discoveries (not recitations)
5. Add 1 slightly-imperfect analogy (not clean polished metaphors)
6. Sentence rhythm: short. short. medium sentence here. Very short.
7. 4 direct viewer questions total ("Think about your own situation here...")
8. Replace all formal transitions with casual speech
9. Add [PAUSE] at natural breath points
10. Add [EMPHASIS] on 3 key phrases per section

FLAG AND REWRITE any sentence that sounds like:
LinkedIn post / press release / Wikipedia article

OUTPUT: Humanized script + 3 title A/B test options
```

**Policy Check #2:**
- `[DISCLAIMER]` marker present within first 2 min
- No: "you should buy", "guaranteed", "risk-free", "will definitely"
- No: "get rich quick", "make money fast", "secret method"
- All stats have Source: citation
- No competitor channel names
- Word count 1,200–2,000
- Not repeated from used_topics

---

## AGENT 3: VOICEOVER AGENT (Kokoro TTS)

**Purpose:** Convert script to natural-sounding audio. Free, local, no API cost.

**Why Kokoro over ElevenLabs:**
- ElevenLabs = $11-22/month
- Kokoro = $0/month (runs locally)
- Quality: #1 on HuggingFace TTS Arena, beats models 15x bigger
- Apache 2.0 license (commercial use OK)
- 350MB model, runs on CPU (no GPU needed)

**Voice Settings for Natural Sound:**
```python
# kokoro-onnx usage
from kokoro_onnx import Kokoro

kokoro = Kokoro("kokoro-v1.0.onnx", "voices.bin")

# Process script markers before TTS
def preprocess_for_tts(script):
    # [PAUSE] → insert 0.7s silence after this segment
    # [EMPHASIS] → wrap in SSML <emphasis> tag
    # [DISCLAIMER] → slow pace slightly for this segment
    segments = parse_script_markers(script)
    return segments

# Generate per-section (better quality than full script at once)
def generate_audio(script, job_id):
    sections = preprocess_for_tts(script)
    audio_parts = []
    
    for section in sections:
        samples, sample_rate = kokoro.create(
            section["text"],
            voice="af_heart",     # Natural US English female voice
            speed=0.95,           # Slightly slower = more natural
            lang="en-us"
        )
        audio_parts.append(samples)
        
        if section.get("pause_after"):
            audio_parts.append(generate_silence(0.7, sample_rate))
    
    # Combine + normalize volume
    final_audio = np.concatenate(audio_parts)
    final_audio = normalize_audio(final_audio)
    
    # Export as WAV (FFmpeg will encode to AAC in video)
    save_wav(final_audio, sample_rate, f"temp/{job_id}/audio.wav")
```

**Anti-Robotic Measures:**
- Speed 0.95 (not exactly 1.0 — sounds more natural)
- Silence gaps between sections (0.5-0.9s varied)
- [EMPHASIS] markers → slightly higher energy on key phrases
- [PAUSE] → genuine breath-like gaps

**Policy Check #3:**
- AI disclosure = True (always set in metadata for synthetic voice)
- Audio duration 8-16 min
- No silence gaps >3 seconds
- Volume normalized to -14 LUFS (YouTube standard)

---

## AGENT 4: VIDEO EDITOR AGENT

**Purpose:** Assemble complete video that does NOT look AI-generated.

**What makes video look human-made (our techniques):**

| Element | AI-Looking (avoid) | Human-Looking (do this) |
|---|---|---|
| B-roll | Same 3 stock clips every video | Different Pexels clips each section, varied duration |
| Charts | Static PNG images | Animated charts (matplotlib animation) |
| Transitions | None or harsh cuts | 0.3s crossfade between major sections |
| Text overlays | Always same position | Vary: bottom-left, center, top |
| Pacing | B-roll changes every 5 sec exactly | 3-8 sec clips, varied |
| Music | Same track every video | 5 tracks, random selection |
| Intro | Generic | Branded 3-sec animated channel intro |
| Captions | None | Burned-in (white, black outline) — boosts retention |

**Assembly Pipeline:**
```python
def assemble_video(job_id, audio_path, script, topic):

    # 1. GENERATE CHARTS (animated, from real data)
    charts = []
    for data_point in script["key_data"]:
        chart = animate_chart(
            data=data_point["values"],
            chart_type=random.choice(["line", "bar", "area"]),
            title=data_point["label"],
            color_scheme=CHANNEL_COLORS,
            duration=4.0  # 4-second animation
        )
        charts.append(chart)
    
    # 2. FETCH B-ROLL (Pexels API, varied per section)
    broll = {}
    for section in script["sections"]:
        keywords = extract_visual_keywords(section["text"])
        clips = pexels.search_videos(query=keywords[0], per_page=8)
        safe = [c for c in clips if no_logos(c) and commercial_ok(c)]
        broll[section["id"]] = random.sample(safe, min(3, len(safe)))
    
    # 3. GENERATE CAPTIONS (Whisper — local, MIT license)
    result = whisper.transcribe(audio_path, word_timestamps=True)
    captions = result["segments"]  # word-level timestamps
    
    # 4. BUILD TIMELINE
    clips = []
    for i, section in enumerate(script["sections"]):
        section_broll = broll[section["id"]]
        section_audio_start = section["start_time"]
        section_audio_end = section["end_time"]
        section_duration = section_audio_end - section_audio_start
        
        # Mix: broll clips + chart at data mention point
        section_clips = build_section_clips(
            broll=section_broll,
            chart=charts[i] if i < len(charts) else None,
            duration=section_duration,
            clip_min=3, clip_max=8  # vary clip duration
        )
        clips.extend(section_clips)
    
    # 5. COMPOSE WITH MOVIEPY
    video = concatenate_videoclips(clips, method="crossfade", padding=-0.3)
    audio = AudioFileClip(audio_path)
    music = AudioFileClip(random.choice(MUSIC_TRACKS)).volumex(0.08)  # -18dB under voice
    
    final_audio = CompositeAudioClip([audio, music])
    video = video.set_audio(final_audio)
    
    # 6. BURN CAPTIONS
    video = burn_captions(video, captions, style="youtube")
    # Style: white text, black stroke, bottom-center, 90% width
    
    # 7. ADD CHANNEL INTRO (3 sec) + OUTRO (20 sec)
    intro = VideoFileClip("data/channel_intro.mp4")
    outro = VideoFileClip("data/channel_outro.mp4")
    final = concatenate_videoclips([intro, video, outro])
    
    # 8. RENDER
    final.write_videofile(
        f"output/{job_id}/final_video.mp4",
        fps=30,
        codec="libx264",
        audio_codec="aac",
        bitrate="8000k",
        preset="slow"  # better quality
    )
```

**Policy Check #4:**
- Duration 8-16 minutes
- Music from approved royalty-free list only
- No external copyrighted logos (OpenCV logo detection)
- Captions present
- Resolution 1920x1080
- Audio: voice audible over music (voice >-6dB, music <-18dB)
- No black frame gaps >2 seconds

---

## AGENT 5: THUMBNAIL AGENT

**Purpose:** High-CTR thumbnail. Runs AFTER video (uses real video frames).

**Why frame extraction > AI image generation:**
- No GPU needed
- No FLUX.1/Stable Diffusion complexity
- Frames from actual video = thumbnail matches content (policy requirement)
- Faster (seconds vs minutes)
- No AI-generated face concerns

**Logic:**
```python
def generate_thumbnail(video_path, script, topic, job_id):
    
    # 1. EXTRACT 30 FRAMES from video (skip intro/outro)
    frames = extract_frames(
        video_path,
        count=30,
        start_pct=0.10,   # skip first 10% (intro)
        end_pct=0.85      # skip last 15% (outro)
    )
    
    # 2. SCORE FRAMES
    # Score = brightness(30) + contrast(30) + not_blurry(20) + no_caption_overlap(20)
    scored = [(score_frame(f), f) for f in frames]
    best_frame = max(scored, key=lambda x: x[0])[1]
    
    # 3. SELECT TEMPLATE (rotate 3)
    template = get_next_thumbnail_template()
    # Template 1: Big bold text bottom, frame top-right
    # Template 2: Split — text left 40%, frame right 60%
    # Template 3: Frame full width, text overlay dark gradient bottom
    
    # 4. BUILD THUMBNAIL
    img = Image.fromarray(best_frame)
    img = img.resize((1280, 720), Image.LANCZOS)
    
    # Add dark gradient for text readability
    img = add_gradient_overlay(img, template["gradient"])
    
    # Add hook text (from script key_quote)
    hook = topic["hook_angles"][0].upper()  # e.g., "YOU'RE LOSING $50K"
    sub = "and you don't even know it"
    
    img = add_text(img,
        main=hook, main_size=110, main_color="#FFFFFF", main_stroke="#000000",
        sub=sub, sub_size=55, sub_color="#FFDD00",
        position=template["text_position"]
    )
    
    # Add channel logo (corner)
    img = add_logo(img, "data/channel_logo.png", position="top-right")
    
    # 5. QUALITY CHECKS
    assert check_contrast(img) > 4.5     # WCAG AA readable
    assert check_text_size_mobile(img)   # readable at 120x68px (mobile)
    
    img.save(f"temp/{job_id}/thumbnail.jpg", quality=95)
```

**Policy Check #5:**
- Dimensions exactly 1280x720
- File size <2MB
- Text readable on mobile (120x68px simulation)
- No misleading $ amounts not in video
- Thumbnail content matches video topic (Claude vision check)
- No graphic/disturbing imagery

---

## AGENT 6: SEO / METADATA AGENT

**Purpose:** Maximum discoverability. Every field optimized.

**Title Rules (Monetization-Safe):**
```
ALLOWED:
✓ "Why 90% of Index Fund Investors Still Lose Money"
✓ "The Hidden Cost of Keeping Cash in Savings"
✓ "I Was Wrong About Dividend Investing"

NOT ALLOWED:
✗ "I Made $50,000 in 30 Days" (unverified claim)
✗ "SECRET Banks Don't Want You To Know" (banned phrase pattern)
✗ "GUARANTEED Way to Build Wealth" (banned word)
✗ "Watch Before YouTube DELETES This" (fake urgency)
```

**Description Template:**
```
[HOOK LINE matching video hook — include primary keyword]
[SECOND LINE expanding on value]
⚠️ Educational content only. Not financial advice.

📌 CHAPTERS:
00:00 Introduction
[auto-generated from script timestamps]

📊 DATA SOURCES:
[auto-populated from script source citations]

⚠️ DISCLAIMER: This video is for educational purposes only. Nothing 
here constitutes financial, legal, or investment advice. Past performance 
does not guarantee future results. Always consult a qualified financial 
professional before making any investment decisions.

[Channel links]
[Affiliate links labeled as: *Affiliate link — I earn commission at no extra cost]
```

**Policy Check #6:**
- Title ≤100 chars, no banned phrases
- Description has financial disclaimer (first fold, before "show more")
- Tags: relevant only, no competitor names, max 500 chars
- Chapters: ≥4 timestamps
- `containsSyntheticMedia: True` set in YouTube API call
- Affiliate links labeled

---

## AGENT 7: UPLOAD AGENT

**Purpose:** Upload UNLISTED first. Never go public until human approves.

```python
def upload_video(job_id):
    job = db.get_job(job_id)
    
    # Upload UNLISTED — not public
    response = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": job.metadata["title"],
                "description": job.metadata["description"],
                "tags": job.metadata["tags"],
                "categoryId": "27",          # Education
                "defaultLanguage": "en",
            },
            "status": {
                "privacyStatus": "unlisted", # NOT public yet
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": True,  # AI voice disclosure
            }
        },
        media_body=MediaFileUpload(
            job.video_path,
            resumable=True,
            chunksize=10*1024*1024  # 10MB chunks
        )
    ).execute()
    
    video_id = response["id"]
    
    # Upload thumbnail
    youtube.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(job.thumbnail_path)
    ).execute()
    
    # Update DB
    db.update_job(job_id, {
        "youtube_video_id": video_id,
        "preview_url": f"https://youtu.be/{video_id}",
        "status": "human_review"
    })
    
    # Notify human via Telegram
    send_telegram_approval_request(job_id, video_id, job.metadata)
```

---

## AGENT 8: SCHEDULER AGENT

**Purpose:** Make video public at optimal time after human approval.

**Optimal Publish Times (US EST — highest CPM + algorithm push):**
- Tuesday 12pm-2pm EST
- Wednesday 12pm-2pm EST  
- Thursday 1pm-3pm EST
- Never: Monday, Friday, weekends

```python
def schedule_publish(job_id, video_id):
    now = datetime.now(pytz.timezone("US/Eastern"))
    publish_time = find_next_slot(now)
    
    youtube.videos().update(
        part="status",
        body={
            "id": video_id,
            "status": {
                "privacyStatus": "private",
                "publishAt": publish_time.isoformat() + "Z"
            }
        }
    ).execute()
    
    # Confirm via Telegram
    notify(f"✅ Scheduled: {publish_time.strftime('%A %b %d, %I:%M %p EST')}")
    db.update_job(job_id, {"status": "scheduled", "publish_time": publish_time})
```

---

## AGENT 9: ANALYTICS AGENT (Daily + Weekly)

**Purpose:** Track performance, feed insights back to Research + Orchestrator.

**Metrics Tracked Per Video:**
```
views, impressions, ctr (target >5%), avg_view_duration_sec,
avg_view_percentage (target >50%), likes, comments, subscribers_gained,
estimated_revenue_usd, rpm (target >$4), cpm
```

**Runs:**
- Daily 9am → pulls last 30 days, updates DB
- Sunday 6pm → generates weekly insight report via Claude → sends to Telegram

**Weekly Report to Telegram:**
```
📊 WEEKLY CHANNEL REPORT

Best video: "Why Index Funds Fail..." 
  CTR: 6.1% | AVD: 54% | RPM: $4.80 | Revenue: ~$32

Worst: "Tax Loss Harvesting..."
  CTR: 3.2% (thumbnail issue?) | AVD: 41% (drop at 4min mark)

Channel: +47 subs this week | Total: 312 subs
Est. revenue this week: $67
YPP progress: 312/1000 subs | 890/4000 watch hours

Next week recommendation:
  → Topic: dividend investing (similar to best performer)
  → Template: B (Data Story performed best this month)
  → Fix: thumbnail for low-CTR videos

/analytics for full breakdown
```

---

## NOTIFICATION SYSTEM (Telegram)

**Why Telegram (not email/Discord/SMS):**
| Option | Cost | Interactive? | Phone? | Bot API? |
|---|---|---|---|---|
| Telegram | Free | Yes | Yes | Yes, free |
| Email | Free | No | Bad UX | No |
| Discord | Free | Yes | Yes | Yes, complex |
| WhatsApp | Free | No | Yes | No public API |
| SMS | Paid | No | Yes | No |

**Telegram = only free option with interactive bot commands on phone.**
You approve 1 video/week with `/approve` on phone while at 9-5 job. That's the whole point.

**Commands:**
```
/status          → current pipeline state
/topics          → this week's 5 scored topics
/approve_topic 2 → pick topic #2
/preview         → get unlisted video link
/approve         → approve video → schedules publish
/reject reason   → reject → retries specific failed step
/analytics       → weekly report
/pause           → pause all automation
/resume          → resume
```

**Security:** Bot only responds to YOUR Telegram user ID. Whitelist enforced.

---

## MONETIZATION SAFETY CHECKLIST

**Things that get channels DEMONETIZED (our system prevents all):**

| Risk | Our Prevention |
|---|---|
| AI-labeled inauthentic content | 1 video/week max, 3 rotating formats, real data + opinions |
| Missing AI disclosure | `containsSyntheticMedia: True` always set in upload |
| Financial advice claims | Policy check #2 blocks any investment advice language |
| Fake earnings claims in title | SEO agent prompt explicitly forbids unverified $ amounts |
| Copyright music | Only YouTube Audio Library + Pixabay Music |
| Copyright footage | Only Pexels API (commercial license) |
| Clickbait mismatch | Supervisor compares thumbnail/title against script content |
| Bought subscribers | Never — organic growth only |
| Mass production pattern | 1 video/week hard limit in APScheduler |
| Channel inactivity | APScheduler ensures weekly publish, never goes inactive |

**YPP Approval Path:**
```
Month 1-3:  Build 12 videos. Focus: CTR >4%, AVD >45%
Month 4-6:  500 subs → Early YPP access (limited monetization)
Month 6-12: 1,000 subs + 4,000 hours → Full YPP
            Supervisor tracks: db query → "watch_hours_total"
            Telegram weekly: "YPP progress: 312/1000 subs | 890/4000 hours"
Year 1+:    $500-5,000/mo AdSense + affiliate commissions
```

---

## CRON SCHEDULE (APScheduler — no n8n needed)

```python
# main.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(timezone="US/Eastern")

# Monday 8am: Research Agent finds 5 topics, sends to Telegram
scheduler.add_job(run_research, "cron", day_of_week="mon", hour=8, minute=0)

# Monday 9am: If topic approved, start full pipeline
scheduler.add_job(check_topic_approval_and_start, "cron", day_of_week="mon", hour=9, minute=0)

# Daily 9am: Analytics pull
scheduler.add_job(run_analytics_pull, "cron", hour=9, minute=0)

# Sunday 6pm: Weekly insight report
scheduler.add_job(run_weekly_report, "cron", day_of_week="sun", hour=18, minute=0)

# Every 5 min: Check for human approval (Telegram bot callback)
scheduler.add_job(check_human_approval, "interval", minutes=5)

scheduler.start()
asyncio.get_event_loop().run_forever()
```

---

## BUILD ORDER (Phase by Phase)

### Phase 1: Foundation (Days 1-3)
```
[ ] Create folder structure
[ ] pip install all dependencies (requirements.txt below)
[ ] Set up .env with API keys
[ ] Build core/config.py
[ ] Build core/database.py + run schema creation
[ ] Build core/logger.py
[ ] Build core/notification.py (Telegram bot)
[ ] TEST: /status command works, bot replies
```

### Phase 2: Policy Core (Days 3-5)
```
[ ] Build core/policy_checker.py (all 7 check functions)
[ ] Policy checker loads YOUTUBE_POLICY_REFERENCE.md
[ ] Unit tests for each check
[ ] TEST: Checker catches test violations correctly
```

### Phase 3: Research Agent (Days 5-7)
```
[ ] Build agents/research_agent.py
[ ] Connect: pytrends + PRAW + NewsAPI + YouTube API + Alpha Vantage
[ ] Build scoring algorithm
[ ] Connect to used_topics DB table (no repeats)
[ ] Send formatted topics to Telegram
[ ] TEST: 5 scored topics appear in Telegram
```

### Phase 4: Script Agent (Days 7-10)
```
[ ] Build agents/script_agent.py
[ ] Two-pass Claude API calls (Draft → Humanize)
[ ] Real data injection from Alpha Vantage + World Bank
[ ] Policy check #2 integrated
[ ] TEST: Script sounds human, passes all policy checks
```

### Phase 5: Voiceover Agent (Days 10-12)
```
[ ] Install Kokoro: pip install kokoro-onnx
[ ] Download model: kokoro-v1.0.onnx + voices.bin
[ ] Build agents/voiceover_agent.py
[ ] SSML marker processing ([PAUSE], [EMPHASIS])
[ ] Audio normalization (-14 LUFS)
[ ] TEST: 12-min audio, natural cadence, no artifacts
```

### Phase 6: Video Agent (Days 12-16)
```
[ ] Install FFmpeg binary (Windows: from gyan.dev)
[ ] pip install moviepy whisper-openai
[ ] Build agents/video_agent.py
[ ] Pexels B-roll fetching + filtering
[ ] Animated chart generation (Matplotlib animation)
[ ] Whisper caption generation + burning
[ ] Channel intro/outro (create simple 3sec branded clip)
[ ] TEST: Full 12-min video assembles correctly
```

### Phase 7: Thumbnail + SEO (Days 16-19)
```
[ ] Build agents/thumbnail_agent.py
[ ] Frame extraction (OpenCV) + scoring
[ ] 3 thumbnail templates with Pillow
[ ] Build agents/seo_agent.py
[ ] Claude API metadata generation
[ ] Policy check #6
[ ] TEST: Thumbnail 1280x720, readable, matches content
```

### Phase 8: Upload + Scheduler (Days 19-22)
```
[ ] Google Cloud Console: enable YouTube Data API v3
[ ] OAuth 2.0 setup + token storage
[ ] Build agents/upload_agent.py (unlisted upload)
[ ] Build agents/scheduler_agent.py (optimal time)
[ ] Telegram approval flow: preview link → /approve → schedule public
[ ] TEST: Full upload → unlisted → approve → scheduled public
```

### Phase 9: Analytics Agent (Days 22-24)
```
[ ] Enable YouTube Analytics API in Google Cloud Console
[ ] Build agents/analytics_agent.py
[ ] Daily pull + DB storage
[ ] Weekly Claude insight report
[ ] Telegram weekly report format
[ ] topic_performance table updates
[ ] TEST: Weekly report generates accurate data
```

### Phase 10: Orchestrator + Full Pipeline (Days 24-28)
```
[ ] Build agents/orchestrator.py (Claude Agent SDK)
[ ] Connect all AgentDefinitions
[ ] APScheduler cron in main.py
[ ] Failure handler + retry logic
[ ] End-to-end dry run (no YouTube upload)
[ ] TEST: Full Monday pipeline simulation
```

### Phase 11: Deploy + First Real Video (Days 28-35)
```
[ ] Run first REAL pipeline end-to-end
[ ] Review output: script quality, video quality, thumbnail
[ ] Approve and publish first video
[ ] Monitor for 2 weeks
[ ] Tune parameters based on actual CTR/AVD
```

---

## requirements.txt

```
# Core
python-dotenv==1.0.0
anthropic>=0.25.0

# Claude Agent SDK
claude-agent-sdk>=0.2.111

# Scheduling
apscheduler==3.10.4
pytz==2024.1

# Database
# (sqlite3 built into Python stdlib — no install needed)

# Notifications
python-telegram-bot==21.3

# Research
praw==7.7.1
pytrends==4.9.2
requests==2.31.0
newsapi-python==0.2.7
google-api-python-client==2.131.0
google-auth-oauthlib==1.2.0
google-auth-httplib2==0.2.0

# TTS
kokoro-onnx==0.4.0
onnxruntime==1.18.0
soundfile==0.12.1
numpy==1.26.4

# Video
moviepy==1.0.3
ffmpeg-python==0.2.0
opencv-python==4.9.0.80
Pillow==10.3.0
colorthief==0.2.1

# Captions
openai-whisper==20231117

# Charts
matplotlib==3.8.4
plotly==5.22.0

# Analytics
pandas==2.2.2

# Financial Data
alpha-vantage==3.0.0

# Audio processing
pydub==0.25.1
sounddevice==0.4.6
```

---

## API KEYS NEEDED

```
# .env file — NEVER commit to git

ANTHROPIC_API_KEY=           # platform.claude.com → API keys
PEXELS_API_KEY=              # pexels.com/api → free
NEWSAPI_KEY=                 # newsapi.org → free tier
ALPHA_VANTAGE_KEY=           # alphavantage.co → free
REDDIT_CLIENT_ID=            # reddit.com/prefs/apps → create app → client_id
REDDIT_CLIENT_SECRET=        # same app → secret
REDDIT_USER_AGENT=           youtube-bot/1.0
TELEGRAM_BOT_TOKEN=          # @BotFather → /newbot → copy token
TELEGRAM_CHAT_ID=            # your Telegram user ID (@userinfobot to get)
# YouTube API: uses credentials.json file (OAuth 2.0 from Google Cloud Console)
```

**Zero paid APIs except Claude. Total cost ~$15-25/month.**

---

## COST SUMMARY

```
Claude API:          ~$15-25/mo    ← only paid cost
Everything else:     $0/mo         ← 100% free/open source
Hosting (optional):  $5/mo         ← Railway if you want 24/7 cloud
                    ──────────
MINIMUM:            ~$15-25/mo
WITH HOSTING:       ~$20-30/mo
```

---

## SUCCESS METRICS (Supervisor Monitors Weekly)

```
MONTHS 1-3 (Build foundation):
  Target: 12 videos live, 0 policy strikes, CTR >3.5%, AVD >42%
  
MONTHS 4-6 (Early monetization):
  Target: 500 subs → Early YPP, CTR >4.5%, AVD >48%
  Revenue: $0-50/mo (early access limited ads)

MONTHS 6-12 (Full YPP):
  Target: 1,000 subs + 4,000 hours → Full AdSense
  Revenue: $50-500/mo

YEAR 1+ (Scale):
  Target: 10K-50K subs
  Revenue: $500-5,000/mo AdSense + affiliate commissions
  
SUPERVISOR BLOCKS UPLOAD IF:
  - CTR drops below 3% for 3 consecutive videos (strategy review)
  - Any policy check fails
  - Channel has active strike
  - Human has not approved
```
