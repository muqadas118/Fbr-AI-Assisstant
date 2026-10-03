"""Re-verify the 16 previously-rejected QAs with the TASK 2 fixed filter."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

from app.rag_engine import FBRRAGEngine  # noqa: E402

REJECT_FILE = PROJECT_ROOT / "data" / "profile" / "auto_qa" / "auto_qa_rejected.json"


def norm(s: str) -> str:
    return s.replace("\\", "/").replace(".pdf", "").lower().strip()


def main() -> int:
    with open(REJECT_FILE, encoding="utf-8") as f:
        rejected = json.load(f)
    print("Previously rejected:", len(rejected))

    rag = FBRRAGEngine()
    now_pass = 0
    still_fail = []

    for qa in rejected:
        g = rag.ground(qa["q"], top_k=3)
        top3 = [str(s.get("source") or "") for s in (g.get("sources") or [])][:3]
        e = norm(qa["source"])
        t3 = [norm(s) for s in top3 if s]
        if any(e in s or s in e for s in t3):
            now_pass += 1
        else:
            still_fail.append((qa["q"][:60], qa["source"], t3))

    print(f"NOW PASS with fixed filter: {now_pass} / {len(rejected)}")
    print(f"Still fail (genuine retrieval miss): {len(still_fail)}")
    for q, src, t3 in still_fail:
        print("  -", src, "|", q)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
