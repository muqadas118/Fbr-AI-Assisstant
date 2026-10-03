"""
SPLICE VECTOR INDEX
====================

Equivalent to build_vector_index.py but reuses existing FAISS vectors for
every chunk whose chunk_id already exists in the current index.

Why this is safe:

- chunk_id is a content hash (sha256 over document_id, chunk index, text,
  page_start, heading, section_reference - see
  scripts/chunk_cleaned_documents.py make_chunk_id). Two chunks with the
  same chunk_id therefore carry the same text at the same document
  position, so their embeddings are interchangeable by construction.
- The retriever contract (app/hybrid_retriever.py) requires exact row
  alignment between chunks.json, metadata.json and the FAISS index, with
  vector_id == embedding_index == row index. This script rebuilds all
  three in canonical chunks.json order, so the contract holds.

Output layout, metadata schema and embedding constants are identical to
build_vector_index.py. Writes are atomic (tmp file + replace).

Run only when the old artifacts are known-good and built with the same
embedding model/revision; the model identity is verified before reuse.
"""

from pathlib import Path
import json
import time

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[1]

CHUNKS_FILE = (
    ROOT / "data" / "profile" / "source_docs" / "chunks" / "chunks.json"
)

VECTOR_DIR = ROOT / "data" / "profile" / "vectorstore"

INDEX_FILE = VECTOR_DIR / "fbr_faiss.index"
METADATA_FILE = VECTOR_DIR / "metadata.json"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
BATCH_SIZE = 64
MAX_SEQ_LENGTH = 256

EMBEDDING_GENERATION = {
    "batch_size": BATCH_SIZE,
    "device": "cpu",
    "dtype": "float32",
    "max_sequence_length": MAX_SEQ_LENGTH,
    "seed": 0,
}


def load_json_list(path: Path, label: str) -> list:
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return value
    raise ValueError(f"{label} must contain a JSON list: {path}")


def main() -> int:

    start_time = time.time()

    chunks = load_json_list(CHUNKS_FILE, "chunks.json")
    old_metadata = load_json_list(METADATA_FILE, "old metadata.json")

    if not chunks:
        raise ValueError("No chunks found")
    if not all(isinstance(row, dict) for row in old_metadata):
        raise ValueError("Old metadata rows must be JSON objects")

    old_index = faiss.read_index(str(INDEX_FILE))

    if old_index.ntotal != len(old_metadata):
        raise RuntimeError(
            f"Old index ({old_index.ntotal}) and metadata "
            f"({len(old_metadata)}) row counts do not match"
        )

    dimension = old_index.d

    print(f"New chunks        : {len(chunks):,}")
    print(f"Old metadata rows : {len(old_metadata):,}")
    print(f"Old FAISS vectors : {old_index.ntotal:,} (dim {dimension})")

    # ------------------------------------------------------------
    # 1. Position lookup by content-hash chunk_id
    # ------------------------------------------------------------

    old_position_by_chunk_id = {}

    for position, row in enumerate(old_metadata):
        chunk_id = row.get("chunk_id")
        if chunk_id is not None and chunk_id not in old_position_by_chunk_id:
            old_position_by_chunk_id[chunk_id] = position

    # ------------------------------------------------------------
    # 2. Verify the old vectors were produced by the same model
    # ------------------------------------------------------------

    models_used = {
        str(row.get("embedding_model"))
        for row in old_metadata
    }
    revisions_used = {
        str(row.get("embedding_model_revision"))
        for row in old_metadata
    }

    if models_used != {MODEL_NAME} or revisions_used != {MODEL_REVISION}:
        raise RuntimeError(
            f"Old vectors come from {models_used}/{revisions_used}, "
            f"expected {MODEL_NAME}/{MODEL_REVISION}. Full rebuild required."
        )

    # ------------------------------------------------------------
    # 3. Reconstruct the old vectors once
    # ------------------------------------------------------------

    print("Reconstructing old vectors...")

    old_vectors = np.vstack(
        [old_index.reconstruct(i) for i in range(old_index.ntotal)]
    ).astype("float32")

    # ------------------------------------------------------------
    # 4. Classify chunks: reuse vs embed-now
    # ------------------------------------------------------------

    new_row_positions = [
        i
        for i, chunk in enumerate(chunks)
        if chunk.get("chunk_id") not in old_position_by_chunk_id
    ]

    reuse_count = len(chunks) - len(new_row_positions)

    print(f"Reuse existing    : {reuse_count:,}")
    print(f"Embed now         : {len(new_row_positions):,}")

    new_vector_by_chunk_id = {}

    if new_row_positions:

        model = SentenceTransformer(
            MODEL_NAME,
            revision=MODEL_REVISION,
            local_files_only=True,
        )
        model.max_seq_length = MAX_SEQ_LENGTH

        texts = []

        for i in new_row_positions:
            chunk = chunks[i]
            text = chunk.get("chunk_text")
            if not isinstance(text, str):
                text = str(chunk.get("text", ""))
            texts.append(text)

        print("Embedding new chunks...")

        vectors = []
        encode_start = time.time()

        for start in range(0, len(texts), BATCH_SIZE):
            batch = texts[start : start + BATCH_SIZE]
            embeddings = model.encode(
                batch,
                batch_size=BATCH_SIZE,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            vectors.append(np.asarray(embeddings, dtype="float32"))

            done = min(start + BATCH_SIZE, len(texts))
            elapsed = time.time() - encode_start
            rate = done / elapsed if elapsed > 0 else 0
            remaining = len(texts) - done
            eta = remaining / rate if rate > 0 else 0
            print(
                f"\rProgress: {done:,}/{len(texts):,} | "
                f"Rate: {rate:.1f} chunks/s | ETA: {eta/60:.1f} min",
                end="",
                flush=True,
            )

        print()

        embedded = np.vstack(vectors).astype("float32")

        for row_in_batch, i in enumerate(new_row_positions):
            new_vector_by_chunk_id[chunks[i].get("chunk_id")] = (
                embedded[row_in_batch]
            )

    # ------------------------------------------------------------
    # 5. Assemble canonical-order vectors + full-contract metadata
    # ------------------------------------------------------------

    print("Assembling index rows...")

    out_vectors = np.empty((len(chunks), dimension), dtype="float32")

    for i, chunk in enumerate(chunks):
        chunk_id = chunk.get("chunk_id")
        old_pos = old_position_by_chunk_id.get(chunk_id)
        if old_pos is not None:
            out_vectors[i] = old_vectors[old_pos]
        else:
            out_vectors[i] = new_vector_by_chunk_id[chunk_id]

    out_vectors = np.ascontiguousarray(out_vectors, dtype="float32")

    metadata = []

    for i, chunk in enumerate(chunks):
        metadata.append(
            {
                "chunk_id": chunk.get("chunk_id", i),
                "chunk_index": chunk.get("chunk_index", i),
                "document_id": chunk.get("document_id"),
                "document_type": chunk.get("document_type"),
                "effective_date": chunk.get("effective_date"),
                "embedding_dimension": dimension,
                "embedding_generation": dict(EMBEDDING_GENERATION),
                "embedding_index": i,
                "embedding_model": MODEL_NAME,
                "embedding_model_revision": MODEL_REVISION,
                "normalization": "l2",
                "page_end": chunk.get("page_end"),
                "page_start": chunk.get("page_start"),
                "publication_date": chunk.get("publication_date"),
                "section_reference": chunk.get("section_reference"),
                "similarity_metric": "cosine_via_inner_product",
                "source": chunk.get("source"),
                "source_path": chunk.get("source_path"),
                "source_sha256": chunk.get("source_sha256"),
                "title": chunk.get("title"),
                "vector_id": i,
            }
        )

    # ------------------------------------------------------------
    # 6. Build the FAISS index and write atomically
    # ------------------------------------------------------------

    index = faiss.IndexFlatIP(dimension)
    index.add(out_vectors)

    print(f"FAISS vectors     : {index.ntotal:,}")

    tmp_index_file = INDEX_FILE.with_name(INDEX_FILE.name + ".tmp")
    tmp_metadata_file = METADATA_FILE.with_name(METADATA_FILE.name + ".tmp")

    print("Saving FAISS index...")

    faiss.write_index(index, str(tmp_index_file))

    print("Saving metadata...")

    with open(
        tmp_metadata_file,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            metadata,
            file,
            ensure_ascii=False,
            indent=2,
        )

    tmp_index_file.replace(INDEX_FILE)
    tmp_metadata_file.replace(METADATA_FILE)

    # ------------------------------------------------------------
    # 7. Post-write verification
    # ------------------------------------------------------------

    reloaded = faiss.read_index(str(INDEX_FILE))

    if reloaded.ntotal != len(chunks):
        raise RuntimeError("Reloaded index row count mismatch")

    first_norm = float(np.linalg.norm(reloaded.reconstruct(0)))

    elapsed = time.time() - start_time

    print()
    print("=" * 60)
    print("VECTOR INDEX SPLICE COMPLETE")
    print("=" * 60)
    print(f"Chunks            : {len(chunks):,}")
    print(f"Vectors           : {reloaded.ntotal:,}")
    print(f"Dimension         : {dimension}")
    print(f"Reused embeddings : {reuse_count:,}")
    print(f"Newly embedded    : {len(new_row_positions):,}")
    print(f"Row-0 vector norm : {first_norm:.4f}")
    print(f"Elapsed time      : {elapsed/60:.2f} minutes")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
