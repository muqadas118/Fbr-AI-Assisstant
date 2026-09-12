"""
FBR LLM client with primary Groq provider and OpenRouter fallback.

Strategy:
  1. Try Groq (OpenAI-compatible base URL) with the configured model.
  2. If Groq returns 429 / 5xx / network error, automatically fall
     back to the OpenRouter free model from .env.
  3. If both fail, raise a single, well-typed LLMError so the RAG
     engine can render a deterministic "no evidence" placeholder
     instead of a raw stack trace.

Configuration (all read from .env):
  - GROQ_API_KEY:    required for the primary provider
  - GROQ_MODEL:      default = "llama-3.1-8b-instant"
  - OPENROUTER_API_KEY: required for fallback
  - OPENROUTER_MODEL:   default = "nvidia/nemotron-3-ultra-550b-a55b:free"

Both providers are accessed through the OpenAI Python SDK because
Groq exposes an OpenAI-compatible API. No new dependency.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


# ============================================================
# SYSTEM PROMPT (unchanged)
# ============================================================

SYSTEM_PROMPT = """
You are an FBR Pakistan tax information assistant.

Answer the user's question using ONLY the provided FBR context.

Rules:
1. Do not invent tax rates, sections, dates, penalties, exemptions, or procedures.
2. If the provided context does not contain enough information, say:
   "The provided FBR documents do not contain enough information to answer this."
3. Prefer the most specific and relevant information from the retrieved context.
4. Keep the answer clear and practical.
5. Mention the relevant FBR source when possible.
6. Do not claim that you are giving an official legal ruling.
"""


# ============================================================
# EXCEPTIONS
# ============================================================

class LLMError(RuntimeError):
    """Raised when both primary and fallback providers fail."""


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
    api_key: Optional[str],
    base_url: str,
    model: str,
    question: str,
    context: str,
    provider_name: str,
    max_retries: int = 2,
) -> _Result:
    if not api_key:
        raise LLMError(f"{provider_name}: API key not configured")

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=60.0)

    prompt = f"""
USER QUESTION:
{question}

RETRIEVED FBR CONTEXT:
{context}

Using the retrieved FBR context, answer the user's question.
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

def generate_answer(question: str, context: str) -> str:
    """
    Generate an FBR-grounded answer with automatic provider fallback.

    Tries Groq first, then OpenRouter, then raises LLMError.
    """

    providers = []

    if GROQ_API_KEY:
        providers.append(
            ("groq", GROQ_API_KEY, GROQ_BASE_URL, GROQ_MODEL)
        )
    if OPENROUTER_API_KEY:
        providers.append(
            (
                "openrouter",
                OPENROUTER_API_KEY,
                OPENROUTER_BASE_URL,
                OPENROUTER_MODEL,
            )
        )

    if not providers:
        raise LLMError(
            "No LLM provider configured. "
            "Set GROQ_API_KEY and/or OPENROUTER_API_KEY in .env"
        )

    errors: list[str] = []

    for provider_name, api_key, base_url, model in providers:
        try:
            result = _call_provider(
                api_key=api_key,
                base_url=base_url,
                model=model,
                question=question,
                context=context,
                provider_name=provider_name,
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
    """Return configuration status of all LLM providers."""

    return {
        "groq_configured": bool(GROQ_API_KEY),
        "groq_model": GROQ_MODEL if GROQ_API_KEY else None,
        "openrouter_configured": bool(OPENROUTER_API_KEY),
        "openrouter_model": OPENROUTER_MODEL
        if OPENROUTER_API_KEY else None,
    }
