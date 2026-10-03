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
retrieval matches the corpus vocabulary. SRO questions (Statutory
Regulatory Orders — issued across all tax laws, not only excise)
additionally gain notification corpus vocabulary ("Notification",
"Federal Board of Revenue", "Revenue Division") so hybrid
retrieval surfaces actual SRO notification chunks instead of
generic "issued/orders" matches from unrelated acts.
"""

from __future__ import annotations

import re

from app.agents.base import SpecializedAgent

_FED_WORD_RE = re.compile(r"\bfed\b", re.IGNORECASE)

# SRO signals: bare abbreviation (whole word), dotted form, or the
# full statutory phrase.
_SRO_RE = re.compile(
    r"\bsros?\b|s\.r\.o\.?|statutory regulatory orders?",
    re.IGNORECASE,
)


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
        q_lower = q.lower()
        if "federal excise" not in q_lower:
            q = _FED_WORD_RE.sub("Federal Excise Duty", q)
            q_lower = q.lower()
        if (
            _SRO_RE.search(q)
            and "notification" not in q_lower
        ):
            q = (
                f"{q} Statutory Regulatory Order SRO Notification "
                "Federal Board of Revenue Revenue Division "
                "notification issued Islamabad"
            )
        return q
