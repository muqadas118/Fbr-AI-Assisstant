from pathlib import Path
import json
import sys
import time

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer


ROOT = Path(__file__).resolve().parents[1]

CHUNKS_FILE = (
    ROOT
    / "data"
    / "profile"
    / "source_docs"
    / "chunks"
    / "chunks.json"
)

VECTOR_DIR = (
    ROOT
    / "data"
    / "profile"
    / "vectorstore"
)

INDEX_FILE = VECTOR_DIR / "fbr_faiss.index"
METADATA_FILE = VECTOR_DIR / "metadata.json"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

BATCH_SIZE = 64


def main():
    print("=" * 60)
    print("FBR VECTOR INDEX BUILD")
    print("=" * 60)

    if not CHUNKS_FILE.exists():
        print(f"ERROR: Chunks file not found:")
        print(CHUNKS_FILE)
        sys.exit(1)

    VECTOR_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Chunks file : {CHUNKS_FILE}")
    print(f"Model       : {MODEL_NAME}")
    print(f"Batch size  : {BATCH_SIZE}")
    print()

    print("Loading chunks...")

    with CHUNKS_FILE.open("r", encoding="utf-8") as f:
        chunks = json.load(f)

    if not isinstance(chunks, list):
        raise ValueError("chunks.json must contain a JSON list")

    print(f"Chunks loaded : {len(chunks):,}")

    texts = []

    for chunk in chunks:
        if not isinstance(chunk, dict):
            texts.append("")
            continue

        text = chunk.get("text", "")

        if not isinstance(text, str):
            text = str(text)

        texts.append(text)

    if not texts:
        raise ValueError("No chunk text found")

    print()
    print("Loading embedding model...")
    print("First run may download the model.")

    model = SentenceTransformer(MODEL_NAME)

    dimension = model.get_sentence_embedding_dimension()

    print(f"Embedding dimension : {dimension}")

    print()
    print("Starting embedding generation...")
    print("=" * 60)

    all_embeddings = []

    total = len(texts)
    start_time = time.time()

    for start in range(0, total, BATCH_SIZE):
        end = min(start + BATCH_SIZE, total)

        batch = texts[start:end]

        embeddings = model.encode(
            batch,
            batch_size=BATCH_SIZE,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

        embeddings = np.asarray(embeddings, dtype="float32")

        all_embeddings.append(embeddings)

        processed = end
        elapsed = time.time() - start_time

        rate = processed / elapsed if elapsed > 0 else 0
        remaining = total - processed
        eta = remaining / rate if rate > 0 else 0

        percent = processed / total * 100

        print(
            f"\rProgress: {processed:,}/{total:,} "
            f"({percent:6.2f}%) | "
            f"Rate: {rate:.1f} chunks/s | "
            f"ETA: {eta/60:.1f} min",
            end="",
            flush=True,
        )

    print()
    print()

    embeddings = np.vstack(all_embeddings).astype("float32")

    print(f"Embeddings shape : {embeddings.shape}")

    # Since embeddings are normalized, inner product = cosine similarity.
    index = faiss.IndexFlatIP(dimension)

    print("Building FAISS index...")

    index.add(embeddings)

    print(f"FAISS vectors : {index.ntotal:,}")

    print()
    print("Saving FAISS index...")

    faiss.write_index(index, str(INDEX_FILE))

    metadata = []

    for i, chunk in enumerate(chunks):
        metadata.append(
            {
                "vector_id": i,
                "chunk_id": chunk.get("chunk_id", i),
                "document_id": chunk.get("document_id"),
                "source": chunk.get("source"),
                "text": chunk.get("text", ""),
            }
        )

    print("Saving metadata...")

    METADATA_FILE.write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    elapsed = time.time() - start_time

    print()
    print("=" * 60)
    print("VECTOR INDEX BUILD COMPLETE")
    print("=" * 60)
    print(f"Documents/chunks : {len(chunks):,}")
    print(f"Vectors           : {index.ntotal:,}")
    print(f"Dimension         : {dimension}")
    print(f"Elapsed time      : {elapsed/60:.2f} minutes")
    print(f"FAISS index       : {INDEX_FILE}")
    print(f"Metadata          : {METADATA_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()