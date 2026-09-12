"""
Document tools.

- document_parser:    reuses the EXISTING extraction pipeline
                      (scripts/extract_source_docs.py) for the
                      project's actual PDF/DOCX/XLS/XLSX/MD/JSONL
                      formats. Corrupted/unsupported files fail
                      safely.
- duplicate_detection: reuses SHA-256 hashing (the same function
                      the daily update layer uses for change
                      detection). Exact duplicates = identical
                      content hash; merely-similar documents are
                      the similarity engine's job.
- similarity_engine:  reuses the EXISTING SentenceTransformer
                      embedding model (the same one behind the
                      FAISS index). No second embedding system.
- anomaly_detection:  honest integrity checks over the existing
                      vector metadata. This is NOT fraud
                      detection.

Project scripts are reused via importlib (they are standalone
scripts, not a package) — no logic is duplicated.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from app.tools.base import BaseTool, ToolError
from app.tools.search_tools import shared_hybrid_retriever

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_MAX_TEXTS = 10
_MAX_TEXT_CHARS = 2000
_MAX_FILES = 50
_MAX_PREVIEW_CHARS = 600
_MAX_ANOMALIES = 200

_script_modules: dict[str, Any] = {}


def _load_script_module(script_name: str):
    """
    Load a project script as a module (cached). Scripts are
    reused, never copied.
    """

    if script_name in _script_modules:
        return _script_modules[script_name]

    script_path = PROJECT_ROOT / "scripts" / script_name

    if not script_path.exists():
        raise ToolError(
            f"Required project script is not available: {script_name}"
        )

    spec = importlib.util.spec_from_file_location(
        f"_tools_reuse_{script_name.replace('.', '_')}",
        script_path,
    )

    if spec is None or spec.loader is None:
        raise ToolError("Required project script could not be loaded.")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    _script_modules[script_name] = module
    return module


def _validated_project_file(raw_path: str) -> Path:
    """
    Validate that a user-supplied path is an existing file INSIDE
    the project root. Blocks path traversal and arbitrary
    filesystem access.
    """

    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ToolError("'path' must be a non-empty string.")

    candidate = Path(raw_path.strip())

    resolved = (
        candidate
        if candidate.is_absolute()
        else (PROJECT_ROOT / candidate)
    ).resolve()

    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError:
        raise ToolError("Path must be inside the project directory.")

    if not resolved.is_file():
        raise ToolError("File does not exist.")

    return resolved


# ============================================================
# DOCUMENT PARSER
# ============================================================

class DocumentParserTool(BaseTool):
    name = "document_parser"
    description = (
        "Parse a project document (PDF, DOCX, XLS, XLSX, MD, "
        "JSONL) by reusing the existing extraction pipeline. "
        "Legacy .doc files are reported as requiring manual "
        "review (no parser dependency). Input: {path: str} "
        "(project-relative or absolute path inside the project). "
        "Returns format, structure stats, SHA-256 and a text "
        "preview. Corrupted/unsupported files fail safely."
    )

    def validate_input(self, payload: dict) -> dict:
        path = _validated_project_file(payload.get("path", ""))
        return {"path": path}

    def execute(self, payload: dict) -> Any:
        extract_module = _load_script_module("extract_source_docs.py")

        path: Path = payload["path"]
        extension = path.suffix.lower()

        if extension not in extract_module.SUPPORTED_EXTENSIONS:
            raise ToolError(
                f"Unsupported document extension: '{extension}'. "
                "Supported: "
                f"{', '.join(sorted(extract_module.SUPPORTED_EXTENSIONS))}."
            )

        extraction, status = extract_module.extract_document(path)

        sha256 = extract_module.sha256_file(path)

        preview = ""

        if extraction.get("format") == "pdf":
            pages = extraction.get("pages_data", [])
            preview = " ".join(
                str(page.get("text", "")) for page in pages[:3]
            )
        elif extraction.get("format") in ("docx", "markdown"):
            preview = " ".join(
                str(item)
                for item in (
                    extraction.get("paragraphs")
                    or extraction.get("sections")
                    or []
                )[:5]
            )
        elif extraction.get("format") in ("xlsx", "xls"):
            preview = " ".join(
                str(cell)
                for row in extraction.get("rows_data", [])[:3]
                for cell in (row if isinstance(row, list) else [row])
            )
        elif extraction.get("format") == "jsonl":
            preview = " ".join(
                str(item.get("text", ""))
                for item in extraction.get("records", [])[:3]
                if isinstance(item, dict)
            )

        preview = " ".join(preview.split())[:_MAX_PREVIEW_CHARS]

        summary = {
            key: extraction[key]
            for key in (
                "format",
                "pages",
                "paragraphs",
                "tables",
                "rows",
                "records",
                "text_characters",
                "message",
            )
            if key in extraction
        }

        return {
            "path": str(path.relative_to(PROJECT_ROOT)),
            "status": status,
            "sha256": sha256,
            "summary": summary,
            "preview": preview,
        }


# ============================================================
# DUPLICATE DETECTION
# ============================================================

class DuplicateDetectionTool(BaseTool):
    name = "duplicate_detection"
    description = (
        "Detect EXACT duplicate documents by content using the "
        "same SHA-256 hashing the daily update layer uses for "
        "change detection. Input: {files: [str]} (paths inside "
        "the project). Documents that are merely similar (not "
        "byte-identical) are reported by similarity_engine "
        "instead. Returns duplicate groups by hash."
    )

    def validate_input(self, payload: dict) -> dict:
        files = payload.get("files")

        if not isinstance(files, list) or not files:
            raise ToolError("'files' must be a non-empty list of paths.")

        if len(files) > _MAX_FILES:
            raise ToolError(f"'files' must not exceed {_MAX_FILES} paths.")

        resolved = [
            _validated_project_file(item) for item in files
        ]

        return {"files": resolved}

    def execute(self, payload: dict) -> Any:
        daily_update = _load_script_module("daily_update.py")

        by_hash: dict[str, list[str]] = {}

        for path in payload["files"]:
            digest = daily_update.calculate_file_hash(path)
            by_hash.setdefault(digest, []).append(
                str(path.relative_to(PROJECT_ROOT))
            )

        duplicate_groups = [
            {"sha256": digest, "files": paths}
            for digest, paths in by_hash.items()
            if len(paths) > 1
        ]

        return {
            "files_checked": len(payload["files"]),
            "unique_documents": len(by_hash),
            "exact_duplicate_groups": duplicate_groups,
            "exact_duplicate_count": sum(
                len(group["files"]) - 1
                for group in duplicate_groups
            ),
            "note": (
                "Exact duplicates share an identical SHA-256 content "
                "hash. Similar-but-not-identical documents require "
                "similarity_engine."
            ),
        }


# ============================================================
# SIMILARITY ENGINE
# ============================================================

class SimilarityEngineTool(BaseTool):
    name = "similarity_engine"
    description = (
        "Compute text similarity using the EXISTING project "
        "embedding model (sentence-transformers/all-MiniLM-L6-v2, "
        "the same model behind the FAISS index). Input: "
        "{texts: [str]} (2-10 texts). Returns pairwise cosine "
        "similarity scores. No second embedding system is created."
    )

    def validate_input(self, payload: dict) -> dict:
        texts = payload.get("texts")

        if not isinstance(texts, list):
            raise ToolError("'texts' must be a list of strings.")

        if len(texts) < 2:
            raise ToolError("'texts' must contain at least 2 strings.")

        if len(texts) > _MAX_TEXTS:
            raise ToolError(f"'texts' must not exceed {_MAX_TEXTS} items.")

        clean = []

        for item in texts:
            if not isinstance(item, str) or not item.strip():
                raise ToolError(
                    "Each text must be a non-empty string."
                )

            if len(item) > _MAX_TEXT_CHARS:
                raise ToolError(
                    f"Each text must not exceed {_MAX_TEXT_CHARS} "
                    "characters."
                )

            clean.append(item.strip())

        return {"texts": clean}

    def execute(self, payload: dict) -> Any:
        import numpy as np

        model = shared_hybrid_retriever().model

        embeddings = model.encode(
            payload["texts"],
            normalize_embeddings=True,
        )

        embeddings = np.asarray(embeddings)

        # Cosine similarity: dot product of L2-normalized vectors,
        # matching the FAISS IndexFlatIP contract.
        similarity = embeddings @ embeddings.T

        pairs = []

        for i in range(len(payload["texts"])):
            for j in range(i + 1, len(payload["texts"])):
                pairs.append(
                    {
                        "text_a_index": i,
                        "text_b_index": j,
                        "score": round(
                            float(similarity[i][j]), 6
                        ),
                    }
                )

        result: dict[str, Any] = {
            "model": "sentence-transformers/all-MiniLM-L6-v2",
            "texts": len(payload["texts"]),
            "pairs": pairs,
        }

        if len(payload["texts"]) == 2:
            result["pair_score"] = pairs[0]["score"]

        return result


# ============================================================
# ANOMALY DETECTION
# ============================================================

class AnomalyDetectionTool(BaseTool):
    name = "anomaly_detection"
    description = (
        "Integrity anomaly checks over the EXISTING vector "
        "metadata: invalid page ranges, missing source hashes, "
        "missing source references, duplicate vector ids, and "
        "vector id sequence breaks. This is data-integrity "
        "checking only — it is NOT fraud detection and makes no "
        "fraud claims. Input: {} (no required fields)."
    )

    def validate_input(self, payload: dict) -> dict:
        scope = payload.get("scope", "metadata")

        if scope != "metadata":
            raise ToolError(
                "Only the 'metadata' integrity scope is supported."
            )

        return {"scope": "metadata"}

    def execute(self, payload: dict) -> Any:
        metadata_path = (
            PROJECT_ROOT
            / "data"
            / "profile"
            / "vectorstore"
            / "metadata.json"
        )

        if not metadata_path.exists():
            raise ToolError("Vector metadata file is not available.")

        with open(metadata_path, "r", encoding="utf-8") as file:
            records = json.load(file)

        if not isinstance(records, list):
            raise ToolError("Vector metadata file is malformed.")

        anomalies: list[dict] = []

        def record_anomaly(
            anomaly_type: str,
            vector_id: Any,
            detail: str,
        ) -> None:
            if len(anomalies) < _MAX_ANOMALIES:
                anomalies.append(
                    {
                        "type": anomaly_type,
                        "vector_id": vector_id,
                        "detail": detail,
                    }
                )

        seen_vector_ids: dict[Any, int] = {}

        for index, record in enumerate(records):
            vector_id = record.get("vector_id")

            if vector_id in seen_vector_ids:
                record_anomaly(
                    "duplicate_vector_id",
                    vector_id,
                    (
                        f"vector_id {vector_id} also assigned to "
                        f"metadata row {seen_vector_ids[vector_id]}."
                    ),
                )
            else:
                seen_vector_ids[vector_id] = index

            if not isinstance(vector_id, int) or vector_id != index:
                record_anomaly(
                    "vector_id_sequence_break",
                    vector_id,
                    (
                        f"metadata row {index} has vector_id "
                        f"{vector_id} (expected {index})."
                    ),
                )

            if not record.get("source_sha256"):
                record_anomaly(
                    "missing_source_sha256",
                    vector_id,
                    "Record has no source_sha256 provenance hash.",
                )

            if not record.get("source"):
                record_anomaly(
                    "missing_source",
                    vector_id,
                    "Record has no source document reference.",
                )

            page_start = record.get("page_start")
            page_end = record.get("page_end")

            if (
                isinstance(page_start, int)
                and isinstance(page_end, int)
                and page_start > page_end
            ):
                record_anomaly(
                    "invalid_page_range",
                    vector_id,
                    (
                        f"page_start {page_start} is greater than "
                        f"page_end {page_end}."
                    ),
                )

        by_type: dict[str, int] = {}

        for anomaly in anomalies:
            by_type[anomaly["type"]] = (
                by_type.get(anomaly["type"], 0) + 1
            )

        return {
            "scope": "metadata",
            "records_checked": len(records),
            "anomaly_count": len(anomalies),
            "anomalies_by_type": by_type,
            "anomalies": anomalies,
            "note": (
                "Integrity checks over vector metadata only. Not "
                "fraud detection."
            ),
        }
