"""List current Groq models to find a free-tier one that actually exists."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from openai import OpenAI  # noqa: E402

from app.llm import GROQ_API_KEY, GROQ_BASE_URL  # noqa: E402


def main() -> int:
    if not GROQ_API_KEY:
        print("GROQ_API_KEY not set")
        return 1
    client = OpenAI(base_url=GROQ_BASE_URL, api_key=GROQ_API_KEY, timeout=30.0)
    try:
        models = client.models.list()
    except Exception as e:  # noqa: BLE001
        print(f"List error: {type(e).__name__}: {e}")
        return 2
    rows = []
    for m in models.data:
        rows.append(m.id)
    print(f"Total models: {len(rows)}")
    for r in rows:
        print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
