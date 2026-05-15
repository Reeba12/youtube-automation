"""
Research Agent — finds 5 best finance/wealth topics per week.
Sources: Google Trends + Finance RSS feeds + NewsAPI + YouTube + Alpha Vantage.
Reddit removed (API requires manual approval since Nov 2025).
"""

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import requests
from pytrends.request import TrendReq

from agents.base import claude_json, advance_job, record_policy
from core.config import (
    ALPHA_VANTAGE_KEY, NEWSAPI_KEY, TARGET_GEO,
)
from core.database import (
    create_job, update_job, get_used_topics,
    mark_topic_used, is_topic_used,
)
from core.logger import get_logger
from core.notification import send_topics_notification
from core.policy_checker import check_topic

log = get_logger("research_agent", "system")

# Free finance RSS feeds — no API key, no approval needed
FINANCE_RSS_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US",
    "https://www.cnbc.com/id/10000664/device/rss/rss.html",      # CNBC Personal Finance
    "https://www.cnbc.com/id/15839069/device/rss/rss.html",      # CNBC Investing
    "https://feeds.marketwatch.com/marketwatch/topstories/",
    "https://www.investors.com/feed/",
]

# Seed keywords for Google Trends
TREND_KEYWORDS = [
    "personal finance", "investing", "stock market",
    "passive income", "business strategy", "financial freedom",
    "wealth building", "side hustle",
]

# CPM tier mapping
CPM_TIERS = {
    "investing":        "$18-35",
    "tax":              "$15-40",
    "business":         "$14-35",
    "real_estate":      "$12-30",
    "passive_income":   "$12-25",
    "budgeting":        "$10-20",
    "side_hustle":      "$10-18",
    "general_finance":  "$8-15",
}

SCRIPT_TEMPLATES = ["A", "B", "C"]


class ResearchAgent:

    def __init__(self):
        self.pytrends = TrendReq(hl="en-US", tz=300)

    async def run(self) -> list[dict]:
        log.info("Research Agent starting")

        # Gather raw signals from all sources
        trend_data    = self._google_trends()
        rss_topics    = self._finance_rss()
        news_topics   = self._newsapi()
        market_topics = self._alpha_vantage_movers()

        # Combine + deduplicate
        raw_candidates = list({
            t["title"]: t
            for t in (trend_data + rss_topics + news_topics + market_topics)
        }.values())

        log.info(f"Raw candidates: {len(raw_candidates)}")

        # Score + filter used topics
        scored = []
        for candidate in raw_candidates:
            if is_topic_used(candidate["title"]):
                continue
            candidate["score"] = self._score_topic(candidate)
            scored.append(candidate)

        scored.sort(key=lambda x: x["score"], reverse=True)

        # Policy-check top 10, keep first 5 that pass
        clean_topics = []
        for t in scored[:10]:
            result = check_topic(t)
            if result["passed"]:
                clean_topics.append(t)
            if len(clean_topics) == 5:
                break

        if not clean_topics:
            log.error("No clean topics found — all failed policy check")
            return []

        # Enrich with Claude
        enriched = self._enrich_topics(clean_topics[:5])
        log.info(f"Research complete — {len(enriched)} topics ready")

        # Send to ntfy
        await send_topics_notification(enriched, self._on_topic_approved)
        return enriched

    def _on_topic_approved(self, chosen_topic: dict) -> None:
        log.info(f"Topic approved: {chosen_topic['title']}")
        from core.database import get_recent_completed_jobs
        recent = get_recent_completed_jobs(limit=3)
        used_templates = [j.get("template_used") for j in recent if j.get("template_used")]
        template = self._next_template(used_templates)

        job_id = create_job(
            topic=chosen_topic["title"],
            topic_score=chosen_topic["score"],
            template=template,
        )
        update_job(job_id, {
            "status": "topic_approved",
            "metadata_json": json.dumps({
                "topic_data": chosen_topic,
                "template":   template,
            }),
        })
        mark_topic_used(chosen_topic["title"])
        log.info(f"Job {job_id} created, template {template}")

    # ── Data sources ──────────────────────────────────────────

    def _google_trends(self) -> list[dict]:
        topics = []
        try:
            self.pytrends.build_payload(
                TREND_KEYWORDS[:4],
                timeframe="now 7-d",
                geo=TARGET_GEO,
            )
            related = self.pytrends.related_queries()
            for kw, data in related.items():
                if data and data.get("rising") is not None:
                    for _, row in data["rising"].head(3).iterrows():
                        query = str(row.get("query", "")).strip()
                        value = int(row.get("value", 0))
                        if len(query) > 10:
                            topics.append({
                                "title":          self._format_title(query),
                                "source":         "google_trends",
                                "trend_value":    value,
                                "trend_momentum": f"+{value}% this week",
                            })
        except Exception as e:
            log.warning(f"Google Trends error: {e}")
        return topics

    def _finance_rss(self) -> list[dict]:
        """Parse free finance RSS feeds — no API key needed."""
        topics = []
        headers = {"User-Agent": "Mozilla/5.0 (compatible; youtube-bot/1.0)"}

        for feed_url in FINANCE_RSS_FEEDS:
            try:
                r = requests.get(feed_url, headers=headers, timeout=10)
                root = ET.fromstring(r.content)

                # Handle both RSS and Atom formats
                items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")

                for item in items[:5]:
                    title_el = item.find("title") or item.find("{http://www.w3.org/2005/Atom}title")
                    if title_el is None or not title_el.text:
                        continue
                    title = title_el.text.strip()
                    if len(title) < 15:
                        continue
                    # Filter finance relevant
                    finance_words = ["invest", "stock", "market", "finance", "money",
                                     "wealth", "bank", "fund", "economy", "budget",
                                     "business", "income", "debt", "saving", "crypto"]
                    if not any(w in title.lower() for w in finance_words):
                        continue
                    topics.append({
                        "title":          self._format_title(title),
                        "source":         "rss",
                        "trend_value":    12,
                        "trend_momentum": f"Trending on {feed_url.split('/')[2]}",
                        "competition":    "Low-Medium",
                    })
            except Exception as e:
                log.warning(f"RSS feed error {feed_url}: {e}")

        return topics

    def _newsapi(self) -> list[dict]:
        topics = []
        if not NEWSAPI_KEY:
            return topics
        try:
            r = requests.get(
                "https://newsapi.org/v2/top-headlines",
                params={
                    "apiKey":   NEWSAPI_KEY,
                    "category": "business",
                    "language": "en",
                    "country":  "us",
                    "pageSize": 15,
                },
                timeout=10,
            )
            for a in r.json().get("articles", []):
                title = a.get("title", "")
                if title and len(title) > 20:
                    topics.append({
                        "title":          self._format_title(title),
                        "source":         "newsapi",
                        "trend_value":    15,
                        "trend_momentum": "Breaking business news",
                        "competition":    "Low",
                    })
        except Exception as e:
            log.warning(f"NewsAPI error: {e}")
        return topics

    def _alpha_vantage_movers(self) -> list[dict]:
        topics = []
        if not ALPHA_VANTAGE_KEY:
            return topics
        try:
            r = requests.get(
                "https://www.alphavantage.co/query",
                params={"function": "TOP_GAINERS_LOSERS", "apikey": ALPHA_VANTAGE_KEY},
                timeout=10,
            )
            for g in r.json().get("top_gainers", [])[:3]:
                ticker = g.get("ticker", "")
                change = g.get("change_percentage", "")
                if ticker:
                    topics.append({
                        "title":          f"Why {ticker} Is Surging {change} (What It Means For Investors)",
                        "source":         "alpha_vantage",
                        "trend_value":    20,
                        "trend_momentum": f"{ticker} up {change} this week",
                        "competition":    "Low",
                        "cpm_category":   CPM_TIERS["investing"],
                    })
        except Exception as e:
            log.warning(f"Alpha Vantage error: {e}")
        return topics

    # ── Scoring ───────────────────────────────────────────────

    def _score_topic(self, t: dict) -> int:
        score = 0
        score += min(t.get("trend_value", 10), 30)
        source_bonus = {"google_trends": 10, "alpha_vantage": 8, "newsapi": 6, "rss": 5}
        score += source_bonus.get(t.get("source", ""), 0)
        title_lower = t["title"].lower()
        if any(w in title_lower for w in ["invest", "stock", "fund", "market", "portfolio"]):
            score += 20
        elif any(w in title_lower for w in ["business", "entrepreneur", "income", "wealth"]):
            score += 15
        elif any(w in title_lower for w in ["budget", "save", "debt", "credit"]):
            score += 10
        else:
            score += 5
        comp = t.get("competition", "Medium").lower()
        if "low" in comp:
            score += 15
        elif "medium" in comp:
            score += 8
        from core.database import get_topic_performance_history
        for h in get_topic_performance_history():
            if h.get("topic_category") and h["topic_category"].lower() in title_lower:
                if (h.get("avg_ctr") or 0) > 5.0:
                    score += 10
                    break
        return score

    # ── Enrichment ────────────────────────────────────────────

    def _enrich_topics(self, topics: list[dict]) -> list[dict]:
        prompt = f"""
You are a YouTube research analyst for a finance and wealth channel targeting US audience.

Enrich each topic below. Return JSON array, each item:
{{
  "title": "YouTube-optimized title (max 70 chars, curiosity gap, no banned phrases)",
  "hook_angles": ["angle1", "angle2", "angle3"],
  "cpm_category": "investing|tax|business|passive_income|budgeting|general_finance",
  "competition": "Low|Medium|High",
  "key_data_points": ["stat1", "stat2", "stat3"]
}}

BANNED in titles: "guaranteed", "get rich quick", "secret", "watch before deleted",
"risk-free", "I made $X" (unverified), "banks don't want"

TOPICS:
{json.dumps([{"raw": t["title"], "source": t["source"], "trend": t.get("trend_momentum","")} for t in topics], indent=2)}
"""
        try:
            enriched_data = claude_json(prompt)
            for i, t in enumerate(topics):
                if i < len(enriched_data):
                    t.update(enriched_data[i])
                    t["cpm_category"] = CPM_TIERS.get(
                        t.get("cpm_category", "general_finance"), "$8-15"
                    )
        except Exception as e:
            log.warning(f"Topic enrichment error: {e}")
        return topics

    # ── Utilities ─────────────────────────────────────────────

    def _format_title(self, raw: str) -> str:
        cleaned = raw.strip().replace("\n", " ")
        # Remove source attribution like " - CNBC" at end
        for sep in [" - ", " | ", " — "]:
            if sep in cleaned:
                cleaned = cleaned.split(sep)[0].strip()
        if cleaned and not cleaned[0].isupper():
            cleaned = cleaned.capitalize()
        return cleaned[:120]

    def _next_template(self, used: list[str]) -> str:
        if not used:
            return "A"
        last = used[0] if used else "C"
        order = SCRIPT_TEMPLATES
        idx = order.index(last) if last in order else -1
        return order[(idx + 1) % len(order)]
