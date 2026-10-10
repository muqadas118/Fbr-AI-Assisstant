"""
Rebuild the Phase-4 embedding artifacts (embeddings.npy +
metadata.jsonl) from the canonical FAISS vectorstore.

Why this exists
---------------
`scripts/splice_vector_index.py` backfills chunks into the vectorstore and
writes only the three artifacts the running app consumes:
`data/profile/vectorstore/fbr_faiss.index`, `.../metadata.json` and
`data/profile/source_docs/chunks/chunks.json`.

The Phase-4 pair (`embeddings.npy` + `metadata.jsonl`), which a *full*
rebuild script (`scripts/generate_embeddings.py` /
`scripts/build_vector_database.py`) would need, is therefore left behind.
It was already stale before the curated-QA ingest (58,953 rows against an
86,398-vector index), so a later full rebuild would have silently produced
a truncated index.

This script restores the pair from the index itself:

   1. Reconstruct every vector from the FAISS index (IndexFlatIP stores the
      embedded values verbatim, so reused vectors stay bit-for-bit) and
      write embeddings.npy atomically.
   2. Stream the vectorstore metadata.json into metadata.jsonl, dropping
      only `vector_id` (that is the exact difference between the two
      schemas, see build_vector_database.write_vector_metadata).
   3. Re-verify that index / metadata.json / chunks.json / matrix /
      metadata.jsonl all agree on one row count, and refresh the embedding
      manifest.

Run once after any splice:
    python scripts/sync_embeddings_artifacts.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import faiss
import numpy as np

from build_vector_database import atomic_json, sha256_file
from generate_embeddings import DIMENSION, iter_json_array

CHUNKS_FILE = ROOT / "data" / "profile" / "source_docs" / "chunks" / "chunks.json"
EMBEDDING_DIR = ROOT / "data" / "profile" / "source_docs" / "embeddings"
EMBEDDINGS_FILE = EMBEDDING_DIR / "embeddings.npy"
EMBEDDING_METADATA_FILE = EMBEDDING_DIR / "metadata.jsonl"
EMBEDDING_MANIFEST_FILE = EMBEDDING_DIR / "manifest.json"
VECTOR_DIR = ROOT / "data" / "profile" / "vectorstore"
INDEX_FILE = VECTOR_DIR / "fbr_faiss.index"
VECTOR_METADATA_FILE = VECTOR_DIR / "metadata.json"


def write_matrix_from_index() -> int:
    index = faiss.read_index(str(INDEX_FILE))
    total = index.ntotal
    if index.d != DIMENSION:
        raise RuntimeError(f"Index dimension {index.d} != {DIMENSION}")

    matrix = np.empty((total, DIMENSION), dtype="float32")
    block = 4096
    for start in range(0, total, block):
        end = min(start + block, total)
        matrix[start:end] = index.reconstruct_n(start, end - start)
    if not np.isfinite(matrix).all():
        raise RuntimeError("Reconstructed matrix contains NaN or infinite values")
    if not np.allclose(np.linalg.norm(matrix, axis=1), 1.0, atol=1e-5):
        raise RuntimeError("Reconstructed matrix is not L2-normalized")

    temporary = EMBEDDINGS_FILE.with_suffix(".npy.tmp")
    with temporary.open("wb") as handle:
        np.save(handle, matrix)
    os.replace(temporary, EMBEDDINGS_FILE)
    print(f"[matrix] embeddings.npy rebuilt: {matrix.shape}")
    return total


def write_metadata_jsonl(total: int) -> None:
    temporary = EMBEDDING_METADATA_FILE.with_suffix(".jsonl.tmp")
    rows = 0
    dropped = 0
    with temporary.open("wb") as target:
        for index, record in enumerate(iter_json_array(VECTOR_METADATA_FILE)):
            if record.get("embedding_index") != index:
                raise RuntimeError(f"metadata.json order mismatch at row {index}")
            payload = {key: value for key, value in record.items() if key != "vector_id"}
            target.write(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                + b"\n"
            )
            rows += 1
            dropped += 1 if "vector_id" in record else 0
    if rows != total:
        raise RuntimeError(f"metadata.json has {rows} rows, expected {total}")
    os.replace(temporary, EMBEDDING_METADATA_FILE)
    print(f"[matrix] metadata.jsonl rebuilt: {rows:,} rows (vector_id dropped from {dropped:,})")


def main() -> None:
    total = write_matrix_from_index()
    write_metadata_jsonl(total)

    index = faiss.read_index(str(INDEX_FILE))
    if index.ntotal != total:
        raise RuntimeError("Index/matrix row count mismatch after rebuild")

    chunk_rows = sum(1 for _ in iter_json_array(CHUNKS_FILE))
    if chunk_rows != total:
        raise RuntimeError(f"chunks.json has {chunk_rows} rows, expected {total}")

    manifest = json.loads(EMBEDDING_MANIFEST_FILE.read_text(encoding="utf-8"))
    manifest["expected_chunks"] = total
    manifest["embedding_count"] = total
    manifest["chunks_sha256"] = sha256_file(CHUNKS_FILE)
    manifest["matrix_sha256"] = sha256_file(EMBEDDINGS_FILE)
    manifest["metadata_sha256"] = sha256_file(EMBEDDING_METADATA_FILE)
    validation = manifest.get("validation")
    if not isinstance(validation, dict):
        validation = {}
    validation["embedding_count"] = total
    validation["embeddings_resynced_from_vectorstore"] = {
        "vectors": total,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    manifest["validation"] = validation
    atomic_json(EMBEDDING_MANIFEST_FILE, manifest)
    print("[matrix] embedding manifest refreshed")

    print()
    print("EMBEDDING ARTIFACTS IN SYNC")
    print(f"  embeddings.npy      : {total:,} x {DIMENSION}")
    print(f"  metadata.jsonl      : {total:,} rows")
    print(f"  fbr_faiss.index     : {index.ntotal:,} vectors")
    print(f"  metadata.json       : {total:,} rows")
    print(f"  chunks.json         : {chunk_rows:,} chunks")


if __name__ == "__main__":
    main()
