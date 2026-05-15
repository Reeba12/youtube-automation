"""
Central config — loads .env, validates required keys, exposes typed settings.
All agents import from here. Never read os.environ directly elsewhere.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")


def _require(key: str) -> str:
    """Return env var value. Returns empty string if missing (validated at runtime, not import)."""
    return os.getenv(key, "")


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# ── API Keys ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY       = _require("ANTHROPIC_API_KEY")
TELEGRAM_BOT_TOKEN      = _require("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID        = _require("TELEGRAM_CHAT_ID")
PEXELS_API_KEY          = _require("PEXELS_API_KEY")
NEWSAPI_KEY             = _require("NEWSAPI_KEY")
ALPHA_VANTAGE_KEY       = _require("ALPHA_VANTAGE_KEY")
# Reddit removed — API requires manual approval since Nov 2025
# Using RSS feeds instead (no key needed)
REDDIT_CLIENT_ID        = _optional("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET    = _optional("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT       = _optional("REDDIT_USER_AGENT", "youtube-automation-bot/1.0")

# ── YouTube OAuth ─────────────────────────────────────────────────────────────
YOUTUBE_CLIENT_SECRETS_PATH = _optional(
    "YOUTUBE_CLIENT_SECRETS_PATH", "data/youtube_client_secrets.json"
)
YOUTUBE_TOKEN_PATH = _optional("YOUTUBE_TOKEN_PATH", "data/youtube_token.json")

# ── Channel Config ────────────────────────────────────────────────────────────
CHANNEL_NAME        = _optional("CHANNEL_NAME", "Finance & Wealth")
CHANNEL_NICHE       = _optional("CHANNEL_NICHE", "finance_and_wealth")
TARGET_GEO          = _optional("TARGET_AUDIENCE_GEO", "US")
UPLOAD_DAY          = _optional("UPLOAD_DAY", "tuesday")          # mon/tue/wed/thu/fri
UPLOAD_HOUR_EST     = int(_optional("UPLOAD_HOUR_EST", "13"))     # 1pm EST default

# ── Pipeline Config ───────────────────────────────────────────────────────────
MAX_RETRIES             = int(_optional("MAX_RETRIES", "3"))
VIDEO_MIN_DURATION_MIN  = int(_optional("VIDEO_MIN_DURATION_MIN", "8"))
VIDEO_MAX_DURATION_MIN  = int(_optional("VIDEO_MAX_DURATION_MIN", "16"))
SCRIPT_MIN_WORDS        = int(_optional("SCRIPT_MIN_WORDS", "1200"))
SCRIPT_MAX_WORDS        = int(_optional("SCRIPT_MAX_WORDS", "2000"))

# ── Paths ─────────────────────────────────────────────────────────────────────
TEMP_DIR    = Path(_optional("TEMP_DIR", "temp"))
OUTPUT_DIR  = Path(_optional("OUTPUT_DIR", "output"))
LOGS_DIR    = Path(_optional("LOGS_DIR", "logs"))
DATA_DIR    = Path(_optional("DATA_DIR", "data"))
DB_PATH     = Path(_optional("DB_PATH", "data/analytics.db"))

# Ensure dirs exist at import time
for _d in [TEMP_DIR, OUTPUT_DIR, LOGS_DIR, DATA_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ── Claude Model (direct anthropic SDK — no agent SDK) ────────────────────────
CLAUDE_MODEL = "claude-sonnet-4-6"

# ── Kokoro TTS ────────────────────────────────────────────────────────────────
KOKORO_VOICE    = "af_heart"   # US English female, natural
KOKORO_SPEED    = 0.95         # Slightly slower = more natural

# ── Video ─────────────────────────────────────────────────────────────────────
VIDEO_RESOLUTION    = (1920, 1080)
VIDEO_FPS           = 30
VIDEO_BITRATE       = "8000k"
AUDIO_BITRATE       = "192k"
AUDIO_TARGET_LUFS   = -14      # YouTube standard loudness

# ── Script Templates ──────────────────────────────────────────────────────────
SCRIPT_TEMPLATES = ["A", "B", "C"]   # rotate in order

# ── Policy ────────────────────────────────────────────────────────────────────
POLICY_REF_PATH = DATA_DIR / "YOUTUBE_POLICY_REFERENCE.md"

# ── Avatar (disabled until GPU available) ─────────────────────────────────────
AVATAR_ENABLED      = False
AVATAR_BASE_IMAGE   = DATA_DIR / "avatar" / "aria_base.png"
