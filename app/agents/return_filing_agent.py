"""
Return Filing Agent (Phase 9 corrected).

Scope:
- tax return filing
- return procedures
- filing requirements
- filing deadlines (where supported by retrieved evidence)
- corrections / amendments where supported

Behavior:
- Uses the existing RAG + verification pipeline.
- Query expansion is light: the existing RAG retrieval already
  resolves return-filing queries with high precision through
  strong signals like "return filing", "due date", "amend
  return".
"""

from __future__ import annotations

from app.agents.base import SpecializedAgent


class ReturnFilingAgent(SpecializedAgent):
    domain = "return_filing"

    TOOLS = (
        "rag_search",
        "hybrid_search",
        "metadata_filter",
        "rule_engine",
        "calculation_engine",
    )
