"""
Notice / Appeal Agent (Phase 9 corrected).

Scope:
- FBR notices (show-cause, demand, recovery)
- notice interpretation
- response guidance based on available FBR documents
- appeals (CIT(A), ATIR, IRAC, rectification)
- appeal procedures and timelines only when supported by
  authoritative corpus evidence
- section-linked notice interpretation (e.g. "I received an
  FBR notice under section 177")

Behavior:
- Uses the existing RAG + verification pipeline.
- Does NOT fabricate deadlines, sections, forms, or procedures.
- If the user supplies a bare section number, the agent surfaces
  both the notice/appeal framing AND the section context by
  asking the RAG engine about the section + notice scope.

Query expansion: when the user references a bare section number
in a notice/appeal context, the agent appends a "notice and
appeal" qualifier so retrieval is anchored to procedural and
section-relevant material in the corpus.
"""

from __future__ import annotations

import re

from app.agents.base import SpecializedAgent

_SECTION_RE = re.compile(r"\bsection\s+\d+\b", re.IGNORECASE)

_OTHER_LAW_TERMS: tuple[str, ...] = (
    "income tax",
    "incometax",
    "income-tax",
    "sales tax",
    "salestax",
    "federal excise",
    "customs",
)

# Phrases that already contain the notice/appeal framing. When
# the user's question already includes one of these, the agent
# must NOT append an extra "notice and appeal procedure"
# qualifier (the input is already the best retrieval signal).
_NOTICE_APPEAL_PHRASES: tuple[str, ...] = (
    "notice and appeal",
    "appeal and notice",
    "notice appeal",
    "appeal notice",
    "show cause",
    "show-cause",
    "demand notice",
    "recovery notice",
    "appellate",
    "commissioner appeal",
    "irac",
    "itat",
    "file appeal",
    "first appeal",
    "second appeal",
    "rectification",
)


class NoticeAppealAgent(SpecializedAgent):
    domain = "notice_appeal"

    TOOLS = (
        "document_parser",
        "rag_search",
        "hybrid_search",
        "metadata_filter",
        "rule_engine",
        "web_research",
    )

    def expand_query(self, question: str) -> str:
        q = (question or "").strip()
        if not q:
            return q
        q_lower = q.lower()
        # If the input already carries notice/appeal framing,
        # leave it untouched: the existing vocabulary is the
        # best retrieval signal.
        if any(phrase in q_lower for phrase in _NOTICE_APPEAL_PHRASES):
            return q
        if _SECTION_RE.search(q) and not any(
            term in q_lower for term in _OTHER_LAW_TERMS
        ):
            return f"{q} notice and appeal procedure"
        return q
