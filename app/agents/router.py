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

When the same phrase appears in two signal lists, the
higher-priority domain wins and the question maps to exactly one
domain (see _collapse_duplicate_signal_domains), so a single-domain
question never runs two agents.
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

# Collision-prone signals matched on word boundaries. Short ASCII
# signals (e.g. "cd", "strn", "pos") are substrings of ordinary
# words ("record", "according", "purpose"), and "import" is a
# substring of "important", so a plain substring test produces
# false customs / sales-tax routing. These are matched with
# compiled word-boundary regexes instead, following the
# _FED_WORD_RE / _WHT_WORD_RE / _NTN_WORD_RE pattern below.
_SHORT_SIGNAL_MAX_LEN = 4
_WORD_BOUNDARY_TOKENS: tuple[str, ...] = ("import", "export")

# All signal lists, so the word-boundary map below is built from
# one place and shared by every matching site.
_ALL_SIGNAL_TUPLES: tuple[tuple[str, ...], ...] = (
    _INCOME_TAX_SIGNALS,
    _SALES_TAX_SIGNALS,
    _FEDERAL_EXCISE_SIGNALS,
    _CUSTOMS_SIGNALS,
    _REGISTRATION_SIGNALS,
    _RETURN_FILING_SIGNALS,
    _CALCULATION_SIGNALS,
    _NOTICE_APPEAL_SIGNALS,
    _RESEARCH_SIGNALS,
)


def _needs_word_boundary(signal: str) -> bool:
    """True when a signal must not be matched as a plain substring.
    """

    if not signal or not signal.isascii():
        return False
    if len(signal) <= _SHORT_SIGNAL_MAX_LEN:
        return True
    return signal in _WORD_BOUNDARY_TOKENS


# Compiled word-boundary regexes for every collision-prone signal,
# shared by _match_phrases and the per-domain match sites.
_WORD_BOUNDARY_SIGNAL_RES: dict[str, re.Pattern[str]] = {
    signal: re.compile(rf"\b{re.escape(signal)}\b", re.IGNORECASE)
    for signals in _ALL_SIGNAL_TUPLES
    for signal in signals
    if _needs_word_boundary(signal)
}

# Deterministic primary-domain tie-break for phrases that appear in
# two domain signal lists. DOMAIN_PRIORITY above decides the
# surviving domain: registration > sales_tax for STRN, and
# return_filing > income_tax for return / filer status queries.
# Format: (dropped_domain, kept_domain, signals in both lists).
_SHARED_SIGNALS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (DOMAIN_SALES_TAX, DOMAIN_REGISTRATION, ("strn",)),
    (
        DOMAIN_INCOME_TAX,
        DOMAIN_RETURN_FILING,
        ("income tax return", "filer", "non-filer"),
    ),
)

# A bare domain-name mention ("sales tax") is a topic qualifier,
# not a second intent: "how do I register for sales tax" is one
# registration question, not a registration question plus a
# sales-tax question. Format: (dropped_domain, kept_domain,
# dropped-only signals, kept-required signals).
_TIE_BREAK_RULES: tuple[
    tuple[str, str, tuple[str, ...], tuple[str, ...]], ...
] = (
    (
        DOMAIN_SALES_TAX,
        DOMAIN_REGISTRATION,
        ("sales tax",),
        ("register",),
    ),
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
        # route() never returns an empty domains tuple (it falls
        # back to research), so domains[0] always exists.
        return self.domains[0]

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
    """Match signals against a lower-cased query.

    Collision-prone signals (short ASCII tokens such as "cd" or
    "import"; see _WORD_BOUNDARY_SIGNAL_RES) are matched on word
    boundaries so they cannot fire inside longer words. Longer
    phrases remain plain substring matches.
    """

    matched: list[str] = []
    for signal in signals:
        word_re = _WORD_BOUNDARY_SIGNAL_RES.get(signal)
        if word_re is not None:
            if word_re.search(query_lower):
                matched.append(signal)
        elif signal in query_lower:
            matched.append(signal)
    return tuple(matched)


def _collapse_duplicate_signal_domains(
    matched: dict[str, tuple[str, ...]],
) -> dict[str, tuple[str, ...]]:
    """Apply the deterministic primary-domain tie-break.

    The same phrase can appear in two domain signal lists, which
    would otherwise make a single-domain question run two agents
    and contradict the documented contract "Single-domain question
    -> exactly one agent". When a domain's ONLY matched signals are
    shared with (or merely name) another matched domain, that
    domain is dropped and the question maps to exactly one domain.
    A domain with at least one exclusive signal of its own keeps
    running, so genuine multi-domain questions still run every
    routed agent.
    """

    for dropped, kept, shared in _SHARED_SIGNALS:
        dropped_signals = matched.get(dropped)
        if dropped_signals and all(
            s in shared for s in dropped_signals
        ):
            del matched[dropped]

    for dropped, kept, only_signals, required in _TIE_BREAK_RULES:
        dropped_signals = matched.get(dropped)
        if (
            dropped_signals
            and all(s in only_signals for s in dropped_signals)
            and kept in matched
            and any(s in required for s in matched[kept])
        ):
            del matched[dropped]

    return matched


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
        # when explicit FA detection already fired (the generic
        # phrase then adds no signal of its own).
        if "finance-act" in rs_signals or "fa-year" in rs_signals:
            rs_signals = [
                s for s in rs_signals
                if s not in ("finance act", "finance-act", "fa-year")
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
        rf_signals = list(
            _match_phrases(query_lower, _RETURN_FILING_SIGNALS)
        )
        if rf_signals and not _SECTION_RETURN_RE.search(query_lower):
            matched[DOMAIN_RETURN_FILING] = tuple(rf_signals)

        # --- 5. Registration ---------------------------------
        reg_signals = list(
            _match_phrases(query_lower, _REGISTRATION_SIGNALS)
        )
        if reg_signals:
            matched[DOMAIN_REGISTRATION] = tuple(reg_signals)

        # --- 6. Customs --------------------------------------
        cu_signals = list(
            _match_phrases(query_lower, _CUSTOMS_SIGNALS)
        )
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
            # de-dup: the word-regex "wht" match above can repeat
            # the "wht" phrase signal from _INCOME_TAX_SIGNALS.
            seen = set()
            unique = []
            for s in it_signals:
                if s not in seen:
                    seen.add(s)
                    unique.append(s)
            matched[DOMAIN_INCOME_TAX] = tuple(unique)

        # --- Duplicate-signal tie-break ----------------------
        # Shared phrases must not make a single-domain question
        # run two agents (see _collapse_duplicate_signal_domains).
        _collapse_duplicate_signal_domains(matched)

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
