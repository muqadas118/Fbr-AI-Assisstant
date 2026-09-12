"""
Research Agent (Phase 9 corrected).

The Research Agent handles broad FBR research questions that
require:

- comparing multiple provisions
- comparing documents
- tracing an issue across multiple sources
- finding relevant sections / documents
- multi-document evidence gathering
- historical / current provision comparison
- Finance Act amendment research
- Property valuation research (city-specific valuation data
  and document lookup)

The Research Agent must NOT become an unrestricted web-search
agent: it must remain grounded in the existing RAG corpus.

MIGRATED FUNCTIONALITY
======================

This agent absorbs the useful logic from the removed
PropertyValuation and FinanceAct agents:

- City-specific valuation queries are normalized to the
  corpus retrieval vocabulary ("{city} tehsil property
  valuation"). This addresses the documented Phase 8
  hybrid scoring limitation where a bare city name
  combined with generic legal phrasing was pulled toward
  Income Tax Ordinance property-acquisition text by the
  semantic component of the hybrid score.
- "FA <year>" abbreviation is normalized to "Finance Act
  <year>" so the existing Phase 7 source-identity boost
  in FBRHybridRetriever applies. The boost itself is
  NOT modified; the agent only ensures the retrieval
  question carries the full "Finance Act" phrase.

Query expansion is purely deterministic string rewriting
on the retrieval question. The original user question is
preserved in the response, and no value, rate, year, or
section is ever fabricated.
"""

from __future__ import annotations

import re

from app.agents.base import SpecializedAgent
from app.agents.router import detect_city

_FA_YEAR_RE = re.compile(r"\bfa[\s-]*(20\d{2})\b", re.IGNORECASE)


class ResearchAgent(SpecializedAgent):
    domain = "research"

    TOOLS = (
        "rag_search",
        "hybrid_search",
        "metadata_filter",
        "web_research",
        "report_generator",
    )

    def expand_query(self, question: str) -> str:
        q = (question or "").strip()
        if not q:
            return q

        # 1. Property valuation vocabulary normalization.
        #    City + context -> "{City} tehsil property valuation"
        q_lower = q.lower()
        city = detect_city(q_lower)
        if city is not None:
            if "tehsil" in q_lower and "valuation" in q_lower:
                pass  # already in canonical form
            elif any(
                term in q_lower
                for term in (
                    "valuation",
                    "property",
                    "value",
                    "values",
                    "district",
                )
            ):
                return f"{city} tehsil property valuation"

        # 2. Finance Act year abbreviation -> "Finance Act YYYY"
        if "finance act" not in q_lower:
            match = _FA_YEAR_RE.search(q)
            if match:
                year = match.group(1)
                q = _FA_YEAR_RE.sub(f"Finance Act {year}", q)

        return q
