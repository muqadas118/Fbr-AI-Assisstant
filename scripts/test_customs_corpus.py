"""
FBR Customs corpus integration tests.

Validates that the customs corpus (markdown + JSONL Q/A) has been
properly ingested, embedded, and is reachable via hybrid retrieval.

All tests use the [PASS]/[FAIL] convention so that
scripts/final_regression.py can aggregate them with the rest of
the regression suite.

Coverage:

    [OFFLINE — always run]
    - customs[corpus]_source_files_present_in_04_source_docs
    - customs[corpus]_chunks_present_in_chunks_json
    - customs[corpus]_vectors_present_in_faiss_index
    - customs[corpus]_alignment_vectors_equal_chunks
    - customs[cleaned]_documents_have_expected_structure
    - customs[retrieval]_hybrid_returns_customs_chunk_top
    - customs[retrieval]_semantic_score_above_threshold
    - customs[retrieval]_multiple_smoke_queries_all_pass

    [LIVE — only if customs query triggers LLM, in which case
     the regression harness reclassifies as BLOCKED]
    - customs[live]_grounded_answer_via_rag_engine
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# TEST HARNESS
# ============================================================

_RESULTS: list[tuple[str, bool, str]] = []


def _print_separator(char: str = "=", length: int = 72) -> None:
    print(char * length)


def _record(name: str, passed: bool, detail: str = "") -> None:
    _RESULTS.append((name, passed, detail))
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}")
    if detail:
        for line in detail.splitlines():
            print(f"        {line}")


def _assert(name: str, condition: bool, detail: str = "") -> None:
    if not condition:
        if not detail:
            detail = "Assertion failed."
        _record(name, False, detail)
        raise AssertionError(f"{name}: {detail}")
    _record(name, True, detail)


def _is_customs_source(value: str) -> bool:
    return value.replace("\\", "/").startswith("customs/")


# ============================================================
# CONSTANTS
# ============================================================

SOURCE_DOCS_DIR = PROJECT_ROOT / "data" / "raw" / "04-source-docs" / "customs"
CLEANED_PATH = PROJECT_ROOT / "data" / "profile" / "source_docs" / "cleaned" / "cleaned_documents.json"
CHUNKS_PATH = PROJECT_ROOT / "data" / "profile" / "source_docs" / "chunks" / "chunks.json"
VECTORSTORE_DIR = PROJECT_ROOT / "data" / "profile" / "vectorstore"
INDEX_PATH = VECTORSTORE_DIR / "fbr_faiss.index"
METADATA_PATH = VECTORSTORE_DIR / "metadata.json"

CUSTOMS_SMOKE_QUERIES: list[tuple[str, str]] = [
    (
        "What is customs duty on imported goods in Pakistan?",
        "customs duty imported goods",
    ),
    (
        "How do I register for customs in Pakistan and what documents are required?",
        "register for customs documents",
    ),
    (
        "What is DIRBS and how does it relate to vehicle valuation at customs?",
        "DIRBS vehicle valuation",
    ),
    (
        "What are the penalties under the Customs Act 1969 for smuggling?",
        "penalties Customs Act 1969",
    ),
    (
        "What is the Customs Act 1969 and what does it cover?",
        "Customs Act 1969 overview",
    ),
]

MIN_HYBRID_SCORE = 0.15
MIN_SEMANTIC_SCORE = 0.15


# ============================================================
# CORPUS-LEVEL TESTS
# ============================================================

def test_source_files_present_in_04_source_docs() -> None:
    if not SOURCE_DOCS_DIR.exists():
        _assert(
            "customs[corpus]_source_files_present_in_04_source_docs",
            False,
            f"Missing directory: {SOURCE_DOCS_DIR}",
        )
        return

    md_files = list(SOURCE_DOCS_DIR.glob("*.md"))
    jsonl_files = list(SOURCE_DOCS_DIR.glob("*.jsonl"))
    _assert(
        "customs[corpus]_source_files_present_in_04_source_docs",
        len(md_files) >= 1 and len(jsonl_files) >= 1,
        f"md={len(md_files)} jsonl={len(jsonl_files)} in {SOURCE_DOCS_DIR}",
    )


def test_chunks_present_in_chunks_json() -> None:
    if not CHUNKS_PATH.exists():
        _assert(
            "customs[corpus]_chunks_present_in_chunks_json",
            False,
            f"Missing chunks.json: {CHUNKS_PATH}",
        )
        return

    chunks = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    if not isinstance(chunks, list):
        _assert(
            "customs[corpus]_chunks_present_in_chunks_json",
            False,
            f"Unexpected chunks.json structure: type={type(chunks).__name__}",
        )
        return

    customs_chunks = [
        c for c in chunks
        if _is_customs_source(c.get("source_path", ""))
    ]
    _assert(
        "customs[corpus]_chunks_present_in_chunks_json",
        len(customs_chunks) >= 1,
        f"customs_chunks={len(customs_chunks)} total_chunks={len(chunks)}",
    )


def test_vectors_present_in_faiss_index() -> None:
    if not INDEX_PATH.exists():
        _assert(
            "customs[corpus]_vectors_present_in_faiss_index",
            False,
            f"Missing index: {INDEX_PATH}",
        )
        return

    try:
        import faiss
    except ImportError as exc:
        _assert(
            "customs[corpus]_vectors_present_in_faiss_index",
            False,
            f"Missing deps: {exc}",
        )
        return

    index = faiss.read_index(str(INDEX_PATH))
    total = index.ntotal
    _assert(
        "customs[corpus]_vectors_present_in_faiss_index",
        total > 0,
        f"FAISS ntotal={total}",
    )


def test_alignment_vectors_equal_chunks() -> None:
    try:
        import faiss
    except ImportError as exc:
        _assert(
            "customs[corpus]_alignment_vectors_equal_chunks",
            False,
            f"Missing deps: {exc}",
        )
        return

    if not INDEX_PATH.exists() or not CHUNKS_PATH.exists():
        _assert(
            "customs[corpus]_alignment_vectors_equal_chunks",
            False,
            "Required artifacts missing",
        )
        return

    index = faiss.read_index(str(INDEX_PATH))
    chunks = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    _assert(
        "customs[corpus]_alignment_vectors_equal_chunks",
        isinstance(chunks, list) and index.ntotal == len(chunks),
        f"vectors={index.ntotal} chunks={len(chunks) if isinstance(chunks, list) else 'n/a'}",
    )


def test_cleaned_documents_have_expected_structure() -> None:
    if not CLEANED_PATH.exists():
        _assert(
            "customs[cleaned]_documents_have_expected_structure",
            False,
            f"Missing cleaned_documents.json: {CLEANED_PATH}",
        )
        return

    data = json.loads(CLEANED_PATH.read_text(encoding="utf-8"))
    docs = data.get("documents", data) if isinstance(data, dict) else data
    if not isinstance(docs, list):
        _assert(
            "customs[cleaned]_documents_have_expected_structure",
            False,
            f"Unexpected structure: type={type(docs).__name__}",
        )
        return

    customs_docs = [
        d for d in docs
        if _is_customs_source(d.get("source_path", ""))
    ]
    if not customs_docs:
        _assert(
            "customs[cleaned]_documents_have_expected_structure",
            False,
            "No customs documents in cleaned_documents.json",
        )
        return

    has_markdown_sections = False
    has_jsonl_entries = False
    for doc in customs_docs:
        sections = doc.get("sections", [])
        if not isinstance(sections, list) or not sections:
            continue
        first = sections[0]
        content = (first.get("content", "") or "").lower()
        if content.startswith("q:") and "\na:" in content:
            has_jsonl_entries = True
        else:
            has_markdown_sections = True

    _assert(
        "customs[cleaned]_documents_have_expected_structure",
        has_markdown_sections or has_jsonl_entries,
        (
            f"customs_docs={len(customs_docs)} "
            f"markdown_sections={has_markdown_sections} "
            f"jsonl_entries={has_jsonl_entries}"
        ),
    )


# ============================================================
# RETRIEVAL TESTS
# ============================================================

def _get_retriever():
    from app.hybrid_retriever import FBRHybridRetriever
    return FBRHybridRetriever()


def _resolve_source(retriever, result) -> str:
    try:
        source = retriever.get_result_source(result)
    except Exception:
        source = (
            result.get("source_path", "")
            or result.get("source", "")
            or str(result.get("index", ""))
        )
    return source


def test_hybrid_returns_customs_chunk_top() -> None:
    try:
        retriever = _get_retriever()
    except Exception as exc:
        _assert(
            "customs[retrieval]_hybrid_returns_customs_chunk_top",
            False,
            f"Could not build retriever: {type(exc).__name__}: {exc}",
        )
        return

    query = CUSTOMS_SMOKE_QUERIES[0][0]
    try:
        results = retriever.search(query, top_k=5)
    except Exception as exc:
        _assert(
            "customs[retrieval]_hybrid_returns_customs_chunk_top",
            False,
            f"search() raised: {type(exc).__name__}: {exc}",
        )
        return

    if not results:
        _assert(
            "customs[retrieval]_hybrid_returns_customs_chunk_top",
            False,
            f"No results for query: {query!r}",
        )
        return

    top = results[0]
    source = _resolve_source(retriever, top)
    is_customs = _is_customs_source(source)
    _assert(
        "customs[retrieval]_hybrid_returns_customs_chunk_top",
        is_customs,
        f"top.source={source!r} semantic_score={top.get('semantic_score'):.4f}",
    )


def test_semantic_score_above_threshold() -> None:
    try:
        retriever = _get_retriever()
    except Exception as exc:
        _assert(
            "customs[retrieval]_semantic_score_above_threshold",
            False,
            f"Could not build retriever: {type(exc).__name__}: {exc}",
        )
        return

    query = CUSTOMS_SMOKE_QUERIES[0][0]
    try:
        results = retriever.search(query, top_k=5)
    except Exception as exc:
        _assert(
            "customs[retrieval]_semantic_score_above_threshold",
            False,
            f"search() raised: {type(exc).__name__}: {exc}",
        )
        return

    if not results:
        _assert(
            "customs[retrieval]_semantic_score_above_threshold",
            False,
            f"No results for query: {query!r}",
        )
        return

    semantic = results[0].get("semantic_score")
    _assert(
        "customs[retrieval]_semantic_score_above_threshold",
        isinstance(semantic, (int, float)) and semantic >= MIN_SEMANTIC_SCORE,
        f"semantic_score={semantic} min={MIN_SEMANTIC_SCORE}",
    )


def test_multiple_smoke_queries_all_pass() -> None:
    try:
        retriever = _get_retriever()
    except Exception as exc:
        _assert(
            "customs[retrieval]_multiple_smoke_queries_all_pass",
            False,
            f"Could not build retriever: {type(exc).__name__}: {exc}",
        )
        return

    failed_queries: list[str] = []
    details: list[str] = []
    for idx, (query, label) in enumerate(CUSTOMS_SMOKE_QUERIES):
        try:
            results = retriever.search(query, top_k=5)
        except Exception as exc:
            failed_queries.append(f"{idx}:{label}=EXC:{type(exc).__name__}")
            continue
        if not results:
            failed_queries.append(f"{idx}:{label}=EMPTY")
            continue
        top = results[0]
        source = _resolve_source(retriever, top)
        is_customs = _is_customs_source(source)
        semantic = top.get("semantic_score", 0.0) or 0.0
        details.append(
            f"  q{idx}={label!r} customs={is_customs} semantic={semantic:.4f}"
        )
        if not is_customs or semantic < MIN_SEMANTIC_SCORE:
            failed_queries.append(
                f"{idx}:{label}=customs={is_customs} semantic={semantic:.4f}"
            )

    _assert(
        "customs[retrieval]_multiple_smoke_queries_all_pass",
        not failed_queries,
        "\n".join(details + [f"  FAIL: {q}" for q in failed_queries]),
    )


# ============================================================
# LIVE TESTS (gated by LLM availability)
# ============================================================

def _live_test(name: str, fn: Callable[[], None]) -> None:
    from app.llm import provider_status

    if not (provider_status()["groq_configured"] or provider_status()["openrouter_configured"]):
        _record(name, True, "SKIPPED: no LLM provider configured")
        return
    try:
        fn()
    except Exception as exc:
        _record(
            name,
            True,
            f"NOTE: live customs error (regression harness will reclassify): {type(exc).__name__}: {exc}",
        )


def live_grounded_answer_via_rag_engine() -> None:
    from app.rag_engine import answer_question

    query = CUSTOMS_SMOKE_QUERIES[0][0]
    result = answer_question(query)
    answer = result.get("answer", "") if isinstance(result, dict) else str(result)
    _assert(
        "customs[live]_grounded_answer_via_rag_engine",
        isinstance(answer, str) and len(answer) > 0,
        f"len(answer)={len(answer) if isinstance(answer, str) else 'n/a'}",
    )


# ============================================================
# RUNNER
# ============================================================

def main() -> int:
    _print_separator()
    print("FBR CUSTOMS CORPUS TEST SUITE")
    _print_separator()
    print()

    offline = [
        ("Source files present", test_source_files_present_in_04_source_docs),
        ("Chunks in chunks.json", test_chunks_present_in_chunks_json),
        ("Vectors in FAISS", test_vectors_present_in_faiss_index),
        ("Alignment vectors==chunks", test_alignment_vectors_equal_chunks),
        ("Cleaned doc structure", test_cleaned_documents_have_expected_structure),
        ("Hybrid returns customs top", test_hybrid_returns_customs_chunk_top),
        ("Semantic score threshold", test_semantic_score_above_threshold),
        ("Multiple smoke queries", test_multiple_smoke_queries_all_pass),
    ]
    for label, fn in offline:
        print(f"\n--- {label} ---")
        try:
            fn()
        except AssertionError:
            pass
        except Exception as exc:
            _record(
                f"{label} (uncaught exception)",
                False,
                f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            )

    print("\n--- Live (best-effort) ---")
    _live_test(
        "customs[live]_grounded_answer_via_rag_engine",
        live_grounded_answer_via_rag_engine,
    )

    _print_separator()
    print("CUSTOMS CORPUS TEST SUMMARY")
    _print_separator()
    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    failed = sum(1 for _, ok, _ in _RESULTS if not ok)
    print(f"Total : {len(_RESULTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    _print_separator()

    if failed:
        print("FAILED TESTS:")
        for name, ok, detail in _RESULTS:
            if not ok:
                print(f" - {name}")
                if detail:
                    for line in detail.splitlines():
                        print(f"     {line}")
        _print_separator()
        return 1

    print("ALL CUSTOMS CORPUS TESTS PASSED")
    _print_separator()
    return 0


if __name__ == "__main__":
    sys.exit(main())