"""Non-destructive LLM provider probe.

Reads .env via app.llm.generate_answer and reports which provider
served the response. Does not touch FAISS, embeddings, or chunks.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.llm import generate_answer, provider_status  # noqa: E402


def main() -> int:
    status = provider_status()
    print("Provider status:", status)
    if not (status["groq_configured"] or status["openrouter_configured"]):
        print("No LLM provider configured.")
        return 1
    try:
        answer = generate_answer(
            question=(
                "What is the Sales Tax registration threshold "
                "for services under the Sales Tax Act, 1990?"
            ),
            context=(
                "Sales Tax Act 1990, Section 14: A person who is "
                "required to be registered under this Act shall apply "
                "for registration to the relevant authority. The "
                "registration threshold for services is Rs. 10 million "
                "annual turnover. Source: SalesTaxAct1990.pdf."
            ),
        )
    except Exception as e:  # noqa: BLE001
        print(f"PROBE FAIL: {type(e).__name__}: {str(e)[:500]}")
        return 2
    print(f"PROBE OK (answer length={len(answer)})")
    print("Answer:", answer[:400])
    return 0


if __name__ == "__main__":
    sys.exit(main())
