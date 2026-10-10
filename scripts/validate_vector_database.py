import argparse
import json
import sys
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from build_vector_database import (
    CHUNKS_FILE,
    DIMENSION,
    EMBEDDING_MANIFEST_FILE,
    EMBEDDING_METADATA_FILE,
    EMBEDDINGS_FILE,
    EXPECTED_VECTORS,
    INDEX_TYPE,
    MANIFEST_FILE,
    MODEL_NAME,
    MODEL_REVISION,
    ROOT,
    SIMILARITY_METRIC,
    STAGING_DIR,
    VECTOR_DIR,
    atomic_json,
    sha256_file,
)
from generate_embeddings import configure_determinism, iter_json_array


CLEANED_FILE = ROOT / "data" / "profile" / "source_docs" / "cleaned" / "cleaned_documents.json"
RAW_SOURCE_DIR = ROOT / "data" / "raw" / "04-source-docs"
SAMPLE_ROWS = (0, 1, 100, 1000, 10000, 30000, 50000, EXPECTED_VECTORS - 1)
SMOKE_TESTS = (
    ("income_tax", "Section 177 audit by Commissioner under the Income Tax Ordinance 2001", ("incometax",)),
    ("sales_tax", "Sales Tax Act 1990 registration and filing of returns", ("salestax",)),
    ("federal_excise", "Federal Excise Act 2005 duties and offences", ("federalexcise",)),
    ("finance_act", "Finance Act 2026", ("financeact2026", "financeact")),
    ("property_valuation", "FBR valuation of immovable property rates", ("propertyvaluation",)),
    ("sop_manual", "FBR standard operating procedure SOP compliance", ("sop", "manual")),
    ("vehari", "Vehari immovable property valuation rates", ("vehari",)),
    ("customs", "Pakistan Customs duty on imported goods and the Customs Act 1969", ("customs",)),
)


def source_file(source_path):
    path = (RAW_SOURCE_DIR / Path(source_path)).resolve()
    if RAW_SOURCE_DIR.resolve() not in path.parents:
        raise RuntimeError(f"Source path escapes canonical source directory: {source_path}")
    return path


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_path(directory, manifest, field):
    name = manifest.get(field)
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise RuntimeError(f"Invalid manifest artifact path: {field}")
    path = (directory / name).resolve()
    if path.parent != directory.resolve():
        raise RuntimeError(f"Manifest artifact must remain directly inside vectorstore: {field}")
    return path


def validate_metadata(metadata_path):
    documents = load_json(CLEANED_FILE)
    document_map = {document["document_id"]: document for document in documents}
    embedding_records = iter_json_array(metadata_path)
    phase5_records = (
        json.loads(line)
        for line in EMBEDDING_METADATA_FILE.open("r", encoding="utf-8")
    )
    chunks = iter_json_array(CHUNKS_FILE)
    seen = set()
    source_hashes = {}
    count = 0
    table_rows = []
    for index, values in enumerate(zip(embedding_records, phase5_records, chunks)):
        vector_record, embedding_record, chunk = values
        count += 1
        if vector_record.get("vector_id") != index:
            raise RuntimeError(f"vector_id ordering mismatch at row {index}")
        if vector_record.get("embedding_index") != index:
            raise RuntimeError(f"embedding_index ordering mismatch at row {index}")
        chunk_id = vector_record.get("chunk_id")
        if chunk_id in seen:
            raise RuntimeError(f"Duplicate vector chunk_id: {chunk_id}")
        seen.add(chunk_id)
        if chunk_id != embedding_record.get("chunk_id") or chunk_id != chunk.get("chunk_id"):
            raise RuntimeError(f"Chunk alignment mismatch at row {index}")
        for field, value in embedding_record.items():
            if vector_record.get(field) != value:
                raise RuntimeError(f"Embedding metadata {field} mismatch at row {index}")
        for field in (
            "document_id",
            "source",
            "source_path",
            "source_sha256",
            "document_type",
            "title",
            "publication_date",
            "effective_date",
            "page_start",
            "page_end",
            "section_reference",
            "chunk_index",
        ):
            if vector_record.get(field) != chunk.get(field):
                raise RuntimeError(f"Chunk metadata {field} mismatch at row {index}")
        document = document_map.get(vector_record.get("document_id"))
        if document is None:
            raise RuntimeError(f"Unknown document_id at row {index}")
        for field in ("source", "source_path", "source_sha256"):
            if vector_record.get(field) != document.get(field):
                raise RuntimeError(f"Document provenance {field} mismatch at row {index}")
        path = source_file(vector_record["source_path"])
        if not path.is_file():
            raise RuntimeError(f"Missing canonical source at row {index}: {path}")
        expected_hash = vector_record["source_sha256"]
        if path not in source_hashes:
            source_hashes[path] = sha256_file(path)
        if source_hashes[path] != expected_hash:
            raise RuntimeError(f"Source SHA-256 mismatch at row {index}")
        if chunk.get("table_data") and len(table_rows) < 20:
            table_rows.append(index)
    try:
        next(embedding_records)
        raise RuntimeError("Vector metadata is shorter than Phase 5 metadata")
    except StopIteration:
        pass
    try:
        next(phase5_records)
        raise RuntimeError("Vector metadata is shorter than Phase 5 metadata")
    except StopIteration:
        pass
    try:
        next(chunks)
        raise RuntimeError("Vector metadata is shorter than chunks")
    except StopIteration:
        pass
    if count != EXPECTED_VECTORS or len(seen) != EXPECTED_VECTORS:
        raise RuntimeError(f"Expected {EXPECTED_VECTORS} unique metadata rows, found {count}")
    return table_rows


def validate_index(index_path, matrix):
    index = faiss.read_index(str(index_path))
    if type(index).__name__ != INDEX_TYPE:
        raise RuntimeError(f"Expected {INDEX_TYPE}, found {type(index).__name__}")
    if index.metric_type != faiss.METRIC_INNER_PRODUCT:
        raise RuntimeError(f"Expected METRIC_INNER_PRODUCT, found {index.metric_type}")
    if index.d != DIMENSION:
        raise RuntimeError(f"Expected dimension {DIMENSION}, found {index.d}")
    if index.ntotal != EXPECTED_VECTORS:
        raise RuntimeError(f"Expected {EXPECTED_VECTORS} vectors, found {index.ntotal}")
    for row in SAMPLE_ROWS:
        reconstructed = index.reconstruct(row)
        if not np.array_equal(reconstructed, np.asarray(matrix[row])):
            delta = float(np.max(np.abs(reconstructed - matrix[row])))
            raise RuntimeError(f"Vector reconstruction mismatch at row {row}; max delta {delta}")
    return index


def compact(value):
    return "".join(character for character in str(value).lower() if character.isalnum())


def smoke_tests(index, metadata, table_rows):
    configure_determinism()
    model = SentenceTransformer(
        MODEL_NAME,
        revision=MODEL_REVISION,
        device="cpu",
        local_files_only=True,
    )
    model.max_seq_length = 256
    results = []
    for name, query, expected_terms in SMOKE_TESTS:
        vector = model.encode(
            [query],
            batch_size=1,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        ).astype("float32")
        scores, rows = index.search(vector, 100)
        matches = []
        for score, row in zip(scores[0], rows[0]):
            if row < 0:
                continue
            record = metadata[row]
            identity = compact(" ".join(str(record.get(field) or "") for field in ("source", "source_path")))
            if any(compact(term) in identity for term in expected_terms):
                matches.append({"row": int(row), "chunk_id": record["chunk_id"], "score": float(score)})
        if not matches:
            raise RuntimeError(f"Retrieval smoke test failed: {name}")
        results.append({"name": name, "query": query, "matches": matches[:3]})
    if not table_rows:
        raise RuntimeError("No structured table rows were available for smoke testing")
    table_row = table_rows[0]
    reconstructed = index.reconstruct(table_row).reshape(1, -1)
    _, rows = index.search(reconstructed, 100)
    if table_row not in {int(row) for row in rows[0]}:
        raise RuntimeError("Structured table vector identity smoke test failed")
    results.append(
        {
            "name": "structured_table",
            "query": "stored structured-table vector identity",
            "matches": [{"row": table_row, "chunk_id": metadata[table_row]["chunk_id"], "score": 1.0}],
        }
    )
    return results


def validate(directory, mark_validated, run_smoke_tests):
    manifest_path = directory / MANIFEST_FILE
    manifest = load_json(manifest_path)
    index_path = artifact_path(directory, manifest, "index_file")
    metadata_path = artifact_path(directory, manifest, "metadata_file")
    phase5_manifest = load_json(EMBEDDING_MANIFEST_FILE)
    matrix_hash = sha256_file(EMBEDDINGS_FILE)
    metadata_hash = sha256_file(EMBEDDING_METADATA_FILE)
    chunks_hash = sha256_file(CHUNKS_FILE)
    expected = {
        "schema_version": 1,
        "index_type": INDEX_TYPE,
        "similarity_metric": SIMILARITY_METRIC,
        "faiss_metric": "METRIC_INNER_PRODUCT",
        "vector_count": EXPECTED_VECTORS,
        "dimension": DIMENSION,
        "dtype": "float32",
        "normalization": "l2",
        "embedding_model": MODEL_NAME,
        "embedding_model_revision": MODEL_REVISION,
        "embeddings_sha256": matrix_hash,
        "embedding_metadata_sha256": metadata_hash,
        "chunks_sha256": chunks_hash,
        "index_sha256": sha256_file(index_path),
        "metadata_sha256": sha256_file(metadata_path),
    }
    if phase5_manifest.get("matrix_sha256") != matrix_hash:
        raise RuntimeError("Phase 5 matrix SHA-256 does not match the independently recomputed hash")
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise RuntimeError(f"Vector manifest {field} mismatch")
    matrix = np.load(EMBEDDINGS_FILE, mmap_mode="r", allow_pickle=False)
    if matrix.shape != (EXPECTED_VECTORS, DIMENSION) or matrix.dtype != np.dtype("float32"):
        raise RuntimeError("Canonical embedding matrix contract mismatch")
    if not np.isfinite(matrix).all():
        raise RuntimeError("Canonical embedding matrix contains non-finite values")
    if not np.allclose(np.linalg.norm(matrix, axis=1), 1.0, atol=1e-5):
        raise RuntimeError("Canonical embedding matrix is not L2-normalized")
    table_rows = validate_metadata(metadata_path)
    index = validate_index(index_path, matrix)
    smoke_results = []
    if run_smoke_tests:
        metadata = load_json(metadata_path)
        smoke_results = smoke_tests(index, metadata, table_rows)
    if mark_validated:
        manifest["status"] = "validated"
        manifest["validation"] = {
            "result": "pass",
            "index_type": INDEX_TYPE,
            "metric": "METRIC_INNER_PRODUCT",
            "vector_count": EXPECTED_VECTORS,
            "dimension": DIMENSION,
            "unique_chunk_ids": EXPECTED_VECTORS,
            "sampled_reconstruction_rows": list(SAMPLE_ROWS),
            "sampled_reconstruction": "exact",
            "metadata_alignment": "pass",
            "source_provenance": "pass",
            "normalization": "pass",
            "retrieval_smoke_tests": smoke_results,
        }
        atomic_json(manifest_path, manifest)
    print("Vector database validation: PASS")
    print(f"Index: {INDEX_TYPE}, vectors: {index.ntotal:,}, dimension: {index.d}")
    if run_smoke_tests:
        print("Retrieval smoke tests: " + ", ".join(result["name"] for result in smoke_results))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=STAGING_DIR)
    parser.add_argument("--mark-validated", action="store_true")
    parser.add_argument("--smoke-tests", action="store_true")
    args = parser.parse_args()
    directory = args.directory.resolve()
    if directory not in {STAGING_DIR.resolve(), VECTOR_DIR.resolve()}:
        parser.error("Validation is restricted to the staging or canonical vectorstore")
    try:
        validate(directory, args.mark_validated, args.smoke_tests)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
