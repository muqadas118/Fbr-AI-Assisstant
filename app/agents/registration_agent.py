"""
Registration Agent (Phase 9 corrected).

Scope:
- taxpayer registration
- NTN / STRN enrollment
- IRIS registration
- new taxpayer onboarding
- registration requirements and procedures

Behavior:
- Uses the existing RAG + verification pipeline.
- Expands the common abbreviation "NTN" to "National Tax Number
  registration" so lexical retrieval matches the corpus
  vocabulary.
- Expands "STRN" to "Sales Tax Registration Number" similarly.
"""

from __future__ import annotations

import re

from app.agents.base import SpecializedAgent

_NTN_WORD_RE = re.compile(r"\bntn\b", re.IGNORECASE)
_STRN_WORD_RE = re.compile(r"\bstrn\b", re.IGNORECASE)


class RegistrationAgent(SpecializedAgent):
    domain = "registration"

    TOOLS = (
        "rag_search",
        "hybrid_search",
        "metadata_filter",
        "rule_engine",
    )

    def expand_query(self, question: str) -> str:
        q = (question or "").strip()
        if not q:
            return q
        q = _NTN_WORD_RE.sub("National Tax Number", q)
        q = _STRN_WORD_RE.sub("Sales Tax Registration Number", q)
        return q
