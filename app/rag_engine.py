"""
FBR RAG Engine (Phase 7).

Minimal, production-safe Retrieval-Augmented Generation layer that:

1. Validates the user question (non-empty, size-limited).
2. Retrieves top-k evidence from the validated Phase 6 FAISS index
   via the canonical FBRHybridRetriever.
3. Maps each FAISS row to its metadata + canonical chunk text
   for full source/page/section provenance.
4. Assembles a structured LLM context with explicit provenance.
5. Calls the LLM through the canonical generate_answer() with a
   strict grounded-only system prompt.
6. Runs the existing verify_answer() grounded-answer pipeline
   (size, section consistency, lexical grounding, numeric
   grounding, speculation).
7. Returns a deterministic, provenance-preserving response dict.

No new frameworks. Reuses:
- app.hybrid_retriever.FBRHybridRetriever
- app.llm.generate_answer
- app.answer_generator.verify_answer (full pipeline)
- canonical chunks loaded row-aligned in hybrid_retriever
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.answer_generator import verify_answer
from app.hybrid_retriever import FBRHybridRetriever
from app.llm import generate_answer


# ============================================================
# RAG ENGINE CONFIGURATION
# ============================================================

MAX_QUESTION_LENGTH = 1000
MIN_QUESTION_LENGTH = 3
DEFAULT_TOP_K = 5
MAX_CONTEXT_CHARS = 16000


# ============================================================
# QUESTION VALIDATION
# ============================================================

def _validate_question(question: Any) -> str:
    """
    Normalize and validate the user question.

    Rules:
    - Must be a string
    - Must not be empty after strip
    - Must not exceed MAX_QUESTION_LENGTH
    - Must not be excessively short (likely accidental input)
    """

    if question is None:
        raise ValueError("Question is required.")

    if not isinstance(question, str):
        raise ValueError("Question must be a string.")

    cleaned = question.strip()

    if len(cleaned) < MIN_QUESTION_LENGTH:
        raise ValueError(
            f"Question is too short (min {MIN_QUESTION_LENGTH} characters)."
        )

    if len(cleaned) > MAX_QUESTION_LENGTH:
        raise ValueError(
            f"Question exceeds maximum length of {MAX_QUESTION_LENGTH} characters."
        )

    return cleaned


# ============================================================
# QUESTION ANALYSIS (NON-MUTATING)
# ============================================================

_SECTION_PATTERNS = [
    r"\bsection\s+(\d{1,3})\b",
    r"\bsec\.?\s*(\d{1,3})\b",
    r"\bs\.?\s*(\d{1,3})\b",
]


def _analyze_question(question: str) -> dict:
    """
    Extract lightweight structural signals from the question.

    Returns a dict with:
    - is_section_query
    - section_number (int or None)
    - is_income_tax (bool)
    - is_sales_tax (bool)
    - is_federal_excise (bool)
    - is_finance_act (bool)
    - is_property_valuation (bool)
    """

    question_lower = question.lower()

    section_number = None

    for pattern in _SECTION_PATTERNS:
        match = re.search(pattern, question_lower)
        if match:
            section_number = int(match.group(1))
            break

    is_income_tax = any(
        term in question_lower
        for term in (
            "income tax",
            "income-tax",
            "ordinance 2001",
            "incometaxordinance",
        )
    )

    is_sales_tax = any(
        term in question_lower
        for term in ("sales tax", "salestax")
    )

    is_federal_excise = any(
        term in question_lower
        for term in ("federal excise", "excise duty")
    )

    is_finance_act = "finance act" in question_lower

    is_property_valuation = any(
        term in question_lower
        for term in (
            "property valuation",
            "property valuations",
            "immovable property",
        )
    )

    return {
        "is_section_query": section_number is not None,
        "section_number": section_number,
        "is_income_tax": is_income_tax,
        "is_sales_tax": is_sales_tax,
        "is_federal_excise": is_federal_excise,
        "is_finance_act": is_finance_act,
        "is_property_valuation": is_property_valuation,
    }


# ============================================================
# RETRIEVAL
# ============================================================

def _retrieve(retriever: FBRHybridRetriever, question: str, top_k: int) -> list[dict]:
    """
    Run hybrid retrieval through the canonical retriever.

    The retriever already enforces the Phase 6 contract:
    IndexFlatIP, dimension 384, INNER_PRODUCT metric, and
    returns results that may include exact-section continuations.
    """

    if top_k <= 0:
        raise ValueError("top_k must be positive.")

    return retriever.search(question, top_k=top_k)


# ============================================================
# PROVENANCE MAPPING
# ============================================================

def _map_to_provenance(retriever: FBRHybridRetriever, results: list[dict]) -> list[dict]:
    """
    Map each retrieval hit to a full provenance record.

    Each record preserves:
    - chunk_id
    - source (document filename)
    - document_id
    - page (from metadata)
    - section (from metadata, if any)
    - source_path
    - source_sha256
    - score (final hybrid score)
    - semantic_score
    - bm25_score
    - exact_match
    - text (chunk content from canonical chunks)
    """

    provenance = []

    for result in results:
        idx = int(result.get("index", -1))

        if idx < 0 or idx >= len(retriever.metadata):
            continue

        item = retriever.metadata[idx]

        if not isinstance(item, dict):
            continue

        text = str(
            item.get("text")
            or item.get("chunk_text")
            or ""
        ).strip()

        if not text:
            continue

        page_start = item.get("page_start")
        page_end = item.get("page_end")

        if page_start is not None and page_end is not None and page_start != page_end:
            page_value = f"{page_start}-{page_end}"
        else:
            page_value = page_start

        record = {
            "vector_id": int(item.get("vector_id", idx)),
            "chunk_id": str(
                item.get("chunk_id")
                or item.get("id")
                or ""
            ),
            "document_id": item.get("document_id"),
            "source": str(item.get("source", "")),
            "source_path": item.get("source_path"),
            "source_sha256": item.get("source_sha256"),
            "page": page_value,
            "page_start": page_start,
            "page_end": page_end,
            "section": item.get("section_reference"),
            "section_reference": item.get("section_reference"),
            "section_number": item.get("section_number"),
            "law_tag": result.get("law_tag"),
            "multi_law_candidate": bool(
                result.get("multi_law_candidate", False)
            ),
            "chunk_index": item.get("chunk_index"),
            "chunking_strategy": item.get("chunking_strategy"),
            "document_type": item.get("document_type"),
            "text": text,
            "score": float(result.get("score", 0.0)),
            "semantic_score": float(result.get("semantic_score", 0.0)),
            "bm25_score": float(result.get("bm25_score", 0.0)),
            "exact_match": bool(result.get("exact_match", False)),
        }

        provenance.append(record)

    return provenance


def _has_sufficient_evidence(question_analysis: dict, records: list[dict]) -> bool:
    if not records:
        return False

    if any(record.get("exact_match") for record in records):
        return True

    if max(float(record.get("semantic_score", 0.0)) for record in records) >= 0.20:
        return True

    recognized_intent = any(
        question_analysis.get(field)
        for field in (
            "is_income_tax",
            "is_sales_tax",
            "is_federal_excise",
            "is_finance_act",
            "is_property_valuation",
        )
    )
    return bool(recognized_intent)


def _detect_ambiguous_section_query(question: str) -> dict:
    """
    Detect ambiguous section queries where the user mentioned a
    section number but no specific law (e.g. "What is Section 177?").
    Returns a dict with keys:
      - is_ambiguous_section: bool
      - section_number: int | None
      - law_intent: list[str]
    """

    if not isinstance(question, str) or not question.strip():
        return {
            "is_ambiguous_section": False,
            "section_number": None,
            "law_intent": [],
        }

    question_lower = question.lower().strip()

    section_match = re.search(
        r"\b(?:section|sec\.?|s\.?)\s*(\d{1,3})\b",
        question_lower,
    )

    if not section_match:
        return {
            "is_ambiguous_section": False,
            "section_number": None,
            "law_intent": [],
        }

    section_number = int(section_match.group(1))

    law_terms = {
        "income tax": "income_tax",
        "incometax": "income_tax",
        "ordinance 2001": "income_tax",
        "ordinance, 2001": "income_tax",
        "sales tax": "sales_tax",
        "salestax": "sales_tax",
        "federal excise": "federal_excise",
        "excise duty": "federal_excise",
        "finance act": "finance_act",
    }

    detected_laws = sorted(
        {
            tag
            for term, tag in law_terms.items()
            if term in question_lower
        }
    )

    return {
        "is_ambiguous_section": len(detected_laws) == 0,
        "section_number": section_number,
        "law_intent": detected_laws,
    }


_AMBIGUOUS_SECTION_ANSWER = (
    "This question mentions a section number but does not specify "
    "which FBR law you are asking about. The same section number may "
    "appear in multiple FBR laws (for example, Income Tax Ordinance "
    "2001, Sales Tax Act 1990, and Federal Excise Act 2005). "
    "Please rephrase your question and include the specific law, e.g. "
    "\"Section 177 of the Income Tax Ordinance 2001\" or "
    "\"Section 177 of the Sales Tax Act 1990\". The retrieved evidence "
    "below shows where this section appears in each available FBR law."
)


# ============================================================
# CONTEXT ASSEMBLY
# ============================================================
def _assemble_context(records: list[dict]) -> str:
    """
    Build a deterministic, provenance-rich context string for the LLM.

    Each source block is clearly separated and includes:
    - source index
    - document filename
    - source_path
    - source_sha256
    - chunk_id
    - page / section (when available)
    - retrieval score
    - exact match flag
    - chunk text
    """

    if not records:
        return ""

    blocks = []
    total_chars = 0

    for index, record in enumerate(records, start=1):
        if total_chars >= MAX_CONTEXT_CHARS:
            break

        text = record["text"]
        truncated = False

        if total_chars + len(text) > MAX_CONTEXT_CHARS:
            remaining = max(0, MAX_CONTEXT_CHARS - total_chars)
            text = text[:remaining]
            truncated = True

        page_section_lines = []

        if record.get("page") is not None:
            page_section_lines.append(f"Page: {record['page']}")

        if record.get("section") is not None:
            page_section_lines.append(f"Section: {record['section']}")

        page_section_str = (
            " | ".join(page_section_lines)
            if page_section_lines
            else "Page/Section: not specified"
        )

        block = (
            f"\n[SOURCE {index}]\n"
            f"Document: {record['source']}\n"
            f"Source path: {record.get('source_path') or 'n/a'}\n"
            f"Source SHA-256: {record.get('source_sha256') or 'n/a'}\n"
            f"Chunk ID: {record['chunk_id']}\n"
            f"{page_section_str}\n"
            f"Retrieval score: {record['score']:.4f}\n"
            f"Exact-section match: {record['exact_match']}\n"
            f"--- TEXT BEGIN ---\n"
            f"{text}\n"
            f"--- TEXT END ---"
        )

        if truncated:
            block += "\n[TRUNCATED]"

        blocks.append(block)
        total_chars += len(text)

    header = (
        "You are given the following FBR document excerpts as authoritative context.\n"
        "Each source is identified by document name, source path, source SHA-256, "
        "chunk ID, and (where available) page and section.\n"
        "Use ONLY this context to answer the user's question.\n"
        "If the context does not contain enough information, say so explicitly.\n"
    )

    return header + "\n".join(blocks)


# ============================================================
# PROVENANCE SERIALIZATION
# ============================================================

def _serialize_provenance(records: list[dict]) -> list[dict]:
    """
    Build a clean, public-facing provenance list (no internal text).
    """

    public = []

    for record in records:
        public.append({
            "chunk_id": record["chunk_id"],
            "document_id": record.get("document_id"),
            "source": record["source"],
            "source_path": record.get("source_path"),
            "source_sha256": record.get("source_sha256"),
            "page": record.get("page"),
            "page_start": record.get("page_start"),
            "page_end": record.get("page_end"),
            "section": record.get("section"),
            "section_reference": record.get("section_reference"),
            "section_number": record.get("section_number"),
            "law_tag": record.get("law_tag"),
            "multi_law_candidate": record.get("multi_law_candidate", False),
            "score": record["score"],
            "semantic_score": record["semantic_score"],
            "bm25_score": record["bm25_score"],
            "exact_match": record["exact_match"],
        })

    return public


# ============================================================
# NO-EVIDENCE RESPONSE
# ============================================================

_NO_EVIDENCE_ANSWER = (
    "The provided FBR documents do not contain enough information to answer this."
)


# ============================================================
# RAG ENGINE
# ============================================================

class FBRRAGEngine:
    """
    Canonical Phase 7 RAG engine.

    Composes the validated Phase 6 FAISS index, the canonical
    chunks, the OpenRouter-backed LLM, and the existing grounded
    verification pipeline.
    """

    def __init__(self, retriever: FBRHybridRetriever | None = None):
        """
        Construct the engine.

        If retriever is None, the canonical FBRHybridRetriever
        is instantiated (which loads FAISS, metadata, model,
        and BM25).
        """

        if retriever is None:
            retriever = FBRHybridRetriever()

        self.retriever = retriever
        self.top_k = DEFAULT_TOP_K

    # --------------------------------------------------------
    # PUBLIC API
    # --------------------------------------------------------

    def answer(
        self,
        question: str,
        top_k: int = DEFAULT_TOP_K,
    ) -> dict:
        """
        Run the full RAG pipeline for a single user question.

        Returns a dict with:
        - question
        - question_analysis
        - context (assembled LLM context, may be empty)
        - answer (LLM answer or no-evidence answer)
        - sources (provenance list, may be empty)
        - verification (grounded-answer verification result)
        - grounded (bool, True iff verification passed)
        """

        try:
            question = _validate_question(question)
        except ValueError as e:
            return {
                "question": str(question) if question is not None else "",
                "question_analysis": {},
                "context": "",
                "answer": str(e),
                "sources": [],
                "verification": {
                    "passed": False,
                    "reason": str(e),
                    "failed_checks": ["question_validation"],
                    "checks": {},
                },
                "grounded": False,
            }

        question_analysis = _analyze_question(question)
        ambiguous = _detect_ambiguous_section_query(question)

        results = _retrieve(self.retriever, question, top_k)

        provenance = _map_to_provenance(self.retriever, results)

        if (
            ambiguous["is_ambiguous_section"]
            and any(
                record.get("multi_law_candidate")
                for record in provenance
            )
        ):
            laws = sorted({
                str(record.get("law_tag", ""))
                for record in provenance
                if record.get("law_tag")
            })
            answer_text = _AMBIGUOUS_SECTION_ANSWER
            verification = {
                "passed": True,
                "reason": (
                    f"Ambiguous section query: section "
                    f"{ambiguous['section_number']} present in "
                    f"multiple FBR laws: {', '.join(laws) or 'unknown'}."
                ),
                "failed_checks": [],
                "checks": {},
                "ambiguous_section": True,
                "candidate_laws": laws,
                "section_number": ambiguous["section_number"],
            }
            return {
                "question": question,
                "question_analysis": question_analysis,
                "context": "",
                "answer": answer_text,
                "sources": _serialize_provenance(provenance),
                "verification": verification,
                "grounded": True,
                "ambiguous_section": True,
            }

        if not _has_sufficient_evidence(question_analysis, provenance):
            return {
                "question": question,
                "question_analysis": question_analysis,
                "context": "",
                "answer": _NO_EVIDENCE_ANSWER,
                "sources": [],
                "verification": {
                    "passed": True,
                    "reason": "Retrieved evidence was insufficient or out of domain.",
                    "failed_checks": [],
                    "checks": {},
                },
                "grounded": True,
            }

        if not provenance:
            return {
                "question": question,
                "question_analysis": question_analysis,
                "context": "",
                "answer": _NO_EVIDENCE_ANSWER,
                "sources": [],
                "verification": {
                    "passed": True,
                    "reason": "No evidence to verify.",
                    "failed_checks": [],
                    "checks": {},
                },
                "grounded": True,
            }

        context = _assemble_context(provenance)

        if not context.strip():
            return {
                "question": question,
                "question_analysis": question_analysis,
                "context": "",
                "answer": _NO_EVIDENCE_ANSWER,
                "sources": _serialize_provenance(provenance),
                "verification": {
                    "passed": True,
                    "reason": "Empty context after assembly.",
                    "failed_checks": [],
                    "checks": {},
                },
                "grounded": True,
            }

        try:
            answer = generate_answer(
                question=question,
                context=context,
            )
        except Exception as e:  # noqa: BLE001
            return {
                "question": question,
                "question_analysis": question_analysis,
                "context": context,
                "answer": _NO_EVIDENCE_ANSWER,
                "sources": _serialize_provenance(provenance),
                "verification": {
                    "passed": False,
                    "reason": f"LLM error: {e}",
                    "failed_checks": ["llm_call"],
                    "checks": {},
                },
                "grounded": False,
            }

        verification = verify_answer(
            question=question,
            answer=answer,
            context=context,
        )

        final_answer = answer

        if not verification["passed"]:
            final_answer = _NO_EVIDENCE_ANSWER

        return {
            "question": question,
            "question_analysis": question_analysis,
            "context": context,
            "answer": final_answer,
            "sources": _serialize_provenance(provenance),
            "verification": verification,
            "grounded": bool(verification["passed"]),
        }


# ============================================================
# CONVENIENCE ENTRY POINT
# ============================================================

def answer_question(question: str, top_k: int = DEFAULT_TOP_K) -> dict:
    """
    Module-level convenience: build the engine and answer.
    """

    engine = FBRRAGEngine()
    return engine.answer(question, top_k=top_k)
