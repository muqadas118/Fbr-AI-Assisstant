"""
Federal Excise Agent (Phase 9).

Scope:
- Federal Excise Act 2005
- FED applicability
- registration/compliance
- duties/rates where supported by corpus
- exemptions
- penalties/compliance
- relevant amendments

Deterministic query expansion: the common abbreviation "FED"
(whole word) is expanded to "Federal Excise Duty" so lexical
retrieval matches the corpus vocabulary.
"""

from __future__ import annotations

import re

from app.agents.base import SpecializedAgent

_FED_WORD_RE = re.compile(r"\bfed\b", re.IGNORECASE)


class FederalExciseAgent(SpecializedAgent):
    domain = "federal_excise"

    TOOLS = (
        "rag_search",
        "hybrid_search",
        "metadata_filter",
        "rule_engine",
        "calculation_engine",
    )

    def expand_query(self, question: str) -> str:
        q = (question or "").strip()
        if not q:
            return q
        if "federal excise" in q.lower():
            return q
        return _FED_WORD_RE.sub("Federal Excise Duty", q)
