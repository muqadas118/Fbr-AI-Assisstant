"""
Incrementally ingest the Customs knowledge corpus (markdown + JSONL)
into the existing cleaned / chunks / embeddings / vectorstore artifacts.

Root cause being fixed
----------------------
The Customs source material lives in `data/raw/01-markdown/` and
`data/raw/02-jsonl/` but was never placed in `data/raw/04-source-docs/`
(the canonical extraction input), so the one-time pipeline never
extracted, cleaned, chunked, embedded, or indexed it. The result:
0 customs chunks, 0 customs vectors, vector scores of 0.0 for every
customs query.

Approach
--------
A full pipeline re-run would regenerate all ~58k embeddings (hours of
CPU). This script appends ONLY the new customs chunks:

  1. Back up every canonical artifact (one time, `data/profile/.backup_pre_customs`).
  2. Copy the customs .md/.jsonl sources into `data/raw/04-source-docs/customs/`.
  3. Extract them with the (extended) extract_source_docs extractors.
  4. Normalize them with clean_extracted_documents.normalize_record.
  5. Chunk them with chunk_cleaned_documents.chunk_document.
  6. Embed ONLY the new chunks (pinned model, pinned revision).
  7. Extend the embedding matrix / metadata / manifest.
  8. Rebuild the FAISS index from the extended matrix.
  9. Extend the vectorstore metadata and manifest.
 10. Verify alignment end-to-end and run customs retrieval smoke tests.

Existing vectors are preserved bit-for-bit; the appended order matches
what a full pipeline re-run would produce (customs paths sort last).

Run once:
    python scripts/add_customs_corpus.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from build_vector_database import atomic_json, sha256_file
from clean_extracted_documents import normalize_record
from chunk_cleaned_documents import chunk_document
from extract_source_docs import (
    extract_document,
    write_json,
)
from generate_embeddings import (
    DIMENSION,
    DTYPE,
    MODEL_NAME,
    MODEL_REVISION,
    configure_determinism,
    iter_json_array,
    metadata_record,
)

RAW_MARKDOWN_DIR = ROOT / "data" / "raw" / "01-markdown"
RAW_JSONL_DIR = ROOT / "data" / "raw" / "02-jsonl"
SOURCE_DIR = ROOT / "data" / "raw" / "04-source-docs"
CUSTOMS_SOURCE_DIR = SOURCE_DIR / "customs"
EXTRACTED_DIR = ROOT / "data" / "profile" / "source_docs" / "extracted"
CLEANED_DIR = ROOT / "data" / "profile" / "source_docs" / "cleaned"
CLEANED_MASTER = CLEANED_DIR / "cleaned_documents.json"
CHUNKS_FILE = ROOT / "data" / "profile" / "source_docs" / "chunks" / "chunks.json"
EMBEDDING_DIR = ROOT / "data" / "profile" / "source_docs" / "embeddings"
EMBEDDINGS_FILE = EMBEDDING_DIR / "embeddings.npy"
EMBEDDING_METADATA_FILE = EMBEDDING_DIR / "metadata.jsonl"
EMBEDDING_MANIFEST_FILE = EMBEDDING_DIR / "manifest.json"
VECTOR_DIR = ROOT / "data" / "profile" / "vectorstore"
INDEX_FILE = VECTOR_DIR / "fbr_faiss.index"
VECTOR_METADATA_FILE = VECTOR_DIR / "metadata.json"
VECTOR_MANIFEST_FILE = VECTOR_DIR / "vector_manifest.json"
BACKUP_DIR = ROOT / "data" / "profile" / ".backup_pre_customs"

MARKDOWN_FILES = [
    "26-customs-basics.md",
    "27-register-for-customs.md",
    "30-customs-vehicles.md",
    "31-customs-travel-guide.md",
    "32-customs-tariff-dirbs-valuation.md",
    "50-customs-duty-overview.md",
]

JSONL_FILES = [
    "customs-basics.jsonl",
    "customs-penalties-depth.jsonl",
    "customs-tariff-dirbs-valuation.jsonl",
    "customs-travel-guide.jsonl",
    "customs-vehicles.jsonl",
    "register-for-customs.jsonl",
    "sales-customs-expansion.jsonl",
]

CUSTOMS_SMOKE_QUERIES = [
    "What is customs duty on imported goods?",
    "How do I register for customs in Pakistan?",
    "What is DIRBS?",
    "What are the penalties for customs violations?",
    "What is the Customs Act 1969?",
]


def backup_artifacts() -> None:
    if BACKUP_DIR.exists():
        print(f"[backup] already exists, skipping: {BACKUP_DIR}")
        return
    BACKUP_DIR.mkdir(parents=True)
    targets = [
        CLEANED_MASTER,
        CHUNKS_FILE,
        EMBEDDINGS_FILE,
        EMBEDDING_METADATA_FILE,
        EMBEDDING_MANIFEST_FILE,
        INDEX_FILE,
        VECTOR_METADATA_FILE,
        VECTOR_MANIFEST_FILE,
    ]
    for target in targets:
        if not target.exists():
            raise FileNotFoundError(f"Cannot back up missing artifact: {target}")
        shutil.copy2(target, BACKUP_DIR / target.name)
        print(f"[backup] {target.name} ({target.stat().st_size:,} bytes)")


def copy_customs_sources() -> list[Path]:
    CUSTOMS_SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    sources: list[tuple[Path, str]] = []
    for name in MARKDOWN_FILES:
        origin = RAW_MARKDOWN_DIR / name
        if not origin.is_file():
            raise FileNotFoundError(f"Customs markdown source missing: {origin}")
        sources.append((origin, name))
    for name in JSONL_FILES:
        origin = RAW_JSONL_DIR / name
        if not origin.is_file():
            raise FileNotFoundError(f"Customs JSONL source missing: {origin}")
        sources.append((origin, name))

    copied: list[Path] = []
    for origin, name in sorted(sources, key=lambda item: f"customs/{item[1]}"):
        destination = CUSTOMS_SOURCE_DIR / name
        if destination.exists():
            if sha256_file(destination) != sha256_file(origin):
                raise RuntimeError(
                    f"Existing customs source differs from raw original: {destination}"
                )
            print(f"[copy] unchanged: customs/{name}")
        else:
            shutil.copy2(origin, destination)
            print(f"[copy] customs/{name}")
        copied.append(destination)
    return copied


def extract_customs(source_paths: list[Path]) -> list[Path]:
    extracted_paths: list[Path] = []
    for source_path in source_paths:
        relative = source_path.relative_to(SOURCE_DIR)
        output_path = EXTRACTED_DIR / relative.with_suffix(".json")
        extracted_data, status = extract_document(source_path)
        if status != "extracted":
            raise RuntimeError(f"Extraction failed for {relative}: {status}")
        write_json(
            output_path,
            {
                "source": str(relative),
                "sha256": sha256_file(source_path),
                "data": extracted_data,
            },
        )
        entry_count = extracted_data.get("section_count") or extracted_data.get("entry_count")
        print(f"[extract] {relative.as_posix()} (units={entry_count})")
        extracted_paths.append(output_path)
    return extracted_paths


def normalize_customs(extracted_paths: list[Path]) -> list[dict]:
    records: list[dict] = []
    for extracted_path in extracted_paths:
        record = normalize_record(extracted_path)
        relative = extracted_path.relative_to(EXTRACTED_DIR)
        target = CLEANED_DIR / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            f"[clean] {record['source_path']} "
            f"(type={record['document_type']}, sections={len(record['sections'])}, "
            f"chars={record['text_chars']})"
        )
        records.append(record)
    return records


def append_cleaned_master(records: list[dict]) -> None:
    master = json.loads(CLEANED_MASTER.read_text(encoding="utf-8"))
    existing_paths = {str(item.get("source_path", "")) for item in master}
    for record in records:
        if record["source_path"] in existing_paths:
            raise RuntimeError(
                f"Customs document already ingested: {record['source_path']} "
                f"(remove it or restore from backup before re-running)"
            )
    master.extend(records)
    master.sort(key=lambda item: (item["source_path"], item["document_id"]))
    temporary = CLEANED_MASTER.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(master, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, CLEANED_MASTER)
    print(f"[clean] master now contains {len(master)} documents")


def build_customs_chunks(records: list[dict]) -> list[dict]:
    chunks: list[dict] = []
    for record in records:
        produced = chunk_document(record)
        print(f"[chunk] {record['source_path']} -> {len(produced)} chunks")
        chunks.extend(produced)
    return chunks


def append_chunks(new_chunks: list[dict]) -> None:
    data = CHUNKS_FILE.read_bytes()
    tail = b"\n]\n"
    if not data.endswith(tail):
        raise RuntimeError("chunks.json does not end with the expected array tail")
    body = data[: -len(tail)]
    parts = [
        json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8")
        for record in new_chunks
    ]
    updated = body + b",\n" + b",\n".join(parts) + tail
    temporary = CHUNKS_FILE.with_suffix(".json.tmp")
    temporary.write_bytes(updated)
    os.replace(temporary, CHUNKS_FILE)
    print("[chunk] chunks.json updated")


def count_existing_vectors() -> int:
    count = 0
    with EMBEDDING_METADATA_FILE.open("rb") as handle:
        for count, _ in enumerate(handle, start=1):
            pass
    return count


def embed_new_chunks(new_chunks: list[dict], batch_size: int, old_count: int) -> "np.ndarray":
    import numpy as np
    from sentence_transformers import SentenceTransformer

    configure_determinism()
    model = SentenceTransformer(
        MODEL_NAME,
        revision=MODEL_REVISION,
        device="cpu",
        local_files_only=True,
    )
    model.max_seq_length = 256
    if model.get_sentence_embedding_dimension() != DIMENSION:
        raise RuntimeError("Embedding model dimension mismatch")

    texts = [str(record["chunk_text"]) for record in new_chunks]
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    vectors = np.asarray(vectors, dtype=DTYPE)
    if vectors.shape != (len(new_chunks), DIMENSION):
        raise RuntimeError(f"Unexpected embedding shape: {vectors.shape}")
    if not np.isfinite(vectors).all():
        raise RuntimeError("New embeddings contain non-finite values")
    norms = np.linalg.norm(vectors, axis=1)
    if not np.allclose(norms, 1.0, atol=1e-5):
        raise RuntimeError("New embeddings are not L2-normalized")

    old_matrix = np.load(EMBEDDINGS_FILE, mmap_mode="r", allow_pickle=False)
    if old_matrix.shape != (old_count, DIMENSION):
        raise RuntimeError(
            f"Existing matrix shape {old_matrix.shape} does not match metadata count {old_count}"
        )
    total = old_count + len(new_chunks)
    matrix = np.empty((total, DIMENSION), dtype=DTYPE)
    matrix[:old_count] = old_matrix
    matrix[old_count:] = vectors
    del old_matrix
    del vectors
    import gc

    gc.collect()
    temporary = EMBEDDINGS_FILE.with_suffix(".npy.tmp")
    with temporary.open("wb") as handle:
        np.save(handle, matrix)
    os.replace(temporary, EMBEDDINGS_FILE)
    print(f"[embed] matrix extended to {total:,} vectors")
    return matrix


def append_embedding_metadata(new_chunks: list[dict], batch_size: int, old_count: int) -> None:
    config = {
        "model_revision": MODEL_REVISION,
        "batch_size": batch_size,
        "device": "cpu",
        "seed": 0,
        "max_sequence_length": 256,
    }
    with EMBEDDING_METADATA_FILE.open("ab") as handle:
        for offset, chunk in enumerate(new_chunks):
            record = metadata_record(chunk, old_count + offset, config)
            handle.write(
                json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                + b"\n"
            )
    print(f"[embed] metadata.jsonl extended by {len(new_chunks)} rows")


def update_embedding_manifest(total: int, documents: int, chunks: int) -> None:
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
    validation["customs_corpus_added"] = {
        "documents": documents,
        "chunks": chunks,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    manifest["validation"] = validation
    atomic_json(EMBEDDING_MANIFEST_FILE, manifest)
    print("[embed] manifest.json updated")


def rebuild_faiss_index(matrix) -> int:
    import faiss

    index = faiss.IndexFlatIP(DIMENSION)
    index.add(matrix)
    if index.ntotal != matrix.shape[0]:
        raise RuntimeError("FAISS did not accept every vector")
    temporary = INDEX_FILE.with_suffix(".index.tmp")
    faiss.write_index(index, str(temporary))
    os.replace(temporary, INDEX_FILE)
    print(f"[index] rebuilt with {index.ntotal:,} vectors")
    return index.ntotal


def append_vector_metadata(new_chunks: list[dict], batch_size: int, old_count: int) -> None:
    config = {
        "model_revision": MODEL_REVISION,
        "batch_size": batch_size,
        "device": "cpu",
        "seed": 0,
        "max_sequence_length": 256,
    }
    data = VECTOR_METADATA_FILE.read_bytes()
    if not data.endswith(b"]"):
        raise RuntimeError("vectorstore metadata.json does not end with ']'")
    body = data[:-1]
    parts = []
    for offset, chunk in enumerate(new_chunks):
        record = metadata_record(chunk, old_count + offset, config)
        record["vector_id"] = old_count + offset
        parts.append(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
    updated = body + b"," + b",".join(parts) + b"]"
    temporary = VECTOR_METADATA_FILE.with_suffix(".json.tmp")
    temporary.write_bytes(updated)
    os.replace(temporary, VECTOR_METADATA_FILE)
    print(f"[vector] metadata.json extended by {len(new_chunks)} rows")


def update_vector_manifest(total: int, documents: int, chunks: int) -> None:
    manifest = json.loads(VECTOR_MANIFEST_FILE.read_text(encoding="utf-8"))
    manifest["vector_count"] = total
    manifest["index_sha256"] = sha256_file(INDEX_FILE)
    manifest["metadata_sha256"] = sha256_file(VECTOR_METADATA_FILE)
    manifest["embeddings_sha256"] = sha256_file(EMBEDDINGS_FILE)
    manifest["embedding_metadata_sha256"] = sha256_file(EMBEDDING_METADATA_FILE)
    manifest["chunks_sha256"] = sha256_file(CHUNKS_FILE)
    manifest["build_timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    validation = manifest.get("validation")
    if not isinstance(validation, dict):
        validation = {}
    validation["vector_count"] = total
    validation["unique_chunk_ids"] = total
    validation["customs_corpus_added"] = {
        "documents": documents,
        "chunks": chunks,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    manifest["validation"] = validation
    atomic_json(VECTOR_MANIFEST_FILE, manifest)
    print("[vector] vector_manifest.json updated")


def verify_alignment(total: int, new_chunk_count: int) -> None:
    import faiss
    import numpy as np

    index = faiss.read_index(str(INDEX_FILE))
    if index.ntotal != total:
        raise RuntimeError(f"Index has {index.ntotal} vectors, expected {total}")

    chunk_count = sum(1 for _ in iter_json_array(CHUNKS_FILE))
    if chunk_count != total:
        raise RuntimeError(f"chunks.json has {chunk_count} chunks, expected {total}")

    metadata = json.loads(VECTOR_METADATA_FILE.read_text(encoding="utf-8"))
    if len(metadata) != total:
        raise RuntimeError(f"vectorstore metadata has {len(metadata)} rows, expected {total}")
    for idx in (0, total - new_chunk_count, total - 1):
        row = metadata[idx]
        if row.get("vector_id") != idx or row.get("embedding_index") != idx:
            raise RuntimeError(f"Vector ordering mismatch at row {idx}")

    embedding_manifest = json.loads(EMBEDDING_MANIFEST_FILE.read_text(encoding="utf-8"))
    if embedding_manifest.get("embedding_count") != total:
        raise RuntimeError("Embedding manifest count mismatch")

    matrix = np.load(EMBEDDINGS_FILE, mmap_mode="r", allow_pickle=False)
    if matrix.shape != (total, DIMENSION):
        raise RuntimeError(f"Matrix shape is {matrix.shape}")
    norms = np.linalg.norm(matrix[total - new_chunk_count :], axis=1)
    if not np.allclose(norms, 1.0, atol=1e-5):
        raise RuntimeError("New customs vectors are not L2-normalized")

    print(f"[verify] alignment OK: {total:,} vectors / chunks / metadata rows")


def verify_customs_retrieval() -> list[dict]:
    from app.hybrid_retriever import FBRHybridRetriever

    def _is_customs_source(value: str) -> bool:
        return value.replace("\\", "/").startswith("customs/")

    retriever = FBRHybridRetriever()
    results = []
    for position, query in enumerate(CUSTOMS_SMOKE_QUERIES, start=1):
        hits = retriever.search(query, top_k=5)
        customs_hits = [
            hit
            for hit in hits
            if _is_customs_source(str(retriever.metadata[hit["index"]].get("source", "")))
        ]
        best = customs_hits[0] if customs_hits else None
        if best is None:
            raise RuntimeError(f"No customs chunk retrieved for: {query}")
        if float(best.get("semantic_score", 0.0)) < 0.15:
            raise RuntimeError(
                f"Customs semantic score too low for {query!r}: {best.get('semantic_score')}"
            )
        source = str(retriever.metadata[best["index"]].get("source", ""))
        score = float(best.get("score", 0.0))
        semantic = float(best.get("semantic_score", 0.0))
        print(
            f"[smoke] {query}\n"
            f"        best customs source: {source} "
            f"(hybrid={score:.4f}, semantic={semantic:.4f})"
        )
        results.append(
            {
                "name": f"customs_query_{position}",
                "query": query,
                "matches": [
                    {
                        "row": int(best["index"]),
                        "chunk_id": retriever.metadata[best["index"]].get("chunk_id"),
                        "score": score,
                    }
                ],
            }
        )
    return results


def main() -> None:
    verify_only = "--verify-only" in sys.argv

    print("=" * 72)
    print("CUSTOMS CORPUS INGESTION (incremental)")
    print("=" * 72)

    if verify_only:
        embedding_manifest = json.loads(EMBEDDING_MANIFEST_FILE.read_text(encoding="utf-8"))
        total = int(embedding_manifest.get("embedding_count", 0))
        chunks_added = total - 58_822
        verify_alignment(total, chunks_added)
        smoke_results = verify_customs_retrieval()
        vector_manifest = json.loads(VECTOR_MANIFEST_FILE.read_text(encoding="utf-8"))
        validation = vector_manifest.get("validation")
        if isinstance(validation, dict):
            existing_tests = validation.get("retrieval_smoke_tests")
            if isinstance(existing_tests, list):
                known_names = {item.get("name") for item in existing_tests if isinstance(item, dict)}
                fresh = [item for item in smoke_results if item["name"] not in known_names]
                if fresh:
                    validation["retrieval_smoke_tests"] = existing_tests + fresh
                    atomic_json(VECTOR_MANIFEST_FILE, vector_manifest)
        print("[verify-only] customs retrieval verification PASSED")
        return

    embedding_manifest = json.loads(EMBEDDING_MANIFEST_FILE.read_text(encoding="utf-8"))
    batch_size = int(embedding_manifest.get("batch_size", 64))

    backup_artifacts()
    source_paths = copy_customs_sources()
    extracted_paths = extract_customs(source_paths)
    records = normalize_customs(extracted_paths)
    append_cleaned_master(records)
    new_chunks = build_customs_chunks(records)
    if not new_chunks:
        raise RuntimeError("Customs ingestion produced no chunks")
    append_chunks(new_chunks)

    old_count = count_existing_vectors()
    print(f"[embed] existing vectors: {old_count:,}")
    total = old_count + len(new_chunks)

    matrix = embed_new_chunks(new_chunks, batch_size, old_count)
    append_embedding_metadata(new_chunks, batch_size, old_count)
    update_embedding_manifest(total, len(records), len(new_chunks))
    rebuild_faiss_index(matrix)
    del matrix
    append_vector_metadata(new_chunks, batch_size, old_count)
    update_vector_manifest(total, len(records), len(new_chunks))

    verify_alignment(total, len(new_chunks))
    smoke_results = verify_customs_retrieval()

    vector_manifest = json.loads(VECTOR_MANIFEST_FILE.read_text(encoding="utf-8"))
    validation = vector_manifest.get("validation")
    if isinstance(validation, dict):
        existing_tests = validation.get("retrieval_smoke_tests")
        if isinstance(existing_tests, list):
            validation["retrieval_smoke_tests"] = existing_tests + smoke_results
            atomic_json(VECTOR_MANIFEST_FILE, vector_manifest)

    print()
    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(f"Customs documents ingested : {len(records)}")
    print(f"Customs chunks added       : {len(new_chunks)}")
    print(f"Total vectors              : {total:,} (was {old_count:,})")
    print(f"Backup directory           : {BACKUP_DIR}")
    print()
    print("NEXT (manual steps):")
    print("  1. Update EXPECTED_CHUNKS in scripts/generate_embeddings.py "
          f"to {total}")
    print("  2. Update EXPECTED_VECTORS in scripts/build_vector_database.py "
          f"to {total}")
    print("  3. Run the four validators, then scripts/final_regression.py")


if __name__ == "__main__":
    main()
