"""
Phase 6: Answer Generation / Answer Synthesis.

This module sits strictly AFTER the RAG engine (Phase 4/7) and the
Verification Layer (Phase 8). It takes the raw, verified outputs of
the specialized agents and structures them into a clean, source-
attribution-rich, query-type-appropriate answer for the user.

The canonical pipeline after this module is:

  Query (Phase 2)
  → Router (Phase 3)
  → RAG Retrieval (Phase 4)
  → Specialized Agent (Phase 5)
  → Verification (Phase 7/8)
  → ANSWER SYNTHESIS (Phase 6 — this module)
  → Final Response (Phase 8/9)

CRITICAL CONTRACT (see master prompt):

  - This module does NOT bypass RAG, Verification, or source
    provenance. Those remain authoritative.
  - This module does NOT introduce a new LLM framework or call
    the LLM again. The RAG engine has already produced a grounded
    draft answer. This module structures that answer.
  - If verification says evidence is insufficient, this module
    returns the deterministic safe-refusal answer unchanged.
  - If the answer is grounded but unstructured, this module adds
    query-type-appropriate structure (steps, source refs, etc.).
  - Examples are inserted ONLY when supported by retrieved evidence
    and ONLY when the query type benefits from one.
  - Every answer carries source provenance. Nothing is fabricated.

This module is pure (no LLM, no FAISS, no randomness). It only
formats and enriches already-verified outputs.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.verification_layer import PLACEHOLDER_ANSWER

_NO_EVIDENCE_ANSWER = (
    "The provided FBR documents do not contain enough information "
    "to answer this."
)

_SAFE_ANSWERS = (PLACEHOLDER_ANSWER, _NO_EVIDENCE_ANSWER)


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class SourceReference:
    """Clean, human-readable source citation."""

    document: str
    section: str | None = None
    page_range: str | None = None
    score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"document": self.document}
        if self.section:
            d["section"] = self.section
        if self.page_range:
            d["page_range"] = self.page_range
        if self.score is not None:
            d["score"] = round(self.score, 4)
        return d

    def to_citation_text(self) -> str:
        parts: list[str] = [self.document]
        if self.section:
            parts.append(f"({self.section})")
        if self.page_range:
            parts.append(f"pp. {self.page_range}")
        return " ".join(parts)


@dataclass
class ConfidenceInfo:
    """Deterministic confidence metadata derived from the pipeline."""

    grounded: bool = False
    verification_passed: bool = False
    sources_count: int = 0
    has_numeric_support: bool = False
    confidence_label: str = "low"
    confidence_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Example:
    """A supporting example, derived from evidence — NOT fabricated."""

    text: str
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"text": self.text}
        if self.source:
            d["source"] = self.source
        return d


@dataclass
class StructuredAnswer:
    """The final structured answer output from Phase 6.

    The 'answer' field is the primary user-facing text.
    The 'sections' dict contains query-type-appropriate sub-parts
    (e.g., 'steps' for procedural queries, 'calculation' for
    calculation queries). Not every section is populated for every
    query type.
    """

    answer: str
    answer_type: str = "informational"
    sections: dict[str, Any] = field(default_factory=dict)
    sources: list[SourceReference] = field(default_factory=list)
    confidence: ConfidenceInfo = field(default_factory=ConfidenceInfo)
    examples: list[Example] = field(default_factory=list)
    disclaimer: str | None = None
    follow_up_questions: list[str] = field(default_factory=list)
    raw_answer: str = ""
    raw_verification: dict[str, Any] = field(default_factory=dict)
    raw_grounded: bool = False
    grounded: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "answer": self.answer,
            "answer_type": self.answer_type,
            "sources": [s.to_dict() for s in self.sources],
            "confidence": self.confidence.to_dict(),
            "examples": [e.to_dict() for e in self.examples],
            "grounded": self.grounded,
        }
        if self.sections:
            out["sections"] = self.sections
        if self.disclaimer:
            out["disclaimer"] = self.disclaimer
        if self.follow_up_questions:
            out["follow_up_questions"] = self.follow_up_questions
        return out


# ============================================================
# SAFE REFUSAL CHECK
# ============================================================

def _is_safe_refusal(answer: str) -> bool:
    """Return True when the answer is the deterministic safe
    refusal / no-evidence placeholder. These answers MUST pass
    through unchanged — no structuring, no examples, no
    embellishment."""

    if not answer:
        return True
    stripped = (answer or "").strip()
    if stripped in _SAFE_ANSWERS:
        return True
    lower = stripped.lower()
    refusal_phrases = (
        "not contain enough information",
        "does not support a verified answer",
        "insufficient evidence",
    )
    return any(phrase in lower for phrase in refusal_phrases)


# ============================================================
# A. INFORMATION SYNTHESIS
# ============================================================

@dataclass
class SynthesizedContext:
    """Organized pipeline output: question, classification, evidence,
    agent result, verification, and confidence — ready for structuring.

    This is the input to the structuring step. The fields mirror the
    data already available from the orchestrator output; this module
    does NOT re-run any pipeline stage.
    """

    question: str = ""
    answer: str = ""
    sources: list[dict] = field(default_factory=list)
    verification: dict[str, Any] = field(default_factory=dict)
    grounded: bool = False
    domain: str = ""
    retrieval_question: str = ""
    intent: str = "information"
    intent_type: str = "informational"
    classification: dict[str, Any] = field(default_factory=dict)
    calculation: dict[str, Any] | None = None
    domain_results: list[dict] | None = None
    multi_domain: bool = False
    routing: dict[str, Any] | None = None


def synthesize_context(
    agent_response: dict[str, Any],
    classification: dict[str, Any] | None = None,
) -> SynthesizedContext:
    """A. Information Synthesis.

    Takes the raw agent/orchestrator output and (optionally) the
    Phase 2 classification, and organizes them into a SynthesizedContext.
    No facts are invented. No pipeline is re-run.
    """

    sources_raw = agent_response.get("sources", []) or []
    verification_raw = agent_response.get("verification", {}) or {}

    intent = "information"
    intent_type = "informational"
    if classification:
        intent = classification.get("intent", "information")
        intent_type = classification.get("intent_type", "informational")

    return SynthesizedContext(
        question=str(agent_response.get("question", "") or ""),
        answer=str(agent_response.get("answer", "") or ""),
        sources=sources_raw,
        verification=verification_raw,
        grounded=bool(agent_response.get("grounded", False)),
        domain=str(agent_response.get("domain", "") or ""),
        retrieval_question=str(
            agent_response.get("retrieval_question", "") or ""
        ),
        intent=intent,
        intent_type=intent_type,
        classification=classification or {},
        calculation=agent_response.get("calculation"),
        domain_results=agent_response.get("domain_results"),
        multi_domain=bool(agent_response.get("multi_domain", False)),
        routing=agent_response.get("routing"),
    )


# ============================================================
# B. SOURCE EXTRACTION
# ============================================================

def _extract_sources(sources: list[dict]) -> list[SourceReference]:
    """Build clean, human-readable source references from raw source
    dicts, preserving full provenance metadata."""

    refs: list[SourceReference] = []
    seen: set[str] = set()

    for src in sources:
        if not isinstance(src, dict):
            continue

        doc_name = str(
            src.get("source", "") or src.get("document_id", "") or ""
        ).strip()
        if not doc_name:
            doc_path = str(src.get("source_path", "") or "")
            if doc_path:
                doc_name = doc_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if not doc_name:
            continue

        chunk_id = str(src.get("chunk_id", "") or "")
        dedup_key = f"{doc_name}:{chunk_id}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        section = src.get("section_reference") or src.get("section") or None
        if isinstance(section, str):
            section = section.strip() or None

        page_start = src.get("page_start")
        page_end = src.get("page_end")
        page_range: str | None = None
        if page_start is not None and page_end is not None:
            try:
                ps = int(page_start)
                pe = int(page_end)
                if ps == pe:
                    page_range = str(ps)
                else:
                    page_range = f"{ps}-{pe}"
            except (TypeError, ValueError):
                pass

        raw_page = src.get("page")
        if page_range is None and raw_page is not None:
            page_range = str(raw_page)

        score = src.get("score") or src.get("retrieval_score") or None
        if isinstance(score, (int, float)):
            score = float(score)

        refs.append(
            SourceReference(
                document=doc_name,
                section=section,
                page_range=page_range,
                score=score,
            )
        )

    return refs


# ============================================================
# C. CONFIDENCE SCORING
# ============================================================

def _compute_confidence(ctx: SynthesizedContext) -> ConfidenceInfo:
    """Compute a deterministic confidence label from the verified
    pipeline output. Does NOT re-run verification."""

    grounded = ctx.grounded
    verification_passed = bool(
        ctx.verification.get("passed", False)
    )
    sources_count = len(ctx.sources)
    failed_checks = ctx.verification.get("failed_checks", [])

    has_numeric = False
    for src in ctx.sources:
        if not isinstance(src, dict):
            continue
        text = str(
            src.get("text", "") or src.get("chunk_text", "") or ""
        )
        if re.search(r"\d[\d,\.]{2,}", text):
            has_numeric = True
            break

    if grounded and verification_passed and sources_count >= 3:
        label = "high"
        reason = (
            f"Answer grounded in {sources_count} verified sources; "
            f"verification passed."
        )
    elif grounded and verification_passed and sources_count >= 1:
        label = "medium"
        reason = (
            f"Answer grounded in {sources_count} verified source(s); "
            f"verification passed."
        )
    elif grounded and sources_count >= 1:
        label = "low"
        reason = (
            f"Answer grounded but verification flagged: "
            f"{', '.join(failed_checks) if failed_checks else 'partial'}."
        )
    elif verification_passed and sources_count >= 1:
        label = "medium"
        reason = (
            f"Verification passed with {sources_count} source(s) but "
            f"grounded flag is False."
        )
    else:
        label = "low"
        reason = (
            f"grounded={grounded}, verification_passed="
            f"{verification_passed}, sources={sources_count}."
        )

    return ConfidenceInfo(
        grounded=grounded,
        verification_passed=verification_passed,
        sources_count=sources_count,
        has_numeric_support=has_numeric,
        confidence_label=label,
        confidence_reason=reason,
    )


# ============================================================
# D. EXAMPLE HANDLING
# ============================================================

def _should_add_example(
    ctx: SynthesizedContext,
    confidence: ConfidenceInfo,
) -> bool:
    """Decide whether an example would be helpful for this query.

    Examples are added ONLY when:
      - The query is a calculation, procedure, or legal/rule
        query.
      - The confidence is at least medium.
      - There is at least one source.
    """

    if _is_safe_refusal(ctx.answer):
        return False
    if confidence.confidence_label in ("low",):
        return False
    if ctx.intent in ("calculation", "procedure", "legal_rule"):
        return len(ctx.sources) >= 1
    return False


def _build_example(
    ctx: SynthesizedContext,
) -> Example | None:
    """Build a single supporting example from the available evidence.

    Examples are derived FROM the retrieved evidence and clearly
    marked as illustrative. They never introduce unsupported facts.
    """

    if ctx.intent == "calculation" and ctx.calculation:
        calc = ctx.calculation
        kind = calc.get("kind", "")
        percent = calc.get("percent")
        amount = calc.get("amount")
        result = calc.get("result")
        if kind == "percent_of_amount" and all(
            v is not None for v in (percent, amount, result)
        ):
            text = (
                f"Example: {percent}% of Rs {amount:,.2f} = "
                f"Rs {result:,.2f}"
            )
            return Example(text=text, source=None)

    if ctx.intent == "procedure":
        first_source = ctx.sources[0] if ctx.sources else None
        src_name = ""
        if first_source and isinstance(first_source, dict):
            src_name = str(
                first_source.get("source", "")
                or first_source.get("document_id", "")
                or ""
            ).strip()
        text = (
            "This answer is based on the steps found in the referenced "
            "FBR source document(s). Refer to the sources section for "
            "full details."
        )
        return Example(
            text=text,
            source=src_name if src_name else None,
        )

    if ctx.intent == "legal_rule":
        first_source = ctx.sources[0] if ctx.sources else None
        if first_source and isinstance(first_source, dict):
            doc = str(
                first_source.get("source", "")
                or first_source.get("document_id", "")
                or ""
            ).strip()
            sec_ref = str(
                first_source.get("section_reference", "")
                or first_source.get("section", "")
                or ""
            ).strip()
            if doc and sec_ref:
                return Example(
                    text=(
                        f"For the exact legal text, refer to "
                        f"{sec_ref} in {doc}."
                    ),
                    source=doc,
                )

    return None


# ============================================================
# E. STRUCTURED ANSWER FORMATTING
# ============================================================

def _format_answer(
    ctx: SynthesizedContext,
    sources: list[SourceReference],
    confidence: ConfidenceInfo,
    example: Example | None,
) -> str:
    """Format the final user-facing answer string.

    The formatting is deterministic and query-type-appropriate.
    When the raw answer is already clean and grounded, it is used
    as the primary text. Structure is added around it.
    """

    if _is_safe_refusal(ctx.answer):
        return ctx.answer

    parts: list[str] = []
    answer_body = (ctx.answer or "").strip()

    if answer_body:
        parts.append(answer_body)

    if example:
        parts.append("")
        parts.append("---")
        parts.append(example.text)

    if sources:
        parts.append("")
        parts.append("**Sources:**")
        for idx, src in enumerate(sources[:10], start=1):
            parts.append(f"  {idx}. {src.to_citation_text()}")

    if confidence.confidence_label in ("low",) and ctx.grounded:
        parts.append("")
        parts.append(
            "Note: This answer is based on the available FBR documents. "
            "For official guidance, please consult the Federal Board of "
            "Revenue directly."
        )

    return "\n".join(parts)


def _build_sections(
    ctx: SynthesizedContext,
) -> dict[str, Any]:
    """Build query-type-specific structural sub-sections.

    Not every section is populated for every query type. Only
    relevant sections are included.
    """

    sections: dict[str, Any] = {}

    if ctx.intent == "calculation" and ctx.calculation:
        calc = ctx.calculation
        sections["calculation"] = {
            "kind": calc.get("kind", ""),
            "percent": calc.get("percent"),
            "amount": calc.get("amount"),
            "expression": calc.get("expression", ""),
            "result": calc.get("result"),
        }
        if calc.get("percent") and calc.get("amount"):
            sections["inputs"] = {
                "rate": f"{calc['percent']}%",
                "base_amount": f"Rs {calc.get('amount', 0):,.2f}",
            }

    if ctx.intent == "procedure":
        sections["procedure"] = {
            "description": (
                "Refer to the answer and source documents above "
                "for the complete procedure."
            ),
        }

    if ctx.intent == "legal_rule":
        sections["legal"] = {
            "description": (
                "The answer above is based on the retrieved FBR "
                "document(s) and applicable rules. Consult the "
                "sources for the exact legal text."
            ),
        }

    if ctx.intent == "date_deadline":
        date_entities = ctx.classification.get("dates", [])
        tax_years = ctx.classification.get("tax_year", [])
        if date_entities or tax_years:
            sections["dates"] = {
                "mentioned_dates": date_entities,
                "tax_years": tax_years,
            }

    if ctx.intent == "notice_appeal":
        sections["notice_appeal"] = {
            "description": (
                "The response covers the applicable notice/appeal "
                "process based on the retrieved FBR source material."
            ),
        }

    if ctx.intent == "registration":
        sections["registration"] = {
            "description": (
                "Refer to the answer and source documents for "
                "registration steps and requirements."
            ),
        }

    if ctx.intent == "filing":
        sections["filing"] = {
            "description": (
                "The answer above addresses the filing requirement "
                "based on available FBR documents."
            ),
        }

    if ctx.intent == "research":
        sections["research"] = {
            "description": (
                "This is a research/comparison response drawn from "
                "multiple FBR source documents."
            ),
        }

    section_refs = ctx.classification.get("section_references", [])
    if section_refs:
        sections["referenced_sections"] = section_refs

    return sections


def _build_disclaimer(
    ctx: SynthesizedContext,
    confidence: ConfidenceInfo,
) -> str | None:
    """Generate a disclaimer when appropriate.

    Disclaimers are included for:
      - Low-confidence answers
      - Calculation answers (to clarify that rates may change)
      - Notice/appeal answers (to note that legal advice is needed)
    """

    if _is_safe_refusal(ctx.answer):
        return None

    if ctx.intent == "calculation":
        return (
            "Disclaimer: The calculation above is based on the rates "
            "and figures found in the retrieved FBR documents. Actual "
            "tax liability may differ based on applicable exemptions, "
            "adjustments, and Finance Act amendments. Consult a tax "
            "professional or the FBR for official assessment."
        )

    if ctx.intent == "notice_appeal":
        return (
            "Disclaimer: This information is based on FBR source "
            "documents and is provided for general guidance only. "
            "For specific legal advice regarding notices and appeals, "
            "consult a qualified tax lawyer or the FBR directly."
        )

    if confidence.confidence_label == "low":
        return (
            "Disclaimer: This answer is based on limited available "
            "FBR source material. For authoritative guidance, please "
            "consult the Federal Board of Revenue or a qualified tax "
            "professional."
        )

    return None


def _build_follow_ups(
    ctx: SynthesizedContext,
) -> list[str]:
    """Generate contextually relevant follow-up questions."""

    follow_ups: list[str] = []

    if ctx.intent == "information" and ctx.domain:
        domain_label = ctx.domain.replace("_", " ")
        follow_ups.append(
            f"How do I file a return for {domain_label}?"
        )
    if ctx.intent == "filing":
        follow_ups.append("What are the penalties for late filing?")
    if ctx.intent == "calculation":
        follow_ups.append(
            "What exemptions apply to this calculation?"
        )
    if ctx.intent == "notice_appeal":
        follow_ups.append(
            "What is the timeline for filing an appeal?"
        )
    if ctx.intent == "registration":
        follow_ups.append(
            "What documents are needed for NTN registration?"
        )
    if ctx.intent == "legal_rule":
        section_refs = ctx.classification.get("section_references", [])
        if section_refs:
            follow_ups.append(
                f"Are there any exemptions under {section_refs[0]}?"
            )
    if ctx.intent == "research":
        follow_ups.append(
            "Can you compare this with the previous Finance Act?"
        )

    return follow_ups[:3]


# ============================================================
# F. VERIFICATION CANNOT BE BYPASSED
# ============================================================

def _enforce_verification(
    ctx: SynthesizedContext,
    structured: StructuredAnswer,
) -> StructuredAnswer:
    """Final guard: ensure the verification layer result is honored.

    If verification failed, the answer must be the safe refusal.
    This function is a safety net that catches any code path where
    the answer was not already replaced.
    """

    verification_passed = bool(
        ctx.verification.get("passed", False)
    )
    grounded = ctx.grounded

    if _is_safe_refusal(ctx.answer):
        structured.answer = ctx.answer
        structured.raw_answer = ctx.answer
        structured.grounded = False
        structured.confidence = ConfidenceInfo(
            grounded=False,
            verification_passed=True,
            sources_count=0,
            confidence_label="low",
            confidence_reason="safe_refusal",
        )
        structured.sources = []
        structured.examples = []
        structured.sections = {}
        return structured

    if not verification_passed:
        structured.answer = PLACEHOLDER_ANSWER
        structured.raw_answer = ctx.answer
        structured.grounded = False
        structured.confidence = ConfidenceInfo(
            grounded=False,
            verification_passed=False,
            sources_count=len(structured.sources),
            confidence_label="low",
            confidence_reason="verification_failed",
        )
        structured.examples = []
        return structured

    if not grounded:
        structured.answer = PLACEHOLDER_ANSWER
        structured.raw_answer = ctx.answer
        structured.grounded = False
        structured.confidence = ConfidenceInfo(
            grounded=False,
            verification_passed=True,
            sources_count=len(structured.sources),
            confidence_label="low",
            confidence_reason="grounded_false",
        )
        structured.examples = []
        return structured

    structured.grounded = grounded
    structured.raw_verification = ctx.verification
    return structured


# ============================================================
# MULTI-DOMAIN ANSWER HANDLING
# ============================================================

def _synthesize_multi_domain(
    ctx: SynthesizedContext,
) -> StructuredAnswer:
    """Handle the multi-domain combined answer from the orchestrator.

    The multi-domain answer is already a label-prefixed combination
    of per-domain answers. We extract sources and compute confidence
    across all domains.
    """

    sources = _extract_sources(ctx.sources)
    confidence = _compute_confidence(ctx)
    answer_text = (ctx.answer or "").strip()

    if _is_safe_refusal(answer_text):
        return StructuredAnswer(
            answer=answer_text,
            answer_type="multi_domain",
            sections={},
            sources=[],
            confidence=ConfidenceInfo(
                grounded=False,
                verification_passed=False,
                sources_count=0,
                confidence_label="low",
                confidence_reason="safe_refusal",
            ),
            raw_answer=answer_text,
            raw_verification=ctx.verification,
            raw_grounded=False,
            grounded=False,
        )

    return StructuredAnswer(
        answer=answer_text,
        answer_type="multi_domain",
        sections={"domains": ctx.domain_results is not None},
        sources=sources,
        confidence=confidence,
        raw_answer=ctx.answer,
        raw_verification=ctx.verification,
        raw_grounded=ctx.grounded,
        grounded=ctx.grounded,
    )


# ============================================================
# PUBLIC API
# ============================================================

def synthesize_answer(
    agent_response: dict[str, Any],
    classification: dict[str, Any] | None = None,
) -> StructuredAnswer:
    """Phase 6 top-level entry point.

    Takes the raw orchestrator/agent output and (optionally) the
    Phase 2 classification dict, and returns a StructuredAnswer.

    This module is a pure formatting and structuring layer. It does
    NOT:
      - re-run the RAG engine
      - re-run verification
      - call the LLM
      - invent facts
      - fabricate sources or citations
      - bypass safe refusal behavior
    """

    ctx = synthesize_context(agent_response, classification)

    if ctx.multi_domain:
        return _synthesize_multi_domain(ctx)

    sources = _extract_sources(ctx.sources)
    confidence = _compute_confidence(ctx)

    if _is_safe_refusal(ctx.answer):
        return StructuredAnswer(
            answer=ctx.answer,
            answer_type="safe_refusal",
            sections={},
            sources=[],
            confidence=ConfidenceInfo(
                grounded=False,
                verification_passed=True,
                sources_count=0,
                confidence_label="low",
                confidence_reason="safe_refusal",
            ),
            raw_answer=ctx.answer,
            raw_verification=ctx.verification,
            raw_grounded=False,
            grounded=False,
        )

    example = None
    if _should_add_example(ctx, confidence):
        example = _build_example(ctx)

    answer_text = _format_answer(ctx, sources, confidence, example)
    sections = _build_sections(ctx)
    disclaimer = _build_disclaimer(ctx, confidence)
    follow_ups = _build_follow_ups(ctx)

    structured = StructuredAnswer(
        answer=answer_text,
        answer_type=ctx.intent,
        sections=sections,
        sources=sources,
        confidence=confidence,
        examples=[example] if example else [],
        disclaimer=disclaimer,
        follow_up_questions=follow_ups,
        raw_answer=ctx.answer,
        raw_verification=ctx.verification,
        raw_grounded=ctx.grounded,
    )

    structured = _enforce_verification(ctx, structured)

    return structured


__all__ = [
    "SourceReference",
    "ConfidenceInfo",
    "Example",
    "StructuredAnswer",
    "SynthesizedContext",
    "synthesize_context",
    "synthesize_answer",
]
