"""
Search tools — thin, validated wrappers around the EXISTING
retrieval stack.

- rag_search:      FBRRAGEngine.answer() (retrieval + LLM +
                   verification + safe fallback)
- hybrid_search:   FBRHybridRetriever.search() (semantic FAISS +
                   BM25 hybrid retrieval)
- metadata_filter: filtering over the EXISTING vector metadata
                   (data/profile/vectorstore/metadata.json) using
                   only fields that actually exist there.

No new retrieval system is created. All heavy resources are lazy
singletons shared across tools (one FAISS load, one embedding
model).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.tools.base import BaseTool, ToolError

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_MAX_QUERY_LENGTH = 1000
_MAX_TOP_K = 50
_DEFAULT_TOP_K = 5
_MAX_METADATA_LIMIT = 200

# Fields that ACTUALLY exist in the project's vector metadata
# (verified against data/profile/vectorstore/metadata.json).
ALLOWED_METADATA_FILTERS = {
    "document_type",
    "source",
    "section_reference",
    "document_id",
    "title",
    "publication_date",
    "effective_date",
}


# ============================================================
# SHARED LAZY SINGLETONS (one FAISS load for all tools)
# ============================================================

_shared_engine = None


def shared_rag_engine():
    """
    One shared FBRRAGEngine across all tools (one FAISS index,
    one BM25 index, one embedding model).
    """

    global _shared_engine

    if _shared_engine is None:
        from app.rag_engine import FBRRAGEngine

        _shared_engine = FBRRAGEngine()

    return _shared_engine


def shared_hybrid_retriever():
    """Reuse the RAG engine's retriever (never build a second one)."""

    return shared_rag_engine().retriever


# ============================================================
# INPUT VALIDATION HELPERS
# ============================================================

def _validated_query(payload: dict) -> str:
    query = payload.get("query")

    if not isinstance(query, str):
        raise ToolError("'query' must be a string.")

    query = query.strip()

    if not query:
        raise ToolError("'query' must not be empty or whitespace-only.")

    if len(query) > _MAX_QUERY_LENGTH:
        raise ToolError(
            f"'query' must not exceed {_MAX_QUERY_LENGTH} characters."
        )

    return query


def _validated_top_k(payload: dict) -> int:
    top_k = payload.get("top_k", _DEFAULT_TOP_K)

    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise ToolError("'top_k' must be an integer.")

    if top_k < 1 or top_k > _MAX_TOP_K:
        raise ToolError(f"'top_k' must be between 1 and {_MAX_TOP_K}.")

    return top_k


# ============================================================
# RAG SEARCH
# ============================================================

class RAGSearchTool(BaseTool):
    name = "rag_search"
    description = (
        "Full RAG answer over the official FBR corpus using the "
        "canonical FBRRAGEngine (hybrid retrieval + LLM answer + "
        "verification + safe no-evidence fallback). Input: "
        "{query: str, top_k?: int}. Returns the engine's answer, "
        "sources with full provenance, verification result, and "
        "grounded flag."
    )

    def validate_input(self, payload: dict) -> dict:
        return {
            "query": _validated_query(payload),
            "top_k": _validated_top_k(payload),
        }

    def execute(self, payload: dict) -> Any:
        response = shared_rag_engine().answer(
            payload["query"],
            top_k=payload["top_k"],
        )

        return {
            "answer": response.get("answer", ""),
            "sources": response.get("sources", []),
            "verification": response.get("verification", {}),
            "grounded": bool(response.get("grounded", False)),
        }


# ============================================================
# HYBRID SEARCH
# ============================================================

class HybridSearchTool(BaseTool):
    name = "hybrid_search"
    description = (
        "Raw hybrid retrieval (semantic FAISS + BM25 + exact "
        "section matching) over the FBR corpus using the EXISTING "
        "FBRHybridRetriever. No answer synthesis. Input: "
        "{query: str, top_k?: int}. Returns retrieved records "
        "with scores and provenance."
    )

    def validate_input(self, payload: dict) -> dict:
        return {
            "query": _validated_query(payload),
            "top_k": _validated_top_k(payload),
        }

    def execute(self, payload: dict) -> Any:
        results = shared_hybrid_retriever().search(
            payload["query"],
            top_k=payload["top_k"],
        )

        records = [
            result if isinstance(result, dict) else {"value": result}
            for result in results
        ]

        return {
            "results": records,
            "count": len(records),
        }


# ============================================================
# METADATA FILTER
# ============================================================

class MetadataFilterTool(BaseTool):
    name = "metadata_filter"
    description = (
        "Filter the existing vector metadata records using actual "
        "metadata fields only: document_type, source, "
        "section_reference, document_id, title (substring), "
        "publication_date, effective_date. Input: "
        "{filters: {field: value}, limit?: int}. No metadata is "
        "invented — only fields present in the knowledge base."
    )

    def validate_input(self, payload: dict) -> dict:
        filters = payload.get("filters")

        if not isinstance(filters, dict) or not filters:
            raise ToolError(
                "'filters' must be a non-empty JSON object."
            )

        unknown = [
            key for key in filters
            if key not in ALLOWED_METADATA_FILTERS
        ]

        if unknown:
            raise ToolError(
                "Unknown metadata filter field(s): "
                f"{', '.join(sorted(unknown))}. Allowed: "
                f"{', '.join(sorted(ALLOWED_METADATA_FILTERS))}."
            )

        clean_filters: dict[str, str] = {}

        for key, value in filters.items():
            if not isinstance(value, str) or not value.strip():
                raise ToolError(
                    f"Filter '{key}' must be a non-empty string."
                )
            clean_filters[key] = value.strip()

        limit = payload.get("limit", 20)

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ToolError("'limit' must be an integer.")

        if limit < 1 or limit > _MAX_METADATA_LIMIT:
            raise ToolError(
                f"'limit' must be between 1 and {_MAX_METADATA_LIMIT}."
            )

        return {"filters": clean_filters, "limit": limit}

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

        filters = payload["filters"]

        def matches(record: dict) -> bool:
            for key, expected in filters.items():
                actual = record.get(key)

                if key == "title":
                    if not isinstance(actual, str):
                        return False
                    if expected.lower() not in actual.lower():
                        return False
                    continue

                if str(actual if actual is not None else "") != expected:
                    return False

            return True

        matched = [record for record in records if matches(record)]

        return {
            "matches": matched[: payload["limit"]],
            "match_count": len(matched),
            "total_records": len(records),
        }
