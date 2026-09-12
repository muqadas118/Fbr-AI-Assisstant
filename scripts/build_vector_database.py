import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import faiss
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
EMBEDDING_DIR = ROOT / "data" / "profile" / "source_docs" / "embeddings"
EMBEDDINGS_FILE = EMBEDDING_DIR / "embeddings.npy"
EMBEDDING_METADATA_FILE = EMBEDDING_DIR / "metadata.jsonl"
EMBEDDING_MANIFEST_FILE = EMBEDDING_DIR / "manifest.json"
CHUNKS_FILE = ROOT / "data" / "profile" / "source_docs" / "chunks" / "chunks.json"
VECTOR_DIR = ROOT / "data" / "profile" / "vectorstore"
STAGING_DIR = ROOT / "data" / "profile" / ".vectorstore.staging"
INDEX_FILE = "fbr_faiss.index"
METADATA_FILE = "metadata.json"
MANIFEST_FILE = "vector_manifest.json"
EXPECTED_VECTORS = 58953
DIMENSION = 384
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
INDEX_TYPE = "IndexFlatIP"
SIMILARITY_METRIC = "cosine_via_inner_product"


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_manifest():
    manifest = json.loads(EMBEDDING_MANIFEST_FILE.read_text(encoding="utf-8"))
    matrix_hash = sha256_file(EMBEDDINGS_FILE)
    metadata_hash = sha256_file(EMBEDDING_METADATA_FILE)
    chunks_hash = sha256_file(CHUNKS_FILE)
    expected = {
        "status": "validated",
        "embedding_count": EXPECTED_VECTORS,
        "embedding_dimension": DIMENSION,
        "dtype": "float32",
        "normalization": "l2",
        "similarity_metric": SIMILARITY_METRIC,
        "model": MODEL_NAME,
        "model_revision": MODEL_REVISION,
        "matrix_sha256": matrix_hash,
        "metadata_sha256": metadata_hash,
        "chunks_sha256": chunks_hash,
    }
    mismatches = {
        field: (expected_value, manifest.get(field))
        for field, expected_value in expected.items()
        if manifest.get(field) != expected_value
    }
    if mismatches:
        details = "; ".join(
            f"{field}: expected {expected_value!r}, found {actual!r}"
            for field, (expected_value, actual) in mismatches.items()
        )
        raise RuntimeError(f"Phase 5 manifest validation failed: {details}")
    return manifest, matrix_hash, metadata_hash, chunks_hash


def validate_input_alignment(matrix):
    if matrix.shape != (EXPECTED_VECTORS, DIMENSION):
        raise RuntimeError(f"Unexpected embedding matrix shape: {matrix.shape}")
    if matrix.dtype != np.dtype("float32"):
        raise RuntimeError(f"Unexpected embedding dtype: {matrix.dtype}")
    if not np.isfinite(matrix).all():
        raise RuntimeError("Embedding matrix contains NaN or infinite values")
    if not np.allclose(np.linalg.norm(matrix, axis=1), 1.0, atol=1e-5):
        raise RuntimeError("Embedding matrix is not L2-normalized")
    count = 0
    with EMBEDDING_METADATA_FILE.open("r", encoding="utf-8") as handle:
        for count, line in enumerate(handle, start=1):
            record = json.loads(line)
            if record.get("embedding_index") != count - 1:
                raise RuntimeError(f"Embedding metadata order mismatch at row {count - 1}")
    if count != EXPECTED_VECTORS:
        raise RuntimeError(f"Expected {EXPECTED_VECTORS} metadata rows, found {count}")


def write_vector_metadata(destination):
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with EMBEDDING_METADATA_FILE.open("r", encoding="utf-8") as source, temporary.open(
        "wb"
    ) as target:
        target.write(b"[")
        for index, line in enumerate(source):
            record = json.loads(line)
            record["vector_id"] = index
            if index:
                target.write(b",")
            target.write(
                json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            )
        target.write(b"]")
    os.replace(temporary, destination)


def build(restart):
    if restart and STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    if STAGING_DIR.exists() and any(STAGING_DIR.iterdir()):
        raise RuntimeError("Staging directory is not empty; use --restart after reviewing it")
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    embedding_manifest, matrix_hash, metadata_hash, chunks_hash = load_manifest()
    matrix = np.load(EMBEDDINGS_FILE, mmap_mode="r", allow_pickle=False)
    validate_input_alignment(matrix)
    index = faiss.IndexFlatIP(DIMENSION)
    index.add(matrix)
    if index.ntotal != EXPECTED_VECTORS:
        raise RuntimeError(f"FAISS accepted {index.ntotal} vectors")
    index_path = STAGING_DIR / INDEX_FILE
    metadata_path = STAGING_DIR / METADATA_FILE
    faiss.write_index(index, str(index_path))
    write_vector_metadata(metadata_path)
    manifest = {
        "schema_version": 1,
        "status": "complete_unvalidated",
        "index_type": INDEX_TYPE,
        "similarity_metric": SIMILARITY_METRIC,
        "faiss_metric": "METRIC_INNER_PRODUCT",
        "vector_count": EXPECTED_VECTORS,
        "dimension": DIMENSION,
        "dtype": "float32",
        "normalization": "l2",
        "embedding_model": MODEL_NAME,
        "embedding_model_revision": MODEL_REVISION,
        "index_file": INDEX_FILE,
        "metadata_file": METADATA_FILE,
        "embeddings_file": EMBEDDINGS_FILE.relative_to(ROOT).as_posix(),
        "embedding_metadata_file": EMBEDDING_METADATA_FILE.relative_to(ROOT).as_posix(),
        "chunks_file": CHUNKS_FILE.relative_to(ROOT).as_posix(),
        "embeddings_sha256": matrix_hash,
        "embedding_metadata_sha256": metadata_hash,
        "chunks_sha256": chunks_hash,
        "index_sha256": sha256_file(index_path),
        "metadata_sha256": sha256_file(metadata_path),
        "faiss_version": faiss.__version__,
        "numpy_version": np.__version__,
        "python_version": sys.version.split()[0],
        "build_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "phase5_manifest_schema_version": embedding_manifest.get("schema_version"),
    }
    atomic_json(STAGING_DIR / MANIFEST_FILE, manifest)
    print(f"Staged {index.ntotal:,} vectors at {STAGING_DIR}")


def promote():
    manifest_path = STAGING_DIR / MANIFEST_FILE
    if not manifest_path.exists():
        raise RuntimeError("Staged vector manifest does not exist")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "validated":
        raise RuntimeError("Staged vector artifacts have not passed validation")
    for name, field in ((INDEX_FILE, "index_sha256"), (METADATA_FILE, "metadata_sha256")):
        path = STAGING_DIR / name
        if sha256_file(path) != manifest.get(field):
            raise RuntimeError(f"Staged artifact changed after validation: {name}")
    VECTOR_DIR.mkdir(parents=True, exist_ok=True)
    backup_dir = VECTOR_DIR / ".previous_vectorstore"
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    backup_dir.mkdir()
    existing_names = (INDEX_FILE, "metadata.json", METADATA_FILE, MANIFEST_FILE)
    moved = []
    try:
        for name in existing_names:
            existing = VECTOR_DIR / name
            if existing.exists():
                os.replace(existing, backup_dir / name)
                moved.append(name)
        for name in (INDEX_FILE, METADATA_FILE, MANIFEST_FILE):
            os.replace(STAGING_DIR / name, VECTOR_DIR / name)
        STAGING_DIR.rmdir()
    except Exception:
        for name in (INDEX_FILE, METADATA_FILE, MANIFEST_FILE):
            promoted = VECTOR_DIR / name
            if promoted.exists():
                promoted.unlink()
        for name in moved:
            previous = backup_dir / name
            if previous.exists():
                os.replace(previous, VECTOR_DIR / name)
        raise
    shutil.rmtree(backup_dir)
    print(f"Promoted vectorstore: {VECTOR_DIR}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--promote", action="store_true")
    args = parser.parse_args()
    if args.promote:
        promote()
    else:
        build(args.restart)


if __name__ == "__main__":
    main()
