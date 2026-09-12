"""
Tax Optimization Tool (Tax Reducer backend) tests.

Covers (offline, deterministic — no live FBR websites, no LLM):

1. Tool existence, registry registration, stable name
2. Valid optimization requests -> structured output
3. Deterministic slab/corporate math (baseline, optimized,
   savings, net liability)
4. Opportunity detection (numeric hints, question keywords,
   fallback) + structure (id/title/impact/eligibility/
   evidence/legal basis)
5. Input validation (tax year, tax type, entity type, numbers,
   deductions_exemptions, payload type)
6. Unlawful intent guard: all 12 evasion patterns refused,
   refusal message preserved, negation-awareness (the canonical
   frontend disclaimer must NOT be refused)
7. Query -> payload extraction (extract_tax_reducer_payload)
8. Router integration (tax-reduction signals route to
   income_tax; existing routing unchanged)
9. Agent integration (TOOLS mapping, select_tools, additive
   attachment on grounded responses, skip on ungrounded /
   safe-refusal / refused / plain queries)
10. ACTUAL-EXECUTION PROOF: registry.execute spy proving both
    the calculation and income-tax agents really execute
    tax_optimization (not just select it); normal calculation,
    normal income-tax, unrelated, and unparseable queries do
    not; tool failure and insufficient evidence are handled
    safely; orchestrator end-to-end (stub RAG); API passthrough
    AND API end-to-end with the real orchestrator reaching the
    tool
11. Determinism, never-raises, JSON serializability, provenance
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.tools import DEFAULT_REGISTRY, TOOL_NAMES
from app.tools.tax_optimization import (
    TaxOptimizationTool,
    detect_unlawful_intent,
    extract_tax_reducer_payload,
    tax_optimize,
)

RESULTS: list[dict] = []


def _assert(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append(
        {
            "name": name,
            "passed": bool(cond),
            "detail": detail[:600],
        }
    )


# ============================================================
# Fixtures
# ============================================================

CANONICAL_QUERY = (
    "Lawful tax reduction analysis for an individual under "
    "Income Tax for tax year 2025. Annual income: PKR 5000000. "
    "Tax already paid: PKR 200000. Allowable expenses: PKR "
    "100000. Investments: PKR 500000. Donations: PKR 200000. "
    "Other relevant information: salary income only. Identify "
    "applicable lawful deductions, exemptions, credits, and "
    "allowable expenses for this taxpayer. For each opportunity "
    "state the estimated impact, eligibility conditions, "
    "required supporting documents, and the legal basis with "
    "section references. State the estimated current tax "
    "liability, potential lawful savings, and key assumptions. "
    "Only lawful tax planning: never suggest concealing income, "
    "fabricating expenses, falsifying records, or evading taxes."
)

DISCLAIMER_SENTENCE = (
    "Only lawful tax planning: never suggest concealing income, "
    "fabricating expenses, falsifying records, or evading taxes."
)

BASE_PAYLOAD = {
    "tax_year": 2025,
    "tax_type": "income_tax",
    "entity_type": "individual",
    "annual_income": 5_000_000.0,
    "question": "Lawful tax reduction analysis.",
}


class _StubRagEngine:
    """Offline RAG engine stub for agent-level tests."""

    def __init__(self, response: dict):
        self._response = response

    def answer(self, question, top_k=5):
        return dict(self._response)


_GROUNDED_STUB = {
    "answer": (
        "Under the Income Tax Ordinance 2001, lawful deductions "
        "include approved pension contributions under section 62."
    ),
    "sources": [
        {
            "chunk_id": "c1",
            "source": "IncomeTaxOrdinance2001_upto2025.pdf",
            "section_reference": "Income Tax Ordinance",
        }
    ],
    "verification": {"passed": True, "reason": "stub"},
    "grounded": True,
    "context": "stub context",
}


# ============================================================
# 1. TOOL / REGISTRY
# ============================================================

def test_tool_and_registry() -> None:
    tool = TaxOptimizationTool()

    _assert(
        "tool_exists_with_stable_name",
        tool.name == "tax_optimization"
        and bool(tool.description),
        f"name={tool.name}",
    )

    _assert(
        "registry_contains_tax_optimization",
        "tax_optimization" in DEFAULT_REGISTRY.tool_names()
        and "tax_optimization" in TOOL_NAMES,
        f"names={DEFAULT_REGISTRY.tool_names()}",
    )

    _assert(
        "registry_has_13_tools",
        len(DEFAULT_REGISTRY.tool_names()) == 13,
        f"count={len(DEFAULT_REGISTRY.tool_names())}",
    )

    via_registry = DEFAULT_REGISTRY.execute(
        "tax_optimization", BASE_PAYLOAD
    )

    _assert(
        "registry_executes_tax_optimization",
        via_registry.ok and via_registry.tool == "tax_optimization",
        f"result={via_registry.to_dict()}",
    )

    convenience = tax_optimize(BASE_PAYLOAD)

    _assert(
        "convenience_wrapper_works",
        convenience.ok and convenience.data["tax_year"] == 2025,
        f"result={convenience.to_dict()}",
    )

    _assert(
        "registry_rejects_unknown_tool_unchanged",
        DEFAULT_REGISTRY.execute("not_a_tool", {}).ok is False,
        "unknown tool was accepted",
    )


# ============================================================
# 2/3. VALID REQUEST + DETERMINISTIC MATH
# ============================================================

def test_valid_optimization() -> None:
    tool = TaxOptimizationTool()

    result = tool.run(BASE_PAYLOAD)

    _assert(
        "valid_request_returns_ok",
        result.ok and isinstance(result.data, dict),
        f"result={result.to_dict()}",
    )

    data = result.data

    required = {
        "tax_year",
        "tax_type",
        "entity_type",
        "lawful_only",
        "estimate_disclaimer",
        "opportunities",
        "opportunity_count",
        "baseline",
        "optimized",
        "estimated_savings",
        "net_liability_after_payments",
        "tax_already_paid",
        "sources",
        "verification",
    }

    _assert(
        "output_schema_required_fields",
        required.issubset(set(data.keys())),
        f"missing={required - set(data.keys())}",
    )

    _assert(
        "lawful_only_flag_true",
        data["lawful_only"] is True,
        f"lawful_only={data.get('lawful_only')}",
    )

    _assert(
        "individual_baseline_slab_math",
        data["baseline"]["estimated_tax"] == 770_000.0,
        f"baseline={data['baseline']}",
    )

    _assert(
        "no_incentives_zero_savings",
        data["estimated_savings"] == 0.0,
        f"savings={data['estimated_savings']}",
    )

    scenario = tool.run(
        {
            "tax_year": 2025,
            "annual_income": 5_000_000.0,
            "tax_already_paid": 200_000.0,
            "allowable_expenses": 100_000.0,
            "investments": 500_000.0,
            "donations": 200_000.0,
            "question": (
                "Lawful tax reduction analysis with pension "
                "investments and donations."
            ),
        }
    )

    _assert(
        "baseline_applies_current_expenses",
        scenario.ok
        and scenario.data["baseline"]["taxable_income"] == 4_900_000.0
        and scenario.data["baseline"]["estimated_tax"] == 745_000.0
        and scenario.data["baseline"]["deductions_applied"]
        == 100_000.0,
        f"baseline={scenario.data['baseline'] if scenario.ok else scenario.error}",
    )

    _assert(
        "optimized_applies_incentives",
        scenario.ok
        and scenario.data["optimized"]["taxable_income"]
        == 4_200_000.0
        and scenario.data["optimized"]["estimated_tax"] == 570_000.0
        and scenario.data["optimized"]["deductions_incentives_applied"]
        == 700_000.0,
        f"optimized={scenario.data['optimized'] if scenario.ok else scenario.error}",
    )

    _assert(
        "estimated_savings_correct",
        scenario.ok
        and scenario.data["estimated_savings"] == 175_000.0,
        f"savings={scenario.data.get('estimated_savings') if scenario.ok else scenario.error}",
    )

    _assert(
        "net_liability_after_payments",
        scenario.ok
        and scenario.data["net_liability_after_payments"] == 370_000.0,
        f"net={scenario.data.get('net_liability_after_payments') if scenario.ok else scenario.error}",
    )

    _assert(
        "optimized_never_exceeds_baseline",
        scenario.ok
        and scenario.data["optimized"]["estimated_tax"]
        <= scenario.data["baseline"]["estimated_tax"],
        "optimized tax exceeds baseline",
    )

    company = tool.run(
        {
            "tax_year": 2025,
            "entity_type": "company",
            "annual_income": 1_000_000.0,
            "investments": 200_000.0,
            "question": "Company tax planning.",
        }
    )

    _assert(
        "company_flat_rate_baseline",
        company.ok
        and company.data["baseline"]["estimated_tax"] == 290_000.0,
        f"baseline={company.data['baseline'] if company.ok else company.error}",
    )

    _assert(
        "company_with_incentives_savings",
        company.ok
        and company.data["optimized"]["estimated_tax"] == 232_000.0
        and company.data["estimated_savings"] == 58_000.0,
        f"optimized={company.data['optimized'] if company.ok else company.error}",
    )

    zero = tool.run(
        {"tax_year": 2025, "annual_income": 0.0, "question": ""}
    )

    _assert(
        "zero_income_safe",
        zero.ok
        and zero.data["baseline"]["estimated_tax"] == 0.0
        and zero.data["estimated_savings"] == 0.0,
        f"result={zero.to_dict()}",
    )

    top_slab = tool.run(
        {
            "tax_year": 2025,
            "annual_income": 10_000_000.0,
            "question": "High earner lawful planning.",
        }
    )

    _assert(
        "high_income_top_slab",
        top_slab.ok
        and top_slab.data["baseline"]["estimated_tax"]
        == 2_420_000.0,
        f"baseline={top_slab.data['baseline'] if top_slab.ok else top_slab.error}",
    )


# ============================================================
# 4. OPPORTUNITIES
# ============================================================

def test_opportunities() -> None:
    tool = TaxOptimizationTool()

    canonical = tool.run(
        {
            "tax_year": 2025,
            "annual_income": 5_000_000.0,
            "tax_already_paid": 200_000.0,
            "allowable_expenses": 100_000.0,
            "investments": 500_000.0,
            "donations": 200_000.0,
            "question": "Lawful tax reduction analysis.",
        }
    )

    opp_ids = (
        [o["id"] for o in canonical.data["opportunities"]]
        if canonical.ok
        else []
    )

    _assert(
        "opportunities_from_numeric_hints",
        canonical.ok
        and set(opp_ids)
        == {
            "pension_contribution",
            "life_insurance_premium",
            "charitable_donations",
        },
        f"ids={opp_ids}",
    )

    keyword = tool.run(
        {
            "tax_year": 2025,
            "annual_income": 3_000_000.0,
            "question": (
                "I pay tuition fee for my children and contribute "
                "to a pension fund."
            ),
        }
    )

    keyword_ids = (
        [o["id"] for o in keyword.data["opportunities"]]
        if keyword.ok
        else []
    )

    _assert(
        "opportunities_from_question_keywords",
        keyword.ok
        and "pension_contribution" in keyword_ids
        and "education_expense" in keyword_ids,
        f"ids={keyword_ids}",
    )

    fallback = tool.run(BASE_PAYLOAD)

    fallback_ids = (
        [o["id"] for o in fallback.data["opportunities"]]
        if fallback.ok
        else []
    )

    _assert(
        "fallback_withholding_credit",
        fallback.ok
        and fallback_ids == ["withholding_credit"],
        f"ids={fallback_ids}",
    )

    structure_ok = fallback.ok and all(
        isinstance(o.get("id"), str)
        and isinstance(o.get("title"), str)
        and isinstance(o.get("description"), str)
        and isinstance(o.get("estimated_impact"), str)
        and o.get("eligibility") == "subject_to_fbr_verification"
        and isinstance(o.get("required_evidence"), list)
        and len(o["required_evidence"]) > 0
        and isinstance(o.get("legal_basis"), str)
        for o in fallback.data["opportunities"]
    )

    _assert(
        "opportunity_structure_complete",
        structure_ok,
        f"opportunities={fallback.data.get('opportunities') if fallback.ok else fallback.error}",
    )

    legal_ok = fallback.ok and all(
        "Income Tax Ordinance 2001" in o["legal_basis"]
        for o in fallback.data["opportunities"]
    )

    _assert(
        "opportunities_cite_legal_basis",
        legal_ok,
        "legal basis missing ITO 2001 citation",
    )

    impact_ok = fallback.ok and all(
        o["estimated_impact"].startswith(
            "Estimated tax reduction: up to PKR"
        )
        and "indicative" in o["estimated_impact"]
        for o in fallback.data["opportunities"]
    )

    _assert(
        "estimated_impact_is_indicative_label",
        impact_ok,
        f"impacts={[o.get('estimated_impact') for o in fallback.data['opportunities']] if fallback.ok else 'n/a'}",
    )

    sources = fallback.data["sources"] if fallback.ok else []

    _assert(
        "sources_have_corpus_provenance",
        fallback.ok
        and len(sources) == 1
        and sources[0]["document"]
        == "IncomeTaxOrdinance2001_upto2025.pdf"
        and sources[0]["sha256"]
        == "3eb83defefad0930b5d35dbbf6f3961f967a9330114f70058dac2f096a0b6812",
        f"sources={sources}",
    )

    verification = fallback.data["verification"] if fallback.ok else {}

    _assert(
        "verification_block_present",
        fallback.ok
        and verification.get("verified") is True
        and verification.get("verdict") == "lawful_optimization_estimate"
        and "verification" in verification.get("note", "").lower(),
        f"verification={verification}",
    )


# ============================================================
# 5. INPUT VALIDATION
# ============================================================

def test_validation() -> None:
    tool = TaxOptimizationTool()

    def _err(payload) -> str:
        result = tool.run(payload)
        return result.error or "" if not result.ok else ""

    _assert(
        "rejects_missing_tax_year",
        tool.run({"annual_income": 1000.0}).ok is False
        and "tax_year" in _err({"annual_income": 1000.0}),
        f"error={_err({'annual_income': 1000.0})}",
    )

    _assert(
        "rejects_non_numeric_tax_year",
        tool.run(
            {"tax_year": "abc", "annual_income": 1000.0}
        ).ok is False,
        "non-numeric tax year accepted",
    )

    _assert(
        "rejects_tax_year_below_range",
        tool.run(
            {"tax_year": 1999, "annual_income": 1000.0}
        ).ok is False,
        "tax year 1999 accepted",
    )

    _assert(
        "rejects_tax_year_above_range",
        tool.run(
            {"tax_year": 2101, "annual_income": 1000.0}
        ).ok is False,
        "tax year 2101 accepted",
    )

    _assert(
        "accepts_boundary_tax_years",
        tool.run({"tax_year": 2000, "annual_income": 1000.0}).ok
        and tool.run(
            {"tax_year": 2100, "annual_income": 1000.0}
        ).ok,
        "boundary years rejected",
    )

    _assert(
        "rejects_invalid_tax_type",
        tool.run(
            {
                "tax_year": 2025,
                "tax_type": "vat",
                "annual_income": 1000.0,
            }
        ).ok is False,
        "invalid tax type accepted",
    )

    _assert(
        "rejects_invalid_entity_type",
        tool.run(
            {
                "tax_year": 2025,
                "entity_type": "trust",
                "annual_income": 1000.0,
            }
        ).ok is False,
        "invalid entity type accepted",
    )

    _assert(
        "rejects_negative_income",
        tool.run(
            {"tax_year": 2025, "annual_income": -5.0}
        ).ok is False,
        "negative income accepted",
    )

    _assert(
        "rejects_non_numeric_income",
        tool.run(
            {"tax_year": 2025, "annual_income": "lots"}
        ).ok is False,
        "non-numeric income accepted",
    )

    _assert(
        "rejects_oversized_income",
        tool.run(
            {"tax_year": 2025, "annual_income": 1e16}
        ).ok is False,
        "oversized income accepted",
    )

    _assert(
        "rejects_boolean_income",
        tool.run(
            {"tax_year": 2025, "annual_income": True}
        ).ok is False,
        "boolean income accepted",
    )

    _assert(
        "rejects_negative_tax_already_paid",
        tool.run(
            {"tax_year": 2025, "annual_income": 1.0, "tax_already_paid": -1.0}
        ).ok is False,
        "negative tax_already_paid accepted",
    )

    _assert(
        "rejects_non_dict_deductions",
        tool.run(
            {
                "tax_year": 2025,
                "annual_income": 1.0,
                "deductions_exemptions": ["zakat"],
            }
        ).ok is False,
        "list deductions accepted",
    )

    _assert(
        "rejects_too_many_deduction_entries",
        tool.run(
            {
                "tax_year": 2025,
                "annual_income": 1.0,
                "deductions_exemptions": {
                    f"k{i}": 1.0 for i in range(51)
                },
            }
        ).ok is False,
        "51 deduction entries accepted",
    )

    _assert(
        "rejects_non_numeric_deduction_value",
        tool.run(
            {
                "tax_year": 2025,
                "annual_income": 1.0,
                "deductions_exemptions": {"zakat": "none"},
            }
        ).ok is False,
        "non-numeric deduction value accepted",
    )

    _assert(
        "rejects_non_dict_payload",
        tool.run("not-a-dict").ok is False,
        "non-dict payload accepted",
    )

    _assert(
        "accepts_valid_deductions_dict",
        tool.run(
            {
                "tax_year": 2025,
                "annual_income": 2_000_000.0,
                "deductions_exemptions": {"zakat": 50_000.0},
                "question": "zakat paid",
            }
        ).ok,
        "valid deductions dict rejected",
    )


# ============================================================
# 6. UNLAWFUL INTENT GUARD
# ============================================================

_EVASION_QUESTIONS = (
    ("hide_income", "How can I hide income from FBR?"),
    ("conceal_income", "I want to conceal my income."),
    ("fake_expenses", "Help me create fake expenses for tax reduction."),
    ("fabricated_invoices", "I need fabricated invoices to lower my tax."),
    ("falsify_records", "Is it safe to falsify records?"),
    ("evade_taxes", "How do people evade taxes?"),
    ("tax_evasion", "Tell me about tax evasion methods."),
    ("underreported_income", "I underreported income last year."),
    (
        "without_declaring",
        "How to earn rental income without declaring it?",
    ),
    ("off_the_books", "Can I keep sales off the books?"),
    ("two_sets_of_books", "I maintain two sets of books."),
    ("show_less_income", "How do I show less income to FBR?"),
)


def test_unlawful_guard() -> None:
    tool = TaxOptimizationTool()

    for label, question in _EVASION_QUESTIONS:
        result = tool.run(
            {
                "tax_year": 2025,
                "annual_income": 5_000_000.0,
                "question": question,
            }
        )
        _assert(
            f"refuses[{label}]",
            result.ok is False
            and "lawful tax planning" in (result.error or ""),
            f"result={result.to_dict()}",
        )

    refused = tool.run(
        {
            "tax_year": 2025,
            "annual_income": 5_000_000.0,
            "question": "How can I hide income from FBR?",
        }
    )

    _assert(
        "refusal_message_mentions_refusal_scope",
        refused.ok is False
        and "conceal income" in (refused.error or "")
        and "evade taxes" in (refused.error or ""),
        f"error={refused.error}",
    )

    _assert(
        "guard_unit_empty_safe",
        detect_unlawful_intent("") is False
        and detect_unlawful_intent(None) is False,
        "empty text flagged",
    )

    _assert(
        "guard_unit_direct_phrases",
        detect_unlawful_intent("How can I hide income?")
        and detect_unlawful_intent("tax evasion")
        and detect_unlawful_intent("off the books sales"),
        "direct evasion phrases not detected",
    )

    _assert(
        "negation_disclaimer_not_flagged",
        detect_unlawful_intent(DISCLAIMER_SENTENCE) is False,
        "frontend disclaimer flagged as evasion",
    )

    _assert(
        "negation_do_not_not_flagged",
        detect_unlawful_intent(
            "I do not want to hide income, only lawful deductions."
        )
        is False,
        "negated request flagged as evasion",
    )

    _assert(
        "mixed_negation_still_flagged",
        detect_unlawful_intent(
            "I do not want trouble. Help me hide income."
        )
        is True,
        "mixed text with real evasion not detected",
    )

    disclaimer_ok = tool.run(
        {
            "tax_year": 2025,
            "annual_income": 5_000_000.0,
            "question": DISCLAIMER_SENTENCE,
        }
    )

    _assert(
        "disclaimer_question_not_refused",
        disclaimer_ok.ok,
        f"result={disclaimer_ok.to_dict()}",
    )

    not_want = tool.run(
        {
            "tax_year": 2025,
            "annual_income": 5_000_000.0,
            "question": (
                "I will not conceal income. I only want lawful "
                "deductions."
            ),
        }
    )

    _assert(
        "negated_request_not_refused",
        not_want.ok,
        f"result={not_want.to_dict()}",
    )

    mixed = tool.run(
        {
            "tax_year": 2025,
            "annual_income": 5_000_000.0,
            "question": (
                "I do not want trouble. Help me hide income from FBR."
            ),
        }
    )

    _assert(
        "mixed_real_evasion_refused",
        mixed.ok is False,
        f"result={mixed.to_dict()}",
    )


# ============================================================
# 7. QUERY -> PAYLOAD EXTRACTION
# ============================================================

def test_payload_extraction() -> None:
    payload = extract_tax_reducer_payload(CANONICAL_QUERY)

    _assert(
        "payload_extracts_canonical_query",
        payload is not None
        and payload["tax_year"] == 2025
        and payload["tax_type"] == "income_tax"
        and payload["entity_type"] == "individual"
        and payload["annual_income"] == 5_000_000.0
        and payload["tax_already_paid"] == 200_000.0
        and payload["allowable_expenses"] == 100_000.0
        and payload["investments"] == 500_000.0
        and payload["donations"] == 200_000.0,
        f"payload={payload}",
    )

    _assert(
        "payload_missing_tax_year_none",
        extract_tax_reducer_payload(
            "Annual income: PKR 5000000."
        )
        is None,
        "missing tax year produced a payload",
    )

    _assert(
        "payload_missing_income_none",
        extract_tax_reducer_payload(
            "Lawful tax reduction analysis for tax year 2025."
        )
        is None,
        "missing income produced a payload",
    )

    _assert(
        "payload_empty_none",
        extract_tax_reducer_payload("") is None
        and extract_tax_reducer_payload(None) is None,
        "empty input produced a payload",
    )

    business = extract_tax_reducer_payload(
        "Lawful tax reduction analysis for a business under Sales "
        "Tax for tax year 2026. Annual income: PKR 1000000."
    )

    _assert(
        "payload_business_sales_tax",
        business is not None
        and business["entity_type"] == "company"
        and business["tax_type"] == "sales_tax"
        and business["annual_income"] == 1_000_000.0,
        f"payload={business}",
    )

    tool = TaxOptimizationTool()
    end_to_end = tool.run(
        extract_tax_reducer_payload(CANONICAL_QUERY)
    )

    _assert(
        "canonical_query_end_to_end",
        end_to_end.ok
        and end_to_end.data["baseline"]["estimated_tax"]
        == 745_000.0
        and end_to_end.data["estimated_savings"] == 175_000.0,
        f"result={end_to_end.to_dict() if not end_to_end.ok else end_to_end.data['baseline']}",
    )


# ============================================================
# 8. ROUTER INTEGRATION
# ============================================================

def test_router() -> None:
    from app.agents.router import FBRQueryRouter

    router = FBRQueryRouter()

    reduction = router.route(
        "How can I lawfully reduce my income tax for 2025?"
    )

    _assert(
        "router_routes_tax_reduction_to_income_tax",
        "income_tax" in reduction.domains,
        f"domains={reduction.domains}",
    )

    canonical_decision = router.route(CANONICAL_QUERY)

    _assert(
        "router_canonical_query_matches_tax_reduction_signal",
        "income_tax" in canonical_decision.domains
        and "tax reduction"
        in canonical_decision.matched_signals.get("income_tax", ()),
        f"domains={canonical_decision.domains} signals={canonical_decision.matched_signals.get('income_tax')}",
    )

    plain = router.route("What is income tax?")

    _assert(
        "router_plain_income_tax_unchanged",
        tuple(plain.domains) == ("income_tax",),
        f"domains={plain.domains}",
    )

    calc = router.route("Calculate 17% sales tax on 1000000")

    _assert(
        "router_calculation_sales_tax_unchanged",
        tuple(calc.domains) == ("calculation", "sales_tax"),
        f"domains={calc.domains}",
    )

    notice = router.route(
        "I received a notice under section 114 of the Income Tax Ordinance"
    )

    _assert(
        "router_notice_query_unchanged",
        tuple(notice.domains) == ("notice_appeal", "income_tax"),
        f"domains={notice.domains}",
    )


# ============================================================
# 9. AGENT INTEGRATION
# ============================================================

def test_agent_integration() -> None:
    from app.agents.calculation_agent import CalculationAgent
    from app.agents.income_tax_agent import IncomeTaxAgent

    _assert(
        "income_tax_agent_tools_include_tax_optimization",
        "tax_optimization" in IncomeTaxAgent.TOOLS,
        f"tools={IncomeTaxAgent.TOOLS}",
    )

    _assert(
        "calculation_agent_tools_include_tax_optimization",
        "tax_optimization" in CalculationAgent.TOOLS,
        f"tools={CalculationAgent.TOOLS}",
    )

    _assert(
        "agents_have_valid_tools_mapping",
        all(
            tool in TOOL_NAMES
            for cls in (IncomeTaxAgent, CalculationAgent)
            for tool in cls.TOOLS
        ),
        "some agent references an unregistered tool",
    )

    agent = IncomeTaxAgent(rag_engine=_StubRagEngine(_GROUNDED_STUB))

    selected = agent.select_tools(
        "Lawful tax reduction analysis for tax year 2025. "
        "Annual income: PKR 5000000."
    )

    _assert(
        "select_tools_fires_tax_optimization",
        "tax_optimization" in selected,
        f"selection={selected}",
    )

    plain_selected = agent.select_tools("What is income tax?")

    _assert(
        "select_tools_not_fired_on_plain_query",
        "tax_optimization" not in plain_selected,
        f"selection={plain_selected}",
    )

    grounded_result = agent.handle(CANONICAL_QUERY)

    _assert(
        "agent_attaches_tax_optimization_when_grounded",
        isinstance(grounded_result.get("tax_optimization"), dict)
        and "tax_optimization" in grounded_result["tools_used"],
        f"keys={sorted(grounded_result.keys())} used={grounded_result.get('tools_used')}",
    )

    attached = grounded_result.get("tax_optimization", {})

    _assert(
        "agent_attached_result_correct_math",
        attached.get("baseline", {}).get("estimated_tax")
        == 745_000.0
        and attached.get("estimated_savings") == 175_000.0,
        f"attached={ {k: attached.get(k) for k in ('baseline', 'estimated_savings')} }",
    )

    _assert(
        "agent_preserves_canonical_fields",
        all(
            key in grounded_result
            for key in (
                "domain",
                "question",
                "retrieval_question",
                "answer",
                "sources",
                "verification",
                "grounded",
                "context",
                "tools_selected",
                "tools_used",
            )
        ),
        f"keys={sorted(grounded_result.keys())}",
    )

    ungrounded_stub = dict(_GROUNDED_STUB)
    ungrounded_stub["grounded"] = False
    ungrounded_agent = IncomeTaxAgent(
        rag_engine=_StubRagEngine(ungrounded_stub)
    )
    ungrounded_result = ungrounded_agent.handle(CANONICAL_QUERY)

    _assert(
        "agent_skips_when_ungrounded",
        "tax_optimization" not in ungrounded_result,
        "tool attached on ungrounded response",
    )

    from app.verification_layer import PLACEHOLDER_ANSWER

    refusal_stub = dict(_GROUNDED_STUB)
    refusal_stub["answer"] = PLACEHOLDER_ANSWER
    refusal_agent = IncomeTaxAgent(
        rag_engine=_StubRagEngine(refusal_stub)
    )
    refusal_result = refusal_agent.handle(CANONICAL_QUERY)

    _assert(
        "agent_skips_when_safe_refusal",
        "tax_optimization" not in refusal_result,
        "tool attached on safe-refusal answer",
    )

    evasion_agent = IncomeTaxAgent(
        rag_engine=_StubRagEngine(_GROUNDED_STUB)
    )
    evasion_result = evasion_agent.handle(
        "How can I hide income to reduce tax for tax year 2025? "
        "Annual income: PKR 5000000."
    )

    _assert(
        "agent_skips_when_tool_refuses_evasion",
        "tax_optimization" not in evasion_result,
        "refused tool result was attached",
    )

    plain_agent = IncomeTaxAgent(
        rag_engine=_StubRagEngine(_GROUNDED_STUB)
    )
    plain_result = plain_agent.handle("What is income tax?")

    _assert(
        "agent_plain_query_no_attachment",
        "tax_optimization" not in plain_result
        and plain_result["tools_used"]
        == ["rag_search", "hybrid_search"],
        f"used={plain_result.get('tools_used')}",
    )


# ============================================================
# 9b. ACTUAL-EXECUTION PROOF (registry.execute spy)
# ============================================================

def _spied_registry(calls: list[str]):
    """
    Build a real registry whose execute() records every tool
    invocation (spy) while still running the real tools.
    """

    from app.tools import build_default_registry

    registry = build_default_registry()
    original_execute = registry.execute

    def spy(name, payload):
        calls.append(name)
        return original_execute(name, payload)

    registry.execute = spy
    return registry


def test_actual_execution_proof() -> None:
    from app.agents.calculation_agent import CalculationAgent
    from app.agents.income_tax_agent import IncomeTaxAgent
    from app.verification_layer import PLACEHOLDER_ANSWER

    # 1) CalculationAgent (primary domain for Tax Reducer
    #    queries) actually EXECUTES tax_optimization through the
    #    registry — previously it only listed it in
    #    tools_selected.
    calls: list[str] = []
    spied = _spied_registry(calls)
    calc_agent = CalculationAgent(
        rag_engine=_StubRagEngine(_GROUNDED_STUB)
    )
    with mock.patch(
        "app.tools.get_default_registry", lambda: spied
    ):
        calc_result = calc_agent.handle(CANONICAL_QUERY)

    _assert(
        "calc_agent_registry_executes_tax_optimization",
        "tax_optimization" in calls,
        f"calls={calls}",
    )

    _assert(
        "calc_agent_result_carries_tool_data",
        isinstance(
            calc_result.get("tax_optimization"), dict
        )
        and calc_result["tax_optimization"][
            "estimated_savings"
        ]
        == 175_000.0
        and "tax_optimization" in calc_result["tools_used"],
        f"keys={sorted(calc_result.keys())} "
        f"used={calc_result.get('tools_used')}",
    )

    _assert(
        "calc_agent_preserves_calculation_none_branch",
        calc_result["calculation"] is None
        and calc_result["grounded"] is True,
        f"calculation={calc_result.get('calculation')}",
    )

    # 2) IncomeTaxAgent executes via the registry (spy proof).
    calls2: list[str] = []
    spied2 = _spied_registry(calls2)
    income_agent = IncomeTaxAgent(
        rag_engine=_StubRagEngine(_GROUNDED_STUB)
    )
    with mock.patch(
        "app.tools.get_default_registry", lambda: spied2
    ):
        income_agent.handle(CANONICAL_QUERY)

    _assert(
        "income_agent_registry_executes_tax_optimization",
        "tax_optimization" in calls2,
        f"calls={calls2}",
    )

    # 3) Normal calculation query: calculation_engine still
    #    executes; tax_optimization does NOT.
    calls3: list[str] = []
    spied3 = _spied_registry(calls3)
    calc_agent2 = CalculationAgent(
        rag_engine=_StubRagEngine(_GROUNDED_STUB)
    )
    with mock.patch(
        "app.tools.get_default_registry", lambda: spied3
    ):
        normal_calc = calc_agent2.handle(
            "Calculate 17% sales tax on Rs 1,000,000"
        )

    _assert(
        "normal_calc_query_still_executes_calculation_engine",
        "calculation_engine" in calls3
        and normal_calc["calculation"] is not None
        and normal_calc["calculation"]["result"] == 170_000.0,
        f"calls={calls3} "
        f"calc={normal_calc.get('calculation')}",
    )

    _assert(
        "normal_calc_query_skips_tax_optimization",
        "tax_optimization" not in calls3
        and "tax_optimization" not in normal_calc,
        f"calls={calls3} keys={sorted(normal_calc.keys())}",
    )

    # 4) Normal income tax query: no tax_optimization execution.
    calls4: list[str] = []
    spied4 = _spied_registry(calls4)
    income_agent2 = IncomeTaxAgent(
        rag_engine=_StubRagEngine(_GROUNDED_STUB)
    )
    with mock.patch(
        "app.tools.get_default_registry", lambda: spied4
    ):
        plain_income = income_agent2.handle("What is income tax?")

    _assert(
        "normal_income_tax_query_skips_tax_optimization",
        "tax_optimization" not in calls4
        and "tax_optimization" not in plain_income,
        f"calls={calls4} keys={sorted(plain_income.keys())}",
    )

    # 5) Unrelated (customs) query through the real
    #    orchestrator: tax_optimization never executed.
    from app.agents.orchestrator import AgentOrchestrator

    calls5: list[str] = []
    spied5 = _spied_registry(calls5)
    unrelated_orch = AgentOrchestrator(
        rag_engine=_StubRagEngine(_GROUNDED_STUB)
    )
    with mock.patch(
        "app.tools.get_default_registry", lambda: spied5
    ):
        unrelated = unrelated_orch.handle(
            "What is the customs duty rate on imported machinery?"
        )

    _assert(
        "unrelated_query_never_executes_tax_optimization",
        "tax_optimization" not in calls5,
        f"calls={calls5} domains={unrelated['domains']}",
    )

    # 6) Tax Reducer query selected but unparseable (no tax
    #    year/income): no execution, no fabricated savings.
    calls6: list[str] = []
    spied6 = _spied_registry(calls6)
    calc_agent3 = CalculationAgent(
        rag_engine=_StubRagEngine(_GROUNDED_STUB)
    )
    with mock.patch(
        "app.tools.get_default_registry", lambda: spied6
    ):
        unparseable = calc_agent3.handle(
            "How can I lawfully reduce tax?"
        )

    _assert(
        "unparseable_tax_reducer_query_no_execution",
        "tax_optimization" not in calls6
        and "tax_optimization" not in unparseable,
        f"calls={calls6} keys={sorted(unparseable.keys())}",
    )

    # 7) Tool failure (ok=False ToolResult): response stays
    #    intact, no fabricated savings, no exception.
    from app.tools import build_default_registry
    from app.tools.base import ToolResult

    failing_registry = build_default_registry()
    failing_original = failing_registry.execute

    def failing_execute(name, payload):
        if name == "tax_optimization":
            return ToolResult(
                tool="tax_optimization",
                ok=False,
                data=None,
                error="simulated tool failure",
            )
        return failing_original(name, payload)

    failing_registry.execute = failing_execute

    calc_agent4 = CalculationAgent(
        rag_engine=_StubRagEngine(_GROUNDED_STUB)
    )
    with mock.patch(
        "app.tools.get_default_registry",
        lambda: failing_registry,
    ):
        failed = calc_agent4.handle(CANONICAL_QUERY)

    _assert(
        "tool_failure_handled_safely",
        "tax_optimization" not in failed
        and failed["grounded"] is True
        and failed["answer"] == _GROUNDED_STUB["answer"],
        f"keys={sorted(failed.keys())}",
    )

    # 8) Insufficient evidence (safe-refusal answer): the tool
    #    is never executed and no savings are fabricated.
    calls7: list[str] = []
    spied7 = _spied_registry(calls7)
    refusal_stub = dict(_GROUNDED_STUB)
    refusal_stub["answer"] = PLACEHOLDER_ANSWER
    refusal_agent = CalculationAgent(
        rag_engine=_StubRagEngine(refusal_stub)
    )
    with mock.patch(
        "app.tools.get_default_registry", lambda: spied7
    ):
        refusal = refusal_agent.handle(CANONICAL_QUERY)

    _assert(
        "insufficient_evidence_skips_tool_execution",
        "tax_optimization" not in calls7
        and "tax_optimization" not in refusal,
        f"calls={calls7} keys={sorted(refusal.keys())}",
    )


# ============================================================
# 10. ORCHESTRATOR + API
# ============================================================

def test_orchestrator_end_to_end() -> None:
    from app.agents.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator(
        rag_engine=_StubRagEngine(_GROUNDED_STUB)
    )

    response = orchestrator.handle(CANONICAL_QUERY)

    _assert(
        "orchestrator_routes_canonical_to_income_tax",
        "income_tax" in response["domains"],
        f"domains={response['domains']}",
    )

    income_result = next(
        (
            r
            for r in response["domain_results"]
            if r.get("domain") == "income_tax"
        ),
        None,
    )

    _assert(
        "orchestrator_income_tax_result_has_tool_data",
        income_result is not None
        and isinstance(
            income_result.get("tax_optimization"), dict
        )
        and income_result["tax_optimization"]["estimated_savings"]
        == 175_000.0,
        f"result_keys={sorted((income_result or {}).keys())}",
    )

    calc_entry = next(
        (
            r
            for r in response["domain_results"]
            if r.get("domain") == "calculation"
        ),
        None,
    )

    _assert(
        "orchestrator_calculation_result_has_tool_data",
        calc_entry is not None
        and isinstance(
            calc_entry.get("tax_optimization"), dict
        )
        and calc_entry["tax_optimization"][
            "estimated_savings"
        ]
        == 175_000.0
        and "tax_optimization"
        in calc_entry.get("tools_used", []),
        f"result_keys={sorted((calc_entry or {}).keys())}",
    )


def test_api_passthrough() -> None:
    from fastapi.testclient import TestClient

    from app.api import app

    tool_data = DEFAULT_REGISTRY.execute(
        "tax_optimization",
        extract_tax_reducer_payload(CANONICAL_QUERY),
    ).data

    orchestrator_response = {
        "question": CANONICAL_QUERY,
        "domains": ["calculation", "income_tax"],
        "primary_domain": "calculation",
        "multi_domain": True,
        "routing": {"domains": ["calculation", "income_tax"]},
        "domain_results": [
            {
                "domain": "income_tax",
                "question": CANONICAL_QUERY,
                "answer": "Lawful deductions under section 62.",
                "sources": [],
                "verification": {},
                "grounded": True,
                "context": "",
                "tools_selected": ["rag_search", "tax_optimization"],
                "tools_used": ["rag_search", "tax_optimization"],
                "tax_optimization": tool_data,
            }
        ],
        "answer": "Lawful deductions under section 62.",
        "sources": [],
        "verification": {
            "passed": True,
            "checks": {
                "answer_size": {"passed": True, "reason": "ok"},
                "section_consistency": {
                    "passed": True,
                    "reason": "ok",
                },
                "grounding": {"passed": True, "reason": "ok"},
                "speculation": {"passed": True, "reason": "ok"},
            },
            "failed_checks": [],
            "reason": "All verification checks passed.",
        },
        "grounded": True,
    }

    with mock.patch("app.api._get_orchestrator") as mock_get:
        mock_orch = mock.MagicMock()
        mock_orch.handle.return_value = orchestrator_response
        mock_get.return_value = mock_orch

        client = TestClient(app)
        resp = client.post(
            "/answer", json={"query": CANONICAL_QUERY}
        )

    ok = resp.status_code == 200
    data = resp.json() if ok else {}
    income_entry = next(
        (
            r
            for r in data.get("domain_results", [])
            if r.get("domain") == "income_tax"
        ),
        None,
    )

    _assert(
        "api_preserves_tax_optimization_field",
        ok
        and income_entry is not None
        and income_entry.get("tax_optimization", {}).get(
            "estimated_savings"
        )
        == 175_000.0,
        f"status={resp.status_code} entry={income_entry}",
    )


# ============================================================
# 10b. API END-TO-END (real orchestrator, spied registry)
# ============================================================

def test_api_end_to_end_reaches_tool() -> None:
    """
    POST /answer with a canonical Tax Reducer query through the
    REAL orchestrator (only the RAG engine is stubbed, the
    existing agent-test convention): the request must route,
    select, and ACTUALLY execute the registered
    tax_optimization tool, and the structured result must
    survive the API serialization on the calculation domain
    entry (the entry the frontend Tax Reducer UI reads).
    """

    from fastapi.testclient import TestClient

    from app.agents.orchestrator import AgentOrchestrator
    from app.api import app as api_app

    calls: list[str] = []
    spied = _spied_registry(calls)
    orchestrator = AgentOrchestrator(
        rag_engine=_StubRagEngine(_GROUNDED_STUB)
    )

    with mock.patch(
        "app.tools.get_default_registry", lambda: spied
    ), mock.patch(
        "app.api._get_orchestrator", lambda: orchestrator
    ):
        client = TestClient(api_app)
        resp = client.post(
            "/answer", json={"query": CANONICAL_QUERY}
        )

    ok = resp.status_code == 200
    data = resp.json() if ok else {}
    calc_entry = next(
        (
            r
            for r in data.get("domain_results", [])
            if r.get("domain") == "calculation"
        ),
        None,
    )
    income_entry = next(
        (
            r
            for r in data.get("domain_results", [])
            if r.get("domain") == "income_tax"
        ),
        None,
    )

    _assert(
        "api_end_to_end_executes_tax_optimization_tool",
        ok
        and "tax_optimization" in calls
        and calc_entry is not None
        and calc_entry.get("tax_optimization", {}).get(
            "estimated_savings"
        )
        == 175_000.0,
        f"status={resp.status_code} calls={calls} "
        f"calc_keys={sorted((calc_entry or {}).keys())}",
    )

    _assert(
        "api_end_to_end_income_tax_entry_has_tool_data",
        income_entry is not None
        and income_entry.get("tax_optimization", {}).get(
            "estimated_savings"
        )
        == 175_000.0,
        f"keys={sorted((income_entry or {}).keys())}",
    )


# ============================================================
# 11. DETERMINISM / ROBUSTNESS
# ============================================================

def test_determinism_and_robustness() -> None:
    tool = TaxOptimizationTool()

    payload = {
        "tax_year": 2025,
        "annual_income": 5_000_000.0,
        "investments": 500_000.0,
        "question": "pension contributions",
    }

    first = tool.run(payload).data
    identical = all(
        tool.run(payload).data == first for _ in range(4)
    )

    _assert(
        "tool_deterministic_repeat_5x",
        identical,
        "repeated runs produced different data",
    )

    battery = (
        None,
        "string",
        42,
        [],
        {},
        {"tax_year": "abc"},
        {"tax_year": 2025, "annual_income": "lots"},
        {"tax_year": 2025, "annual_income": -1},
        {"tax_year": 2025, "donations": [1, 2]},
        {"tax_year": 2025, "annual_income": 1.0, "question": 12345},
    )

    never_raised = True
    all_failed_cleanly = True

    for bad in battery:
        try:
            result = tool.run(bad)
            if result.ok and bad not in (
                {"tax_year": 2025, "annual_income": 1.0, "question": 12345},
            ):
                all_failed_cleanly = False
        except Exception:
            never_raised = False

    _assert(
        "tool_never_raises_on_invalid_input",
        never_raised,
        "run() raised on invalid input",
    )

    _assert(
        "invalid_battery_fails_cleanly",
        all_failed_cleanly,
        "some invalid payload was accepted",
    )

    valid = tool.run(BASE_PAYLOAD)

    try:
        json.dumps(valid.data)
        serializable = True
    except (TypeError, ValueError):
        serializable = False

    _assert(
        "output_json_serializable",
        valid.ok and serializable,
        "output is not JSON serializable",
    )

    question_int = tool.run(
        {"tax_year": 2025, "annual_income": 1.0, "question": 12345}
    )

    _assert(
        "non_string_question_coerced",
        question_int.ok,
        f"result={question_int.to_dict()}",
    )


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    print("=" * 72)
    print("TAX OPTIMIZATION TOOL (TAX REDUCER BACKEND) TEST")
    print("=" * 72)

    test_tool_and_registry()
    test_valid_optimization()
    test_opportunities()
    test_validation()
    test_unlawful_guard()
    test_payload_extraction()
    test_router()
    test_agent_integration()
    test_actual_execution_proof()
    test_orchestrator_end_to_end()
    test_api_passthrough()
    test_api_end_to_end_reaches_tool()
    test_determinism_and_robustness()

    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["passed"])

    print()
    for r in RESULTS:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"[{status}] {r['name']}")
        if not r["passed"]:
            print(f"        detail: {r['detail']}")
    print("=" * 72)
    print(f"Total : {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print("=" * 72)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
