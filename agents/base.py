"""
Base agent — shared LLM call helpers + DB state updater.
All agents import claude() and claude_json() from here.
Internally routes to Groq or Claude based on LLM_PROVIDER in .env.
"""

import json
from typing import Any

from core.database import update_job, log_policy_check
from core.llm import llm_call, llm_json
from core.logger import get_logger

log = get_logger("base", "system")


def claude(
    prompt: str,
    system: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> str:
    """
    Main LLM call. Name kept as 'claude' for compatibility —
    actually routes to Groq or Claude based on LLM_PROVIDER env var.
    """
    return llm_call(prompt, system=system, max_tokens=max_tokens, temperature=temperature)


def claude_json(
    prompt: str,
    system: str = "",
    max_tokens: int = 4096,
) -> Any:
    """LLM call returning parsed JSON."""
    return llm_json(prompt, system=system, max_tokens=max_tokens)


def advance_job(job_id: int, status: str, fields: dict | None = None) -> None:
    """Update job status + optional extra fields."""
    data = {"status": status}
    if fields:
        data.update(fields)
    update_job(job_id, data)


def record_policy(
    job_id: int,
    agent: str,
    passed: bool,
    violations: list,
    action: str,
) -> None:
    log_policy_check(job_id, agent, passed, violations, action)
