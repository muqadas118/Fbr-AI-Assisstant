"""
Phase 8 deterministic post-RAG verification layer.

This module sits strictly after the RAG pipeline. It does not change
the RAG response, it only validates the retrieved evidence and the
provenance claims that reach the caller.

It enforces:
  1. Every generated answer is grounded in retrieved evidence.
  2. Every citation / provenance reference maps to an actual
     retrieved chunk.
  3. Source SHA-256, document ID, chunk ID, page range and section
     provenance remain consistent.
  4. No unsupported legal/tax claim is presented as verified evidence.
  5. Insufficient evidence produces a deterministic refusal.
  6. Out-of-domain queries are rejected safely.
  7. LLM/API failures never produce an ungrounded answer.
  8. Retrieved context cannot be replaced or fabricated by the
     generation layer.
  9. Conflicting or insufficient retrieved evidence is handled
     conservatively.
 10. Verification behavior is deterministic where possible.
"""

from __future__ import annotations

import copy
import hashlib
import re
from collections import Counter
from typing import Any, Iterable

from app.rag_engine import _NO_EVIDENCE_ANSWER

PLACEHOLDER_ANSWER = (
    "The retrieved evidence does not support a verified answer."
)


def _stringify_chunk_id(value: Any) -> str:
    return str(value or "").strip()


def _stringify_source_path(value: Any) -> str:
    return str(value or "").strip()


def _normalize_provenance(retrieved_sources: Iterable[dict]) -> list[dict]:
    """Return a deep, immutable, deterministically ordered copy of the
    retrieved sources. Any later mutation by the generator cannot
    affect the verification layer."""

    snapshot: list[dict] = []
    for index, source in enumerate(retrieved_sources or []):
        if not isinstance(source, dict):
            continue
        cloned = copy.deepcopy(source)
        cloned["_verified_index"] = index
        cloned["_immutable"] = True
        snapshot.append(cloned)
    snapshot.sort(
        key=lambda item: (
            _stringify_chunk_id(item.get("chunk_id")),
            _stringify_source_path(item.get("source_path")),
        )
    )
    return snapshot


def _expected_field(record: dict, field: str) -> str:
    value = record.get(field, "")
    if value is None:
        return ""
    return str(value).strip()


def _digit_ratio(text: str) -> float:
    if not text:
        return 0.0
    digits = sum(ch.isdigit() for ch in text)
    return digits / max(1, len(text))


def _looks_like_unsupported_numeric_claim(answer: str) -> bool:
    """Detect dense numeric runs that look like fabricated legal/tax
    figures (e.g. '15%', 'Rs 2,500,000') which are not present in the
    retrieved evidence. Conservative: a run of 4+ consecutive digits is
    treated as a candidate figure and must appear in the evidence."""

    if not answer:
        return False
    for match in re.finditer(r"\d[\d,.]{2,}", answer):
        candidate = match.group(0)
        if _digit_ratio(candidate) < 0.5:
            continue
        if not any(ch.isdigit() for ch in candidate):
            continue
        if len(re.sub(r"[^\d]", "", candidate)) < 3:
            continue
        return True
    return False


def _collect_unsupported_numeric_claims(
    answer: str, evidence_text: str
) -> list[str]:
    claims: list[str] = []
    if not answer:
        return claims
    for match in re.finditer(r"\d[\d,.]{2,}", answer):
        candidate = match.group(0).strip()
        if not candidate or not any(ch.isdigit() for ch in candidate):
            continue
        if _digit_ratio(candidate) < 0.5:
            continue
        if len(re.sub(r"[^\d]", "", candidate)) < 3:
            continue
        normalized = re.sub(r"[^\d]", "", candidate)
        if normalized and normalized not in re.sub(
            r"[^\d]", "", evidence_text or ""
        ):
            claims.append(candidate)
    return claims


def _detect_numeric_conflicts(retrieved_sources: list[dict]) -> list[str]:
    """Detect contradictory numeric claims across retrieved sources.

    Conservative: only flags when the same surrounding context
    contains DIFFERENT percentage / currency values across two or
    more sources. Returns a list of human-readable conflict strings.
    """

    if len(retrieved_sources) < 2:
        return []

    context_window = 60
    pattern = re.compile(
        r"(\d[\d,\.]*)\s*(?:%|percent|pc|rs\.?|rupees?)",
        re.IGNORECASE,
    )

    buckets: dict[str, set[str]] = {}
    for source in retrieved_sources:
        text = str(
            source.get("text")
            or source.get("chunk_text")
            or ""
        )
        if not text:
            continue
        for match in pattern.finditer(text):
            value = re.sub(r"[^\d]", "", match.group(1))
            if not value:
                continue
            start = max(0, match.start() - context_window)
            end = min(len(text), match.end() + context_window)
            surrounding = re.sub(r"\s+", " ", text[start:end].lower())
            tokens = [
                tok for tok in re.findall(r"[a-z]{4,}", surrounding)
                if tok not in {
                    "that", "this", "with", "from", "into", "than",
                    "when", "where", "whose", "which", "shall",
                    "rate", "rates", "percent", "amount",
                }
            ]
            key = " ".join(tokens[:8])
            if not key:
                continue
            buckets.setdefault(key, set()).add(value)

    conflicts: list[str] = []
    for key, values in buckets.items():
        if len(values) >= 2:
            conflicts.append(
                f"numeric_conflict_in_{key!r}: {sorted(values)}"
            )
    return conflicts


def _collect_unsupported_lexical_claims(
    answer: str, evidence_text: str
) -> list[str]:
    claims: list[str] = []
    if not answer:
        return claims
    stopwords = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "into",
        "any",
        "are",
        "but",
        "not",
        "you",
        "your",
        "have",
        "has",
        "was",
        "were",
        "will",
        "shall",
        "may",
        "can",
        "must",
        "of",
        "in",
        "on",
        "to",
        "by",
        "an",
        "a",
        "or",
        "as",
        "is",
        "it",
        "be",
        "if",
        "or",
        "no",
        "yes",
    }
    tokens = re.findall(r"[A-Za-z]{4,}", answer.lower())
    seen: set[str] = set()
    for token in tokens:
        if token in stopwords:
            continue
        if token in seen:
            continue
        seen.add(token)
        if token in (evidence_text or "").lower():
            continue
        claims.append(token)
    return claims


def _build_evidence_text(retrieved_sources: list[dict]) -> str:
    parts: list[str] = []
    for source in retrieved_sources:
        if not isinstance(source, dict):
            continue
        text = str(
            source.get("text")
            or source.get("chunk_text")
            or ""
        )
        if text:
            parts.append(text)
    return "\n".join(parts)


def _validate_provenance_consistency(
    retrieved_sources: list[dict],
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Validate chunk ID, source path, source SHA-256, document ID,
    page range and section consistency across the retrieved snapshot.

    Returns (hard_errors, soft_warnings, summary).
      - hard_errors: list of strings that fail the verification
      - soft_warnings: list of strings that are reported but do not
        fail verification (e.g. missing section_reference for
        continuation / table chunks where no section heading is
        present in the chunk text)
    """

    errors: list[str] = []
    warnings: list[str] = []
    seen_chunk_ids: Counter[str] = Counter()
    chunk_id_to_source_paths: dict[str, set[str]] = {}
    chunk_id_to_sha: dict[str, set[str]] = {}
    chunk_id_to_document_id: dict[str, set[str]] = {}
    chunk_id_to_page_range: dict[str, tuple[tuple[int | None, int | None], ...]] = {}
    chunk_id_to_section: dict[str, set[str]] = {}

    for index, source in enumerate(retrieved_sources):
        chunk_id = _stringify_chunk_id(source.get("chunk_id"))
        source_path = _stringify_source_path(source.get("source_path"))
        source_sha = _expected_field(source, "source_sha256")
        document_id = _expected_field(source, "document_id")

        page_start = source.get("page_start")
        page_end = source.get("page_end")
        if page_start is None and page_end is None:
            raw_page = source.get("page")
            if isinstance(raw_page, str) and "-" in raw_page:
                parts = raw_page.split("-", 1)
                try:
                    page_start = int(parts[0].strip())
                    page_end = int(parts[1].strip())
                except (TypeError, ValueError):
                    page_start = None
                    page_end = None
            elif raw_page is not None:
                try:
                    page_start = int(raw_page)
                    page_end = int(raw_page)
                except (TypeError, ValueError):
                    page_start = None
                    page_end = None

        section_reference = _expected_field(
            source, "section_reference"
        ) or _expected_field(source, "section")

        if not chunk_id:
            errors.append(
                f"provenance[{index}].chunk_id_missing"
            )
            continue
        if not source_path:
            errors.append(
                f"provenance[{index}].source_path_missing"
            )
        if not source_sha:
            errors.append(
                f"provenance[{index}].source_sha256_missing"
            )
        if not document_id:
            errors.append(
                f"provenance[{index}].document_id_missing"
            )
        if page_start is None or page_end is None:
            errors.append(
                f"provenance[{index}].page_range_missing"
            )
        else:
            try:
                page_start_int = int(page_start)
                page_end_int = int(page_end)
            except (TypeError, ValueError):
                errors.append(
                    f"provenance[{index}].page_range_invalid"
                )
                page_start_int = None
                page_end_int = None
            if (
                page_start_int is not None
                and page_end_int is not None
                and page_start_int > page_end_int
            ):
                errors.append(
                    f"provenance[{index}].page_range_inverted"
                )
        if not section_reference:
            warnings.append(
                f"provenance[{index}].section_reference_missing"
            )

        if chunk_id:
            seen_chunk_ids[chunk_id] += 1
            chunk_id_to_source_paths.setdefault(
                chunk_id, set()
            ).add(source_path)
            chunk_id_to_sha.setdefault(chunk_id, set()).add(source_sha)
            chunk_id_to_document_id.setdefault(
                chunk_id, set()
            ).add(document_id)
            if page_start is not None and page_end is not None:
                try:
                    page_key = (int(page_start), int(page_end))
                except (TypeError, ValueError):
                    page_key = (None, None)
                chunk_id_to_page_range.setdefault(chunk_id, ())
                chunk_id_to_page_range[chunk_id] = (
                    chunk_id_to_page_range[chunk_id] + (page_key,)
                )
            chunk_id_to_section.setdefault(
                chunk_id, set()
            ).add(section_reference)

    duplicate_chunk_ids = {
        chunk_id
        for chunk_id, count in seen_chunk_ids.items()
        if count > 1
    }
    for chunk_id in duplicate_chunk_ids:
        errors.append(f"duplicate_chunk_id:{chunk_id}")

    for chunk_id, paths in chunk_id_to_source_paths.items():
        paths.discard("")
        if len(paths) > 1:
            errors.append(
                f"chunk_source_path_conflict:{chunk_id}"
            )
    for chunk_id, shas in chunk_id_to_sha.items():
        shas.discard("")
        if len(shas) > 1:
            errors.append(f"chunk_source_sha_conflict:{chunk_id}")
    for chunk_id, docs in chunk_id_to_document_id.items():
        docs.discard("")
        if len(docs) > 1:
            errors.append(
                f"chunk_document_id_conflict:{chunk_id}"
            )
    for chunk_id, page_ranges in chunk_id_to_page_range.items():
        unique_ranges = {
            range_
            for range_ in page_ranges
            if range_ != (None, None)
        }
        if len(unique_ranges) > 1:
            errors.append(
                f"chunk_page_range_conflict:{chunk_id}"
            )
    for chunk_id, sections in chunk_id_to_section.items():
        sections.discard("")
        if len(sections) > 1:
            errors.append(
                f"chunk_section_conflict:{chunk_id}"
            )

    summary = {
        "chunk_count": len(seen_chunk_ids),
        "duplicate_chunk_ids": sorted(duplicate_chunk_ids),
    }
    return errors, warnings, summary


def _resolve_citations(
    citations: Iterable[Any],
    retrieved_sources: list[dict],
) -> tuple[list[dict], list[str]]:
    """Map each citation/provenance reference to a retrieved chunk.
    Returns resolved citations and unresolved errors."""

    resolved: list[dict] = []
    errors: list[str] = []
    chunk_index = {
        _stringify_chunk_id(source.get("chunk_id")): source
        for source in retrieved_sources
    }
    for index, citation in enumerate(citations or []):
        if isinstance(citation, str):
            chunk_id = citation
        elif isinstance(citation, dict):
            chunk_id = _stringify_chunk_id(citation.get("chunk_id"))
        else:
            errors.append(f"citation[{index}].invalid_type")
            continue
        if not chunk_id:
            errors.append(f"citation[{index}].chunk_id_missing")
            continue
        source = chunk_index.get(chunk_id)
        if source is None:
            errors.append(
                f"citation[{index}].unresolved:{chunk_id}"
            )
            continue
        resolved.append(
            {
                "chunk_id": chunk_id,
                "source_path": _stringify_source_path(
                    source.get("source_path")
                ),
                "source_sha256": _expected_field(
                    source, "source_sha256"
                ),
                "document_id": _expected_field(source, "document_id"),
                "section_reference": _expected_field(
                    source, "section_reference"
                ),
                "page_start": source.get("page_start"),
                "page_end": source.get("page_end"),
                "retrieval_score": source.get("retrieval_score"),
            }
        )
    return resolved, errors


def _hash_provenance_snapshot(retrieved_sources: list[dict]) -> str:
    hasher = hashlib.sha256()
    for source in sorted(
        retrieved_sources,
        key=lambda item: _stringify_chunk_id(item.get("chunk_id")),
    ):
        hasher.update(
            _stringify_chunk_id(source.get("chunk_id")).encode("utf-8")
        )
        hasher.update(b"|")
        hasher.update(
            _stringify_source_path(source.get("source_path")).encode(
                "utf-8"
            )
        )
        hasher.update(b"|")
        hasher.update(
            _expected_field(source, "source_sha256").encode("utf-8")
        )
        hasher.update(b"|")
        hasher.update(
            _expected_field(source, "section_reference").encode(
                "utf-8"
            )
        )
        hasher.update(b"|")
        hasher.update(
            str(source.get("page_start", "")).encode("utf-8")
        )
        hasher.update(b"|")
        hasher.update(
            str(source.get("page_end", "")).encode("utf-8")
        )
        hasher.update(b"\n")
    return hasher.hexdigest()


def verify_rag_response(rag_response: dict) -> dict:
    """Apply the deterministic Phase 8 verification layer to a RAG
    response. Returns a verification verdict that includes:

      - verified: bool
      - verified_answer: safe final answer for the caller
      - citations: resolved citations
      - provenance_errors: list of provenance integrity issues
      - unsupported_claims: list of unsupported numeric / lexical claims
      - conflicts: list of conflicting evidence items
      - provenance_hash: SHA-256 of the immutable retrieved snapshot
      - reason: short deterministic explanation
    """

    if not isinstance(rag_response, dict):
        return {
            "verified": False,
            "verified_answer": PLACEHOLDER_ANSWER,
            "citations": [],
            "provenance_errors": ["rag_response_invalid_type"],
            "unsupported_claims": [],
            "conflicts": [],
            "provenance_hash": "",
            "reason": "rag_response_invalid_type",
        }

    raw_sources = rag_response.get("sources", []) or []
    retrieved_sources = _normalize_provenance(raw_sources)
    provenance_hash = _hash_provenance_snapshot(retrieved_sources)

    provenance_errors, provenance_warnings, provenance_summary = (
        _validate_provenance_consistency(retrieved_sources)
    )

    citations_input = rag_response.get("citations", []) or []
    resolved_citations, citation_errors = _resolve_citations(
        citations_input, retrieved_sources
    )

    answer = str(rag_response.get("answer", "") or "").strip()
    evidence_text = _build_evidence_text(retrieved_sources)

    unsupported_numeric = _collect_unsupported_numeric_claims(
        answer, evidence_text
    )
    unsupported_lexical = _collect_unsupported_lexical_claims(
        answer, evidence_text
    )

    rag_verification = rag_response.get("verification", {}) or {}
    rag_failed_checks = list(rag_verification.get("failed_checks", []))
    rag_passed = bool(rag_verification.get("passed"))

    if not rag_response.get("grounded", False):
        rag_failed_checks.append("rag_grounded_false")

    conflicts: list[str] = []
    for chunk_id in provenance_summary["duplicate_chunk_ids"]:
        conflicts.append(f"duplicate_chunk_id:{chunk_id}")
    for error in provenance_errors:
        if "conflict" in error:
            conflicts.append(error)
    for error in citation_errors:
        if error.startswith("citation[") and (
            "unresolved" in error
            or "invalid_type" in error
            or "chunk_id_missing" in error
        ):
            conflicts.append(error)
    for content_conflict in _detect_numeric_conflicts(
        retrieved_sources
    ):
        conflicts.append(content_conflict)

    if not retrieved_sources:
        rag_failed_checks.append("no_evidence")
    if not answer:
        rag_failed_checks.append("empty_answer")

    if _looks_like_unsupported_numeric_claim(answer) and (
        unsupported_numeric
    ):
        rag_failed_checks.append("unsupported_numeric_claim")
    if unsupported_lexical and len(unsupported_lexical) > 6:
        rag_failed_checks.append("unsupported_lexical_claim")
    if provenance_errors:
        rag_failed_checks.append("provenance_inconsistent")
    if citation_errors:
        rag_failed_checks.append("citation_unresolved")
    if conflicts:
        rag_failed_checks.append("conflicting_evidence")

    failed_checks = sorted(set(rag_failed_checks))
    no_evidence_safe = (
        not retrieved_sources
        and rag_passed
        and rag_response.get("grounded", False) is True
        and answer
        in {PLACEHOLDER_ANSWER, _NO_EVIDENCE_ANSWER}
    )
    verified = (
        no_evidence_safe
        or (
            rag_passed
            and not provenance_errors
            and not citation_errors
            and not conflicts
            and bool(retrieved_sources)
            and bool(answer)
            and not unsupported_numeric
            and len(unsupported_lexical) <= 6
        )
    )

    if verified:
        verified_answer = answer
        if no_evidence_safe:
            reason = "no_evidence_safe_refusal"
        else:
            reason = "verified"
    else:
        verified_answer = PLACEHOLDER_ANSWER
        if not retrieved_sources:
            reason = "no_evidence"
        elif not answer:
            reason = "empty_answer"
        elif not rag_passed:
            reason = "rag_verification_failed"
        elif provenance_errors:
            reason = "provenance_inconsistent"
        elif citation_errors:
            reason = "citation_unresolved"
        elif conflicts:
            reason = "conflicting_evidence"
        elif unsupported_numeric:
            reason = "unsupported_numeric_claim"
        elif len(unsupported_lexical) > 6:
            reason = "unsupported_lexical_claim"
        else:
            reason = "verification_failed"

    return {
        "verified": verified,
        "verified_answer": verified_answer,
        "citations": resolved_citations,
        "provenance_errors": provenance_errors,
        "provenance_warnings": provenance_warnings,
        "unsupported_claims": {
            "numeric": unsupported_numeric,
            "lexical": unsupported_lexical,
        },
        "conflicts": sorted(set(conflicts)),
        "provenance_hash": provenance_hash,
        "provenance_chunk_count": provenance_summary["chunk_count"],
        "failed_checks": failed_checks,
        "reason": reason,
    }


__all__ = [
    "PLACEHOLDER_ANSWER",
    "verify_rag_response",
]
