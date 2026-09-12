import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rerank_retriever import FBRRerankRetriever


def main():

    print("=" * 60)
    print("FBR RERANKER TEST")
    print("=" * 60)

    retriever = FBRRerankRetriever()

    question = input("\nEnter your FBR question: ").strip()

    if not question:
        print("Question cannot be empty.")
        return

    print("\nRetrieving and reranking...")

    results = retriever.search(
        question,
        retrieve_k=20,
        top_k=5
    )

    print("\n")
    print("=" * 60)
    print("RERANKED RESULTS")
    print("=" * 60)

    for i, result in enumerate(results, 1):

        print(f"\nRESULT #{i}")
        print("-" * 60)

        print(
            f"Reranker Score : "
            f"{result.get('reranker_score', 0):.4f}"
        )

        print(
            f"Hybrid Score   : "
            f"{result.get('final_score', 0):.4f}"
        )

        print(
            f"Semantic Score : "
            f"{result.get('semantic_score', 0):.4f}"
        )

        print(
            f"BM25 Score     : "
            f"{result.get('bm25_score', 0):.4f}"
        )

        print(f"Source         : {result.get('source')}")
        print(f"Chunk          : {result.get('chunk_id')}")

        print("\nText:")
        print(result.get("text", "")[:2000])


if __name__ == "__main__":
    main()