"""
Calculation Agent (Phase 9 corrected).

Specialized calculation agent.

Its purpose is to handle questions where the user asks for an
actual calculation, computation, comparison, or numeric
derivation:

- tax calculation
- percentage calculation
- tax amount from taxable income
- sales tax calculation
- penalty calculation
- property valuation calculation when the required valuation
  evidence exists
- arithmetic based on retrieved FBR rules / rates
- lawful tax reduction / optimization analysis (Tax Reducer)

CRITICAL:
The Calculation Agent MUST NOT invent the rate or legal rule
needed for a calculation.

Correct flow:

  User question
    -> identify required legal/rate inputs
    -> RAG retrieves authoritative evidence
    -> verification validates those inputs
    -> calculation is performed deterministically
    -> answer includes the calculation basis and provenance

Arithmetic itself is deterministic Python logic where
possible, NOT delegated blindly to the LLM.

For ambiguous calculations, the agent returns the
insufficient-evidence behavior rather than guessing.
"""

from __future__ import annotations

import re
from typing import Any

from app.agents.base import SpecializedAgent
from app.rag_engine import _NO_EVIDENCE_ANSWER
from app.verification_layer import PLACEHOLDER_ANSWER

_AMOUNT_RE = re.compile(
    r"(\d[\d,]*\.?\d*)\s*(rs\.?|rupees|pkr)?",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", re.IGNORECASE)


def _to_float(token: str) -> float | None:
    cleaned = token.replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_calculation(question: str) -> dict[str, Any] | None:
    """
    Attempt to extract a deterministic calculation request
    from a free-form question.

    Returns a dict with:
      - kind: "percent_of_amount"
      - percent: float
      - amount: float
      - expression: human-readable form

    Returns None if no clear (amount, percent) pair is found.
    """

    q = (question or "").strip()
    if not q:
        return None

    percent_match = _PERCENT_RE.search(q)
    if not percent_match:
        return None
    percent = _to_float(percent_match.group(1))
    if percent is None:
        return None

    # Find amounts (prefer the largest one as the base amount).
    # Skip any numeric token that overlaps with the percent
    # match span so the percent itself is not picked up as the
    # amount (e.g. "calculate 10% tax" must not treat "10" as
    # both the percent and the amount).
    percent_span = (percent_match.start(), percent_match.end())
    amounts: list[float] = []
    for m in _AMOUNT_RE.finditer(q):
        m_start, m_end = m.start(), m.end()
        if m_start < percent_span[1] and m_end > percent_span[0]:
            continue
        n = _to_float(m.group(1))
        if n is not None and n > 0:
            amounts.append(n)
    if not amounts:
        return None
    amount = max(amounts)

    return {
        "kind": "percent_of_amount",
        "percent": percent,
        "amount": amount,
        "expression": f"{amount} x {percent}% = {amount * percent / 100.0}",
        "result": round(amount * percent / 100.0, 2),
    }


class CalculationAgent(SpecializedAgent):
    domain = "calculation"

    TOOLS = (
        "metadata_filter",
        "rag_search",
        "hybrid_search",
        "rule_engine",
        "calculation_engine",
        "tax_optimization",
    )

    def expand_query(self, question: str) -> str:
        # Calculation agent does NOT pre-expand the query: the
        # RAG engine still needs to see the original user
        # question to retrieve the rate/rule on which the
        # calculation depends.
        return question

    def handle(
        self,
        question: object,
        top_k: int = 5,
    ) -> dict:
        """
        Calculation-specific handle:

        1. Ask the existing RAG engine to retrieve the
           authoritative rate / rule.
        2. If RAG returns a grounded/verified answer, invoke the
           reusable calculation_engine tool (which reuses this
           module's _extract_calculation) for the deterministic
           Python calculation.
        3. If no rate is established by authoritative corpus
           evidence, return the safe-refusal path unchanged.
        4. Tax Reducer: when the deterministic tool plan selects
           tax_optimization, execute the registered tool through
           the same registry and attach its structured result
           additively; the canonical RAG response fields are
           never replaced.
        """

        original = str(question) if question is not None else ""
        retrieval_question = self.expand_query(original)

        tools_selected = self.select_tools(original)
        tools_used = [
            tool for tool in ("rag_search", "hybrid_search")
            if tool in self.TOOLS
        ]

        response = self.rag_engine.answer(
            retrieval_question, top_k=top_k
        )
        answer = response.get("answer", "")
        grounded = bool(response.get("grounded", False))

        # The RAG engine returns grounded=True for the verified
        # safe-refusal answer as well (the safe refusal IS the
        # verified answer when no evidence exists). The
        # Calculation Agent must never append a calculation
        # basis to a safe-refusal text, even when grounded.
        is_safe_refusal = (
            not answer
            or answer == _NO_EVIDENCE_ANSWER
            or answer == PLACEHOLDER_ANSWER
        )

        if not grounded or is_safe_refusal:
            return {
                "domain": self.domain,
                "question": original,
                "retrieval_question": retrieval_question,
                "answer": answer or _NO_EVIDENCE_ANSWER,
                "sources": response.get("sources", []),
                "verification": response.get("verification", {}),
                "grounded": False,
                "context": response.get("context", ""),
                "calculation": None,
                "tools_selected": tools_selected,
                "tools_used": tools_used,
            }

        # Invoke the reusable calculation_engine tool through the
        # tool registry. The tool reuses _extract_calculation, so
        # the outcome is identical to the previous direct call.
        from app.tools import get_default_registry

        tool_result = get_default_registry().execute(
            "calculation_engine",
            {"question": retrieval_question},
        )

        if tool_result.ok and isinstance(tool_result.data, dict):
            calc = tool_result.data.get("calculation")
        else:
            calc = None

        # Tax Reducer: when the deterministic tool plan selects
        # tax_optimization, ACTUALLY execute the registered tool
        # through the same registry (the established pattern
        # above). The natural-language request is converted to
        # the structured payload with the tool's own extractor;
        # the result is attached additively and the canonical
        # RAG response fields are never replaced. Queries without
        # a parseable tax-year/income payload are skipped, and
        # the tool itself refuses tax-evasion intent.
        tax_optimization_data = None
        if "tax_optimization" in tools_selected:
            from app.tools.tax_optimization import (
                extract_tax_reducer_payload,
            )

            tax_payload = extract_tax_reducer_payload(original)
            if tax_payload is not None:
                tax_result = get_default_registry().execute(
                    "tax_optimization", tax_payload
                )
                if tax_result.ok and isinstance(
                    tax_result.data, dict
                ):
                    tax_optimization_data = tax_result.data

        if calc is None:
            result = {
                "domain": self.domain,
                "question": original,
                "retrieval_question": retrieval_question,
                "answer": answer,
                "sources": response.get("sources", []),
                "verification": response.get("verification", {}),
                "grounded": grounded,
                "context": response.get("context", ""),
                "calculation": None,
                "tools_selected": tools_selected,
                "tools_used": tools_used,
            }
            if tax_optimization_data is not None:
                result["tax_optimization"] = tax_optimization_data
                result["tools_used"] = list(
                    result["tools_used"]
                ) + ["tax_optimization"]
            return result

        # If grounded but no numeric parse is possible, the
        # safe-refusal path still applies; otherwise we expose
        # the calculation basis + result.
        tools_used = tools_used + ["calculation_engine"]

        result = {
            "domain": self.domain,
            "question": original,
            "retrieval_question": retrieval_question,
            "answer": (
                f"{answer}\n\n"
                f"Calculation basis: {calc['expression']}\n"
                f"Result: {calc['result']}"
            ),
            "sources": response.get("sources", []),
            "verification": response.get("verification", {}),
            "grounded": grounded,
            "context": response.get("context", ""),
            "calculation": calc,
            "tools_selected": tools_selected,
            "tools_used": tools_used,
        }
        if tax_optimization_data is not None:
            result["tax_optimization"] = tax_optimization_data
            result["tools_used"] = list(
                result["tools_used"]
            ) + ["tax_optimization"]
        return result
