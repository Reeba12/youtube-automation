# YouTube Automation System

Fully automated finance & wealth YouTube channel. Weekly video pipeline: research → script → voice → avatar → video → SEO → upload → analytics. Human approves via Telegram before publish.

**Monthly cost: ~$15-25 (Claude API only). Everything else free/open source.**

---

## Architecture

```
APScheduler (cron)
    └── Research Agent     → 5 topics → Telegram
         └── [You pick topic via /approve_topic]
              └── LangGraph Pipeline:
                   Script → Voiceover → Avatar → Video → Thumbnail → SEO
                        └── Supervisor Policy Gate (7 checks)
                             └── Upload (unlisted) → Telegram preview
                                  └── [You approve via /approve]
                                       └── Scheduler → YouTube public
                                            └── Analytics (daily)
```

---

## Stack

| Layer | Tool | License |
|---|---|---|
| AI Brain | Claude API (anthropic) | Paid |
| Orchestration | LangGraph + SQLite checkpoints | MIT |
| Scheduling | APScheduler | MIT |
| Notifications | python-telegram-bot | LGPL |
| TTS Voice | Kokoro ONNX (CPU) | Apache 2.0 |
| Avatar | SadTalker (CPU) | MIT |
| Video | FFmpeg + MoviePy | LGPL / MIT |
| Captions | OpenAI Whisper (local) | MIT |
| Thumbnails | OpenCV + Pillow | MIT |
| Charts | Matplotlib + Plotly | PSF / MIT |
| Stock footage | Pexels API | Free |
| Financial data | Alpha Vantage + World Bank + NewsAPI | Free |
| Research | pytrends + PRAW | MIT |
| YouTube | YouTube Data API v3 + Analytics API | Free |
| Database | SQLite | Public domain |

---

## Setup

### 1. Clone repo

```bash
git clone https://github.com/yourusername/youtube-automation.git
cd youtube-automation
```

### 2. Run setup

```bash
python setup_project.py
```

This installs deps, downloads Kokoro TTS model, clones SadTalker, downloads fonts.

### 3. Configure .env

```bash
cp .env.example .env
# Fill in all API keys
```

**APIs needed (all free except Claude):**
- `ANTHROPIC_API_KEY` — platform.claude.com
- `TELEGRAM_BOT_TOKEN` — @BotFather on Telegram → /newbot
- `TELEGRAM_CHAT_ID` — send /start to @userinfobot
- `PEXELS_API_KEY` — pexels.com/api
- `NEWSAPI_KEY` — newsapi.org (free tier)
- `ALPHA_VANTAGE_KEY` — alphavantage.co (free tier)
- `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` — reddit.com/prefs/apps
- YouTube OAuth — see below

### 4. YouTube OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create project → Enable: YouTube Data API v3, YouTube Analytics API
3. Create OAuth 2.0 credentials → Desktop app
4. Download JSON → save as `data/youtube_client_secrets.json`
5. First run will open browser to authorize

### 5. Add music tracks

Download 5-10 royalty-free MP3s into `data/music/`:
- [YouTube Audio Library](https://studio.youtube.com) → Audio Library
- [Pixabay Music](https://pixabay.com/music/) → free commercial

### 6. Add channel logo

Save your logo as `data/channel_logo.png` (PNG with transparency, any size)

### 7. Generate Aria avatar (optional, takes 10-15 min on CPU)

```bash
python setup_project.py --avatar
```

Then enable in `.env`: `AVATAR_ENABLED=true`

### 8. Activate venv + Run

```bash
# Activate the Python 3.11 venv (created by setup_project.py)
.venv\Scripts\activate

# Run the system
python main.py
```

Or without activating:
```bash
.venv\Scripts\python.exe main.py
```

---

## Telegram Commands

| Command | Action |
|---|---|
| `/status` | System status + channel stats |
| `/topics` | Show this week's 5 topic options |
| `/approve_topic 2` | Approve topic #2 |
| `/preview` | Get unlisted video link |
| `/approve` | Approve video → schedules publish |
| `/reject reason` | Reject video with reason |
| `/analytics` | Channel analytics summary |
| `/pause` | Pause all automation |
| `/resume` | Resume automation |

---

## Weekly Schedule

| Time | Action |
|---|---|
| Monday 8am EST | Research runs, sends 5 topics to Telegram |
| Monday 9am EST | Pipeline starts after topic approval |
| Monday (runs all day) | Script → Voice → Avatar → Video → SEO |
| Monday evening | Supervisor review → Telegram preview sent to you |
| Anytime Mon-Tue | You review + /approve |
| Tuesday 1pm EST | Video goes public |
| Daily 9am EST | Analytics pull |
| Sunday 6pm EST | Weekly report → Telegram |

---

## Upgrade: GPU Avatar (after monetization)

When you have NVIDIA GPU (4GB+ VRAM):

1. `python setup_project.py --install-musetalk` (when ready)
2. In `agents/avatar_agent.py` change line: `AVATAR_ENGINE = "musetalk"`
3. Quality upgrades from acceptable → near-photorealistic. One line change.

---

## File Structure

```
youtube-automation/
├── agents/
│   ├── orchestrator.py       LangGraph pipeline
│   ├── research_agent.py     Topic research + scoring
│   ├── script_agent.py       Two-pass human-like script
│   ├── voiceover_agent.py    Kokoro TTS
│   ├── avatar_agent.py       SadTalker CPU (→ MuseTalk GPU)
│   ├── video_agent.py        FFmpeg assembly
│   ├── thumbnail_agent.py    Frame extraction + Pillow
│   ├── seo_agent.py          YouTube metadata
│   ├── upload_agent.py       YouTube Data API v3
│   ├── scheduler_agent.py    Optimal publish time
│   └── analytics_agent.py   YouTube Analytics
├── core/
│   ├── config.py             All settings from .env
│   ├── database.py           SQLite — jobs, analytics, policy log
│   ├── logger.py             Colored console + JSON file logging
│   ├── notification.py       Telegram bot
│   └── policy_checker.py     YouTube policy enforcement (7 gates)
├── data/
│   ├── YOUTUBE_POLICY_REFERENCE.md
│   ├── avatar/aria_base.png  (generated by setup)
│   ├── fonts/                (downloaded by setup)
│   ├── music/                (add manually)
│   └── models/               (Kokoro ONNX — downloaded by setup)
├── temp/                     Auto-cleaned per job
├── output/                   Final videos
├── logs/                     Per-job JSON logs
├── main.py                   Entry point
├── setup_project.py          First-run setup
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Monetization Path

```
Month 1-3:  12 videos, build consistency. CTR >3.5%, AVD >42%
Month 4-6:  500 subs → Early YPP (limited monetization)
Month 6-12: 1,000 subs + 4,000 watch hours → Full AdSense
Year 1+:    $500-5,000/mo AdSense + affiliate commissions
```

---

## Push to GitHub

```bash
git init
git add .
git commit -m "Initial YouTube automation system"
git remote add origin https://github.com/yourusername/youtube-automation.git
git push -u origin main
```

Deploy anywhere with Python 3.11+: Railway, DigitalOcean, Render, or your own VPS.
