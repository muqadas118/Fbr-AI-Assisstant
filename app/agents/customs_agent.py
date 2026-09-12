"""
Customs Agent (Phase 9 corrected).

Scope:
- Customs Act / rules
- imports / exports
- tariffs
- customs valuation
- customs procedures
- customs documentation
- customs notices where supported

Behavior:
- Uses the existing RAG + verification pipeline.
- Does NOT invent customs rates, procedures, sections, or values
  when the corpus does not contain sufficient evidence.
- If the corpus has no customs material, the existing RAG engine
  will return the deterministic safe-refusal / no-evidence
  answer; the agent passes this through unchanged.
"""

from __future__ import annotations

import re

from app.agents.base import SpecializedAgent

_CD_WORD_RE = re.compile(r"\bcd\b", re.IGNORECASE)


class CustomsAgent(SpecializedAgent):
    domain = "customs"

    TOOLS = (
        "rag_search",
        "hybrid_search",
        "metadata_filter",
        "rule_engine",
        "document_parser",
        "web_research",
    )

    def expand_query(self, question: str) -> str:
        q = (question or "").strip()
        if not q:
            return q
        if "customs duty" in q.lower():
            return q
        return _CD_WORD_RE.sub("customs duty", q)
