import sys
from pathlib import Path

# ============================================================
# ADD PROJECT ROOT TO PYTHON PATH
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.hybrid_retriever import FBRHybridRetriever


def _run_smoke_suite(retriever) -> None:
    """
    Non-interactive smoke gate for the daily pipeline: three canonical
    retrieval probes that must each hit their expected source in top-5.
    """
    probes = [
        (
            "section 177 audit of taxpayer records income tax ordinance",
            ("IncomeTaxOrdinance2001",),
        ),
        (
            "sales tax registration threshold requirements",
            # The curated customs/sales expansion corpus is a legitimate
            # sales-tax-registration source alongside the Act itself.
            ("SalesTaxAct1990", "sales-customs-expansion"),
        ),
        (
            "federal excise duty on services",
            ("FederalExciseAct2005",),
        ),
    ]

    failures = 0

    for query, expected_markers in probes:
        print(f"\nPROBE: {query}")
        results = retriever.search(query, top_k=5)

        if not results:
            print("  FAIL: no results")
            failures += 1
            continue

        top_sources = [
            str(retriever.metadata[r["index"]].get("source", ""))
            for r in results
        ]

        hit = any(
            marker.lower() in s.lower().replace(" ", "")
            for s in top_sources
            for marker in expected_markers
        )

        for rank, s in enumerate(top_sources, start=1):
            print(f"  {rank}. {s[:80]}")

        if hit:
            print("  PASS")
        else:
            print(f"  FAIL: none of {expected_markers} in top-5")
            failures += 1

    if failures:
        print(
            f"\nHYBRID RETRIEVER SMOKE: FAIL "
            f"({failures} of {len(probes)} probes failed)"
        )
        raise SystemExit(1)

    print("\nHYBRID RETRIEVER SMOKE: PASS")


def main():

    print("=" * 60)
    print("FBR HYBRID RETRIEVER TEST")
    print("=" * 60)

    # ========================================================
    # LOAD RETRIEVER
    # ========================================================

    retriever = FBRHybridRetriever()

    # ========================================================
    # GET QUESTION
    # ========================================================

    # Non-interactive runs (Task Scheduler / CI close stdin) previously
    # crashed on input() with EOFError, so the daily pipeline's final
    # validation could never pass. Non-TTY stdin now runs a fixed smoke
    # suite with real assertions; interactive use keeps the prompt.
    try:
        interactive = sys.stdin.isatty()
    except (AttributeError, ValueError, OSError):
        interactive = False

    if not interactive:
        _run_smoke_suite(retriever)
        return

    # isatty() can still be True while the handle yields EOF (Windows
    # scheduler / service context, GUI-launched process). That used to kill
    # the daily updater's final validation stage with EOFError, so the hash
    # state was never advanced. Fall back to the smoke suite instead.
    try:
        query = input(
            "\nEnter your FBR question: "
        ).strip()
    except (EOFError, KeyboardInterrupt, OSError):
        print()
        print(
            "No interactive input available - "
            "running the smoke suite instead."
        )
        _run_smoke_suite(retriever)
        return

    if not query:
        print("No question entered.")
        return

    # ========================================================
    # SEARCH
    # ========================================================

    results = retriever.search(
        query,
        top_k=5
    )

    # ========================================================
    # DISPLAY RESULTS
    # ========================================================

    print("\n")
    print("=" * 60)
    print("HYBRID SEARCH RESULTS")
    print("=" * 60)

    if not results:
        print("\nNo results found.")
        return

    for rank, result in enumerate(
        results,
        start=1
    ):

        idx = result["index"]

        if idx < 0 or idx >= len(retriever.metadata):
            continue

        metadata = retriever.metadata[idx]

        source = str(
            metadata.get(
                "source",
                ""
            )
        )

        chunk = str(
            metadata.get(
                "chunk_id",
                metadata.get(
                    "id",
                    ""
                )
            )
        )

        text = str(
            metadata.get(
                "text",
                ""
            )
        )

        print(f"\nRESULT #{rank}")
        print("-" * 60)

        print(
            f"Final Score    : "
            f"{result.get('score', 0.0):.4f}"
        )

        print(
            f"Semantic Score : "
            f"{result.get('semantic_score', 0.0):.4f}"
        )

        print(
            f"BM25 Score     : "
            f"{result.get('bm25_score', 0.0):.4f}"
        )

        print(
            f"Source         : {source}"
        )

        print(
            f"Chunk          : {chunk}"
        )

        print("\nTEXT:")
        print(text[:2000])


if __name__ == "__main__":
    main()