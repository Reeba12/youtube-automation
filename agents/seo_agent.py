"""
SEO / Metadata Agent — generates YouTube-optimized title, description, tags, chapters.
Uses Claude + channel analytics history to maximize discoverability.
Enforces all financial disclaimer requirements.
"""

import json
import re

from agents.base import claude_json, advance_job, record_policy
from core.config import CHANNEL_NAME
from core.database import get_topic_performance_history
from core.logger import get_logger
from core.policy_checker import check_metadata, load_policy_reference

log = get_logger("seo_agent", "system")

FINANCIAL_DISCLAIMER = (
    "⚠️ DISCLAIMER: This video is for educational and entertainment purposes only. "
    "Nothing in this video constitutes financial, legal, or investment advice. "
    "Always consult a qualified financial professional before making any decisions. "
    "Past performance does not guarantee future results."
)


class SEOAgent:

    def run(self, state: dict) -> dict:
        job_id   = state["job_id"]
        topic    = state["topic"]
        script   = state["script"]
        metadata = state.get("metadata", {})

        log.info(f"[Job {job_id}] SEO Agent starting")
        advance_job(job_id, "seo")

        # Pull analytics history to inform title style
        history = get_topic_performance_history()
        best_categories = [
            h["topic_category"] for h in history
            if (h["avg_ctr"] or 0) > 5.0
        ]

        # Generate metadata
        raw = self._generate_metadata(topic, script, metadata, best_categories)

        # Build final metadata dict
        final_meta = self._build_metadata(raw, topic, metadata, state.get("duration_sec", 720))

        # Policy check
        result = check_metadata(final_meta)
        record_policy(job_id, "seo", result["passed"], result["violations"],
                      "continue" if result["passed"] else "retry")

        if not result["passed"]:
            state["policy_violations"] = result["violations"]
            state["error"] = "seo_policy_failed"
            return state

        advance_job(job_id, "seo_done", {"metadata_json": json.dumps(final_meta)})
        state["metadata"] = final_meta
        log.info(f"[Job {job_id}] SEO Agent complete — title: {final_meta['title']}")
        return state

    # ── Claude metadata generation ────────────────────────────

    def _generate_metadata(
        self,
        topic: dict,
        script: str,
        existing_meta: dict,
        best_categories: list,
    ) -> dict:
        policy_ref = load_policy_reference()

        # Script summary (first 1500 chars for context)
        script_summary = script[:1500].strip()

        # Title options from script agent (if available)
        title_options = existing_meta.get("title_options", [])

        prompt = f"""
Generate YouTube SEO metadata for a finance/wealth education video.

TOPIC: {topic.get('title', '')}
HOOK ANGLES: {json.dumps(topic.get('hook_angles', []))}
SCRIPT OPENING (first 1500 chars): {script_summary}
EXISTING TITLE OPTIONS: {json.dumps(title_options)}
HIGH-PERFORMING CATEGORIES ON THIS CHANNEL: {best_categories}
CHANNEL NAME: {CHANNEL_NAME}

Generate a JSON object with these exact keys:

{{
  "title": "Best title under 70 chars — no banned phrases, accurate to content",
  "title_b": "Second title variation for A/B test",
  "description_hook": "First 2 lines of description (keyword-rich, matches video hook)",
  "tags": ["tag1", "tag2", ...],  // 25-30 tags, mix broad+specific+long-tail
  "chapters": [
    {{"time": "0:00", "label": "Introduction"}},
    ...
  ],
  "category_id": "27",
  "primary_keyword": "the main SEO keyword for this video"
}}

TITLE RULES (strictly enforce):
- Max 70 characters
- Must be accurate — thumbnail and title must match video content
- Never: "guaranteed", "secret", "watch before deleted", "banks don't want"
- Never: unverified dollar amounts like "I made $50,000"
- Create genuine curiosity — not manufactured clickbait shock
- Include primary keyword naturally
- Examples of GOOD titles:
  "Why Index Funds Fail 90% of Investors (The Math)"
  "The Hidden Cost of Keeping Cash in Savings"
  "I Was Wrong About Dividend Investing — Here's Why"

TAG RULES:
- 25-30 tags
- Mix: 5 broad (personal finance, investing) + 15 specific (topic keywords) + 5-10 long-tail
- No competitor channel names in tags
- Total length under 500 characters

CHAPTERS:
- Extract from script structure — minimum 5 chapters
- Format: "0:00", "1:30", "4:00" etc (MM:SS or H:MM:SS)
"""
        try:
            return claude_json(prompt, max_tokens=2000)
        except Exception as e:
            log.warning(f"SEO generation error: {e} — using fallback")
            return self._fallback_metadata(topic, title_options)

    # ── Build final metadata ──────────────────────────────────

    def _build_metadata(
        self,
        raw: dict,
        topic: dict,
        existing: dict,
        duration_sec: float,
    ) -> dict:
        title = raw.get("title") or (existing.get("title_options") or [topic.get("title", "Finance Video")])[0]
        title = title[:100]  # YouTube hard limit

        hook = raw.get("description_hook", f"In this video we explore: {topic.get('title', '')}")
        chapters_list = raw.get("chapters", [])
        chapters_text = self._format_chapters(chapters_list)

        # Build description
        description = (
            f"{hook}\n"
            f"Not financial advice — for educational purposes only.\n\n"
            f"📌 CHAPTERS:\n{chapters_text}\n\n"
            f"📊 Subscribe for weekly finance & wealth insights.\n\n"
            f"{FINANCIAL_DISCLAIMER}"
        )

        tags = raw.get("tags", [])
        # Ensure tags fit within 500 chars
        final_tags = []
        char_count = 0
        for tag in tags:
            if char_count + len(tag) + 1 > 490:
                break
            final_tags.append(tag)
            char_count += len(tag) + 1

        return {
            "title":                  title,
            "title_b":                raw.get("title_b", title),
            "title_options":          existing.get("title_options", [title]),
            "description":            description,
            "tags":                   final_tags,
            "chapters":               chapters_list,
            "category_id":            "27",   # Education
            "primary_keyword":        raw.get("primary_keyword", topic.get("title", "")),
            "contains_synthetic_media": True, # AI voice + avatar = always True
            "duration_min":           round(duration_sec / 60, 1),
            "self_declared_made_for_kids": False,
        }

    def _format_chapters(self, chapters: list) -> str:
        if not chapters:
            return "0:00 Introduction"
        lines = []
        for c in chapters:
            time  = c.get("time", "0:00")
            label = c.get("label", "Section")
            lines.append(f"{time} {label}")
        return "\n".join(lines)

    def _fallback_metadata(self, topic: dict, title_options: list) -> dict:
        title = (title_options or [topic.get("title", "Finance Insight")])[0]
        return {
            "title":           title[:70],
            "title_b":         title[:70],
            "description_hook": f"Let's talk about: {title}",
            "tags":            ["personal finance", "investing", "wealth building",
                                "financial freedom", "money tips", "finance education"],
            "chapters":        [
                {"time": "0:00", "label": "Introduction"},
                {"time": "1:30", "label": "The Core Concept"},
                {"time": "5:00", "label": "The Data"},
                {"time": "9:00", "label": "What To Do"},
                {"time": "12:00", "label": "Key Takeaway"},
            ],
            "primary_keyword": topic.get("title", "personal finance"),
        }
