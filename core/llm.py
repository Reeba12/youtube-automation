"""
LLM backend — switchable between Groq (free default) and Claude (paid, better quality).
Control via .env:
  LLM_PROVIDER=groq      # default — free, Llama 3.3 70B
  LLM_PROVIDER=claude    # paid — Claude Sonnet, better scripts

Switch anytime by changing LLM_PROVIDER in .env. No code changes needed.
"""

import json
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER   = os.getenv("LLM_PROVIDER", "groq").lower()
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "")

# Model selection per provider
MODELS = {
    "groq":   "llama-3.3-70b-versatile",   # best free Groq model
    "claude": "claude-sonnet-4-6",          # best Claude for scripts
}

from core.logger import get_logger
log = get_logger("llm", "system")


# ── Groq backend ──────────────────────────────────────────────

def _call_groq(
    prompt: str,
    system: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> str:
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=MODELS["groq"],
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content


# ── Claude backend ────────────────────────────────────────────

def _call_claude(
    prompt: str,
    system: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    kwargs: dict[str, Any] = {
        "model":      MODELS["claude"],
        "max_tokens": max_tokens,
        "messages":   [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)
    return response.content[0].text


# ── Public API ────────────────────────────────────────────────

def llm_call(
    prompt: str,
    system: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> str:
    """Single LLM call. Uses provider from LLM_PROVIDER env var."""
    provider = LLM_PROVIDER
    log.debug(f"LLM call via {provider} ({max_tokens} max tokens)")

    if provider == "groq":
        if not GROQ_API_KEY:
            raise EnvironmentError("GROQ_API_KEY not set in .env")
        return _call_groq(prompt, system, max_tokens, temperature)

    elif provider == "claude":
        if not ANTHROPIC_KEY:
            raise EnvironmentError("ANTHROPIC_API_KEY not set in .env")
        return _call_claude(prompt, system, max_tokens, temperature)

    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}. Use 'groq' or 'claude'")


def llm_json(
    prompt: str,
    system: str = "",
    max_tokens: int = 4096,
) -> Any:
    """LLM call that returns parsed JSON. Prompt must instruct JSON output."""
    raw = llm_call(prompt, system=system, max_tokens=max_tokens, temperature=0.2)
    raw = raw.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(raw)


def current_provider() -> str:
    return LLM_PROVIDER


def current_model() -> str:
    return MODELS.get(LLM_PROVIDER, "unknown")
