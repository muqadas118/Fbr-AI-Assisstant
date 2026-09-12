import sys
from pathlib import Path

# ============================================================
# ADD PROJECT ROOT TO PYTHON PATH
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.hybrid_retriever import FBRHybridRetriever


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

    query = input(
        "\nEnter your FBR question: "
    ).strip()

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