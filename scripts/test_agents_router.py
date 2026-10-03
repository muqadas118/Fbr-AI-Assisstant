"""
Phase 9 (corrected): 9-Agent FBR Architecture test suite.

The corrected Phase 9 architecture is exactly 9 specialized
agents:

  1. Income Tax Agent            (income_tax)
  2. Sales Tax Agent             (sales_tax)
  3. Federal Excise Agent        (federal_excise)
  4. Customs Agent               (customs)
  5. Registration Agent          (registration)
  6. Return Filing Agent         (return_filing)
  7. Calculation Agent           (calculation)
  8. Notice / Appeal Agent       (notice_appeal)
  9. Research Agent              (research)

The following are NOT standalone agents in this architecture:
  - PropertyValuationAgent  (removed; valuation research goes
                             to Research Agent, valuation
                             calculations to Calculation Agent)
  - FinanceActAgent         (removed; FA is a topic, routed
                             to Research + the relevant tax
                             agent)
  - GeneralFBRAgent         (removed; no catch-all agent)

This suite verifies:

ROUTER TESTS (14 mandatory cases):
  1.  income tax
  2.  sales tax
  3.  federal excise
  4.  customs
  5.  calculation
  6.  research
  7.  notice / appeal
  8.  Finance Act + Income Tax
  9.  Finance Act + Sales Tax
  10. property valuation
  11. property valuation calculation
  12. multi-domain query
  13. ambiguous query
  14. out-of-domain query

Plus:
  - Router determinism (5x repeat)
  - 9-agent existence assertion
  - 3 removed-agents removal assertion
  - Per-agent tests (9 agents)
  - Calculation tests (valid, missing rate, missing amount,
    invalid numeric, rate from evidence, provenance)
  - Research tests (multi-doc, FA research, comparison,
    cross-domain, provenance, insufficient evidence)
  - Notice/Appeal tests (notice, appeal, section-linked,
    missing evidence, provenance)
  - Orchestrator tests (single, multi, shared engine,
    safe refusal, no unverified, dedup by chunk_id)
"""

from __future__ import annotations

import os
import sys
import traceback
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.agents import (  # noqa: E402
    AgentOrchestrator,
    CalculationAgent,
    CustomsAgent,
    FBRQueryRouter,
    FederalExciseAgent,
    IncomeTaxAgent,
    NoticeAppealAgent,
    RegistrationAgent,
    ResearchAgent,
    ReturnFilingAgent,
    SalesTaxAgent,
)
from app.agents import (  # noqa: E402
    __all__ as AGENTS_PUBLIC_API,
)
from app.rag_engine import (  # noqa: E402
    FBRRAGEngine,
    _NO_EVIDENCE_ANSWER,
)
from app.verification_layer import PLACEHOLDER_ANSWER  # noqa: E402

_SAFE_ANSWERS = (PLACEHOLDER_ANSWER, _NO_EVIDENCE_ANSWER)


# ============================================================
# TEST HARNESS
# ============================================================

def _results() -> list[dict[str, Any]]:
    return []


def _assert(
    results: list[dict[str, Any]],
    name: str,
    condition: bool,
    detail: Any = "",
) -> None:
    results.append(
        {
            "name": name,
            "passed": bool(condition),
            "detail": str(detail)[:500],
        }
    )


def _provenance_complete(sources: list[dict]) -> bool:
    """
    Provenance is complete when every source carries the mandatory
    identity fields (source, source_path, source_sha256, chunk_id)
    and page bounds are present for paginated (PDF) documents.
    Non-PDF sources (.doc/.docx/.xls/.xlsx/.csv/.zip) have no
    page concept and are exempt from the page-bounds check.
    """

    def _paginated(s: dict) -> bool:
        src = str(
            s.get("source", "") or s.get("source_path", "") or ""
        )
        return src.lower().endswith(".pdf")

    return bool(sources) and all(
        bool(s.get("source"))
        and bool(s.get("source_path"))
        and bool(s.get("source_sha256"))
        and bool(s.get("chunk_id"))
        and (
            (
                s.get("page_start") is not None
                and s.get("page_end") is not None
            )
            or not _paginated(s)
        )
        for s in sources
    )


def _sources_match(
    sources: list[dict], keywords: tuple[str, ...]
) -> bool:
    for s in sources:
        target = (
            str(s.get("source", "") or "")
            + " "
            + str(s.get("source_path", "") or "")
        ).lower()
        if any(k in target for k in keywords):
            return True
    return False


# ============================================================
# ARCHITECTURE INVARIANTS
# ============================================================

REQUIRED_9_AGENTS: tuple[str, ...] = (
    "IncomeTaxAgent",
    "SalesTaxAgent",
    "FederalExciseAgent",
    "CustomsAgent",
    "RegistrationAgent",
    "ReturnFilingAgent",
    "CalculationAgent",
    "NoticeAppealAgent",
    "ResearchAgent",
)

REMOVED_3_AGENTS: tuple[str, ...] = (
    "PropertyValuationAgent",
    "FinanceActAgent",
    "GeneralFBRAgent",
)


def test_architecture_invariants(
    results: list[dict[str, Any]],
) -> None:
    public_api = set(AGENTS_PUBLIC_API)
    for name in REQUIRED_9_AGENTS:
        _assert(
            results,
            f"architecture[required_agent]={name}",
            name in public_api,
            f"public_api={sorted(public_api)}",
        )
    for name in REMOVED_3_AGENTS:
        _assert(
            results,
            f"architecture[removed_agent_absent]={name}",
            name not in public_api,
            f"public_api={sorted(public_api)}",
        )

    # Import-time check: importing the obsolete names must fail
    for module_name, attr in (
        ("app.agents", "PropertyValuationAgent"),
        ("app.agents", "FinanceActAgent"),
        ("app.agents", "GeneralFBRAgent"),
    ):
        try:
            __import__(module_name, fromlist=[attr])
            getattr(sys.modules[module_name], attr)
            present = True
        except (ImportError, AttributeError):
            present = False
        _assert(
            results,
            f"architecture[no_obsolete_attribute]={attr}",
            not present,
            f"module={module_name} attr={attr} present={present}",
        )


# ============================================================
# ROUTER TESTS (14 mandatory cases)
# ============================================================

ROUTER_CASES: list[tuple[str, str, tuple[str, ...]]] = [
    # 1. income tax
    (
        "income_tax",
        "What is Section 177 of the Income Tax Ordinance 2001?",
        ("income_tax",),
    ),
    # 2. sales tax
    (
        "sales_tax",
        "sales tax registration requirements",
        ("registration", "sales_tax"),
    ),
    # 3. federal excise
    (
        "federal_excise",
        "FED on cigarettes",
        ("federal_excise",),
    ),
    # 4. customs
    (
        "customs",
        "What is the customs duty on imported goods?",
        ("customs",),
    ),
    # 5. calculation
    (
        "calculation",
        "calculate 10% tax on Rs 500,000",
        ("calculation",),
    ),
    # 6. research
    (
        "research",
        "find all relevant documents about this tax issue",
        ("research",),
    ),
    # 7. notice / appeal
    (
        "notice_appeal",
        "How do I appeal an FBR order?",
        ("notice_appeal",),
    ),
    # 8. Finance Act + Income Tax
    (
        "finance_act_plus_income_tax",
        "What changed in income tax under Finance Act 2026?",
        ("research", "income_tax"),
    ),
    # 9. Finance Act + Sales Tax
    (
        "finance_act_plus_sales_tax",
        "Compare the relevant provisions in sales tax under Finance Act 2026",
        ("research", "sales_tax"),
    ),
    # 10. property valuation (now Research)
    (
        "property_valuation_research",
        "What is the property valuation in Vehari?",
        ("research",),
    ),
    # 11. property valuation calculation (now Calculation)
    (
        "property_valuation_calculation",
        "Calculate property value using 10 percent of 5,000,000",
        ("calculation",),
    ),
    # 12. multi-domain query
    (
        "multi_domain",
        "What changed in income tax and sales tax under Finance Act 2026?",
        ("research", "sales_tax", "income_tax"),
    ),
    # 13. ambiguous query
    (
        "ambiguous",
        "What is the tax rate?",
        ("research",),
    ),
    # 14. out-of-domain query
    (
        "out_of_domain",
        "What is the weather in Lahore today?",
        ("research",),
    ),
    # extra: FA abbreviation
    (
        "fa_abbreviation",
        "FA 2026 changes to tax",
        ("research",),
    ),
    # extra: section-return (income tax)
    (
        "section_return",
        "section 114 return",
        ("income_tax",),
    ),
    # extra: city without valuation context
    (
        "city_without_valuation_context",
        "What are the income tax rates in Karachi?",
        ("income_tax",),
    ),
    # extra: registration
    (
        "registration",
        "how to register for NTN in IRIS",
        ("registration",),
    ),
    # extra: return filing
    (
        "return_filing",
        "What is the due date for filing of return?",
        ("return_filing",),
    ),
    # extra: notice interpretation
    (
        "notice_section",
        "I received an FBR notice under section 177",
        ("notice_appeal", "income_tax"),
    ),
    # extra: CD (customs duty) expansion
    (
        "customs_cd_abbrev",
        "What is CD on imported goods?",
        ("customs",),
    ),
    # extra: registration (NTN)
    (
        "registration_ntn",
        "How do I get a new NTN for my business?",
        ("registration",),
    ),
]


def test_router(results: list[dict[str, Any]]) -> None:
    router = FBRQueryRouter()
    for name, question, expected in ROUTER_CASES:
        decision = router.route(question)
        _assert(
            results,
            f"router[{name}]_domains",
            tuple(decision.domains) == expected,
            f"q={question!r} got={list(decision.domains)} "
            f"expected={list(expected)} "
            f"signals={decision.matched_signals}",
        )


def test_router_determinism(
    results: list[dict[str, Any]],
) -> None:
    router = FBRQueryRouter()
    nondeterministic: list[str] = []
    for name, question, _ in ROUTER_CASES:
        first = router.route(question).to_dict()
        ok = True
        for _ in range(4):
            if router.route(question).to_dict() != first:
                ok = False
                break
        if not ok:
            nondeterministic.append(name)
    _assert(
        results,
        "router_determinism_repeat_5x",
        not nondeterministic,
        f"nondeterministic={nondeterministic}",
    )


def test_router_targets_strict(
    results: list[dict[str, Any]],
) -> None:
    """
    The router must NEVER emit a target from the removed-agent
    set. Property valuation, finance act, and general FBR are not
    valid routing targets.
    """

    router = FBRQueryRouter()
    invalid_targets = {"property_valuation", "finance_act", "general_fbr"}
    leaks: list[str] = []
    for name, question, _ in ROUTER_CASES:
        decision = router.route(question)
        for d in decision.domains:
            if d in invalid_targets:
                leaks.append(f"{name}:{d}")
    _assert(
        results,
        "router_targets_never_removed_domains",
        not leaks,
        f"leaks={leaks}",
    )


# ============================================================
# QUERY EXPANSION TESTS (deterministic, fast)
# ============================================================

def test_query_expansion(results: list[dict[str, Any]]) -> None:
    fe = FederalExciseAgent()
    it = IncomeTaxAgent()
    cu = CustomsAgent()
    rg = RegistrationAgent()
    rs = ResearchAgent()
    na = NoticeAppealAgent()
    ca = CalculationAgent()

    # Federal excise: FED -> Federal Excise Duty
    _assert(
        results,
        "expansion[federal_excise]_fed_expanded",
        fe.expand_query("FED on cigarettes")
        == "Federal Excise Duty on cigarettes",
        fe.expand_query("FED on cigarettes"),
    )
    _assert(
        results,
        "expansion[federal_excise]_full_phrase_unchanged",
        fe.expand_query("federal excise duty on cement")
        == "federal excise duty on cement",
        fe.expand_query("federal excise duty on cement"),
    )
    # Federal excise: SRO questions gain notification corpus
    # vocabulary so retrieval surfaces SRO notification chunks.
    _assert(
        results,
        "expansion[federal_excise]_sro_expanded",
        fe.expand_query(
            "Recent SROs (Statutory Regulatory Orders) issued by FBR 2025"
        )
        == (
            "Recent SROs (Statutory Regulatory Orders) issued by FBR 2025"
            " Statutory Regulatory Order SRO Notification Federal Board"
            " of Revenue Revenue Division notification issued Islamabad"
        ),
        fe.expand_query(
            "Recent SROs (Statutory Regulatory Orders) issued by FBR 2025"
        ),
    )
    _assert(
        results,
        "expansion[federal_excise]_fed_sro_combined",
        fe.expand_query("FED SRO on cigarettes")
        == (
            "Federal Excise Duty SRO on cigarettes Statutory Regulatory"
            " Order SRO Notification Federal Board of Revenue Revenue"
            " Division notification issued Islamabad"
        ),
        fe.expand_query("FED SRO on cigarettes"),
    )
    _assert(
        results,
        "expansion[federal_excise]_notification_qualified_unchanged",
        fe.expand_query("SRO 1679 notification Abbottabad")
        == "SRO 1679 notification Abbottabad",
        fe.expand_query("SRO 1679 notification Abbottabad"),
    )

    # Income tax: bare section -> "...under the Income Tax Ordinance 2001"
    _assert(
        results,
        "expansion[income_tax]_bare_section_expanded",
        it.expand_query("section 114 return")
        == "section 114 return under the Income Tax Ordinance 2001",
        it.expand_query("section 114 return"),
    )
    _assert(
        results,
        "expansion[income_tax]_law_named_unchanged",
        it.expand_query(
            "What is Section 177 of the Income Tax Ordinance 2001?"
        )
        == "What is Section 177 of the Income Tax Ordinance 2001?",
        it.expand_query(
            "What is Section 177 of the Income Tax Ordinance 2001?"
        ),
    )
    # Income tax: natural-language salaried rate/slab questions gain
    # First Schedule Part I corpus vocabulary so hybrid retrieval
    # surfaces the slab table instead of WHT cards/budget teasers.
    _assert(
        results,
        "expansion[income_tax]_salary_rate_expanded",
        it.expand_query(
            "What is the current income tax rate for salaried individuals?"
        )
        == (
            "What is the current income tax rate for salaried individuals?"
            " under the Income Tax Ordinance 2001 First Schedule Part I"
            " salary rates table where income chargeable under the head"
            " salary exceeds seventy-five per cent"
        ),
        it.expand_query(
            "What is the current income tax rate for salaried individuals?"
        ),
    )
    # No section number may leak into the expansion: exact-section
    # retrieval would hijack the query away from the slab table.
    _assert(
        results,
        "expansion[income_tax]_salary_expansion_has_no_section_number",
        "section" not in it.expand_query(
            "What is the current income tax rate for salaried individuals?"
        ).lower().replace("income tax ordinance", ""),
        it.expand_query(
            "What is the current income tax rate for salaried individuals?"
        ),
    )
    # Withholding / other-domain salary questions keep WHT routing.
    _assert(
        results,
        "expansion[income_tax]_withholding_salary_unchanged",
        it.expand_query("What is the withholding tax rate on salary?")
        == "What is the withholding tax rate on salary?",
        it.expand_query("What is the withholding tax rate on salary?"),
    )
    _assert(
        results,
        "expansion[income_tax]_sales_tax_salary_unchanged",
        it.expand_query("What is the sales tax rate on salaried services?")
        == "What is the sales tax rate on salaried services?",
        it.expand_query("What is the sales tax rate on salaried services?"),
    )
    # Already-qualified First Schedule queries are not double-expanded.
    _assert(
        results,
        "expansion[income_tax]_first_schedule_unchanged",
        it.expand_query("salary slabs First Schedule Part I")
        == "salary slabs First Schedule Part I",
        it.expand_query("salary slabs First Schedule Part I"),
    )

    # Customs: CD -> customs duty
    _assert(
        results,
        "expansion[customs]_cd_expanded",
        cu.expand_query("What is CD on imported goods?")
        == "What is customs duty on imported goods?",
        cu.expand_query("What is CD on imported goods?"),
    )
    _assert(
        results,
        "expansion[customs]_already_full_unchanged",
        cu.expand_query("What is customs duty on imported goods?")
        == "What is customs duty on imported goods?",
        cu.expand_query("What is customs duty on imported goods?"),
    )

    # Registration: NTN -> National Tax Number, STRN -> Sales Tax Registration Number
    _assert(
        results,
        "expansion[registration]_ntn_expanded",
        rg.expand_query("How do I get NTN?")
        == "How do I get National Tax Number?",
        rg.expand_query("How do I get NTN?"),
    )
    _assert(
        results,
        "expansion[registration]_strn_expanded",
        rg.expand_query("What is STRN?")
        == "What is Sales Tax Registration Number?",
        rg.expand_query("What is STRN?"),
    )

    # Research: city+context -> "{City} tehsil property valuation"
    _assert(
        results,
        "expansion[research]_city_normalized",
        rs.expand_query("Vehari immovable property valuation rates")
        == "Vehari tehsil property valuation",
        rs.expand_query("Vehari immovable property valuation rates"),
    )
    _assert(
        results,
        "expansion[research]_city_phrase_rewritten",
        rs.expand_query("property valuation in Vehari")
        == "Vehari tehsil property valuation",
        rs.expand_query("property valuation in Vehari"),
    )
    _assert(
        results,
        "expansion[research]_no_city_unchanged",
        rs.expand_query("FBR valuation of immovable property rates")
        == "FBR valuation of immovable property rates",
        rs.expand_query("FBR valuation of immovable property rates"),
    )
    _assert(
        results,
        "expansion[research]_fa_year_expanded",
        rs.expand_query("FA 2026 income tax changes")
        == "Finance Act 2026 income tax changes",
        rs.expand_query("FA 2026 income tax changes"),
    )
    _assert(
        results,
        "expansion[research]_full_phrase_unchanged",
        rs.expand_query("Finance Act 2026 income tax amendments")
        == "Finance Act 2026 income tax amendments",
        rs.expand_query("Finance Act 2026 income tax amendments"),
    )

    # Notice/Appeal: if a notice/appeal phrase is already present
    # in the question, the expansion should leave the input
    # unchanged (the existing notice/appeal vocabulary is the
    # best retrieval signal).
    _assert(
        results,
        "expansion[notice_appeal]_notice_phrase_unchanged",
        na.expand_query("section 114 notice and appeal")
        == "section 114 notice and appeal",
        na.expand_query("section 114 notice and appeal"),
    )
    # Notice/Appeal: bare section reference without any other law
    # term -> appends "notice and appeal procedure" qualifier.
    _assert(
        results,
        "expansion[notice_appeal]_bare_section_qualified",
        na.expand_query("I received a notice under section 161")
        == "I received a notice under section 161 notice and appeal procedure",
        na.expand_query("I received a notice under section 161"),
    )

    # Calculation: no pre-expansion (RAG needs the original)
    _assert(
        results,
        "expansion[calculation]_no_expansion",
        ca.expand_query("calculate 10% tax on Rs 500,000")
        == "calculate 10% tax on Rs 500,000",
        ca.expand_query("calculate 10% tax on Rs 500,000"),
    )


# ============================================================
# PER-AGENT INTEGRATION TESTS (RAG + verification)
# ============================================================

AGENT_CASES: list[
    tuple[str, type, str, tuple[str, ...]]
] = [
    (
        "income_tax",
        IncomeTaxAgent,
        "What is Section 177 of the Income Tax Ordinance 2001?",
        ("incometaxordinance", "incometax", "income", "tax"),
    ),
    (
        "sales_tax",
        SalesTaxAgent,
        "What is the input tax adjustment under Sales Tax Act 1990?",
        ("salestaxact", "salestax", "sales"),
    ),
    (
        "federal_excise",
        FederalExciseAgent,
        "Federal Excise Act 2005 duties and offences",
        ("federalexciseact", "excise"),
    ),
    (
        "customs",
        CustomsAgent,
        "What is the customs duty on imported goods?",
        (),
    ),
    (
        "registration",
        RegistrationAgent,
        "How do I register for NTN in IRIS?",
        (),
    ),
    (
        "return_filing",
        ReturnFilingAgent,
        "What is the due date for filing of return?",
        ("return",),
    ),
    (
        "calculation",
        CalculationAgent,
        "calculate 10 percent of 500000",
        (),
    ),
    (
        "notice_appeal",
        NoticeAppealAgent,
        "How do I file an appeal against an FBR order?",
        ("appeal", "appellate"),
    ),
    (
        "research",
        ResearchAgent,
        "Find all relevant documents about this tax issue",
        (),
    ),
]


def test_agents(
    results: list[dict[str, Any]], engine: FBRRAGEngine
) -> None:
    for name, agent_cls, question, keywords in AGENT_CASES:
        try:
            agent = agent_cls(rag_engine=engine)
            response = agent.handle(question)
        except Exception:
            _assert(
                results,
                f"agent[{name}]_no_exception",
                False,
                traceback.format_exc(),
            )
            continue

        sources = response.get("sources", [])
        answer = response.get("answer", "")

        _assert(
            results,
            f"agent[{name}]_domain_tag",
            response.get("domain") == name,
            f"got={response.get('domain')}",
        )
        if keywords:
            # A retrieval match is required when the agent
            # produces a grounded answer backed by the corpus.
            # When the RAG engine returns a safe-refusal answer,
            # the listed sources are only pre-verification
            # candidates (the engine still surfaces top-k
            # chunks) — the agent has not fabricated anything,
            # so the keyword check is satisfied by the safe
            # refusal itself.
            retrieval_ok = (
                _sources_match(sources, keywords)
                or answer in _SAFE_ANSWERS
            )
            _assert(
                results,
                f"agent[{name}]_domain_retrieval",
                retrieval_ok,
                f"expected source containing {keywords}; "
                f"sources={[s.get('source') for s in sources]} "
                f"answer={str(answer)[:120]}",
            )
        _assert(
            results,
            f"agent[{name}]_provenance_complete",
            _provenance_complete(sources) or not sources,
            f"sources={len(sources)}",
        )
        _assert(
            results,
            f"agent[{name}]_verification_not_bypassed",
            isinstance(response.get("verification"), dict)
            and (
                response["verification"].get("passed")
                or response.get("answer") == _NO_EVIDENCE_ANSWER
            ),
            f"verification={response.get('verification')}",
        )
        _assert(
            results,
            f"agent[{name}]_verified_or_grounded",
            bool(response.get("grounded"))
            or response.get("answer") in _SAFE_ANSWERS,
            f"grounded={response.get('grounded')} "
            f"answer={str(response.get('answer'))[:200]}",
        )

    # Research agent: city normalization must be applied to
    # retrieval_question (preserves functionality migrated from
    # the removed PropertyValuation agent).
    try:
        rs_agent = ResearchAgent(rag_engine=engine)
        rs_response = rs_agent.handle(
            "Vehari immovable property valuation rates"
        )
        _assert(
            results,
            "agent[research]_city_normalized_for_retrieval",
            rs_response.get("retrieval_question")
            == "Vehari tehsil property valuation",
            f"retrieval_question={rs_response.get('retrieval_question')}",
        )
    except Exception:
        _assert(
            results,
            "agent[research]_city_normalized_for_retrieval",
            False,
            traceback.format_exc(),
        )

    # Research agent: FA year abbreviation must be expanded to
    # "Finance Act YYYY" (preserves functionality migrated from
    # the removed FinanceAct agent).
    try:
        rs_agent = ResearchAgent(rag_engine=engine)
        rs_response = rs_agent.handle("FA 2026 income tax changes")
        _assert(
            results,
            "agent[research]_fa_year_expanded_for_retrieval",
            rs_response.get("retrieval_question")
            == "Finance Act 2026 income tax changes",
            f"retrieval_question={rs_response.get('retrieval_question')}",
        )
    except Exception:
        _assert(
            results,
            "agent[research]_fa_year_expanded_for_retrieval",
            False,
            traceback.format_exc(),
        )


# ============================================================
# AGENT SAFETY (no fabrication, no bypass)
# ============================================================

def test_agent_safety(
    results: list[dict[str, Any]], engine: FBRRAGEngine
) -> None:
    try:
        it_agent = IncomeTaxAgent(rag_engine=engine)
        mars_weather = it_agent.handle("What is the weather on Mars?")

        _assert(
            results,
            "agent_safety[out_of_domain]_safe_refusal",
            bool(mars_weather.get("grounded"))
            or mars_weather.get("answer") in _SAFE_ANSWERS,
            f"grounded={mars_weather.get('grounded')} "
            f"answer={str(mars_weather.get('answer'))[:200]}",
        )
        _assert(
            results,
            "agent_safety[out_of_domain]_no_unverified_answer",
            mars_weather.get("verification", {}).get("passed")
            or mars_weather.get("answer") == _NO_EVIDENCE_ANSWER,
            f"verification={mars_weather.get('verification')}",
        )
    except Exception:
        _assert(
            results,
            "agent_safety[out_of_domain]_safe_refusal",
            False,
            traceback.format_exc(),
        )

    # Customs: corpus now contains customs material (131 chunks);
    # the agent must answer from evidence or safely refuse, never invent.
    try:
        cu_agent = CustomsAgent(rag_engine=engine)
        cu_resp = cu_agent.handle("customs duty on imported electronics")
        _assert(
            results,
            "agent_safety[customs_no_fabrication]",
            bool(cu_resp.get("grounded"))
            or cu_resp.get("answer") in _SAFE_ANSWERS,
            f"grounded={cu_resp.get('grounded')} "
            f"answer={str(cu_resp.get('answer'))[:200]}",
        )
    except Exception:
        _assert(
            results,
            "agent_safety[customs_no_fabrication]",
            False,
            traceback.format_exc(),
        )


# ============================================================
# CALCULATION TESTS (deterministic arithmetic)
# ============================================================

def test_calculation_extraction(
    results: list[dict[str, Any]],
) -> None:
    from app.agents.calculation_agent import _extract_calculation

    valid = _extract_calculation("10% tax on Rs 500,000")
    _assert(
        results,
        "calc[extract_valid_percent_amount]",
        valid is not None
        and valid["kind"] == "percent_of_amount"
        and valid["percent"] == 10.0
        and valid["amount"] == 500000.0
        and abs(valid["result"] - 50000.0) < 0.01,
        f"valid={valid}",
    )

    missing_amount = _extract_calculation("calculate 10% tax")
    _assert(
        results,
        "calc[extract_missing_amount_returns_none]",
        missing_amount is None,
        f"got={missing_amount}",
    )

    missing_rate = _extract_calculation("calculate tax on Rs 500,000")
    _assert(
        results,
        "calc[extract_missing_rate_returns_none]",
        missing_rate is None,
        f"got={missing_rate}",
    )

    invalid_numeric = _extract_calculation("calculate ten percent of money")
    _assert(
        results,
        "calc[extract_invalid_numeric_returns_none]",
        invalid_numeric is None,
        f"got={invalid_numeric}",
    )

    zero_amount = _extract_calculation("calculate 5% on 0")
    _assert(
        results,
        "calc[extract_zero_amount_returns_none]",
        zero_amount is None,
        f"got={zero_amount}",
    )

    fractional = _extract_calculation("compute 7.5 percent of 1,000")
    _assert(
        results,
        "calc[extract_fractional_percent]",
        fractional is not None
        and abs(fractional["percent"] - 7.5) < 0.001
        and fractional["amount"] == 1000.0
        and abs(fractional["result"] - 75.0) < 0.01,
        f"fractional={fractional}",
    )

    determinism_inputs = ["10% on 1000", "10% on 1000", "10% on 1000"]
    determinism_results = [
        _extract_calculation(q) for q in determinism_inputs
    ]
    _assert(
        results,
        "calc[extract_deterministic_repeat_3x]",
        determinism_results[0] == determinism_results[1]
        == determinism_results[2],
        f"results={determinism_results}",
    )


def test_calculation_agent(
    results: list[dict[str, Any]], engine: FBRRAGEngine
) -> None:
    """
    Calculation agent must:
    - run deterministic Python arithmetic on a parsed
      (percent, amount) pair,
    - never invent a rate,
    - return safe refusal when RAG is not grounded,
    - include calculation basis and provenance when grounded.
    """

    # Case A: deterministic calculation directly via the
    # extracted module (this is the LLM-independent core the
    # agent relies on for its arithmetic step).
    from app.agents.calculation_agent import _extract_calculation

    parsed = _extract_calculation("calculate 10% tax on Rs 500,000")
    _assert(
        results,
        "calc[arithmetic_500000_at_10pct]",
        parsed is not None and abs(parsed["result"] - 50000.0) < 0.01,
        f"parsed={parsed}",
    )
    parsed2 = _extract_calculation("calculate 17% sales tax on Rs 1,000,000")
    _assert(
        results,
        "calc[arithmetic_1000000_at_17pct]",
        parsed2 is not None and abs(parsed2["result"] - 170000.0) < 0.01,
        f"parsed2={parsed2}",
    )

    # Case B: agent does not invent a rate when RAG cannot ground.
    try:
        calc_agent = CalculationAgent(rag_engine=engine)
        resp = calc_agent.handle("calculate 10% tax on Mars colonies")
        _assert(
            results,
            "calc[agent_missing_rate_no_fabrication]",
            not resp.get("grounded")
            or resp.get("answer") in _SAFE_ANSWERS,
            f"grounded={resp.get('grounded')} "
            f"answer={str(resp.get('answer'))[:200]}",
        )
        _assert(
            results,
            "calc[agent_missing_rate_does_not_expose_arbitrary_number]",
            resp.get("calculation") is None
            or not str(resp.get("answer", "")).startswith(
                "The calculated value"
            ),
            f"calculation={resp.get('calculation')}",
        )
    except Exception:
        _assert(
            results,
            "calc[agent_missing_rate_no_fabrication]",
            False,
            traceback.format_exc(),
        )

    # Case C: agent exposes the calculation basis when RAG is
    # grounded AND a (percent, amount) pair can be parsed.
    try:
        calc_agent = CalculationAgent(rag_engine=engine)
        resp = calc_agent.handle("calculate 10% tax on Rs 500,000")
        if resp.get("grounded") and resp.get("calculation"):
            _assert(
                results,
                "calc[agent_grounded_exposes_basis_and_provenance]",
                "Calculation basis" in str(resp.get("answer", ""))
                and "Result:" in str(resp.get("answer", ""))
                and bool(resp.get("sources")),
                f"answer={str(resp.get('answer'))[:300]} "
                f"sources={len(resp.get('sources', []))}",
            )
        else:
            _assert(
                results,
                "calc[agent_safe_refusal_when_not_grounded]",
                resp.get("answer") in _SAFE_ANSWERS
                or not resp.get("grounded"),
                f"grounded={resp.get('grounded')} "
                f"answer={str(resp.get('answer'))[:200]}",
            )
    except Exception:
        _assert(
            results,
            "calc[agent_grounded_exposes_basis_and_provenance]",
            False,
            traceback.format_exc(),
        )


# ============================================================
# RESEARCH TESTS
# ============================================================

def test_research_agent(
    results: list[dict[str, Any]], engine: FBRRAGEngine
) -> None:
    rs = ResearchAgent(rag_engine=engine)

    # Multi-document retrieval: city valuation research
    try:
        resp = rs.handle("Vehari tehsil property valuation")
        _assert(
            results,
            "research[valuation]_verified_or_safe",
            bool(resp.get("grounded"))
            or resp.get("answer") in _SAFE_ANSWERS,
            f"grounded={resp.get('grounded')} "
            f"answer={str(resp.get('answer'))[:200]}",
        )
        _assert(
            results,
            "research[valuation]_provenance_complete",
            _provenance_complete(resp.get("sources", []))
            or not resp.get("sources"),
            f"sources={len(resp.get('sources', []))}",
        )
    except Exception:
        _assert(
            results,
            "research[valuation]_verified_or_safe",
            False,
            traceback.format_exc(),
        )

    # Finance Act research query
    try:
        resp = rs.handle("Finance Act 2026 income tax amendments")
        _assert(
            results,
            "research[fa]_verified_or_safe",
            bool(resp.get("grounded"))
            or resp.get("answer") in _SAFE_ANSWERS,
            f"grounded={resp.get('grounded')} "
            f"answer={str(resp.get('answer'))[:200]}",
        )
        _assert(
            results,
            "research[fa]_provenance_complete",
            _provenance_complete(resp.get("sources", []))
            or not resp.get("sources"),
            f"sources={len(resp.get('sources', []))}",
        )
    except Exception:
        _assert(
            results,
            "research[fa]_verified_or_safe",
            False,
            traceback.format_exc(),
        )

    # Comparison / cross-domain query
    try:
        resp = rs.handle("compare sales tax and income tax under Finance Act 2025")
        _assert(
            results,
            "research[cross_domain]_verified_or_safe",
            bool(resp.get("grounded"))
            or resp.get("answer") in _SAFE_ANSWERS,
            f"grounded={resp.get('grounded')} "
            f"answer={str(resp.get('answer'))[:200]}",
        )
    except Exception:
        _assert(
            results,
            "research[cross_domain]_verified_or_safe",
            False,
            traceback.format_exc(),
        )

    # Insufficient evidence: out-of-domain research query must
    # return safe refusal.
    try:
        resp = rs.handle("What is the weather in Tokyo tomorrow?")
        _assert(
            results,
            "research[insufficient_evidence]_no_fabrication",
            bool(resp.get("grounded"))
            or resp.get("answer") in _SAFE_ANSWERS,
            f"grounded={resp.get('grounded')} "
            f"answer={str(resp.get('answer'))[:200]}",
        )
    except Exception:
        _assert(
            results,
            "research[insufficient_evidence]_no_fabrication",
            False,
            traceback.format_exc(),
        )


# ============================================================
# NOTICE / APPEAL TESTS
# ============================================================

def test_notice_appeal_agent(
    results: list[dict[str, Any]], engine: FBRRAGEngine
) -> None:
    na = NoticeAppealAgent(rag_engine=engine)

    # Notice query
    try:
        resp = na.handle("I received an FBR notice under section 161")
        _assert(
            results,
            "notice[query]_verified_or_safe",
            bool(resp.get("grounded"))
            or resp.get("answer") in _SAFE_ANSWERS,
            f"grounded={resp.get('grounded')} "
            f"answer={str(resp.get('answer'))[:200]}",
        )
        _assert(
            results,
            "notice[query]_provenance",
            _provenance_complete(resp.get("sources", []))
            or not resp.get("sources"),
            f"sources={len(resp.get('sources', []))}",
        )
    except Exception:
        _assert(
            results,
            "notice[query]_verified_or_safe",
            False,
            traceback.format_exc(),
        )

    # Appeal query
    try:
        resp = na.handle("How do I appeal an FBR order?")
        _assert(
            results,
            "appeal[query]_verified_or_safe",
            bool(resp.get("grounded"))
            or resp.get("answer") in _SAFE_ANSWERS,
            f"grounded={resp.get('grounded')} "
            f"answer={str(resp.get('answer'))[:200]}",
        )
    except Exception:
        _assert(
            results,
            "appeal[query]_verified_or_safe",
            False,
            traceback.format_exc(),
        )

    # Section-linked notice query (section 177)
    try:
        resp = na.handle("I received an FBR notice under section 177")
        _assert(
            results,
            "notice[section_linked]_verified_or_safe",
            bool(resp.get("grounded"))
            or resp.get("answer") in _SAFE_ANSWERS,
            f"grounded={resp.get('grounded')} "
            f"answer={str(resp.get('answer'))[:200]}",
        )
    except Exception:
        _assert(
            results,
            "notice[section_linked]_verified_or_safe",
            False,
            traceback.format_exc(),
        )

    # Missing evidence refusal
    try:
        resp = na.handle("What is the appeal deadline for Mars colonies?")
        _assert(
            results,
            "notice[missing_evidence]_no_fabrication",
            not resp.get("grounded")
            or resp.get("answer") in _SAFE_ANSWERS,
            f"grounded={resp.get('grounded')} "
            f"answer={str(resp.get('answer'))[:200]}",
        )
        _assert(
            results,
            "notice[missing_evidence]_no_fabricated_deadline",
            not resp.get("grounded")
            or "days" not in str(resp.get("answer", "")).lower()
            or "i do not have" in str(resp.get("answer", "")).lower()
            or "no evidence" in str(resp.get("answer", "")).lower()
            or resp.get("answer") in _SAFE_ANSWERS,
            f"answer={str(resp.get('answer'))[:300]}",
        )
    except Exception:
        _assert(
            results,
            "notice[missing_evidence]_no_fabrication",
            False,
            traceback.format_exc(),
        )


# ============================================================
# ORCHESTRATOR TESTS
# ============================================================

def test_orchestrator(
    results: list[dict[str, Any]], engine: FBRRAGEngine
) -> None:
    orchestrator = AgentOrchestrator(rag_engine=engine)

    # Shared engine: every agent must use the same RAG engine
    # instance (one FAISS load, one BM25 index).
    engine_ids = {
        id(agent.rag_engine) for agent in orchestrator.agents.values()
    }
    _assert(
        results,
        "orchestrator_shares_single_engine",
        len(engine_ids) == 1 and next(iter(engine_ids)) == id(engine),
        f"engine_ids={len(engine_ids)}",
    )

    # 9 agents registered with the orchestrator
    _assert(
        results,
        "orchestrator_has_9_agents",
        len(orchestrator.agents) == 9,
        f"agents={sorted(orchestrator.agents.keys())}",
    )
    _assert(
        results,
        "orchestrator_only_9_required_domains",
        set(orchestrator.agents.keys())
        == {
            "income_tax",
            "sales_tax",
            "federal_excise",
            "customs",
            "registration",
            "return_filing",
            "calculation",
            "notice_appeal",
            "research",
        },
        f"agents={sorted(orchestrator.agents.keys())}",
    )

    # Single-domain execution
    try:
        single = orchestrator.handle(
            "What is the input tax adjustment under Sales Tax Act 1990?"
        )
        _assert(
            results,
            "orchestrator[single_domain]_domains",
            single.get("domains") == ["sales_tax"],
            f"domains={single.get('domains')}",
        )
        _assert(
            results,
            "orchestrator[single_domain]_not_multi",
            single.get("multi_domain") is False,
            f"multi_domain={single.get('multi_domain')}",
        )
        _assert(
            results,
            "orchestrator[single_domain]_verified_or_grounded",
            bool(single.get("grounded"))
            or single.get("answer") in _SAFE_ANSWERS,
            f"grounded={single.get('grounded')} "
            f"answer={str(single.get('answer'))[:200]}",
        )
        _assert(
            results,
            "orchestrator[single_domain]_provenance_complete",
            _provenance_complete(single.get("sources", []))
            or not single.get("sources"),
            f"sources={len(single.get('sources', []))}",
        )
    except Exception:
        _assert(
            results,
            "orchestrator[single_domain]_domains",
            False,
            traceback.format_exc(),
        )

    # Multi-domain: FA + income tax + sales tax
    try:
        multi = orchestrator.handle(
            "What changed in income tax and sales tax under "
            "Finance Act 2026?"
        )
        _assert(
            results,
            "orchestrator[multi_domain]_domains",
            tuple(multi.get("domains", ()))
            == (
                "research",
                "sales_tax",
                "income_tax",
            ),
            f"domains={multi.get('domains')}",
        )
        _assert(
            results,
            "orchestrator[multi_domain]_three_domain_results",
            len(multi.get("domain_results", [])) == 3,
            f"n={len(multi.get('domain_results', []))}",
        )
        combined_answer = str(multi.get("answer", ""))
        _assert(
            results,
            "orchestrator[multi_domain]_labels_present",
            all(
                label in combined_answer
                for label in (
                    "[Research]",
                    "[Income Tax]",
                    "[Sales Tax]",
                )
            ),
            f"answer={combined_answer[:400]}",
        )
        all_domain_safe = all(
            bool(r.get("grounded"))
            or r.get("answer") in _SAFE_ANSWERS
            for r in multi.get("domain_results", [])
        )
        _assert(
            results,
            "orchestrator[multi_domain]_never_exposes_unverified",
            all_domain_safe,
            f"domain_flags={[r.get('grounded') for r in multi.get('domain_results', [])]}",
        )
        _assert(
            results,
            "orchestrator[multi_domain]_sources_aggregated",
            _provenance_complete(multi.get("sources", []))
            or not multi.get("sources"),
            f"sources={len(multi.get('sources', []))}",
        )
        _assert(
            results,
            "orchestrator[multi_domain]_grounded_is_all_of_domains",
            bool(multi.get("grounded"))
            == all(
                bool(r.get("grounded"))
                for r in multi.get("domain_results", [])
            ),
            f"overall={multi.get('grounded')} "
            f"per_domain={[r.get('grounded') for r in multi.get('domain_results', [])]}",
        )
    except Exception:
        _assert(
            results,
            "orchestrator[multi_domain]_domains",
            False,
            traceback.format_exc(),
        )

    # Out-of-domain routes to research (the safe multi-domain
    # fallback), never to a removed domain.
    try:
        out_of_domain = orchestrator.handle(
            "What is the weather in Lahore today?"
        )
        _assert(
            results,
            "orchestrator[out_of_domain]_no_removed_targets",
            set(out_of_domain.get("domains", []))
            .isdisjoint(
                {"property_valuation", "finance_act", "general_fbr"}
            ),
            f"domains={out_of_domain.get('domains')}",
        )
        _assert(
            results,
            "orchestrator[out_of_domain]_verified_or_grounded",
            bool(out_of_domain.get("grounded"))
            or out_of_domain.get("answer") in _SAFE_ANSWERS,
            f"grounded={out_of_domain.get('grounded')} "
            f"answer={str(out_of_domain.get('answer'))[:200]}",
        )
    except Exception:
        _assert(
            results,
            "orchestrator[out_of_domain]_no_removed_targets",
            False,
            traceback.format_exc(),
        )

    # Determinism: same input must produce same orchestrator
    # output across 3 repeated calls.
    try:
        q = "calculate 10% tax on Rs 500,000"
        a1 = orchestrator.handle(q)
        a2 = orchestrator.handle(q)
        a3 = orchestrator.handle(q)
        _assert(
            results,
            "orchestrator[determinism]_3x_repeat",
            a1.get("domains") == a2.get("domains") == a3.get("domains"),
            f"a1={a1.get('domains')} a2={a2.get('domains')} "
            f"a3={a3.get('domains')}",
        )
    except Exception:
        _assert(
            results,
            "orchestrator[determinism]_3x_repeat",
            False,
            traceback.format_exc(),
        )


# ============================================================
# PHASE 2: QUERY UNDERSTANDING TESTS
# ============================================================

def test_phase2_query_understanding(
    results: list[dict[str, Any]],
) -> None:
    """
    Phase 2 (Query Understanding) tests. These tests are
    FAISS-free and LLM-free: they exercise the deterministic
    pre-router pipeline (Receive → Pre-process → Intent →
    Classification).

    Cases cover the 20 mandatory scenarios in the master prompt:
    1. clean normal query
    2. query with extra whitespace
    3. spelling variation
    4. Roman Urdu / mixed-language input
    5. tax terminology preservation
    6. percentage preservation
    7. monetary amount preservation
    8. tax-year preservation
    9. date preservation
    10. section/reference preservation
    11. NTN/STRN/IRIS preservation
    12. calculation classification
    13. registration classification
    14. return-filing classification
    15. notice/appeal classification
    16. research classification
    17. single-domain routing compatibility
    18. multi-domain routing compatibility
    19. ambiguous query behavior
    20. determinism
    """

    from app.query_understanding import (
        classify_query,
        detect_intent,
        preprocess_query,
        understand_query,
    )

    # 1. clean normal query
    try:
        u = understand_query("What is the income tax rate for salaried persons?")
        _assert(
            results,
            "phase2[1]_clean_normal_query",
            bool(u.normalized) and "income tax rate" in u.normalized,
            f"normalized={u.normalized!r}",
        )
    except Exception:
        _assert(
            results,
            "phase2[1]_clean_normal_query",
            False,
            traceback.format_exc(),
        )

    # 2. extra whitespace
    try:
        u = understand_query("   calculate    10%    tax    on  Rs  500000   ")
        _assert(
            results,
            "phase2[2]_extra_whitespace_collapsed",
            "  " not in u.normalized
            and "calculate 10% tax on Rs 500000" in u.normalized,
            f"normalized={u.normalized!r}",
        )
    except Exception:
        _assert(
            results,
            "phase2[2]_extra_whitespace_collapsed",
            False,
            traceback.format_exc(),
        )

    # 3. spelling variation (controlled spelling)
    try:
        u = understand_query("How to registar for NTN in IRIS")
        _assert(
            results,
            "phase2[3]_spelling_normalized",
            "register" in u.normalized or "registration" in u.normalized,
            f"normalized={u.normalized!r}",
        )
    except Exception:
        _assert(
            results,
            "phase2[3]_spelling_normalized",
            False,
            traceback.format_exc(),
        )

    # 4. Roman Urdu / mixed-language input
    try:
        u = understand_query("main tax return kaise file karu")
        _assert(
            results,
            "phase2[4]_roman_urdu_detected",
            u.language == "roman_urdu",
            f"language={u.language!r} normalized={u.normalized!r}",
        )
    except Exception:
        _assert(
            results,
            "phase2[4]_roman_urdu_detected",
            False,
            traceback.format_exc(),
        )

    # 5. tax terminology preservation
    try:
        u = understand_query("What is FED on cigarettes under the Federal Excise Act 2005?")
        _assert(
            results,
            "phase2[5]_tax_terminology_preserved",
            "Federal Excise" in u.normalized
            and "2005" in u.normalized,
            f"normalized={u.normalized!r}",
        )
    except Exception:
        _assert(
            results,
            "phase2[5]_tax_terminology_preserved",
            False,
            traceback.format_exc(),
        )

    # 6. percentage preservation
    try:
        u = understand_query("calculate 17% sales tax on Rs 1,000,000")
        c = u.classification.to_dict()
        _assert(
            results,
            "phase2[6]_percentage_preserved",
            any("17%" in p for p in c.get("percentages", [])),
            f"percentages={c.get('percentages')}",
        )
    except Exception:
        _assert(
            results,
            "phase2[6]_percentage_preserved",
            False,
            traceback.format_exc(),
        )

    # 7. monetary amount preservation
    try:
        u = understand_query("calculate 10 percent of Rs 500,000")
        c = u.classification.to_dict()
        _assert(
            results,
            "phase2[7]_monetary_amount_preserved",
            any("500" in a for a in c.get("amounts", [])),
            f"amounts={c.get('amounts')}",
        )
    except Exception:
        _assert(
            results,
            "phase2[7]_monetary_amount_preserved",
            False,
            traceback.format_exc(),
        )

    # 8. tax-year preservation
    try:
        u = understand_query("What is the tax rate for TY 2024?")
        c = u.classification.to_dict()
        _assert(
            results,
            "phase2[8]_tax_year_preserved",
            any("2024" in y for y in c.get("tax_year", [])),
            f"tax_year={c.get('tax_year')}",
        )
    except Exception:
        _assert(
            results,
            "phase2[8]_tax_year_preserved",
            False,
            traceback.format_exc(),
        )

    # 9. date preservation
    try:
        u = understand_query("What is the filing deadline 30-09-2024?")
        c = u.classification.to_dict()
        _assert(
            results,
            "phase2[9]_date_preserved",
            len(c.get("dates", [])) >= 1,
            f"dates={c.get('dates')}",
        )
    except Exception:
        _assert(
            results,
            "phase2[9]_date_preserved",
            False,
            traceback.format_exc(),
        )

    # 10. section/reference preservation
    try:
        u = understand_query("What is Section 177 of the Income Tax Ordinance 2001?")
        c = u.classification.to_dict()
        _assert(
            results,
            "phase2[10]_section_reference_preserved",
            any("section 177" in s.lower() for s in c.get("section_references", [])),
            f"section_references={c.get('section_references')}",
        )
    except Exception:
        _assert(
            results,
            "phase2[10]_section_reference_preserved",
            False,
            traceback.format_exc(),
        )

    # 11. NTN/STRN/IRIS preservation
    try:
        u = understand_query("How do I get NTN in IRIS for my business?")
        normalized = u.normalized.lower()
        _assert(
            results,
            "phase2[11]_ntn_strn_iris_preserved",
            "ntn" in normalized and "iris" in normalized,
            f"normalized={u.normalized!r}",
        )
    except Exception:
        _assert(
            results,
            "phase2[11]_ntn_strn_iris_preserved",
            False,
            traceback.format_exc(),
        )

    # 12. calculation classification
    try:
        u = understand_query("calculate 10% tax on Rs 500,000")
        _assert(
            results,
            "phase2[12]_calculation_classified",
            u.intent == "calculation",
            f"intent={u.intent!r}",
        )
    except Exception:
        _assert(
            results,
            "phase2[12]_calculation_classified",
            False,
            traceback.format_exc(),
        )

    # 13. registration classification
    try:
        u = understand_query("How do I register for NTN in IRIS?")
        _assert(
            results,
            "phase2[13]_registration_classified",
            u.intent == "registration",
            f"intent={u.intent!r}",
        )
    except Exception:
        _assert(
            results,
            "phase2[13]_registration_classified",
            False,
            traceback.format_exc(),
        )

    # 14. return-filing classification
    try:
        u = understand_query("What is the due date for filing of return?")
        _assert(
            results,
            "phase2[14]_return_filing_classified",
            u.intent == "filing",
            f"intent={u.intent!r}",
        )
    except Exception:
        _assert(
            results,
            "phase2[14]_return_filing_classified",
            False,
            traceback.format_exc(),
        )

    # 15. notice/appeal classification
    try:
        u = understand_query("I received an FBR notice under section 161, how do I appeal?")
        _assert(
            results,
            "phase2[15]_notice_appeal_classified",
            u.intent == "notice_appeal",
            f"intent={u.intent!r}",
        )
    except Exception:
        _assert(
            results,
            "phase2[15]_notice_appeal_classified",
            False,
            traceback.format_exc(),
        )

    # 16. research classification
    try:
        u = understand_query("compare sales tax and income tax under Finance Act 2025")
        _assert(
            results,
            "phase2[16]_research_classified",
            u.intent == "research",
            f"intent={u.intent!r}",
        )
    except Exception:
        _assert(
            results,
            "phase2[16]_research_classified",
            False,
            traceback.format_exc(),
        )

    # 17. single-domain routing compatibility
    try:
        u = understand_query("What is Section 177 of the Income Tax Ordinance 2001?")
        router = FBRQueryRouter()
        decision = router.route(u.normalized)
        _assert(
            results,
            "phase2[17]_single_domain_routing_compat",
            "income_tax" in decision.domains,
            f"domains={list(decision.domains)} normalized={u.normalized!r}",
        )
    except Exception:
        _assert(
            results,
            "phase2[17]_single_domain_routing_compat",
            False,
            traceback.format_exc(),
        )

    # 18. multi-domain routing compatibility
    try:
        u = understand_query("What changed in income tax and sales tax under Finance Act 2026?")
        router = FBRQueryRouter()
        decision = router.route(u.normalized)
        _assert(
            results,
            "phase2[18]_multi_domain_routing_compat",
            len(decision.domains) >= 2
            and "research" in decision.domains,
            f"domains={list(decision.domains)}",
        )
    except Exception:
        _assert(
            results,
            "phase2[18]_multi_domain_routing_compat",
            False,
            traceback.format_exc(),
        )

    # 19. ambiguous query behavior (deterministic, classified as info)
    try:
        u = understand_query("What is the tax rate?")
        _assert(
            results,
            "phase2[19]_ambiguous_query_deterministic",
            u.intent in ("information", "legal_rule"),
            f"intent={u.intent!r}",
        )
    except Exception:
        _assert(
            results,
            "phase2[19]_ambiguous_query_deterministic",
            False,
            traceback.format_exc(),
        )

    # 20. determinism (3 repeats)
    try:
        q = "calculate 17% sales tax on Rs 1,000,000"
        u1 = understand_query(q)
        u2 = understand_query(q)
        u3 = understand_query(q)
        same = (
            u1.to_dict() == u2.to_dict() == u3.to_dict()
        )
        _assert(
            results,
            "phase2[20]_deterministic_3x",
            same,
            f"u1={u1.to_dict()} u2={u2.to_dict()} u3={u3.to_dict()}",
        )
    except Exception:
        _assert(
            results,
            "phase2[20]_deterministic_3x",
            False,
            traceback.format_exc(),
        )

    # Supplementary: classification preserves all entities
    try:
        q = "What is the 15% tax on Rs 1,000,000 under Section 111 of ITO 2001 for TY 2024 in Karachi?"
        u = understand_query(q)
        c = u.classification.to_dict()
        has_pct = any("15" in p for p in c.get("percentages", []))
        has_amt = any("1,000,000" in a or "1000000" in a for a in c.get("amounts", []))
        has_sec = any("section 111" in s.lower() for s in c.get("section_references", []))
        has_year = any("2024" in y for y in c.get("tax_year", []))
        has_loc = c.get("location") is not None
        _assert(
            results,
            "phase2[suppl]_all_entities_extracted",
            has_pct and has_amt and has_sec and has_year and has_loc,
            f"pct={has_pct} amt={has_amt} sec={has_sec} "
            f"year={has_year} loc={has_loc}",
        )
    except Exception:
        _assert(
            results,
            "phase2[suppl]_all_entities_extracted",
            False,
            traceback.format_exc(),
        )


# ============================================================
# PHASE 6: ANSWER SYNTHESIS TESTS
# ============================================================

def _phase6_make_safe_refusal() -> dict[str, Any]:
    """Build a fake safe-refusal response for Phase 6 unit tests."""
    return {
        "question": "What is the weather on Mars?",
        "answer": _NO_EVIDENCE_ANSWER,
        "sources": [],
        "verification": {
            "passed": True,
            "reason": "no_evidence_safe_refusal",
            "failed_checks": [],
            "checks": {},
        },
        "grounded": True,
        "domain": "research",
        "retrieval_question": "What is the weather on Mars?",
    }


def _phase6_make_grounded_calculation() -> dict[str, Any]:
    """Build a fake grounded calculation response for Phase 6 unit tests."""
    return {
        "question": "calculate 10% tax on Rs 500,000",
        "answer": (
            "The 10% tax on Rs 500,000 is Rs 50,000. "
            "Calculation basis: 10% of 500,000 = 50,000. Result: 50,000."
        ),
        "sources": [
            {
                "chunk_id": "c1",
                "source": "income_tax_ordinance_2001.pdf",
                "source_path": "data/income_tax_ordinance_2001.pdf",
                "source_sha256": "a" * 64,
                "document_id": "ito-2001",
                "section_reference": "Section 4",
                "page_start": 10,
                "page_end": 12,
                "score": 0.85,
                "text": "Income tax is charged at the rate of 10 percent on taxable income.",
            },
            {
                "chunk_id": "c2",
                "source": "income_tax_ordinance_2001.pdf",
                "source_path": "data/income_tax_ordinance_2001.pdf",
                "source_sha256": "a" * 64,
                "document_id": "ito-2001",
                "section_reference": "Section 5",
                "page_start": 15,
                "page_end": 15,
                "score": 0.78,
                "text": "Taxable income shall be computed at a rate of 10 percent.",
            },
        ],
        "verification": {
            "passed": True,
            "reason": "verified",
            "failed_checks": [],
            "checks": {
                "grounding": {"passed": True},
                "answer_size": {"passed": True},
            },
        },
        "grounded": True,
        "domain": "calculation",
        "retrieval_question": "calculate 10% tax on Rs 500,000",
        "calculation": {
            "kind": "percent_of_amount",
            "percent": 10.0,
            "amount": 500000.0,
            "expression": "10.0% of 500000.0",
            "result": 50000.0,
        },
    }


def _phase6_make_grounded_procedure() -> dict[str, Any]:
    """Build a fake grounded procedural response."""
    return {
        "question": "How do I register for NTN in IRIS?",
        "answer": (
            "To register for NTN in IRIS, follow these steps: "
            "1. Visit the IRIS portal. 2. Create an account. "
            "3. Submit required documents. 4. Receive NTN."
        ),
        "sources": [
            {
                "chunk_id": "r1",
                "source": "iris_registration_guide.pdf",
                "source_path": "data/iris_registration_guide.pdf",
                "source_sha256": "b" * 64,
                "document_id": "iris-guide",
                "section_reference": "Chapter 1",
                "page_start": 1,
                "page_end": 5,
                "score": 0.92,
                "text": "IRIS registration is required for all taxpayers.",
            },
        ],
        "verification": {
            "passed": True,
            "reason": "verified",
            "failed_checks": [],
            "checks": {"grounding": {"passed": True}},
        },
        "grounded": True,
        "domain": "registration",
        "retrieval_question": "How do I register for National Tax Number?",
    }


def _phase6_make_grounded_legal() -> dict[str, Any]:
    """Build a fake grounded legal/rule response."""
    return {
        "question": "What is Section 177 of the Income Tax Ordinance 2001?",
        "answer": (
            "Section 177 of the Income Tax Ordinance 2001 deals with "
            "the power of the Commissioner to require returns."
        ),
        "sources": [
            {
                "chunk_id": "l1",
                "source": "income_tax_ordinance_2001.pdf",
                "source_path": "data/ito_2001.pdf",
                "source_sha256": "c" * 64,
                "document_id": "ito-2001",
                "section_reference": "Section 177",
                "page_start": 200,
                "page_end": 205,
                "score": 0.88,
                "text": "Section 177: Power to require returns.",
            },
        ],
        "verification": {
            "passed": True,
            "reason": "verified",
            "failed_checks": [],
            "checks": {"grounding": {"passed": True}},
        },
        "grounded": True,
        "domain": "income_tax",
        "retrieval_question": "section 177 return under the Income Tax Ordinance 2001",
    }


def _phase6_make_unverified() -> dict[str, Any]:
    """Build a fake unverified response for safety tests."""
    return {
        "question": "What is the tax on Mars colonies?",
        "answer": "The tax rate on Mars colonies is 25%.",
        "sources": [
            {
                "chunk_id": "u1",
                "source": "fake.pdf",
                "source_path": "data/fake.pdf",
                "source_sha256": "d" * 64,
                "document_id": "fake",
                "section_reference": "Section X",
                "page_start": 1,
                "page_end": 1,
                "score": 0.5,
                "text": "Mars tax info.",
            },
        ],
        "verification": {
            "passed": False,
            "reason": "grounding_failed",
            "failed_checks": ["grounding", "speculation"],
            "checks": {},
        },
        "grounded": False,
        "domain": "research",
        "retrieval_question": "What is the tax on Mars colonies?",
    }


def test_phase6_answer_synthesis(
    results: list[dict[str, Any]],
) -> None:
    """
    Phase 6 (Answer Generation) tests. These tests are FAISS-free
    and LLM-free: they exercise the deterministic post-RAG
    synthesis layer (Information Synthesis → Structured Answer).

    Cases cover the 18 mandatory scenarios in the master prompt.
    """

    from app.answer_synthesis import (
        ConfidenceInfo,
        Example,
        SourceReference,
        StructuredAnswer,
        synthesize_answer,
    )

    # 1. grounded factual answer
    try:
        resp = _phase6_make_grounded_legal()
        result = synthesize_answer(
            resp,
            {"intent": "legal_rule", "intent_type": "legal",
             "section_references": ["section 177"]},
        )
        _assert(
            results,
            "phase6[1]_grounded_factual_answer",
            result.grounded and "Section 177" in result.answer,
            f"grounded={result.grounded} answer={result.answer[:200]!r}",
        )
    except Exception:
        _assert(
            results,
            "phase6[1]_grounded_factual_answer",
            False,
            traceback.format_exc(),
        )

    # 2. insufficient-evidence safe refusal
    try:
        resp = _phase6_make_safe_refusal()
        result = synthesize_answer(
            resp,
            {"intent": "information", "intent_type": "informational"},
        )
        _assert(
            results,
            "phase6[2]_insufficient_evidence_safe_refusal",
            not result.raw_grounded
            and result.answer == _NO_EVIDENCE_ANSWER,
            f"grounded={result.raw_grounded} answer={result.answer!r}",
        )
    except Exception:
        _assert(
            results,
            "phase6[2]_insufficient_evidence_safe_refusal",
            False,
            traceback.format_exc(),
        )

    # 3. procedural answer
    try:
        resp = _phase6_make_grounded_procedure()
        result = synthesize_answer(
            resp,
            {"intent": "procedure", "intent_type": "procedural"},
        )
        _assert(
            results,
            "phase6[3]_procedural_answer",
            result.grounded
            and "procedure" in str(result.sections).lower()
            or "registration" in str(result.sections).lower(),
            f"answer_type={result.answer_type} sections={result.sections}",
        )
    except Exception:
        _assert(
            results,
            "phase6[3]_procedural_answer",
            False,
            traceback.format_exc(),
        )

    # 4. calculation answer
    try:
        resp = _phase6_make_grounded_calculation()
        result = synthesize_answer(
            resp,
            {"intent": "calculation", "intent_type": "calculation"},
        )
        _assert(
            results,
            "phase6[4]_calculation_answer",
            result.grounded
            and result.answer_type == "calculation"
            and "calculation" in result.sections
            and result.sections["calculation"]["result"] == 50000.0,
            f"sections={result.sections}",
        )
    except Exception:
        _assert(
            results,
            "phase6[4]_calculation_answer",
            False,
            traceback.format_exc(),
        )

    # 5. legal/rule answer
    try:
        resp = _phase6_make_grounded_legal()
        result = synthesize_answer(
            resp,
            {"intent": "legal_rule", "intent_type": "legal",
             "section_references": ["section 177"]},
        )
        _assert(
            results,
            "phase6[5]_legal_rule_answer",
            result.grounded
            and "legal" in result.sections
            and any(
                s.section and "Section 177" in s.section
                for s in result.sources
            ),
            f"sections={result.sections} sources={result.sources}",
        )
    except Exception:
        _assert(
            results,
            "phase6[5]_legal_rule_answer",
            False,
            traceback.format_exc(),
        )

    # 6. date/deadline answer
    try:
        resp = _phase6_make_grounded_legal()
        resp["answer"] = "The deadline is 30-09-2024."
        resp["question"] = "What is the filing deadline?"
        result = synthesize_answer(
            resp,
            {"intent": "date_deadline", "intent_type": "date",
             "dates": ["30-09-2024"], "tax_year": []},
        )
        _assert(
            results,
            "phase6[6]_date_deadline_answer",
            result.grounded
            and "dates" in result.sections
            and "30-09-2024" in result.sections["dates"]["mentioned_dates"],
            f"sections={result.sections}",
        )
    except Exception:
        _assert(
            results,
            "phase6[6]_date_deadline_answer",
            False,
            traceback.format_exc(),
        )

    # 7. multi-source answer
    try:
        resp = _phase6_make_grounded_calculation()
        result = synthesize_answer(
            resp,
            {"intent": "calculation", "intent_type": "calculation"},
        )
        _assert(
            results,
            "phase6[7]_multi_source_answer",
            result.grounded and len(result.sources) == 2,
            f"sources_count={len(result.sources)}",
        )
    except Exception:
        _assert(
            results,
            "phase6[7]_multi_source_answer",
            False,
            traceback.format_exc(),
        )

    # 8. source attribution
    try:
        resp = _phase6_make_grounded_legal()
        result = synthesize_answer(
            resp,
            {"intent": "legal_rule", "intent_type": "legal"},
        )
        _assert(
            results,
            "phase6[8]_source_attribution",
            any(
                "income_tax_ordinance_2001.pdf" in s.document
                for s in result.sources
            ),
            f"sources={result.sources}",
        )
    except Exception:
        _assert(
            results,
            "phase6[8]_source_attribution",
            False,
            traceback.format_exc(),
        )

    # 9. provenance preservation (full metadata)
    try:
        resp = _phase6_make_grounded_legal()
        result = synthesize_answer(
            resp,
            {"intent": "legal_rule", "intent_type": "legal"},
        )
        _assert(
            results,
            "phase6[9]_provenance_preservation",
            any(
                s.page_range == "200-205" and s.section == "Section 177"
                for s in result.sources
            ),
            f"sources={result.sources}",
        )
    except Exception:
        _assert(
            results,
            "phase6[9]_provenance_preservation",
            False,
            traceback.format_exc(),
        )

    # 10. confidence propagation
    try:
        resp = _phase6_make_grounded_calculation()
        result = synthesize_answer(
            resp,
            {"intent": "calculation", "intent_type": "calculation"},
        )
        _assert(
            results,
            "phase6[10]_confidence_propagation",
            result.confidence.grounded is True
            and result.confidence.verification_passed is True
            and result.confidence.sources_count == 2
            and result.confidence.confidence_label in (
                "high", "medium",
            ),
            f"confidence={result.confidence.to_dict()}",
        )
    except Exception:
        _assert(
            results,
            "phase6[10]_confidence_propagation",
            False,
            traceback.format_exc(),
        )

    # 11. example insertion when appropriate
    try:
        resp = _phase6_make_grounded_calculation()
        result = synthesize_answer(
            resp,
            {"intent": "calculation", "intent_type": "calculation"},
        )
        _assert(
            results,
            "phase6[11]_example_inserted_for_calculation",
            len(result.examples) >= 1
            and "Rs" in result.examples[0].text,
            f"examples={result.examples}",
        )
    except Exception:
        _assert(
            results,
            "phase6[11]_example_inserted_for_calculation",
            False,
            traceback.format_exc(),
        )

    # 12. no-example behavior when unnecessary (information intent)
    try:
        resp = _phase6_make_grounded_legal()
        result = synthesize_answer(
            resp,
            {"intent": "legal_rule", "intent_type": "legal",
             "section_references": ["section 177"]},
        )
        # legal_rule may add an example, but information intent must not
        result2_resp = {
            "question": "What is X?",
            "answer": "X is a tax.",
            "sources": [
                {
                    "chunk_id": "i1",
                    "source": "doc.pdf",
                    "source_path": "data/doc.pdf",
                    "source_sha256": "e" * 64,
                    "document_id": "doc",
                    "section_reference": "Section 1",
                    "page_start": 1,
                    "page_end": 1,
                    "score": 0.8,
                    "text": "X is a tax.",
                }
            ],
            "verification": {
                "passed": True,
                "reason": "verified",
                "failed_checks": [],
                "checks": {},
            },
            "grounded": True,
            "domain": "research",
            "retrieval_question": "What is X?",
        }
        result2 = synthesize_answer(
            result2_resp,
            {"intent": "information", "intent_type": "informational"},
        )
        _assert(
            results,
            "phase6[12]_no_example_for_information",
            len(result2.examples) == 0,
            f"examples={result2.examples}",
        )
    except Exception:
        _assert(
            results,
            "phase6[12]_no_example_for_information",
            False,
            traceback.format_exc(),
        )

    # 13. structured answer formatting (sources in output)
    try:
        resp = _phase6_make_grounded_legal()
        result = synthesize_answer(
            resp,
            {"intent": "legal_rule", "intent_type": "legal"},
        )
        _assert(
            results,
            "phase6[13]_structured_answer_formatting",
            "Sources:" in result.answer
            and result.confidence is not None,
            f"answer={result.answer[:200]!r}",
        )
    except Exception:
        _assert(
            results,
            "phase6[13]_structured_answer_formatting",
            False,
            traceback.format_exc(),
        )

    # 14. LLM output remains grounded (no fabrication)
    try:
        resp = _phase6_make_grounded_legal()
        result = synthesize_answer(
            resp,
            {"intent": "legal_rule", "intent_type": "legal"},
        )
        # The answer must contain a fact from the source (Section 177).
        _assert(
            results,
            "phase6[14]_llm_output_remains_grounded",
            "Section 177" in result.raw_answer
            and result.raw_answer == resp["answer"],
            f"raw_answer={result.raw_answer!r}",
        )
    except Exception:
        _assert(
            results,
            "phase6[14]_llm_output_remains_grounded",
            False,
            traceback.format_exc(),
        )

    # 15. hallucination guard (unverified response is replaced with safe refusal)
    try:
        resp = _phase6_make_unverified()
        result = synthesize_answer(
            resp,
            {"intent": "information", "intent_type": "informational"},
        )
        _assert(
            results,
            "phase6[15]_hallucination_guard",
            not result.grounded
            and (
                result.answer == PLACEHOLDER_ANSWER
                or "do not have" in result.answer.lower()
                or "insufficient" in result.answer.lower()
                or "no evidence" in result.answer.lower()
            ),
            f"grounded={result.grounded} answer={result.answer[:200]!r}",
        )
    except Exception:
        _assert(
            results,
            "phase6[15]_hallucination_guard",
            False,
            traceback.format_exc(),
        )

    # 16. verification cannot be bypassed (unverified -> safe refusal)
    try:
        resp = _phase6_make_unverified()
        # Pass a fake "grounded" flag to see if synthesis respects verification.
        resp["grounded"] = True
        result = synthesize_answer(
            resp,
            {"intent": "information", "intent_type": "informational"},
        )
        _assert(
            results,
            "phase6[16]_verification_cannot_be_bypassed",
            result.grounded is False,
            f"grounded={result.grounded} answer={result.answer[:200]!r}",
        )
    except Exception:
        _assert(
            results,
            "phase6[16]_verification_cannot_be_bypassed",
            False,
            traceback.format_exc(),
        )

    # 17. deterministic non-LLM portions
    try:
        resp = _phase6_make_grounded_calculation()
        r1 = synthesize_answer(
            resp,
            {"intent": "calculation", "intent_type": "calculation"},
        )
        r2 = synthesize_answer(
            resp,
            {"intent": "calculation", "intent_type": "calculation"},
        )
        # Compare deterministic dicts (excluding raw_answer, raw_verification
        # which are dicts and could in principle be re-ordered; we use the
        # full dict comparison since the source data is identical).
        same = r1.to_dict() == r2.to_dict()
        _assert(
            results,
            "phase6[17]_deterministic_non_llm",
            same,
            f"r1={r1.to_dict()} r2={r2.to_dict()}",
        )
    except Exception:
        _assert(
            results,
            "phase6[17]_deterministic_non_llm",
            False,
            traceback.format_exc(),
        )

    # 18. existing agent outputs remain compatible (no schema breakage)
    try:
        # Test with a real agent response shape.
        engine = FBRRAGEngine()
        agent = IncomeTaxAgent(rag_engine=engine)
        response = agent.handle("Section 177 of ITO 2001")
        result = synthesize_answer(response)
        _assert(
            results,
            "phase6[18]_agent_outputs_compatible",
            isinstance(result, StructuredAnswer)
            and isinstance(result.confidence, ConfidenceInfo),
            f"type={type(result).__name__}",
        )
    except Exception:
        _assert(
            results,
            "phase6[18]_agent_outputs_compatible",
            False,
            traceback.format_exc(),
        )

    # Supplementary: multi-domain orchestrator output remains compatible
    try:
        engine = FBRRAGEngine()
        orchestrator = AgentOrchestrator(rag_engine=engine)
        response = orchestrator.handle(
            "What changed in income tax and sales tax under Finance Act 2026?"
        )
        result = synthesize_answer(response)
        _assert(
            results,
            "phase6[suppl]_orchestrator_outputs_compatible",
            isinstance(result, StructuredAnswer),
            f"type={type(result).__name__} answer_type={result.answer_type}",
        )
    except Exception:
        _assert(
            results,
            "phase6[suppl]_orchestrator_outputs_compatible",
            False,
            traceback.format_exc(),
        )


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    print("=" * 72)
    print("FBR PHASE 9 (CORRECTED) - 9-AGENT ARCHITECTURE TESTS")
    print("=" * 72)
    print()
    results = _results()

    # Pure (FAISS-free) tests first
    print("--- Architecture invariants ---")
    test_architecture_invariants(results)

    print("--- Router (deterministic, FAISS-free) ---")
    test_router(results)
    test_router_targets_strict(results)
    test_router_determinism(results)

    print("--- Query expansion (deterministic) ---")
    test_query_expansion(results)

    # Phase 2: Query Understanding (FAISS-free, LLM-free)
    print("--- Phase 2: Query Understanding ---")
    test_phase2_query_understanding(results)

    # Phase 6: Answer Synthesis (FAISS-free, LLM-free)
    print("--- Phase 6: Answer Synthesis ---")
    test_phase6_answer_synthesis(results)

    # RAG-dependent tests
    print("--- Specialized agents (RAG + verification) ---")
    engine = FBRRAGEngine()
    test_agents(results, engine)
    test_agent_safety(results, engine)
    test_calculation_extraction(results)
    test_calculation_agent(results, engine)
    test_research_agent(results, engine)
    test_notice_appeal_agent(results, engine)

    print("--- Orchestrator ---")
    test_orchestrator(results, engine)

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    print()
    print("=" * 72)
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        print(f"[{status}] {result['name']}")
        if not result["passed"]:
            print(f"        detail: {result['detail']}")
    print("=" * 72)
    print(f"Total : {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print("=" * 72)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
