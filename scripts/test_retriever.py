"""
Non-interactive FBR retriever test.

Runs deterministic default queries so the test can be executed in CI or
unattended validation. An explicit query can still be supplied.

Usage:
    python scripts/test_retriever.py
    python scripts/test_retriever.py --query "Section 177 Income Tax Ordinance"
    python scripts/test_retriever.py --top-k 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.retriever import FBRRetriever

DEFAULT_QUERIES: tuple[str, ...] = (
    "Section 177 of Income Tax Ordinance 2001",
    "Sales Tax Act 1990 registration procedure",
    "Federal Excise Act 2005 duties",
)

PREVIEW_CHARS = 500


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministic non-interactive FBR retriever test."
    )
    parser.add_argument(
        "--query",
        action="append",
        default=None,
        help="Query to run. Repeatable. Defaults to built-in queries.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of results per query (default: 5).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    queries = tuple(args.query) if args.query else DEFAULT_QUERIES

    if args.top_k < 1:
        print("top-k must be >= 1")
        return 1

    print("=" * 60)
    print("FBR RETRIEVER TEST (NON-INTERACTIVE)")
    print("=" * 60)

    retriever = FBRRetriever()

    failures: list[str] = []

    for query in queries:
        print()
        print("=" * 60)
        print(f"QUERY: {query}")
        print("=" * 60)

        results = retriever.search(query, top_k=args.top_k)

        if not results:
            failures.append(f"no results for query: {query}")
            print("[FAIL] no results returned")
            continue

        for position, result in enumerate(results, 1):
            chunk_id = result.get("chunk_id") or ""
            source = result.get("source") or ""

            if not chunk_id:
                failures.append(f"missing chunk_id for query: {query}")
            if not source:
                failures.append(f"missing source for query: {query}")

            print()
            print(f"RESULT #{position}")
            print("-" * 60)
            print(f"Score : {result['score']:.4f}")
            print(f"Source: {source}")
            print(f"Chunk : {chunk_id}")

            text = result.get("text") or ""
            if text:
                print()
                print(text[:PREVIEW_CHARS])

    print()
    print("=" * 60)
    if failures:
        print("RETRIEVER TEST: FAIL")
        for failure in failures:
            print(f" - {failure}")
        print("=" * 60)
        return 1

    print(f"RETRIEVER TEST: PASS ({len(queries)} queries)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
