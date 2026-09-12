"""
Specialized Agent base class (Phase 9 corrected, 9-agent
architecture).

Every specialized agent:

1. belongs to exactly one FBR domain,
2. optionally applies deterministic domain-aware query expansion,
3. calls the EXISTING Phase 7 FBRRAGEngine (retrieval + LLM +
   verification + safe fallback),
4. returns the RAG response unchanged in substance, augmented
   only with routing metadata (domain, retrieval_question).

Agents NEVER:
- search the raw corpus directly,
- build their own vector store,
- bypass the verification layer,
- expose an unverified LLM answer.

All agents can share a single FBRRAGEngine instance (one FAISS
load) by passing rag_engine to the constructor.

The 9 required agents are:
  1. IncomeTaxAgent       (income_tax)
  2. SalesTaxAgent        (sales_tax)
  3. FederalExciseAgent   (federal_excise)
  4. CustomsAgent         (customs)
  5. RegistrationAgent    (registration)
  6. ReturnFilingAgent    (return_filing)
  7. CalculationAgent     (calculation)
  8. NoticeAppealAgent    (notice_appeal)
  9. ResearchAgent        (research)
"""

from __future__ import annotations

from typing import Any

from app.rag_engine import DEFAULT_TOP_K

# ============================================================
# TOOL SELECTION (deterministic, application-controlled)
# ============================================================

# Core capabilities exercised by every agent handle() call through
# the shared RAG engine (hybrid retrieval + verified answer).
_CORE_TOOLS = ("rag_search", "hybrid_search")

# Deterministic keyword signals for optional tools. Tool selection
# is pure application logic — never LLM-driven, never arbitrary.
_TOOL_KEYWORD_SIGNALS: dict[str, tuple[str, ...]] = {
    "web_research": (
        "current", "latest", "today", "recent", "updated", "update",
    ),
    "report_generator": (
        "report", "summarize", "summary", "overview",
    ),
    "document_parser": (
        "notice", "letter", "attachment", "document", "received",
    ),
    "rule_engine": (
        "appeal", "deadline", "penalt", "revise", "compliance",
    ),
    "similarity_engine": (
        "similar", "compare", "difference between",
    ),
    "duplicate_detection": ("duplicate",),
    "anomaly_detection": ("anomaly", "inconsisten"),
    "notification": ("remind", "alert", "notification"),
    "tax_optimization": (
        "reduce tax", "tax reduction", "tax saving", "save tax",
        "minimize tax", "optimize tax", "tax optimization",
        "tax planning", "lower tax", "tax reducer",
    ),
}


class SpecializedAgent:
    """
    Base class for all specialized FBR agents.
    """

    domain: str = ""

    # Reusable tools this agent is allowed to use (capability
    # mapping; see app/tools for the registry).
    TOOLS: tuple[str, ...] = ()

    def __init__(self, rag_engine: Any | None = None):
        self._rag_engine = rag_engine

    @property
    def rag_engine(self):
        """
        Lazily construct the canonical RAG engine when no shared
        instance was provided.
        """

        if self._rag_engine is None:
            from app.rag_engine import FBRRAGEngine

            self._rag_engine = FBRRAGEngine()
        return self._rag_engine

    def expand_query(self, question: str) -> str:
        """
        Deterministic domain-aware query expansion.

        Default: no expansion. Subclasses override to add
        domain-specific retrieval guidance. The expanded string
        is ONLY used as the retrieval/LLM question; the original
        user question is always preserved in the response.
        """

        return question

    def select_tools(self, question: str) -> list[str]:
        """
        Deterministic tool selection for one query.

        Application logic only: core tools (exercised by the RAG
        pipeline) are always selected when the agent has them;
        optional tools are selected when a deterministic query
        signal fires. Only tools declared in this agent's TOOLS
        can ever be selected.
        """

        selected = [
            tool for tool in _CORE_TOOLS if tool in self.TOOLS
        ]

        text = str(question or "").lower()

        from app.query_understanding import classify_query

        classification = classify_query(text)

        has_numbers = bool(
            classification.percentages or classification.amounts
        )

        has_structure = bool(
            classification.section_references
            or classification.tax_year
        )

        for tool in self.TOOLS:
            if tool in selected:
                continue

            if tool == "calculation_engine" and has_numbers:
                selected.append(tool)
                continue

            if tool == "metadata_filter" and has_structure:
                selected.append(tool)
                continue

            signals = _TOOL_KEYWORD_SIGNALS.get(tool, ())

            if signals and any(
                signal in text for signal in signals
            ):
                selected.append(tool)

        return selected

    def handle(
        self,
        question: object,
        top_k: int = DEFAULT_TOP_K,
    ) -> dict:
        """
        Run the full existing RAG pipeline for this domain.

        Returns a dict with the canonical RAG response fields
        (answer, sources, verification, grounded, context) plus:

        - domain: this agent's domain tag
        - question: the original user question
        - retrieval_question: the (possibly expanded) question
          actually sent to the RAG engine
        - tools_selected: deterministic tool plan for this query
        - tools_used: tools actually exercised by this call
        """

        original = str(question) if question is not None else ""
        retrieval_question = self.expand_query(original)

        tools_selected = self.select_tools(original)

        # The RAG engine call exercises the retrieval tools the
        # agent declares (hybrid retrieval + verified answer).
        tools_used = [
            tool for tool in _CORE_TOOLS if tool in self.TOOLS
        ]

        response = self.rag_engine.answer(
            retrieval_question, top_k=top_k
        )

        return {
            "domain": self.domain,
            "question": original,
            "retrieval_question": retrieval_question,
            "answer": response.get("answer", ""),
            "sources": response.get("sources", []),
            "verification": response.get("verification", {}),
            "grounded": bool(response.get("grounded", False)),
            "context": response.get("context", ""),
            "tools_selected": tools_selected,
            "tools_used": tools_used,
        }
