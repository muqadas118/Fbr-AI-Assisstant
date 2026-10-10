"""
Incrementally ingest the curated tax knowledge corpus (markdown + JSONL +
CSV) into the existing cleaned / chunks / embeddings / vectorstore
artifacts.

Root cause being fixed
----------------------
The curated knowledge corpus lives in `data/raw/01-markdown/`,
`data/raw/02-jsonl/` and `data/raw/03-csv/` but (apart from the customs
subset handled by `add_customs_corpus.py`) it was never placed in
`data/raw/04-source-docs/` — the canonical extraction input. The one-time
pipeline therefore never extracted, cleaned, chunked, embedded or indexed
it. Result: 0 curated Q/A vectors, so every curated question (penalties,
ITO sections, WHT rates, income-tax slabs, roman-urdu Q/A, ...) falls back
to PropertyValuation tables and the LLM rule-2 refusal.

Approach
--------
Same pattern as `add_customs_corpus.py`: a full pipeline re-run would
regenerate all ~86k embeddings (hours of CPU). This script appends ONLY
the new curated chunks:

   1. Back up every canonical artifact (one time,
      `data/profile/vectorstore/.backup_pre_curated_qa/`).
   2. Copy the curated .md/.jsonl/.csv sources into
      `data/raw/04-source-docs/tax-qa/` (markdown/, jsonl/, csv/).
   3. Extract them with the extract_source_docs extractors (CSV uses a
      sheets/rows payload identical to the xlsx extractor's shape).
   4. Normalize them with clean_extracted_documents.normalize_record.
   5. Chunk them with chunk_cleaned_documents.chunk_document.
   6. Embed ONLY the new chunks (pinned model, pinned revision).
   7. Extend the embedding matrix / metadata / manifest.
   8. Rebuild the FAISS index from the extended matrix.
   9. Extend the vectorstore metadata and manifest.
  10. Verify alignment end-to-end and run curated-retrieval smoke tests.

`tax-qa/` sorts after `customs/` and every root-level document name, so the
appended order matches what a full pipeline re-run would produce. Existing
vectors are preserved bit-for-bit.

Run once:
    python scripts/add_curated_qa_corpus.py
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
    safe_text,
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
RAW_CSV_DIR = ROOT / "data" / "raw" / "03-csv"
SOURCE_DIR = ROOT / "data" / "raw" / "04-source-docs"
CORPUS_SOURCE_DIR = SOURCE_DIR / "tax-qa"
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
BACKUP_DIR = VECTOR_DIR / ".backup_pre_curated_qa"

# Already ingested by scripts/add_customs_corpus.py into
# data/raw/04-source-docs/customs/ — never duplicate them here.
ALREADY_INGESTED = {
    "26-customs-basics.md",
    "27-register-for-customs.md",
    "30-customs-vehicles.md",
    "31-customs-travel-guide.md",
    "32-customs-tariff-dirbs-valuation.md",
    "50-customs-duty-overview.md",
    "customs-basics.jsonl",
    "customs-penalties-depth.jsonl",
    "customs-tariff-dirbs-valuation.jsonl",
    "customs-travel-guide.jsonl",
    "customs-vehicles.jsonl",
    "register-for-customs.jsonl",
    "sales-customs-expansion.jsonl",
}

CURATED_SMOKE_QUERIES = [
    "What is the penalty for late filing of income tax return?",
    "What is section 154 prohibition of expenditure?",
    "What is the withholding tax rate on dividends?",
    "What is the income tax rate for salaried individuals?",
    "Income tax ki due date kya hai?",
]


def extract_csv(path: Path) -> dict[str, Any]:
    """
    Extract a CSV knowledge file.

    The payload mirrors `extract_xlsx` (one "sheet" per CSV file, cells
    rendered as text), so `clean_extracted_documents.build_sections` and
    `chunk_cleaned_documents.chunk_document` handle it through exactly the
    same code path as the spreadsheets already in the index.
    """

    rows: list[list[str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for record in csv.reader(handle):
            if not any(str(cell).strip() for cell in record):
                continue
            rows.append([safe_text(cell) for cell in record])

    return {
        "format": "csv",
        "sheet_count": 1,
        "sheets": [
            {
                "sheet": path.stem,
                "rows": rows,
                "row_count": len(rows),
            }
        ],
    }


def corpus_sources() -> list[Path]:
    """Curated raw inputs that are not already in 04-source-docs."""

    sources: list[Path] = []

    for name in sorted(path.name for path in RAW_MARKDOWN_DIR.glob("*.md")):
        if name in ALREADY_INGESTED:
            continue
        sources.append(RAW_MARKDOWN_DIR / name)

    for name in sorted(path.name for path in RAW_JSONL_DIR.glob("*.jsonl")):
        if name in ALREADY_INGESTED:
            continue
        sources.append(RAW_JSONL_DIR / name)

    for name in sorted(path.name for path in RAW_CSV_DIR.glob("*.csv")):
        sources.append(RAW_CSV_DIR / name)

    if not sources:
        raise RuntimeError("No curated source files found in data/raw/01-03")
    return sources


def append_json_array(path: Path, new_records: list[dict], indent: int = 2, chunk_bytes: int = 8 * 1024 * 1024) -> None:
    """
    Append records to a JSON array file without loading it into memory.

    The canonical artifacts are 90-270 MB, so the customs-style
    read-everything-into-memory approach is not safe on a low-RAM host.
    The existing body is copied through in blocks (8 MB peak) and the new
    records are appended before the closing bracket. The exact array
    terminator found on disk ("\\n]\\n", "\\r\\n]\\r\\n", or a bare "]") is
    re-emitted unchanged.
    """

    for tail in (b"\r\n]\r\n", b"\n]\n", b"\r\n]", b"\n]", b"]"):
        size = path.stat().st_size
        with path.open("rb") as source:
            source.seek(0, os.SEEK_END)
            end = source.tell()
            source.seek(max(0, end - len(tail)))
            if source.read(len(tail)) == tail:
                break
    else:
        raise RuntimeError(f"{path.name} does not end with a JSON array terminator")

    if not new_records:
        return

    copy_length = max(0, size - len(tail))
    temporary = path.with_suffix(path.suffix + ".tmp")
    # The exact terminator found on disk is re-emitted, so a CRLF-tailed
    # master (cleaned_documents.json) keeps its original shape.
    terminator = tail
    if indent:
        first, separator = b",\n  ", b",\n  "
    else:
        first, separator = b",", b","
    with path.open("rb") as source, temporary.open("wb") as target:
        remaining = copy_length
        while remaining > 0:
            block = source.read(min(chunk_bytes, remaining))
            if not block:
                raise RuntimeError(f"Unexpected EOF while copying {path}")
            target.write(block)
            remaining -= len(block)
        for position, record in enumerate(new_records):
            payload = (
                json.dumps(record, ensure_ascii=False, indent=indent) if indent
                else json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            )
            target.write((first if position == 0 else separator) + payload.encode("utf-8"))
        target.write(terminator)
    os.replace(temporary, path)


def backup_artifacts() -> None:
    if BACKUP_DIR.exists() and any(BACKUP_DIR.iterdir()):
        print(f"[backup] already exists, skipping: {BACKUP_DIR}")
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
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
        # .bak suffix so the three canonical vectorstore artifacts are
        # unmistakably rollback copies; keep them until verification passes.
        destination = BACKUP_DIR / (target.name + ".bak")
        shutil.copy2(target, destination)
        print(f"[backup] {target.name}.bak ({destination.stat().st_size:,} bytes)")


def copy_curated_sources(sources: list[Path]) -> list[Path]:
    copied: list[tuple[Path, Path]] = []
    for origin in sources:
        if origin.parent == RAW_MARKDOWN_DIR:
            destination = CORPUS_SOURCE_DIR / "markdown" / origin.name
        elif origin.parent == RAW_JSONL_DIR:
            destination = CORPUS_SOURCE_DIR / "jsonl" / origin.name
        else:
            destination = CORPUS_SOURCE_DIR / "csv" / origin.name
        copied.append((origin, destination))

    destinations: list[Path] = []
    for origin, destination in sorted(copied, key=lambda item: item[1]):
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if sha256_file(destination) != sha256_file(origin):
                raise RuntimeError(
                    f"Existing curated source differs from raw original: {destination}"
                )
            print(f"[copy] unchanged: {destination.relative_to(SOURCE_DIR).as_posix()}")
        else:
            shutil.copy2(origin, destination)
            print(f"[copy] {destination.relative_to(SOURCE_DIR).as_posix()}")
        destinations.append(destination)
    return destinations


def extract_curated(source_paths: list[Path]) -> list[Path]:
    extracted_paths: list[Path] = []
    for source_path in source_paths:
        relative = source_path.relative_to(SOURCE_DIR)
        output_path = EXTRACTED_DIR / relative.with_suffix(".json")
        if source_path.suffix.lower() == ".csv":
            extracted_data, status = extract_csv(source_path), "extracted"
        else:
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
        entry_count = extracted_data.get("section_count") or extracted_data.get("entry_count") or extracted_data.get("sheet_count")
        print(f"[extract] {relative.as_posix()} (units={entry_count})")
        extracted_paths.append(output_path)
    return extracted_paths


def normalize_curated(extracted_paths: list[Path]) -> list[dict]:
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
    # Streamed (not json.loads): the master is ~212 MB and a full parse
    # exhausts RAM on this host.
    existing_paths = {
        str(item.get("source_path", "")) for item in iter_json_array(CLEANED_MASTER)
    }
    print(f"[clean] master currently contains {len(existing_paths)} documents")
    for record in records:
        if record["source_path"] in existing_paths:
            raise RuntimeError(
                f"Curated document already ingested: {record['source_path']} "
                f"(remove it or restore from backup before re-running)"
            )
    append_json_array(CLEANED_MASTER, records, indent=2)
    print(f"[clean] master now contains {len(existing_paths) + len(records)} documents")


def build_curated_chunks(records: list[dict]) -> list[dict]:
    chunks: list[dict] = []
    for record in sorted(records, key=lambda item: item["source_path"]):
        produced = chunk_document(record)
        print(f"[chunk] {record['source_path']} -> {len(produced)} chunks")
        chunks.extend(produced)
    return chunks


def append_chunks(new_chunks: list[dict]) -> None:
    append_json_array(CHUNKS_FILE, new_chunks, indent=2)
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
    print(f"[embed] encoding {len(texts):,} chunks (batch_size={batch_size})", flush=True)
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
    validation["curated_qa_corpus_added"] = {
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
    payload: list[dict] = []
    for offset, chunk in enumerate(new_chunks):
        record = metadata_record(chunk, old_count + offset, config)
        record["vector_id"] = old_count + offset
        payload.append(record)
    append_json_array(VECTOR_METADATA_FILE, payload, indent=0)
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
    validation["curated_qa_corpus_added"] = {
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

    metadata_rows = 0
    watched: dict[int, dict] = {}
    wanted = {0, total - new_chunk_count, total - 1}
    for index, record in enumerate(iter_json_array(VECTOR_METADATA_FILE)):
        metadata_rows += 1
        if index in wanted:
            watched[index] = record
    if metadata_rows != total:
        raise RuntimeError(f"vectorstore metadata has {metadata_rows} rows, expected {total}")
    for idx, row in watched.items():
        if row.get("vector_id") != idx or row.get("embedding_index") != idx:
            raise RuntimeError(f"Vector ordering mismatch at row {idx}")

    embedding_manifest = json.loads(EMBEDDING_MANIFEST_FILE.read_text(encoding="utf-8"))
    if embedding_manifest.get("embedding_count") != total:
        raise RuntimeError("Embedding manifest count mismatch")

    matrix = np.load(EMBEDDINGS_FILE, mmap_mode="r", allow_pickle=False)
    if matrix.shape != (total, DIMENSION):
        raise RuntimeError(f"Matrix shape is {matrix.shape}")
    norms = np.linalg.norm(matrix[total - new_chunk_count:], axis=1)
    if not np.allclose(norms, 1.0, atol=1e-5):
        raise RuntimeError("New curated vectors are not L2-normalized")

    print(f"[verify] alignment OK: {total:,} vectors / chunks / metadata rows")


def verify_curated_retrieval() -> list[dict]:
    from app.hybrid_retriever import FBRHybridRetriever

    def _is_curated_source(value: str) -> bool:
        return value.replace("\\", "/").startswith("tax-qa/")

    retriever = FBRHybridRetriever()
    results = []
    for position, query in enumerate(CURATED_SMOKE_QUERIES, start=1):
        hits = retriever.search(query, top_k=5)
        curated_hits = [
            hit
            for hit in hits
            if _is_curated_source(str(retriever.metadata[hit["index"]].get("source", "")))
        ]
        best = curated_hits[0] if curated_hits else None
        if best is None:
            raise RuntimeError(f"No curated-QA chunk retrieved for: {query}")
        if float(best.get("semantic_score", 0.0)) < 0.15:
            raise RuntimeError(
                f"Curated semantic score too low for {query!r}: {best.get('semantic_score')}"
            )
        source = str(retriever.metadata[best["index"]].get("source", ""))
        score = float(best.get("score", 0.0))
        semantic = float(best.get("semantic_score", 0.0))
        top_source = str(retriever.metadata[hits[0]["index"]].get("source", ""))
        print(
            f"[smoke] {query}\n"
            f"        best curated source: {source} (hybrid={score:.4f}, semantic={semantic:.4f})\n"
            f"        overall top hit   : {top_source} (hybrid={float(hits[0].get('score', 0.0)):.4f})"
        )
        results.append(
            {
                "name": f"curated_qa_query_{position}",
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
    print("CURATED QA CORPUS INGESTION (incremental)")
    print("=" * 72)

    if verify_only:
        embedding_manifest = json.loads(EMBEDDING_MANIFEST_FILE.read_text(encoding="utf-8"))
        total = int(embedding_manifest.get("embedding_count", 0))
        chunks_added = total - 86_398
        verify_alignment(total, chunks_added)
        smoke_results = verify_curated_retrieval()
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
        print("[verify-only] curated-QA retrieval verification PASSED")
        return

    embedding_manifest = json.loads(EMBEDDING_MANIFEST_FILE.read_text(encoding="utf-8"))
    batch_size = int(embedding_manifest.get("batch_size", 64))

    backup_artifacts()
    source_paths = copy_curated_sources(corpus_sources())
    extracted_paths = extract_curated(source_paths)
    records = normalize_curated(extracted_paths)
    append_cleaned_master(records)
    new_chunks = build_curated_chunks(records)
    if not new_chunks:
        raise RuntimeError("Curated ingestion produced no chunks")
    append_chunks(new_chunks)

    old_count = count_existing_vectors()
    print(f"[embed] existing vectors: {old_count:,}")
    if old_count != 86_398:
        raise RuntimeError(f"Unexpected existing vector count: {old_count:,} (expected 86,398)")
    total = old_count + len(new_chunks)

    matrix = embed_new_chunks(new_chunks, batch_size, old_count)
    append_embedding_metadata(new_chunks, batch_size, old_count)
    update_embedding_manifest(total, len(records), len(new_chunks))
    rebuild_faiss_index(matrix)
    del matrix
    append_vector_metadata(new_chunks, batch_size, old_count)
    update_vector_manifest(total, len(records), len(new_chunks))

    verify_alignment(total, len(new_chunks))

    if "--skip-smoke" in sys.argv:
        print("[smoke] skipped (--skip-smoke): run `python scripts/add_curated_qa_corpus.py --verify-only`")
    else:
        smoke_results = verify_curated_retrieval()
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
    print(f"Curated documents ingested : {len(records)}")
    print(f"Curated chunks added       : {len(new_chunks)}")
    print(f"Total vectors              : {total:,} (was {old_count:,})")
    print(f"Backup directory           : {BACKUP_DIR}")
    print()
    print("NOTE: EXPECTED_CHUNKS (scripts/generate_embeddings.py) and")
    print("      EXPECTED_VECTORS (scripts/build_vector_database.py) are stale")
    print(f"      since the customs ingest; they would now need to be {total:,}.")
    print("      Left untouched here (data-pipeline-only task, and both were")
    print("      already stale before this run).")


if __name__ == "__main__":
    main()
