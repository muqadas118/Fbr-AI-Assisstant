"""
FBR LLM client — provider-agnostic OpenAI-compatible client.

Strategy:
  1. Build the provider chain from .env:
     - Any number of generic providers via LLM_PROVIDERS / LLM_<NAME>_*
       (every OpenAI-compatible API works: OpenRouter, Groq, Ollama,
       LM Studio, vLLM, AgentRouter, Together, DeepSeek, etc.)
     - Plus the legacy well-known providers when their keys exist:
       GROQ_API_KEY (primary) and OPENROUTER_API_KEY (fallback).
  2. Try each provider in order (env order first, then Groq, then
     OpenRouter). On 429 / 5xx / network error / empty content the
     next provider is tried automatically.
  3. If all providers fail, raise a single, well-typed LLMError so
     the RAG engine can render the deterministic "no evidence"
     placeholder instead of a raw stack trace.

Configuration (all from .env):
  # Preferred generic chain (comma-separated logical names):
  LLM_PROVIDERS=openrouter,groq,local

  # Per-provider settings (NAME is the UPPERCASE logical name):
  LLM_LOCAL_BASE_URL=http://localhost:11434/v1
  LLM_LOCAL_MODEL=qwen2.5:7b
  LLM_LOCAL_API_KEY=            # optional; some local servers need any string
  LLM_OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
  LLM_OPENROUTER_MODEL=...
  LLM_OPENROUTER_API_KEY=...

  # Legacy aliases still work (mapped automatically):
  GROQ_API_KEY / GROQ_MODEL
  OPENROUTER_API_KEY / OPENROUTER_MODEL

Any provider that speaks the OpenAI chat-completions protocol is
accessed through the OpenAI Python SDK — no new dependency.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

from app.language import detect_language, output_directive


load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"
DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Accepts optional scheme; "localhost:11434/v1" -> https://localhost:11434/v1
def _normalize_base_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    return url


@dataclass(frozen=True)
class _Provider:
    name: str
    api_key: str
    base_url: str
    model: str


def _provider_from_env(name: str) -> Optional[_Provider]:
    """Build a provider from LLM_<NAME>_* env vars (any OpenAI-compatible service)."""
    prefix = f"LLM_{name.upper()}_"
    base_url = _normalize_base_url(os.getenv(prefix + "BASE_URL", ""))
    model = os.getenv(prefix + "MODEL", "").strip()
    api_key = os.getenv(prefix + "API_KEY", os.getenv(prefix + "KEY", "")).strip()

    # Sensible defaults for well-known logical names.
    if not base_url:
        defaults = {
            "OPENROUTER": _OPENROUTER_BASE_URL,
            "GROQ": _GROQ_BASE_URL,
            "OPENAI": "https://api.openai.com/v1",
            "DEEPSEEK": "https://api.deepseek.com/v1",
            "TOGETHER": "https://api.together.xyz/v1",
            "MISTRAL": "https://api.mistral.ai/v1",
            "FIREWORKS": "https://api.fireworks.ai/inference/v1",
            "AGENTROUTER": "https://api.agentrouter.org/v1",
        }
        base_url = defaults.get(name.upper(), "")
    if not base_url or not model:
        return None
    return _Provider(
        name=name.lower(),
        api_key=api_key or "not-needed",  # local servers ignore the key
        base_url=base_url,
        model=model,
    )


def _legacy_providers() -> list[_Provider]:
    """Map legacy GROQ_* / OPENROUTER_* variables into the provider chain."""
    out: list[_Provider] = []
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key:
        out.append(
            _Provider(
                name="groq",
                api_key=groq_key,
                base_url=os.getenv("GROQ_BASE_URL", _GROQ_BASE_URL).strip(),
                model=os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip(),
            )
        )
    or_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if or_key:
        out.append(
            _Provider(
                name="openrouter",
                api_key=or_key,
                base_url=os.getenv("OPENROUTER_BASE_URL", _OPENROUTER_BASE_URL).strip(),
                model=os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL).strip(),
            )
        )
    return out


def _provider_chain() -> list[_Provider]:
    """
    Ordered provider chain.

    - LLM_PROVIDERS=openrouter,groq,local  -> exactly that order
    - Otherwise legacy order: groq -> openrouter (when keys exist)
    - Generic LLM_<NAME>_* providers with no LLM_PROVIDERS entry are
      appended after the legacy ones so an explicitly ordered chain
      always wins.
    """
    chain: list[_Provider] = []
    seen: set[str] = set()

    order_env = os.getenv("LLM_PROVIDERS", "").strip()
    if order_env:
        for raw in re.split(r"[,\s;]+", order_env):
            name = raw.strip()
            if not name or name.lower() in seen:
                continue
            p = _provider_from_env(name)
            if p is not None:
                chain.append(p)
                seen.add(p.name)

    for p in _legacy_providers():
        if p.name not in seen:
            chain.append(p)
            seen.add(p.name)

    # Auto-discover generic LLM_<NAME>_* providers not listed explicitly.
    generic = set()
    for key in os.environ:
        m = re.match(r"^LLM_([A-Z0-9]+)_(BASE_URL|MODEL|API_KEY|KEY)$", key)
        if m:
            generic.add(m.group(1))
    for name in sorted(generic):
        if name.lower() in seen:
            continue
        p = _provider_from_env(name)
        if p is not None:
            chain.append(p)
            seen.add(p.name)

    return chain


# ============================================================
# SYSTEM PROMPT (partial-coverage rule 2b added 2026-09-20;
# refusal phrase and grounding directives unchanged)
# ============================================================

SYSTEM_PROMPT = """
You are an FBR Pakistan tax information assistant.

Answer the user's question using ONLY the provided FBR context.

Rules:
1. Do not invent tax rates, sections, dates, penalties, exemptions, or procedures.
2. If the provided context does not contain enough information, say:
   "The provided FBR documents do not contain enough information to answer this."
2b. If the context contains relevant items but not a complete answer
   (for example a list question where only some items are present),
   summarize ONLY the items actually present — each with its source —
   and then state plainly and factually what the context does and does
   not cover, including the document years involved. Never present
   older items as current, never fill gaps from outside the context,
   and rule 7 still applies (no hedging words).
3. Prefer the most specific and relevant information from the retrieved context.
4. Keep the answer clear and practical.
5. Mention the relevant FBR source when possible.
6. Do not claim that you are giving an official legal ruling.
7. Never hedge with words like likely, probably, maybe, perhaps,
   possibly, or phrases like I think / I believe / in my opinion.
   State what the context supports and cite the source; if the context
   is insufficient, use the exact sentence from rule 2 instead.
"""


# ============================================================
# EXCEPTIONS
# ============================================================

class LLMError(RuntimeError):
    """Raised when all configured providers fail."""


# ============================================================
# PROVIDER RESULT
# ============================================================

@dataclass(frozen=True)
class _Result:
    content: str
    provider: str
    model: str


# ============================================================
# PROVIDER CALL
# ============================================================

def _call_provider(
    api_key: str,
    base_url: str,
    model: str,
    question: str,
    context: str,
    provider_name: str,
    max_retries: int = 2,
    language: Optional[str] = None,
) -> _Result:
    if not api_key:
        raise LLMError(f"{provider_name}: API key not configured")
    if not base_url:
        raise LLMError(f"{provider_name}: base URL not configured")

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=60.0)

    if not language:
        language = detect_language(question)

    prompt = f"""
USER QUESTION:
{question}

RETRIEVED FBR CONTEXT:
{context}

Using the retrieved FBR context, answer the user's question.

{output_directive(language)}
"""

    last_error: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                # Bound worst-case generation latency/cost. Grounded tax
                # answers are concise tables plus notes (~800 tokens);
                # 2000 leaves ample headroom without runaway output.
                max_tokens=2000,
            )
        except Exception as e:  # noqa: BLE001
            last_error = e
            error_type = type(e).__name__
            error_msg = str(e).lower()
            if any(
                token in error_msg
                for token in (
                    "429", "rate limit", "quota", "timeout",
                    "502", "503", "504", "connection",
                )
            ):
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
            raise LLMError(
                f"{provider_name}: {error_type}: {str(e)[:300]}"
            ) from e

        choice = response.choices[0] if response.choices else None
        if choice is None:
            # Transient free-tier flake (empty choices list) — retry
            # with backoff instead of failing the whole domain.
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            raise LLMError(
                f"{provider_name}: empty choices in response"
            )

        content = choice.message.content
        if content:
            return _Result(
                content=content.strip(),
                provider=provider_name,
                model=model,
            )

        reasoning = getattr(choice.message, "reasoning", None)
        if reasoning:
            return _Result(
                content=reasoning.strip(),
                provider=provider_name,
                model=model,
            )

        # Empty content with no reasoning is also transient — retry.
        if attempt < max_retries:
            time.sleep(2 ** attempt)
            continue
        raise LLMError(
            f"{provider_name}: empty model content "
            f"(finish_reason={getattr(choice, 'finish_reason', None)})"
        )

    raise LLMError(
        f"{provider_name}: exhausted retries: {str(last_error)[:200]}"
    )


# ============================================================
# PUBLIC ENTRY POINT
# ============================================================

def _provider_chain_impl() -> "list[_Provider]":
    """Ordered provider chain (env order first, then legacy aliases)."""
    return _provider_chain()


def generate_answer_stream(
    question: str, context: str, language: Optional[str] = None
):
    """Yield answer text chunks as they arrive from the first working provider.

    Falls back across the provider chain only while NO content has been
    produced yet; once tokens are flowing a mid-stream failure simply ends
    the stream (partial answer is still valid).
    Raises LLMError when every provider fails before producing any content.
    """
    from openai import OpenAI as _OpenAI  # already a hard dependency

    providers = _provider_chain_impl()
    if not providers:
        raise LLMError(
            "No LLM provider configured. Set GROQ_API_KEY, "
            "OPENROUTER_API_KEY, or LLM_<NAME>_BASE_URL + LLM_<NAME>_MODEL "
            "in .env (any OpenAI-compatible provider works)."
        )

    errors: list[str] = []
    if not language:
        language = detect_language(question)

    prompt = f"""
USER QUESTION:
{question}

RETRIEVED FBR CONTEXT:
{context}

Using the retrieved FBR context, answer the user's question.

{output_directive(language)}
"""

    for p in providers:
        produced = False
        try:
            client = _OpenAI(base_url=p.base_url, api_key=p.api_key, timeout=60.0, max_retries=0)
            stream = client.chat.completions.create(
                model=p.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=2000,
                stream=True,
            )
            for event in stream:
                if not event.choices:
                    continue
                delta = event.choices[0].delta
                chunk = getattr(delta, "content", None) if delta is not None else None
                if chunk:
                    produced = True
                    yield chunk
            if produced:
                return
            errors.append(f"{p.name}: empty stream")
        except Exception as e:  # noqa: BLE001
            if produced:
                return  # partial answer already delivered
            errors.append(f"{p.name}: {type(e).__name__}: {str(e)[:200]}")
            continue

    raise LLMError("All LLM providers failed (stream): " + " | ".join(errors))


def generate_answer(
    question: str, context: str, language: Optional[str] = None
) -> str:
    """
    Generate an FBR-grounded answer with automatic provider fallback.

    Tries every configured provider in order; raises LLMError when
    all of them fail.
    """

    providers = _provider_chain()

    if not providers:
        raise LLMError(
            "No LLM provider configured. Set GROQ_API_KEY, "
            "OPENROUTER_API_KEY, or LLM_<NAME>_BASE_URL + LLM_<NAME>_MODEL "
            "in .env (any OpenAI-compatible provider works)."
        )

    errors: list[str] = []

    for p in providers:
        try:
            result = _call_provider(
                api_key=p.api_key,
                base_url=p.base_url,
                model=p.model,
                question=question,
                context=context,
                provider_name=p.name,
                language=language,
            )
            return result.content
        except LLMError as e:
            errors.append(str(e))
            continue

    raise LLMError(
        "All LLM providers failed: " + " | ".join(errors)
    )


# ============================================================
# UTILITIES
# ============================================================

def provider_status() -> dict:
    """Return configuration status of all LLM providers in the chain."""

    chain = _provider_chain()
    return {
        "providers": [
            {"name": p.name, "base_url": p.base_url, "model": p.model}
            for p in chain
        ],
        "count": len(chain),
        # Legacy fields kept for existing scripts/tests.
        "groq_configured": any(p.name == "groq" for p in chain),
        "groq_model": next((p.model for p in chain if p.name == "groq"), None),
        "openrouter_configured": any(p.name == "openrouter" for p in chain),
        "openrouter_model": next(
            (p.model for p in chain if p.name == "openrouter"), None
        ),
    }
