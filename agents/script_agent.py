"""
Script Agent — two-pass human-like script generation.
Pass 1: Draft with real financial data + strong opinion.
Pass 2: Humanize — remove all AI patterns.
Output: timestamped script + 3 title A/B options.
"""

import json
import re
from pathlib import Path

import requests

from agents.base import claude, advance_job, record_policy
from core.config import ALPHA_VANTAGE_KEY, NEWSAPI_KEY, TEMP_DIR
from core.database import get_job, update_job
from core.logger import get_logger
from core.policy_checker import check_script, load_policy_reference

log = get_logger("script_agent", "system")

# ── Templates ─────────────────────────────────────────────────

TEMPLATES = {
    "A": {
        "name": "Myth Buster",
        "target_words": 1500,
        "structure": """
[00:00] HOOK — State common belief. Immediately say it's wrong. ONE data point why.
[00:30] SETUP — How this myth started. Who profits from people believing it.
[01:30] DISCLAIMER — (natural, not fearful)
[02:00] THE EVIDENCE — 3 data points contradicting the myth.
[05:00] DEEP DIVE — What's actually true. Real mechanism explained.
[09:00] WHAT TO DO — Practical application for viewer's situation.
[12:00] THE INSIGHT NOBODY MENTIONS — Your contrarian unique take.
[13:00] CTA — Hook to next video + subscribe ask.
""",
    },
    "B": {
        "name": "Data Story",
        "target_words": 1600,
        "structure": """
[00:00] HOOK — Shocking number. One sentence. Let it land.
[00:30] CONTEXT — What that number means for the viewer specifically.
[01:30] DISCLAIMER — (natural, matter-of-fact)
[02:00] THE STORY — How we got here. Historical context.
[04:00] DATA BREAKDOWN — 4 sub-points each anchored by specific number.
[09:00] FORWARD LOOK — What data predicts. Where this is heading.
[11:30] ACTION — What smart money is doing right now.
[13:00] CTA
""",
    },
    "C": {
        "name": "Insider Reveal",
        "target_words": 1450,
        "structure": """
[00:00] HOOK — "Most people don't know this exists."
[00:30] CREDIBILITY — Why this is underreported. Who benefits from silence.
[01:30] DISCLAIMER — (natural)
[02:00] THE REVEAL — What it is. How it works. Simple terms.
[05:00] HOW TO USE IT — Step-by-step practical breakdown.
[09:00] WHO THIS FITS — Honest: who benefits, who doesn't. Builds trust.
[11:00] REAL EXAMPLES — Specific numbers. Real scenarios.
[13:00] CTA
""",
    },
}

PERSONA = """
CHANNEL PERSONA:
- Voice: Direct, confident, slightly contrarian
- Tone: Smart friend who reads too much finance news
- NOT: neutral reporter, textbook writer, LinkedIn influencer
- Catchphrases: "Here's what the numbers actually show", "And this is the part nobody talks about"
- Speaks to intelligent adults — no dumbing down
- Takes a clear stance. Not both-sides. Has an opinion.
- Disclaimer style: matter-of-fact, not fearful
"""

PASS1_SYSTEM = f"""
You are a YouTube scriptwriter for a finance and wealth channel targeting US audience.
{PERSONA}
You write scripts that challenge conventional wisdom using real data.
Never be neutral. Always take a stance backed by evidence.
"""

PASS2_SYSTEM = """
You are an editor who makes AI-generated scripts sound completely human.
You know every AI writing pattern and you eliminate all of them.
Your edits make scripts sound like a real person speaking — not a content machine.
"""


class ScriptAgent:

    def run(self, state: dict) -> dict:
        job_id   = state["job_id"]
        topic    = state["topic"]
        template = state.get("template", "A")

        log.info(f"[Job {job_id}] Script Agent starting — topic: {topic['title']}, template: {template}")
        advance_job(job_id, "scripting")

        # 1. Fetch real financial data
        data = self._fetch_real_data(topic)
        log.info(f"[Job {job_id}] Real data fetched: {list(data.keys())}")

        # 2. Get competitor angles to avoid
        competitor_angles = self._get_competitor_angles(topic["title"])

        # 3. Pass 1 — Draft
        draft = self._pass1_draft(topic, data, template, competitor_angles)
        log.info(f"[Job {job_id}] Pass 1 draft complete — {len(draft.split())} words")

        # 4. Pass 2 — Humanize
        final_script, title_options = self._pass2_humanize(draft)
        log.info(f"[Job {job_id}] Pass 2 humanized — {len(final_script.split())} words")

        # 5. Policy check
        result = check_script(final_script)
        record_policy(job_id, "script", result["passed"], result["violations"], "continue" if result["passed"] else "retry")

        if not result["passed"]:
            log.warning(f"[Job {job_id}] Script policy failed: {result['violations']}")
            state["policy_violations"] = result["violations"]
            state["error"] = "script_policy_failed"
            return state

        # 6. Save script to file
        script_path = TEMP_DIR / str(job_id) / "script.txt"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(final_script, encoding="utf-8")

        # 7. Save title options + data to metadata
        meta = json.loads(state.get("metadata_json") or "{}")
        meta.update({
            "title_options":  title_options,
            "topic_data":     topic,
            "real_data":      data,
        })

        advance_job(job_id, "scripted", {
            "script_path":   str(script_path),
            "metadata_json": json.dumps(meta),
        })

        state["script"]      = final_script
        state["script_path"] = str(script_path)
        state["metadata"]    = meta
        log.info(f"[Job {job_id}] Script Agent complete")
        return state

    # ── Pass 1: Draft ─────────────────────────────────────────

    def _pass1_draft(self, topic: dict, data: dict, template_key: str, competitors: list) -> str:
        t = TEMPLATES[template_key]
        policy_ref = load_policy_reference()

        prompt = f"""
Write a {t['target_words']}-word YouTube script using the {t['name']} template.

TOPIC: {topic['title']}
HOOK ANGLES TO CHOOSE FROM: {json.dumps(topic.get('hook_angles', []))}

TEMPLATE STRUCTURE:
{t['structure']}

REAL DATA TO WEAVE IN (use exact numbers, cite source inline):
{json.dumps(data, indent=2)}

COMPETITOR ANGLES TO AVOID (don't repeat these existing takes):
{json.dumps(competitors, indent=2)}

YOUTUBE POLICY RULES (MUST follow):
- Add [DISCLAIMER] at ~1:30: "Quick note — everything here is educational, not financial advice. Do your own research."
- Never say: "you should buy X", "guaranteed", "risk-free", "will definitely", "100% safe"
- Never say: "get rich quick", "make money fast", "secret method"
- At least 2 inline source citations: (Source: [name])
- No competitor YouTube channel names

WRITING RULES:
- First sentence creates FOMO (fear of missing knowledge, not fear of loss)
- Take strong stance — never neutral, always have an opinion
- Weave data into story — never list raw statistics
- Speak directly: "you", "your money", "your situation"
- End each section with a teaser to next section
- NEVER use: furthermore, additionally, in conclusion, as we can see,
  "in today's video", "without further ado", "let's dive in",
  "it's important to note", "to wrap things up"
- Break any sentence over 18 words into two sentences
- Vary sentence length: short. short. medium sentence here. Very short.

OUTPUT FORMAT (include timestamps):
[00:00] SECTION NAME
script text...
[KEY QUOTE]: most shareable line from this section

[00:30] NEXT SECTION
...
"""
        return claude(prompt, system=PASS1_SYSTEM, max_tokens=5000, temperature=0.8)

    # ── Pass 2: Humanize ──────────────────────────────────────

    def _pass2_humanize(self, draft: str) -> tuple[str, list]:
        prompt = f"""
This script was written by AI. Make it completely undetectable as AI-written.
A real human finance presenter will read this on camera — it must sound exactly like them.

ORIGINAL SCRIPT:
{draft}

MANDATORY TRANSFORMATIONS:
1. Every sentence over 18 words → split into 2 sentences
2. Add 2 false starts per major section:
   Examples: "Now look —", "Here's the thing —", "And this is the part that gets me —",
   "Wait, before I go further —", "Okay so —"
3. Add exactly 1 self-correction per section:
   Examples: "...actually, scratch that, better example...",
   "...no wait, let me say it differently...",
   "...actually that's not quite right, what I mean is..."
4. Transform 3 statistics from recitation to personal discovery:
   BAD: "According to data, 67% of investors underperform..."
   GOOD: "I pulled the numbers on this last week. 67% of investors. Underperform. Every year."
5. Add 1 slightly imperfect analogy — human analogies are never perfectly clean
6. Sentence rhythm pattern: short. short. medium sentence. Very short. Repeat.
7. Add 4 direct viewer questions total: "Think about your own situation here..."
8. Replace ALL formal transitions:
   "furthermore" → "and here's where it gets interesting"
   "in conclusion" → "so what does all this actually mean for you"
   "additionally" → "oh — and one more thing"
   "however" → "but here's the catch"
9. Add [PAUSE] markers at natural breath points (3-4 per section)
10. Add [EMPHASIS] markers on 3 key phrases per section

FINAL AUDIT — rewrite any sentence that sounds like:
- A LinkedIn post
- A press release
- A Wikipedia article
→ Those 3 are your enemy. Hunt them down.

After the humanized script, output:

TITLE OPTIONS:
1. [60 chars max, curiosity gap, includes primary keyword]
2. [60 chars max, different angle, data-driven]
3. [60 chars max, contrarian or challenge-belief style]

Rules for titles:
- No: "guaranteed", "secret", "watch before deleted", "banks don't want"
- No unverified dollar amounts
- Must accurately represent video content
- Create genuine curiosity — not manufactured shock
"""
        raw = claude(prompt, system=PASS2_SYSTEM, max_tokens=6000, temperature=0.6)

        # Split script from title options
        if "TITLE OPTIONS:" in raw:
            parts = raw.split("TITLE OPTIONS:", 1)
            script = parts[0].strip()
            title_block = parts[1].strip()
            title_lines = [
                re.sub(r"^\d+\.\s*", "", line).strip()
                for line in title_block.splitlines()
                if line.strip() and re.match(r"^\d+\.", line.strip())
            ]
        else:
            script = raw
            title_lines = []

        return script, title_lines

    # ── Real data fetching ────────────────────────────────────

    def _fetch_real_data(self, topic: dict) -> dict:
        data = {}
        title_lower = topic["title"].lower()

        # World Bank — economic indicators (free, no key)
        try:
            data["us_gdp_growth"] = self._world_bank("NY.GDP.MKTP.KD.ZG", "US")
            data["us_inflation"]  = self._world_bank("FP.CPI.TOTL.ZG", "US")
            data["us_unemployment"] = self._world_bank("SL.UEM.TOTL.ZS", "US")
        except Exception as e:
            log.warning(f"World Bank data error: {e}")

        # Alpha Vantage — market data
        if any(w in title_lower for w in ["stock", "market", "invest", "index", "s&p", "fund"]):
            try:
                r = requests.get(
                    "https://www.alphavantage.co/query",
                    params={"function": "GLOBAL_QUOTE", "symbol": "SPY", "apikey": ALPHA_VANTAGE_KEY},
                    timeout=10
                )
                data["spy_price"] = r.json().get("Global Quote", {})
            except Exception as e:
                log.warning(f"Alpha Vantage error: {e}")

        # NewsAPI — recent headlines for context
        try:
            keywords = " ".join(topic["title"].split()[:4])
            r = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q":        keywords,
                    "apiKey":   NEWSAPI_KEY,
                    "language": "en",
                    "sortBy":   "relevancy",
                    "pageSize": 5,
                },
                timeout=10
            )
            articles = r.json().get("articles", [])
            data["recent_news"] = [
                {"title": a["title"], "source": a["source"]["name"]}
                for a in articles[:3]
            ]
        except Exception as e:
            log.warning(f"NewsAPI data error: {e}")

        return data

    def _world_bank(self, indicator: str, country: str) -> dict:
        url = f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
        params = {"format": "json", "mrv": 3, "per_page": 3}
        r = requests.get(url, params=params, timeout=10)
        items = r.json()
        if isinstance(items, list) and len(items) > 1:
            records = items[1] or []
            return [
                {"year": rec["date"], "value": rec["value"]}
                for rec in records if rec.get("value") is not None
            ]
        return {}

    def _get_competitor_angles(self, topic_title: str) -> list[str]:
        """Get top 5 YouTube video titles on this topic to avoid repeating."""
        try:
            from googleapiclient.discovery import build
            from core.config import YOUTUBE_CLIENT_SECRETS_PATH
            # Use public search (no auth needed for search)
            import os
            api_key = os.getenv("YOUTUBE_API_KEY", "")
            if not api_key:
                return []
            yt = build("youtube", "v3", developerKey=api_key)
            search = yt.search().list(
                q=topic_title,
                part="snippet",
                maxResults=5,
                order="viewCount",
                type="video",
            ).execute()
            return [
                item["snippet"]["title"]
                for item in search.get("items", [])
            ]
        except Exception:
            return []
