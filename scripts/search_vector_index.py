from pathlib import Path
import json
import sys

import faiss
from sentence_transformers import SentenceTransformer


ROOT = Path(__file__).resolve().parents[1]

VECTOR_DIR = ROOT / "data" / "profile" / "vectorstore"

INDEX_FILE = VECTOR_DIR / "fbr_faiss.index"
METADATA_FILE = VECTOR_DIR / "metadata.json"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def main():

    print("=" * 60)
    print("FBR VECTOR SEARCH TEST")
    print("=" * 60)

    if not INDEX_FILE.exists():
        print("ERROR: FAISS index not found")
        sys.exit(1)

    if not METADATA_FILE.exists():
        print("ERROR: Metadata not found")
        sys.exit(1)

    print("Loading FAISS index...")
    index = faiss.read_index(str(INDEX_FILE))

    print("Loading metadata...")
    with METADATA_FILE.open("r", encoding="utf-8") as f:
        metadata = json.load(f)

    print("Loading embedding model...")
    model = SentenceTransformer(MODEL_NAME)

    print()
    query = input("Enter your FBR question: ").strip()

    if not query:
        print("No question entered.")
        return

    query_embedding = model.encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    query_embedding = query_embedding.astype("float32")

    k = 5

    scores, indices = index.search(query_embedding, k)

    print()
    print("=" * 60)
    print("SEARCH RESULTS")
    print("=" * 60)

    for rank, (score, idx) in enumerate(
        zip(scores[0], indices[0]), 1
    ):

        if idx < 0 or idx >= len(metadata):
            continue

        item = metadata[idx]

        print()
        print(f"RESULT #{rank}")
        print("-" * 60)
        print(f"Score : {score:.4f}")
        print(f"Source: {item.get('source')}")
        print(f"Chunk : {item.get('chunk_id')}")
        print()
        print(item.get("text", "")[:1500])

    print()
    print("=" * 60)


if __name__ == "__main__":
    main()