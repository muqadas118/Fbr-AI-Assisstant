"""
Income Tax Agent (Phase 9).

Scope:
- Income Tax Ordinance 2001
- income tax rules/provisions
- returns
- registration
- withholding
- assessments
- penalties relating to income tax
- relevant Finance Act amendments affecting income tax
- lawful tax reduction / optimization analysis (Tax Reducer)

Deterministic query expansion: when the query references a bare
section number without naming any law, append the Income Tax
Ordinance 2001 qualifier so exact-section retrieval resolves to
the Income Tax Ordinance instead of remaining ambiguous. When the
query asks about salaried income-tax rates/slabs in natural
language (without a section number or another-domain/withholding
intent), append First Schedule Part I corpus vocabulary so hybrid
retrieval surfaces the authoritative slab table instead of WHT
rate cards or budget teasers.

Tax Reducer integration (same pattern as CalculationAgent):
when the deterministic tool plan selects tax_optimization for a
grounded, non-refusal response, the reusable tax_optimization
tool is executed through the registry and its structured result
is attached additively as `tax_optimization`. The canonical RAG
response fields are never replaced; the tool result is refused
when the request carries tax-evasion intent.
"""

from __future__ import annotations

import re

from app.agents.base import SpecializedAgent

_SECTION_RE = re.compile(r"\bsection\s+\d+\b", re.IGNORECASE)

# Salary-slab signals: natural-language questions about salaried
# income-tax rates (e.g. "income tax rate for salaried individuals")
# otherwise retrieve WHT rate cards / budget teasers instead of the
# authoritative First Schedule Part I slab table, because bare table
# chunks carry almost none of the query vocabulary.
_SALARY_RE = re.compile(r"\bsalaried\b|\bsalary\b", re.IGNORECASE)
_SLAB_RATE_RE = re.compile(r"\brates?\b|\bslabs?\b", re.IGNORECASE)

# Queries carrying these intents must NOT receive slab expansion:
# another tax domain, an already-qualified First Schedule reference,
# or a withholding (section 149 deduction-at-source) question whose
# answer lives in the WHT cards, not the slab table.
_NON_SLAB_TERMS: tuple[str, ...] = (
    "sales tax",
    "salestax",
    "sales-tax",
    "federal excise",
    "customs",
    "property valuation",
    "immovable property",
    "withholding",
    "wht",
    "withheld",
    "first schedule",
)

_OTHER_LAW_TERMS: tuple[str, ...] = (
    "income tax",
    "incometax",
    "income-tax",
    "sales tax",
    "salestax",
    "federal excise",
    "finance act",
    "property valuation",
    "immovable property",
)


class IncomeTaxAgent(SpecializedAgent):
    domain = "income_tax"

    TOOLS = (
        "rag_search",
        "hybrid_search",
        "metadata_filter",
        "rule_engine",
        "calculation_engine",
        "tax_optimization",
    )

    def expand_query(self, question: str) -> str:
        q = (question or "").strip()
        if not q:
            return q
        q_lower = q.lower()
        if _SECTION_RE.search(q) and not any(
            term in q_lower for term in _OTHER_LAW_TERMS
        ):
            return f"{q} under the Income Tax Ordinance 2001"
        if (
            _SALARY_RE.search(q)
            and _SLAB_RATE_RE.search(q)
            and not any(term in q_lower for term in _NON_SLAB_TERMS)
        ):
            return (
                f"{q} under the Income Tax Ordinance 2001 "
                "First Schedule Part I salary rates table where "
                "income chargeable under the head salary exceeds "
                "seventy-five per cent"
            )
        return q

    def handle(
        self,
        question: object,
        top_k: int = 5,
    ) -> dict:
        from app.rag_engine import _NO_EVIDENCE_ANSWER
        from app.tools import get_default_registry
        from app.tools.tax_optimization import (
            extract_tax_reducer_payload,
        )
        from app.verification_layer import PLACEHOLDER_ANSWER

        result = super().handle(question, top_k=top_k)

        if "tax_optimization" not in result.get(
            "tools_selected", []
        ):
            return result

        answer = result.get("answer", "")
        grounded = bool(result.get("grounded", False))

        is_safe_refusal = (
            not answer
            or answer == _NO_EVIDENCE_ANSWER
            or answer == PLACEHOLDER_ANSWER
        )

        if not grounded or is_safe_refusal:
            return result

        original = str(question) if question is not None else ""
        payload = extract_tax_reducer_payload(original)

        if payload is None:
            return result

        tool_result = get_default_registry().execute(
            "tax_optimization", payload
        )

        if tool_result.ok and isinstance(tool_result.data, dict):
            result["tax_optimization"] = tool_result.data
            result["tools_used"] = list(
                result.get("tools_used", [])
            ) + ["tax_optimization"]

        return result
