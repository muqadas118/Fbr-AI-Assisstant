import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.rag import FBRRAG


def main():

    print("=" * 60)
    print("FBR RAG TEST")
    print("=" * 60)

    rag = FBRRAG(top_k=5)

    question = input("\nEnter your FBR question: ").strip()

    if not question:
        print("Question cannot be empty.")
        return

    print("\nRetrieving FBR documents...")
    print("Generating answer...\n")

    result = rag.answer(question)

    print("=" * 60)
    print("ANSWER")
    print("=" * 60)

    print(result["answer"])

    print()
    print("=" * 60)
    print("SOURCES")
    print("=" * 60)

    for i, source in enumerate(result["sources"], start=1):

        print(
            f"{i}. {source['source']} "
            f"| Chunk: {source['chunk_id']} "
            f"| Score: {source['score']:.4f}"
        )

    print("=" * 60)


if __name__ == "__main__":
    main()