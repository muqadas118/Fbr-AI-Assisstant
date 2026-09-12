"""
Deterministic FBR Query Router (Phase 9 corrected).

Classifies a user query into one or more FBR tax domains using
transparent keyword/regex signals. Pure string logic only:

- No LLM.
- No randomness.
- No network.
- No FAISS / embedding loading.

The same query always produces the same routing decision.

FINAL REQUIRED 9-AGENT ARCHITECTURE
===================================

  1. income_tax       - Income Tax Ordinance, sections, returns, WHT
  2. sales_tax        - Sales Tax Act, registration, returns, invoices
  3. federal_excise   - Federal Excise Act, FED rates, SROs
  4. customs          - Customs Act, imports, tariffs, valuation
  5. registration     - NTN, IRIS, taxpayer registration procedures
  6. return_filing    - return forms, deadlines, amendments
  7. calculation      - tax math, penalty math, comparison math
  8. notice_appeal    - FBR notices, appeals, response guidance
  9. research         - multi-domain, FA amendment research,
                        cross-document comparison, property valuation
                        research

Finance Act and Property Valuation are NOT standalone agents.
They are routing / query-expansion / retrieval signals that
feed the appropriate specialized agent or the Research Agent.

Priority order (highest first):

  1. research
  2. calculation
  3. notice_appeal
  4. return_filing
  5. registration
  6. customs
  7. federal_excise
  8. sales_tax
  9. income_tax

Multi-domain queries return every matched domain, priority-ordered.
A city name alone never triggers Research routing; a context
term (property/valuation/tehsil/district) must also be present.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ============================================================
# DOMAIN CONSTANTS
# ============================================================

DOMAIN_INCOME_TAX = "income_tax"
DOMAIN_SALES_TAX = "sales_tax"
DOMAIN_FEDERAL_EXCISE = "federal_excise"
DOMAIN_CUSTOMS = "customs"
DOMAIN_REGISTRATION = "registration"
DOMAIN_RETURN_FILING = "return_filing"
DOMAIN_CALCULATION = "calculation"
DOMAIN_NOTICE_APPEAL = "notice_appeal"
DOMAIN_RESEARCH = "research"

DOMAIN_PRIORITY: tuple[str, ...] = (
    DOMAIN_RESEARCH,
    DOMAIN_CALCULATION,
    DOMAIN_NOTICE_APPEAL,
    DOMAIN_RETURN_FILING,
    DOMAIN_REGISTRATION,
    DOMAIN_CUSTOMS,
    DOMAIN_FEDERAL_EXCISE,
    DOMAIN_SALES_TAX,
    DOMAIN_INCOME_TAX,
)


# ============================================================
# DOMAIN SIGNALS (transparent keyword/regex phrases)
# ============================================================

_INCOME_TAX_SIGNALS: tuple[str, ...] = (
    "income tax",
    "incometax",
    "income-tax",
    "ordinance 2001",
    "income tax ordinance",
    "withholding",
    "return of income",
    "income tax return",
    "assessment order",
    "filer",
    "non-filer",
    "wht",
    "filer status",
    "active taxpayer",
    "atll",
    "reduce tax",
    "reduce my tax",
    "tax reduction",
    "tax saving",
    "tax savings",
    "save tax",
    "minimize tax",
    "optimize tax",
    "tax optimization",
    "tax planning",
    "lower tax",
    "lower my tax",
    "lawful deduction",
)

_SALES_TAX_SIGNALS: tuple[str, ...] = (
    "sales tax",
    "salestax",
    "sales-tax",
    "input tax",
    "output tax",
    "strn",
    "pos",
    "invoice",
)

_FEDERAL_EXCISE_SIGNALS: tuple[str, ...] = (
    "federal excise",
    "excise duty",
    "excise",
    "sro",
)

_CUSTOMS_SIGNALS: tuple[str, ...] = (
    "customs",
    "customs duty",
    "custom duty",
    "import duty",
    "export duty",
    "tariff",
    "hs code",
    "hscode",
    "webooc",
    "cd",
    "import",
    "export",
    "imported goods",
    "exported goods",
    "customs valuation",
    "igm",
    "egm",
    "bill of lading",
    "bill of export",
)

_REGISTRATION_SIGNALS: tuple[str, ...] = (
    "registration",
    "register",
    "registered",
    "ntn",
    "iris",
    "strn",
    "enrollment",
    "new taxpayer",
    "taxpayer registration",
    "iris registration",
    "how to register",
)

_RETURN_FILING_SIGNALS: tuple[str, ...] = (
    "return filing",
    "file return",
    "filing of return",
    "file a return",
    "filing deadline",
    "due date",
    "income tax return",
    "sales tax return",
    "withholding statement",
    "annual return",
    "monthly return",
    "quarterly return",
    "wht return",
    "amend return",
    "revise return",
    "filer",
    "non-filer",
)

_CALCULATION_SIGNALS: tuple[str, ...] = (
    "calculate",
    "calculated",
    "calculated tax",
    "computed",
    "compute",
    "computation",
    "tax amount",
    "tax liability",
    "taxable income",
    "penalty amount",
    "how much tax",
    "how much penalty",
    "wht on",
    "withholding amount",
    "what is the penalty",
    "tax on rs",
    "amount of tax",
    "compute tax",
    "compute penalty",
    "tax on amount",
)

_NOTICE_APPEAL_SIGNALS: tuple[str, ...] = (
    "notice",
    "received a notice",
    "show cause",
    "show-cause",
    "appeal",
    "appellate",
    "appellate tribunal",
    "commissioner appeal",
    "irac",
    "cit appeal",
    "itat",
    "recoverable",
    "recovery notice",
    "demand notice",
    "objection",
    "file appeal",
    "appeal procedure",
    "appeal deadline",
    "response to notice",
    "respond to notice",
    "first appeal",
    "second appeal",
    "rectification",
)

_RESEARCH_SIGNALS: tuple[str, ...] = (
    "research",
    "compare",
    "comparison",
    "what changed",
    "changes in",
    "amendments",
    "amendment",
    "history of",
    "previous provision",
    "before and after",
    "pre and post",
    "finance act 2026",
    "finance act 2025",
    "finance act",
    "fa 2026",
    "fa 2025",
    "fa 2024",
    "all relevant",
    "all documents",
    "find documents",
    "find relevant",
    "what are the documents",
    "what provisions",
    "multi-domain",
)

# Word-boundary regex signals (avoid substring false positives).
_FED_WORD_RE = re.compile(r"\bfed\b", re.IGNORECASE)
_WHT_WORD_RE = re.compile(r"\bwht\b", re.IGNORECASE)
_NTN_WORD_RE = re.compile(r"\bntn\b", re.IGNORECASE)
_FA_YEAR_RE = re.compile(r"\bfa[\s-]*(20\d{2})\b", re.IGNORECASE)
_SECTION_RETURN_RE = re.compile(
    r"\bsection\s+\d+\b[^.]*\breturn\b|\breturn\b[^.]*\bsection\s+\d+\b",
    re.IGNORECASE,
)
_SECTION_RE = re.compile(r"\bsection\s+\d+\b", re.IGNORECASE)

# Research context terms required alongside a city name before
# research routing is triggered by a city mention. Property
# valuation queries go to Research, not to a property_valuation
# agent.
_RESEARCH_CONTEXT_TERMS: tuple[str, ...] = (
    "valuation",
    "property",
    "value",
    "values",
    "tehsil",
    "district",
    "compare",
    "research",
)

# Cities covered by the canonical PropertyValuation corpus
# (data/raw/04-source-docs/PropertyValuation/). Mirrors the 54
# canonical valuation documents; kept static so routing stays
# deterministic and FAISS-free. Property valuation questions
# are routed to the Research Agent (city+context signals).
RESEARCH_CITIES: tuple[str, ...] = (
    "Abbottabad",
    "Attock",
    "Bahawalnagar",
    "Bahawalpur",
    "Bannu",
    "Bhakkar",
    "Chakwal",
    "Chiniot",
    "Dera Ismail Khan",
    "Faisalabad",
    "Ghora Gali",
    "Ghotki",
    "Gujranwala",
    "Gujrat",
    "Gwadar",
    "Hafizabad",
    "Haripur",
    "Hyderabad",
    "Jhang",
    "Jhelum",
    "Karachi",
    "Kasur",
    "Khushab",
    "Kohat",
    "Kotli Sattian",
    "Lahore",
    "Larkana",
    "Lasbela",
    "Lodhran",
    "Mandi Bahauddin",
    "Mansehra",
    "Mardan",
    "Mianwali",
    "Mirpurkhas",
    "Multan",
    "Murree",
    "Nankana",
    "Narowal",
    "Nowshera",
    "Okara",
    "Pakpattan",
    "Peshawar",
    "Quetta",
    "Rahim Yar Khan",
    "Rawalpindi",
    "Sahiwal",
    "Sargodha",
    "Sheikhupura",
    "Sialkot",
    "Sukkur",
    "Talagang",
    "Toba Tek Singh",
    "Vehari",
    "Wazirabad",
)


# ============================================================
# ROUTING DECISION
# ============================================================

@dataclass(frozen=True)
class RoutingDecision:
    """
    Immutable deterministic routing result.
    """

    question: str
    domains: tuple[str, ...]
    matched_signals: dict[str, tuple[str, ...]]

    @property
    def primary_domain(self) -> str:
        return self.domains[0] if self.domains else DOMAIN_RESEARCH

    @property
    def multi_domain(self) -> bool:
        return len(self.domains) > 1

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "domains": list(self.domains),
            "primary_domain": self.primary_domain,
            "multi_domain": self.multi_domain,
            "matched_signals": {
                k: list(v) for k, v in self.matched_signals.items()
            },
        }


# ============================================================
# SIGNAL MATCHING HELPERS
# ============================================================

def _match_phrases(
    query_lower: str, signals: tuple[str, ...]
) -> tuple[str, ...]:
    return tuple(s for s in signals if s in query_lower)


def detect_city(query_lower: str) -> str | None:
    """
    Return the first canonical city name mentioned in the query
    (case-insensitive, matching both spaced and compact forms),
    or None. Deterministic; city-list order is alphabetical.
    """

    for city in RESEARCH_CITIES:
        spaced = city.lower()
        compact = spaced.replace(" ", "")
        if spaced in query_lower or compact in query_lower:
            return city
    return None


# ============================================================
# ROUTER
# ============================================================

class FBRQueryRouter:
    """
    Deterministic rule-based FBR query router for the 9-agent
    architecture.
    """

    def route(self, question: object) -> RoutingDecision:
        query = str(question) if question is not None else ""
        query_lower = query.lower()

        matched: dict[str, tuple[str, ...]] = {}

        # --- 1. Research (top priority) ----------------------
        # FA year abbreviation, explicit research/compare signals,
        # or city+context (former property valuation path).
        rs_signals: list[str] = []
        if "finance act" in query_lower:
            rs_signals.append("finance-act")
        if _FA_YEAR_RE.search(query_lower):
            rs_signals.append("fa-year")
        rs_signals.extend(
            list(_match_phrases(query_lower, _RESEARCH_SIGNALS))
        )
        # Remove self-matches from FA phrases to avoid double-count
        rs_signals = [
            s for s in rs_signals
            if s not in ("finance act", "finance-act", "fa-year")
            or True
        ]
        # If the user clearly asks for a research/compare/FA change
        # question, route to research.
        city = detect_city(query_lower)
        if city is not None and any(
            term in query_lower for term in _RESEARCH_CONTEXT_TERMS
        ):
            rs_signals.append(f"city:{city.lower()}")
        if rs_signals:
            # de-dup
            seen = set()
            unique = []
            for s in rs_signals:
                if s not in seen:
                    seen.add(s)
                    unique.append(s)
            matched[DOMAIN_RESEARCH] = tuple(unique)

        # --- 2. Calculation ----------------------------------
        # Only fire when there is an explicit calculation request.
        # We do NOT auto-fire on every number-bearing question
        # because that would over-route the existing tax-domain
        # agents.
        calc_signals = list(
            _match_phrases(query_lower, _CALCULATION_SIGNALS)
        )
        if calc_signals:
            matched[DOMAIN_CALCULATION] = tuple(calc_signals)

        # --- 3. Notice / Appeal ------------------------------
        na_signals = list(
            _match_phrases(query_lower, _NOTICE_APPEAL_SIGNALS)
        )
        if na_signals:
            matched[DOMAIN_NOTICE_APPEAL] = tuple(na_signals)

        # --- 4. Return Filing --------------------------------
        # Strong return/filing signal that is NOT already a
        # "section 114 return" pattern (which is income_tax).
        rf_signals: list[str] = []
        for s in _RETURN_FILING_SIGNALS:
            if s in query_lower:
                rf_signals.append(s)
        if rf_signals and not _SECTION_RETURN_RE.search(query_lower):
            matched[DOMAIN_RETURN_FILING] = tuple(rf_signals)

        # --- 5. Registration ---------------------------------
        reg_signals: list[str] = []
        for s in _REGISTRATION_SIGNALS:
            if s in query_lower:
                reg_signals.append(s)
        if reg_signals:
            matched[DOMAIN_REGISTRATION] = tuple(reg_signals)

        # --- 6. Customs --------------------------------------
        cu_signals: list[str] = []
        for s in _CUSTOMS_SIGNALS:
            if s in query_lower:
                cu_signals.append(s)
        if cu_signals:
            matched[DOMAIN_CUSTOMS] = tuple(cu_signals)

        # --- 7. Federal Excise -------------------------------
        fe_signals = list(
            _match_phrases(query_lower, _FEDERAL_EXCISE_SIGNALS)
        )
        if _FED_WORD_RE.search(query_lower):
            fe_signals.append("fed")
        if fe_signals:
            matched[DOMAIN_FEDERAL_EXCISE] = tuple(fe_signals)

        # --- 8. Sales Tax ------------------------------------
        st_signals = list(
            _match_phrases(query_lower, _SALES_TAX_SIGNALS)
        )
        if st_signals:
            matched[DOMAIN_SALES_TAX] = tuple(st_signals)

        # --- 9. Income Tax -----------------------------------
        it_signals = list(
            _match_phrases(query_lower, _INCOME_TAX_SIGNALS)
        )
        if _WHT_WORD_RE.search(query_lower):
            it_signals.append("wht")
        if _SECTION_RETURN_RE.search(query_lower):
            it_signals.append("section-return")
        if _SECTION_RE.search(query_lower):
            it_signals.append("section")
        if it_signals:
            matched[DOMAIN_INCOME_TAX] = tuple(it_signals)

        # --- Assemble priority-ordered domains ---------------
        domains = tuple(
            d for d in DOMAIN_PRIORITY if d in matched
        )

        if not domains:
            # No clear signal: research is the safest fallback
            # because it is a multi-domain RAG-friendly path. The
            # RAG engine will still return the safe-refusal if
            # evidence is absent.
            return RoutingDecision(
                question=query,
                domains=(DOMAIN_RESEARCH,),
                matched_signals={
                    DOMAIN_RESEARCH: ("fallback",)
                },
            )

        return RoutingDecision(
            question=query,
            domains=domains,
            matched_signals=matched,
        )


def route_query(question: object) -> RoutingDecision:
    """
    Module-level convenience wrapper around FBRQueryRouter.
    """

    return FBRQueryRouter().route(question)
