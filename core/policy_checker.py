"""
Policy checker — enforces YouTube policies on every agent output.
Loaded from YOUTUBE_POLICY_REFERENCE.md at startup.
Called after each agent step. Blocks pipeline on violations.
"""

import json
import re
from pathlib import Path
from typing import Any

from core.config import POLICY_REF_PATH
from core.logger import get_logger

log = get_logger("policy_checker", "system")

# ── Banned phrase lists ───────────────────────────────────────

BANNED_TITLE_PHRASES = [
    "guaranteed returns", "guaranteed profit", "risk-free investment",
    "get rich quick", "make money fast", "secret method", "secret banks",
    "watch before deleted", "watch before youtube deletes",
    "i made $", "100% safe", "will moon", "will pump",
    "insider secret", "banks don't want you to know",
]

BANNED_SCRIPT_PHRASES = [
    "you should buy", "invest in this now", "guaranteed", "risk-free",
    "will definitely", "100% safe", "get rich quick", "make money fast",
    "pump and dump", "insider trading", "crypto pump",
]

DEMONETIZATION_TRIGGER_WORDS = [
    "shooting", "killed", "murder", "suicide", "terrorist", "bomb",
    "coronavirus", "covid", "war crimes", "genocide",
    # Finance-specific
    "ponzi", "pyramid scheme", "scam guaranteed",
]

FINANCIAL_DISCLAIMER_PATTERNS = [
    r"not financial advice",
    r"educational purposes? only",
    r"not investment advice",
    r"consult a (qualified |financial |professional )?advisor",
    r"do your own research",
]

COMPETITOR_CHANNEL_NAMES: list[str] = []  # add known competitor names if needed

SAFE_MUSIC_SOURCES = [
    "youtube_audio_library", "pixabay_music", "epidemic_sound",
    "artlist", "musicbed", "free_music_archive", "ccmixter",
]

# ── Per-agent checkers ────────────────────────────────────────

def check_topic(topic: dict) -> dict[str, bool]:
    title = topic.get("title", "").lower()
    hook_angles = " ".join(topic.get("hook_angles", [])).lower()
    text = title + " " + hook_angles

    banned_found = [p for p in BANNED_TITLE_PHRASES if p in text]
    has_investment_advice = any(w in text for w in [
        "you should buy", "invest now", "guaranteed"
    ])

    violations = []
    if banned_found:
        violations.append(f"Banned phrases in topic: {banned_found}")
    if has_investment_advice:
        violations.append("Direct investment advice framing in topic title")

    passed = len(violations) == 0
    _log_check("topic", passed, violations)
    return {"passed": passed, "violations": violations}


def check_script(script: str) -> dict[str, bool]:
    lower = script.lower()
    violations = []

    # Disclaimer present
    has_disclaimer = any(
        re.search(pat, lower) for pat in FINANCIAL_DISCLAIMER_PATTERNS
    )
    if not has_disclaimer:
        violations.append("No financial disclaimer found in script")

    # Banned phrases
    found_banned = [p for p in BANNED_SCRIPT_PHRASES if p in lower]
    if found_banned:
        violations.append(f"Banned script phrases: {found_banned}")

    # Demonetization triggers
    found_demo = [w for w in DEMONETIZATION_TRIGGER_WORDS if w in lower]
    if found_demo:
        violations.append(f"Demonetization trigger words (review): {found_demo}")

    # Has data sources cited
    source_count = lower.count("source:") + lower.count("(source") + lower.count("according to")
    if source_count < 2:
        violations.append("Fewer than 2 cited data sources in script")

    # Word count
    wc = len(script.split())
    if not (1200 <= wc <= 2000):
        violations.append(f"Script word count {wc} outside range 1200–2000")

    # Competitor mentions
    for name in COMPETITOR_CHANNEL_NAMES:
        if name.lower() in lower:
            violations.append(f"Competitor channel mentioned: {name}")

    # Disclaimer within first 400 words (approx 2 min)
    first_400 = " ".join(script.split()[:400]).lower()
    disclaimer_early = any(re.search(pat, first_400) for pat in FINANCIAL_DISCLAIMER_PATTERNS)
    if not disclaimer_early:
        violations.append("Financial disclaimer not within first 2 minutes of script")

    passed = len(violations) == 0
    _log_check("script", passed, violations)
    return {"passed": passed, "violations": violations}


def check_audio(audio_path: str, duration_sec: float) -> dict[str, bool]:
    violations = []

    min_sec = 8 * 60
    max_sec = 16 * 60
    if not (min_sec <= duration_sec <= max_sec):
        violations.append(f"Audio duration {duration_sec:.0f}s outside 8–16 min range")

    # AI disclosure is always required when using TTS
    # Flag it — upload agent sets containsSyntheticMedia=True
    ai_disclosure_required = True

    passed = len(violations) == 0
    _log_check("voiceover", passed, violations)
    return {
        "passed": passed,
        "violations": violations,
        "ai_disclosure_required": ai_disclosure_required,
    }


def check_video(video_path: str, duration_sec: float, music_source: str) -> dict[str, bool]:
    violations = []

    min_sec = 8 * 60
    max_sec = 16 * 60
    if not (min_sec <= duration_sec <= max_sec):
        violations.append(f"Video duration {duration_sec:.0f}s outside 8–16 min")

    if music_source.lower() not in SAFE_MUSIC_SOURCES:
        violations.append(f"Music source '{music_source}' not in approved royalty-free list")

    passed = len(violations) == 0
    _log_check("video", passed, violations)
    return {"passed": passed, "violations": violations}


def check_thumbnail(thumbnail_path: str, video_title: str, script_summary: str) -> dict[str, bool]:
    from PIL import Image
    violations = []

    try:
        img = Image.open(thumbnail_path)
        w, h = img.size
        if (w, h) != (1280, 720):
            violations.append(f"Thumbnail size {w}x{h} — must be 1280x720")

        import os
        size_mb = os.path.getsize(thumbnail_path) / (1024 * 1024)
        if size_mb > 2.0:
            violations.append(f"Thumbnail {size_mb:.1f}MB — must be <2MB")
    except Exception as e:
        violations.append(f"Thumbnail file error: {e}")

    # Check for misleading money amounts in title vs thumbnail
    money_pattern = r"\$[\d,]+[KMBk]?"
    title_amounts = re.findall(money_pattern, video_title)
    # If thumbnail shows amounts not mentioned in title → clickbait risk
    # (Full check requires CV — simplified here)

    passed = len(violations) == 0
    _log_check("thumbnail", passed, violations)
    return {"passed": passed, "violations": violations}


def check_metadata(metadata: dict) -> dict[str, bool]:
    violations = []

    title = metadata.get("title", "")
    description = metadata.get("description", "")
    tags = metadata.get("tags", [])

    # Title checks
    title_lower = title.lower()
    if len(title) > 100:
        violations.append(f"Title too long: {len(title)} chars (max 100)")
    banned_in_title = [p for p in BANNED_TITLE_PHRASES if p in title_lower]
    if banned_in_title:
        violations.append(f"Banned phrases in title: {banned_in_title}")

    # Description disclaimer
    desc_lower = description.lower()
    has_disclaimer = any(re.search(p, desc_lower) for p in FINANCIAL_DISCLAIMER_PATTERNS)
    if not has_disclaimer:
        violations.append("No financial disclaimer in description")

    # Description disclaimer in first fold (before show more ~300 chars)
    first_fold = description[:300].lower()
    has_early_disclaimer = (
        "not financial advice" in first_fold
        or "educational" in first_fold
        or "not investment advice" in first_fold
    )
    if not has_early_disclaimer:
        violations.append("Disclaimer not visible before 'show more' in description")

    # Tags
    total_tag_chars = sum(len(t) for t in tags)
    if total_tag_chars > 500:
        violations.append(f"Tags too long: {total_tag_chars} chars (max 500)")
    for name in COMPETITOR_CHANNEL_NAMES:
        if any(name.lower() in t.lower() for t in tags):
            violations.append(f"Competitor name in tags: {name}")

    # Chapters
    chapters = metadata.get("chapters", [])
    if len(chapters) < 4:
        violations.append(f"Only {len(chapters)} chapters — need at least 4")

    # AI disclosure
    if not metadata.get("contains_synthetic_media", True):
        violations.append("containsSyntheticMedia not set — required for AI voice/avatar")

    passed = len(violations) == 0
    _log_check("metadata", passed, violations)
    return {"passed": passed, "violations": violations}


def final_audit(state: dict) -> dict[str, bool]:
    """
    Full supervisor audit before sending to human.
    Aggregates all prior checks + growth alignment.
    """
    violations = state.get("policy_violations", [])
    all_checks_passed = len(violations) == 0

    # Verify no active strikes (placeholder — real check via YouTube API)
    channel_clean = True  # updated by analytics agent

    # Upload frequency guard — max 1 long-form per week
    from core.database import get_jobs_by_status
    scheduled_this_week = len(get_jobs_by_status("scheduled"))
    if scheduled_this_week >= 1:
        violations.append("Already 1 video scheduled this week — max 1 long-form/week")
        all_checks_passed = False

    passed = all_checks_passed and channel_clean
    _log_check("final_audit", passed, violations)
    return {"passed": passed, "violations": violations}


# ── Utility ───────────────────────────────────────────────────

def _log_check(agent: str, passed: bool, violations: list) -> None:
    if passed:
        log.info(f"[{agent}] Policy check PASSED")
    else:
        log.warning(f"[{agent}] Policy check FAILED — {violations}")


def load_policy_reference() -> str:
    """Load full policy doc — used by Claude prompts for context."""
    if POLICY_REF_PATH.exists():
        return POLICY_REF_PATH.read_text(encoding="utf-8")
    log.warning("YOUTUBE_POLICY_REFERENCE.md not found in data/")
    return ""
