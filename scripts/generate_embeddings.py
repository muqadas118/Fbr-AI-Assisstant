import argparse
import hashlib
import json
import os
import random
import shutil
import sys
from importlib.metadata import version
from pathlib import Path

import numpy as np
import torch
from huggingface_hub import scan_cache_dir
from sentence_transformers import SentenceTransformer


ROOT = Path(__file__).resolve().parents[1]
CHUNKS_FILE = ROOT / "data" / "profile" / "source_docs" / "chunks" / "chunks.json"
OUTPUT_DIR = ROOT / "data" / "profile" / "source_docs" / "embeddings"
STAGING_DIR = OUTPUT_DIR.parent / ".embeddings.staging"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
EXPECTED_CHUNKS = 58953
DIMENSION = 384
DEFAULT_BATCH_SIZE = 32
NORMALIZATION = "l2"
SIMILARITY_METRIC = "cosine_via_inner_product"
DTYPE = "float32"
SEED = 0
PROVENANCE_FIELDS = (
    "chunk_id",
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
)


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


def model_revision(model_name):
    revisions = []
    for repo in scan_cache_dir().repos:
        if repo.repo_id == model_name:
            revisions.extend(revision.commit_hash for revision in repo.revisions)
    if MODEL_REVISION not in revisions:
        raise RuntimeError(f"Pinned model revision is not available in the local cache: {MODEL_REVISION}")
    return MODEL_REVISION


def iter_json_array(path):
    decoder = json.JSONDecoder()
    with path.open("r", encoding="utf-8") as handle:
        buffer = ""
        started = False
        finished = False
        while True:
            chunk = handle.read(1024 * 1024)
            if chunk:
                buffer += chunk
            position = 0
            while True:
                while position < len(buffer) and buffer[position].isspace():
                    position += 1
                if not started:
                    if position >= len(buffer):
                        break
                    if buffer[position] != "[":
                        raise ValueError(f"Expected JSON array in {path}")
                    started = True
                    position += 1
                    continue
                while position < len(buffer) and (buffer[position].isspace() or buffer[position] == ","):
                    position += 1
                if position < len(buffer) and buffer[position] == "]":
                    finished = True
                    position += 1
                    break
                if position >= len(buffer):
                    break
                try:
                    value, end = decoder.raw_decode(buffer, position)
                except json.JSONDecodeError:
                    break
                yield value
                position = end
            buffer = buffer[position:]
            if finished:
                if buffer.strip():
                    raise ValueError(f"Unexpected content after JSON array in {path}")
                return
            if not chunk:
                raise ValueError(f"Incomplete JSON array in {path}")


def configuration(batch_size, revision):
    return {
        "schema_version": 1,
        "chunks_file": CHUNKS_FILE.relative_to(ROOT).as_posix(),
        "chunks_sha256": sha256_file(CHUNKS_FILE),
        "expected_chunks": EXPECTED_CHUNKS,
        "model": MODEL_NAME,
        "model_revision": revision,
        "embedding_dimension": DIMENSION,
        "normalization": NORMALIZATION,
        "similarity_metric": SIMILARITY_METRIC,
        "dtype": DTYPE,
        "batch_size": batch_size,
        "device": "cpu",
        "seed": SEED,
        "max_sequence_length": 256,
        "sentence_transformers_version": version("sentence-transformers"),
        "transformers_version": version("transformers"),
        "torch_version": version("torch"),
        "numpy_version": version("numpy"),
    }


def prepare_staging(config, restart):
    if restart and STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    state_path = STAGING_DIR / "state.json"
    matrix_path = STAGING_DIR / "embeddings.npy"
    metadata_path = STAGING_DIR / "metadata.jsonl"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        staged_config = state.get("configuration")
        if staged_config != config:
            differing_fields = sorted(
                key
                for key in set(staged_config or {}) | set(config)
                if not isinstance(staged_config, dict) or staged_config.get(key) != config.get(key)
            )
            raise RuntimeError(
                "Staging configuration does not match this run "
                f"(differing fields: {', '.join(differing_fields) or 'configuration'}); "
                "use --restart after reviewing it"
            )
        committed = state.get("committed_embeddings")
        if not isinstance(committed, int) or not 0 <= committed <= EXPECTED_CHUNKS:
            raise RuntimeError("Invalid staging committed embedding count")
        lines = metadata_path.read_bytes().splitlines() if metadata_path.exists() else []
        if len(lines) < committed:
            raise RuntimeError("Staging metadata is shorter than the committed state")
        if len(lines) != committed:
            metadata_path.write_bytes(b"".join(line + b"\n" for line in lines[:committed]))
        matrix = np.lib.format.open_memmap(matrix_path, mode="r+", dtype=DTYPE, shape=(EXPECTED_CHUNKS, DIMENSION))
        return state, matrix
    if any(STAGING_DIR.iterdir()):
        raise RuntimeError("Unrecognized staging files exist; use --restart after reviewing them")
    matrix = np.lib.format.open_memmap(matrix_path, mode="w+", dtype=DTYPE, shape=(EXPECTED_CHUNKS, DIMENSION))
    state = {"configuration": config, "committed_embeddings": 0, "complete": False}
    atomic_json(state_path, state)
    metadata_path.touch()
    return state, matrix


def configure_determinism():
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(max(1, min(8, os.cpu_count() or 1)))


def metadata_record(chunk, index, config):
    missing = [field for field in PROVENANCE_FIELDS if field not in chunk]
    if missing:
        raise ValueError(f"Chunk {index} is missing provenance fields: {missing}")
    record = {field: chunk[field] for field in PROVENANCE_FIELDS}
    record.update(
        {
            "embedding_index": index,
            "embedding_dimension": DIMENSION,
            "embedding_model": MODEL_NAME,
            "embedding_model_revision": config["model_revision"],
            "normalization": NORMALIZATION,
            "similarity_metric": SIMILARITY_METRIC,
            "embedding_generation": {
                "batch_size": config["batch_size"],
                "device": config["device"],
                "dtype": DTYPE,
                "seed": SEED,
                "max_sequence_length": config["max_sequence_length"],
            },
        }
    )
    return record


def process_batch(model, matrix, metadata_handle, batch, start, state, config):
    texts = []
    records = []
    for offset, chunk in enumerate(batch):
        index = start + offset
        if not isinstance(chunk, dict):
            raise ValueError(f"Chunk {index} is not an object")
        text = chunk.get("chunk_text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Chunk {index} has invalid chunk_text")
        texts.append(text)
        records.append(metadata_record(chunk, index, config))
    vectors = model.encode(
        texts,
        batch_size=config["batch_size"],
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    vectors = np.asarray(vectors, dtype=DTYPE)
    if vectors.shape != (len(batch), DIMENSION):
        raise RuntimeError(f"Unexpected embedding shape: {vectors.shape}")
    if not np.isfinite(vectors).all():
        raise RuntimeError(f"Non-finite embedding values in batch starting at {start}")
    end = start + len(batch)
    matrix[start:end] = vectors
    matrix.flush()
    for record in records:
        metadata_handle.write(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        )
    metadata_handle.flush()
    os.fsync(metadata_handle.fileno())
    state["committed_embeddings"] = end
    atomic_json(STAGING_DIR / "state.json", state)


def generate(batch_size, restart):
    if not CHUNKS_FILE.exists():
        raise FileNotFoundError(CHUNKS_FILE)
    revision = model_revision(MODEL_NAME)
    config = configuration(batch_size, revision)
    state, matrix = prepare_staging(config, restart)
    committed = state["committed_embeddings"]
    configure_determinism()
    model = SentenceTransformer(
        MODEL_NAME,
        revision=revision,
        device="cpu",
        local_files_only=True,
    )
    if model.get_sentence_embedding_dimension() != DIMENSION:
        raise RuntimeError("Configured embedding dimension does not match the loaded model")
    model.max_seq_length = config["max_sequence_length"]
    batch = []
    processed = 0
    with (STAGING_DIR / "metadata.jsonl").open("ab") as metadata_handle:
        for chunk in iter_json_array(CHUNKS_FILE):
            if processed < committed:
                processed += 1
                continue
            batch.append(chunk)
            processed += 1
            if len(batch) == batch_size:
                process_batch(model, matrix, metadata_handle, batch, processed - len(batch), state, config)
                print(f"Embedded {processed:,}/{EXPECTED_CHUNKS:,}", flush=True)
                batch = []
        if batch:
            process_batch(model, matrix, metadata_handle, batch, processed - len(batch), state, config)
            print(f"Embedded {processed:,}/{EXPECTED_CHUNKS:,}", flush=True)
    if processed != EXPECTED_CHUNKS:
        raise RuntimeError(f"Expected {EXPECTED_CHUNKS:,} chunks, found {processed:,}")
    state["complete"] = True
    atomic_json(STAGING_DIR / "state.json", state)
    manifest = dict(config)
    manifest.update(
        {
            "embedding_count": EXPECTED_CHUNKS,
            "failed_chunks": 0,
            "skipped_chunks": 0,
            "matrix_file": "embeddings.npy",
            "metadata_file": "metadata.jsonl",
            "matrix_sha256": sha256_file(STAGING_DIR / "embeddings.npy"),
            "metadata_sha256": sha256_file(STAGING_DIR / "metadata.jsonl"),
            "status": "complete_unvalidated",
        }
    )
    atomic_json(STAGING_DIR / "manifest.json", manifest)
    print(f"Staged embeddings: {STAGING_DIR}")


def promote():
    manifest_path = STAGING_DIR / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError("No completed staging manifest exists")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "validated":
        raise RuntimeError("Staging output has not passed the embedding validator")
    matrix_path = STAGING_DIR / manifest.get("matrix_file", "")
    metadata_path = STAGING_DIR / manifest.get("metadata_file", "")
    if matrix_path.parent != STAGING_DIR or metadata_path.parent != STAGING_DIR:
        raise RuntimeError("Staging manifest contains invalid artifact paths")
    if sha256_file(matrix_path) != manifest.get("matrix_sha256"):
        raise RuntimeError("Staging embedding matrix changed after validation")
    if sha256_file(metadata_path) != manifest.get("metadata_sha256"):
        raise RuntimeError("Staging metadata changed after validation")
    if OUTPUT_DIR.exists():
        raise RuntimeError(f"Canonical embedding directory already exists: {OUTPUT_DIR}")
    (STAGING_DIR / "state.json").unlink(missing_ok=True)
    os.replace(STAGING_DIR, OUTPUT_DIR)
    print(f"Promoted embeddings: {OUTPUT_DIR}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--promote", action="store_true")
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    try:
        if args.promote:
            promote()
        else:
            generate(args.batch_size, args.restart)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
