import argparse
import json
import sys
from pathlib import Path

import numpy as np

from generate_embeddings import (
    CHUNKS_FILE,
    DIMENSION,
    DTYPE,
    EXPECTED_CHUNKS,
    MODEL_NAME,
    MODEL_REVISION,
    NORMALIZATION,
    OUTPUT_DIR,
    PROVENANCE_FIELDS,
    ROOT,
    SIMILARITY_METRIC,
    STAGING_DIR,
    atomic_json,
    iter_json_array,
    sha256_file,
)


CLEANED_FILE = ROOT / "data" / "profile" / "source_docs" / "cleaned" / "cleaned_documents.json"
REPRESENTATIVES = {
    "income_tax": ("income tax",),
    "sales_tax": ("sales tax",),
    "federal_excise": ("federal excise",),
    "finance_act": ("finance act",),
    "property_valuation": ("propertyvaluation", "property valuation"),
    "sop_manual": ("sop", "manual"),
    "vehari": ("vehari",),
}


def load_manifest(directory):
    path = directory / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8")), path


def cleaned_documents():
    with CLEANED_FILE.open("r", encoding="utf-8") as handle:
        documents = json.load(handle)
    if not isinstance(documents, list):
        raise ValueError("cleaned_documents.json must contain a list")
    return documents


def metadata_lines(path):
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if not line.strip():
                raise ValueError(f"Empty metadata line at index {index}")
            yield json.loads(line)


def representative_categories(chunk):
    searchable = " ".join(
        str(chunk.get(field) or "")
        for field in ("source", "source_path", "document_type", "title", "heading")
    ).lower()
    compact = "".join(character for character in searchable if character.isalnum())
    return {name for name, terms in REPRESENTATIVES.items() if any(term.replace(" ", "") in compact for term in terms)}


def validate(directory, mark_validated):
    errors = []
    manifest, manifest_path = load_manifest(directory)
    matrix_name = manifest.get("matrix_file", "embeddings.npy")
    metadata_name = manifest.get("metadata_file", "metadata.jsonl")
    if Path(matrix_name).is_absolute() or Path(metadata_name).is_absolute():
        raise RuntimeError("Manifest artifact paths must be relative")
    matrix_path = (directory / matrix_name).resolve()
    metadata_path = (directory / metadata_name).resolve()
    if matrix_path.parent != directory.resolve() or metadata_path.parent != directory.resolve():
        raise RuntimeError("Manifest artifact paths must remain directly inside the embedding directory")
    expected_manifest = {
        "chunks_file": CHUNKS_FILE.relative_to(ROOT).as_posix(),
        "chunks_sha256": sha256_file(CHUNKS_FILE),
        "expected_chunks": EXPECTED_CHUNKS,
        "embedding_count": EXPECTED_CHUNKS,
        "failed_chunks": 0,
        "skipped_chunks": 0,
        "model": MODEL_NAME,
        "model_revision": MODEL_REVISION,
        "embedding_dimension": DIMENSION,
        "normalization": NORMALIZATION,
        "similarity_metric": SIMILARITY_METRIC,
        "dtype": DTYPE,
        "device": "cpu",
    }
    for field, expected in expected_manifest.items():
        if manifest.get(field) != expected:
            errors.append(f"Manifest {field!r}: expected {expected!r}, found {manifest.get(field)!r}")
    for path, field in ((matrix_path, "matrix_sha256"), (metadata_path, "metadata_sha256")):
        if not path.exists():
            errors.append(f"Missing artifact: {path}")
        elif sha256_file(path) != manifest.get(field):
            errors.append(f"Artifact hash mismatch: {path}")
    if errors:
        raise RuntimeError("\n".join(errors))
    matrix = np.load(matrix_path, mmap_mode="r", allow_pickle=False)
    if matrix.shape != (EXPECTED_CHUNKS, DIMENSION):
        errors.append(f"Matrix shape is {matrix.shape}")
    if matrix.dtype != np.dtype(DTYPE):
        errors.append(f"Matrix dtype is {matrix.dtype}")
    if not np.isfinite(matrix).all():
        errors.append("Matrix contains NaN or infinite values")
    norms = np.linalg.norm(matrix, axis=1)
    if not np.allclose(norms, 1.0, atol=1e-5):
        errors.append("Matrix contains embeddings that are not L2-normalized")
    documents = cleaned_documents()
    document_map = {document["document_id"]: document for document in documents}
    manual_review_ids = {
        document["document_id"]
        for document in documents
        if document.get("status") == "manual_review_required"
    }
    seen_ids = set()
    metadata_count = 0
    representative_hits = set()
    table_hit = False
    chunk_iterator = iter_json_array(CHUNKS_FILE)
    metadata_iterator = metadata_lines(metadata_path)
    while True:
        try:
            chunk = next(chunk_iterator)
        except StopIteration:
            chunk = None
        try:
            record = next(metadata_iterator)
        except StopIteration:
            record = None
        if chunk is None and record is None:
            break
        if chunk is None or record is None:
            errors.append("Chunk and metadata counts differ")
            break
        index = metadata_count
        metadata_count += 1
        chunk_id = chunk.get("chunk_id")
        if chunk_id in seen_ids:
            errors.append(f"Duplicate embedding chunk_id: {chunk_id}")
        seen_ids.add(chunk_id)
        if chunk.get("document_id") in manual_review_ids:
            errors.append(f"Manual-review document has an embedding: {chunk_id}")
        document = document_map.get(chunk.get("document_id"))
        if document is None:
            errors.append(f"Orphan embedding document_id at index {index}")
        else:
            for field in ("source", "source_path", "source_sha256"):
                if chunk.get(field) != document.get(field):
                    errors.append(f"Canonical document {field} mismatch at index {index}")
        for field in PROVENANCE_FIELDS:
            if record.get(field) != chunk.get(field):
                errors.append(f"Metadata {field} mismatch at index {index}")
                break
        expected_record = {
            "embedding_index": index,
            "embedding_dimension": DIMENSION,
            "embedding_model": MODEL_NAME,
            "embedding_model_revision": manifest.get("model_revision"),
            "normalization": NORMALIZATION,
            "similarity_metric": SIMILARITY_METRIC,
        }
        for field, expected in expected_record.items():
            if record.get(field) != expected:
                errors.append(f"Metadata {field} mismatch at index {index}")
        generation = record.get("embedding_generation")
        expected_generation = {
            "batch_size": manifest.get("batch_size"),
            "device": "cpu",
            "dtype": DTYPE,
            "seed": manifest.get("seed"),
            "max_sequence_length": manifest.get("max_sequence_length"),
        }
        if generation != expected_generation:
            errors.append(f"Embedding generation metadata mismatch at index {index}")
        representative_hits.update(representative_categories(chunk))
        if chunk.get("table_data"):
            table_hit = True
        if len(errors) >= 100:
            break
    if metadata_count != EXPECTED_CHUNKS:
        errors.append(f"Expected {EXPECTED_CHUNKS} metadata records, found {metadata_count}")
    missing_categories = sorted(set(REPRESENTATIVES) - representative_hits)
    if missing_categories:
        errors.append(f"Missing representative categories: {missing_categories}")
    if not table_hit:
        errors.append("No structured table representative found")
    if errors:
        raise RuntimeError("\n".join(errors[:100]))
    if mark_validated:
        manifest["status"] = "validated"
        manifest["validation"] = {
            "result": "pass",
            "embedding_count": metadata_count,
            "duplicate_embeddings": 0,
            "missing_embeddings": 0,
            "orphan_embeddings": 0,
            "nan_values": 0,
            "infinite_values": 0,
            "manual_review_embeddings": 0,
            "representative_categories": sorted(representative_hits),
            "structured_table_representative": True,
        }
        atomic_json(manifest_path, manifest)
    print("Embedding validation: PASS")
    print(f"Embeddings: {metadata_count:,}")
    print(f"Dimension: {DIMENSION}")
    print(f"Representatives: {', '.join(sorted(representative_hits))}, structured_table")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=STAGING_DIR)
    parser.add_argument("--mark-validated", action="store_true")
    args = parser.parse_args()
    directory = args.directory.resolve()
    allowed = {STAGING_DIR.resolve(), OUTPUT_DIR.resolve()}
    if directory not in allowed:
        parser.error("Validation is restricted to the canonical or staging embedding directory")
    try:
        validate(directory, args.mark_validated)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
