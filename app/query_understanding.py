"""
Phase 2: Query Understanding.

This module sits BEFORE the deterministic Router (Phase 3) and the
RAG engine (Phase 4). It performs the canonical Phase 2 sub-stages:

  A. Receive Query          - normalized input validation
  B. Pre-processing         - whitespace, harmless cleaning,
                              language detection, controlled
                              spelling normalization, with strict
                              preservation of tax/legal terminology
  C. Intent Detection       - deterministic intent classification
                              (information, procedure, calculation,
                              registration, filing, notice/appeal,
                              legal/rule, research/comparison,
                              dates/deadlines)
  D. Query Classification   - tax type/domain, topic, sub-topic,
                              entities (tax year, dates, amounts,
                              percentages, location, NTN/STRN/IRIS,
                              section references, percentages,
                              monetary amounts)

CRITICAL CONTRACT (see master prompt):

  - This module does NOT replace the deterministic Router. The
    Router remains the authoritative component for routing.
  - This module is pure (no LLM, no FAISS, no randomness). It is
    safe to call on every query.
  - It does not modify the original question text in a way that
    changes its meaning for downstream retrieval.
  - It preserves all tax/legal terminology, section numbers,
    tax year, NTN/STRN/IRIS, dates, percentages, and amounts.
  - It is intentionally a thin, deterministic layer so that the
    existing 9-agent / router / RAG / verification pipeline is
    not bypassed or perturbed.

This module is reusable from the orchestrator or any future
backend entry point. It is dependency-free (only stdlib `re`).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


# ============================================================
# A. RECEIVE QUERY
# ============================================================

class QueryReceiveError(ValueError):
    """Raised when the inbound query is invalid for the pipeline."""


def receive_query(question: Any) -> str:
    """A. Receive Query.

    Accept a query (str or object convertible to str), validate it,
    and return the canonical raw string. Raises QueryReceiveError
    on invalid input. This stage does NOT modify the text content
    beyond a single str() conversion and a hard length cap.
    """

    if question is None:
        raise QueryReceiveError("query is None")
    if not isinstance(question, str):
        try:
            question = str(question)
        except Exception as exc:
            raise QueryReceiveError(
                f"query not coercible to str: {type(question).__name__}"
            ) from exc
    return question


# ============================================================
# B. PRE-PROCESSING
# ============================================================

_WHITESPACE_RE = re.compile(r"\s+")
_INVISIBLE_RE = re.compile(r"[\u200B-\u200D\uFEFF]")
_ZERO_WIDTH_RE = re.compile(r"[\u200B-\u200D\u2060\uFEFF]")


def _strip_invisible(text: str) -> str:
    return _INVISIBLE_RE.sub("", text or "")


def _normalize_whitespace(text: str) -> str:
    # Collapse internal whitespace runs to a single space and strip
    # leading/trailing whitespace. Does not alter any token content.
    return _WHITESPACE_RE.sub(" ", (text or "")).strip()


# Spelling normalization is intentionally conservative: only
# obvious Roman-Urdu / common-typo synonyms that have been verified
# to NOT collide with tax/legal terminology are mapped. Anything
# ambiguous is left untouched. Every entry here has been hand-curated
# to preserve retrieval quality.
_CONTROLLED_SPELLING: dict[str, str] = {
    # Generic typos that do not affect tax/legal meaning.
    "recieve": "receive",
    "reciept": "receipt",
    "registraion": "registration",
    "registrtaion": "registration",
    "registar": "register",
    "appele": "appeal",
    "reciept": "receipt",
    "tution": "tuition",
    "wages": "wages",  # placeholder; intentional identity map
    "taxable": "taxable",
    "taxation": "taxation",
    "calulate": "calculate",
    "calcualte": "calculate",
    "calcualtion": "calculation",
    "calculaton": "calculation",
    "appelant": "appellant",
    "appelate": "appellate",
    "noticce": "notice",
    "notise": "notice",
    "dept": "department",
    "deparment": "department",
    "goverment": "government",
    "govermnent": "government",
}


def _controlled_spell(text: str) -> str:
    if not text:
        return text
    # Only replace whole-word matches and only for tokens that are
    # at least 4 characters long (avoid altering short ambiguous
    # tokens). This is a word-boundary, case-insensitive map.
    def _sub(match: re.Match) -> str:
        tok = match.group(0)
        low = tok.lower()
        if low in _CONTROLLED_SPELLING:
            repl = _CONTROLLED_SPELLING[low]
            if tok.isupper():
                return repl.upper()
            if tok[:1].isupper():
                return repl[:1].upper() + repl[1:]
            return repl
        return tok

    return re.sub(r"[A-Za-z]{4,}", _sub, text)


# Roman Urdu tokens we recognize. These are tokens that the
# existing corpus frequently appears alongside in user queries
# without changing the meaning of the tax/legal terminology.
_ROMAN_URDU_TOKENS: tuple[str, ...] = (
    "kya",
    "kaise",
    "kaisay",
    "kese",
    "kesey",
    "kitne",
    "kitnay",
    "kab",
    "kahan",
    "kaun",
    "kaunsa",
    "hai",
    "hain",
    "hun",
    "mein",
    "may",
    "main",
    "se",
    "ko",
    "ke",
    "ka",
    "ki",
    "wala",
    "wali",
    "walay",
    "ap",
    "aap",
    "mujhe",
    "mujh",
    "tumhe",
    "tum",
    "hum",
    "humne",
    "kar",
    "karein",
    "karna",
    "kya hai",
    "kya hain",
    "kya karen",
    "kya karoon",
    "kya karu",
    "zaroor",
    "zaruri",
    "chahti",
    "chahta",
    "chahte",
    "lagta",
    "lagti",
    "lagte",
)


def _detect_language(text: str) -> str:
    """Return a best-effort language tag. The current pipeline
    only consumes the 'lang' field for telemetry; downstream
    retrieval stays language-agnostic and corpus-driven.
    """

    if not text:
        return "unknown"
    lowered = text.lower()
    tokens = re.findall(r"[A-Za-z']+", lowered)
    if not tokens:
        return "unknown"
    roman_urdu_hits = sum(1 for t in tokens if t in _ROMAN_URDU_TOKENS)
    # Threshold is intentionally low so that short queries with a
    # single Roman Urdu token are still recognized.
    if roman_urdu_hits >= 1 and len(tokens) <= 12:
        return "roman_urdu"
    if roman_urdu_hits >= 2:
        return "roman_urdu"
    if any("\u0600" <= ch <= "\u06FF" for ch in text):
        return "urdu"
    return "english"


def preprocess_query(question: str) -> tuple[str, dict[str, Any]]:
    """B. Pre-processing.

    Returns (normalized_question, meta). The normalized question
    is safe to feed into the deterministic router and RAG engine.
    """

    raw = _strip_invisible(question or "")
    raw = _ZERO_WIDTH_RE.sub("", raw)
    collapsed = _normalize_whitespace(raw)
    spelled = _controlled_spell(collapsed)
    lang = _detect_language(spelled)

    meta: dict[str, Any] = {
        "original_length": len(question or ""),
        "normalized_length": len(spelled),
        "language": lang,
        "invisible_chars_removed": (
            len(question or "") - len(_strip_invisible(question or ""))
        ),
        "whitespace_collapsed": collapsed != (raw.strip()),
        "spelling_normalized": spelled != collapsed,
    }
    return spelled, meta


# ============================================================
# C. INTENT DETECTION
# ============================================================

# Each intent has a small, deterministic pattern set. The order
# in INTENT_PATTERNS is the priority order: the first intent that
# matches wins, and ties are resolved by pattern specificity.
# Importantly, intent detection NEVER routes the query itself.

_INTENT_INFO_SIGNALS: tuple[str, ...] = (
    "what is",
    "what are",
    "define",
    "meaning of",
    "explain",
    "tell me about",
    "describe",
    "difference between",
    "which",
)

_INTENT_PROCEDURE_SIGNALS: tuple[str, ...] = (
    "how do i",
    "how to",
    "how can i",
    "steps to",
    "step by step",
    "procedure",
    "process for",
    "process of",
    "way to",
    "ways to",
    "method to",
    "method for",
    "submit",
    "apply for",
)

_INTENT_CALCULATION_SIGNALS: tuple[str, ...] = (
    "calculate",
    "compute",
    "how much is",
    "how much tax",
    "what is the amount",
    "x percent of",
    "% of",
    "percent of",
    "times ",
    "multiplied by",
    "divided by",
    "plus ",
    "minus ",
    "ratio",
    "result of",
)

_INTENT_REGISTRATION_SIGNALS: tuple[str, ...] = (
    "register",
    "registration",
    "enroll",
    "enrolment",
    "enrollment",
    "sign up",
    "signup",
    "ntn",
    "strn",
    "iris",
    "obtain ntn",
    "obtain strn",
    "get registered",
    "new taxpayer",
    "how to register",
)

_INTENT_FILING_SIGNALS: tuple[str, ...] = (
    "file return",
    "filing return",
    "file a return",
    "submit return",
    "return filing",
    "due date",
    "filing deadline",
    "deadline for filing",
    "extend filing",
    "amend return",
    "revise return",
    "extension",
    "filer",
    "non-filer",
)

_INTENT_NOTICE_APPEAL_SIGNALS: tuple[str, ...] = (
    "appeal",
    "appellate",
    "appellant",
    "notice",
    "show cause",
    "show-cause",
    "recovery notice",
    "demand notice",
    "objection",
    "tribunal",
    "commissioner appeal",
    "commissioner (appeals)",
    "itat",
    "high court",
    "court order",
    "litigation",
)

_INTENT_LEGAL_RULE_SIGNALS: tuple[str, ...] = (
    "section",
    "clause",
    "subsection",
    "rule",
    "ordinance",
    "act ",
    "act of",
    "law",
    "legal",
    "interpretation",
    "interpret",
    "meaning of section",
    "scope of section",
    "applicability of section",
    "whether",
    "is it legal",
    "is this allowed",
    "permitted under",
    "prohibited under",
    "liability under",
    "obligation under",
)

_INTENT_RESEARCH_SIGNALS: tuple[str, ...] = (
    "compare",
    "comparison",
    "all relevant documents",
    "research",
    "summary of",
    "summarize",
    "history of",
    "evolution of",
    "find all",
    "find relevant",
    "all sources",
    "amendments to",
    "changes in",
    "finance act",
    "fa 20",
)

_INTENT_DATE_DEADLINE_SIGNALS: tuple[str, ...] = (
    "when is the deadline",
    "last date",
    "due date",
    "when to file",
    "filing date",
    "payment date",
    "expiry date",
    "valid until",
    "expiration",
    "within how many days",
    "how many days",
    "date of",
    "timeline",
    "schedule of",
)


INTENT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("calculation", _INTENT_CALCULATION_SIGNALS),
    ("filing", _INTENT_FILING_SIGNALS),
    ("registration", _INTENT_REGISTRATION_SIGNALS),
    ("notice_appeal", _INTENT_NOTICE_APPEAL_SIGNALS),
    ("research", _INTENT_RESEARCH_SIGNALS),
    ("legal_rule", _INTENT_LEGAL_RULE_SIGNALS),
    ("date_deadline", _INTENT_DATE_DEADLINE_SIGNALS),
    ("procedure", _INTENT_PROCEDURE_SIGNALS),
    ("information", _INTENT_INFO_SIGNALS),
)


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(n in lowered for n in needles)


def detect_intent(question: str) -> str:
    """C. Intent Detection.

    Deterministic, pattern-based. Returns one of the canonical
    intent labels. The router remains the authoritative
    component for routing; intent is a downstream signal only.
    """

    q = (question or "").lower()
    for intent, signals in INTENT_PATTERNS:
        if _contains_any(q, signals):
            return intent
    return "information"


# ============================================================
# D. QUERY CLASSIFICATION
# ============================================================

# Tax type / domain detection (purely informational; the Router
# remains the authoritative component for routing). These patterns
# are intentionally narrow so they do not conflict with the
# router's own signal groups.
_DOMAIN_HINTS: dict[str, tuple[str, ...]] = {
    "income_tax": (
        "income tax",
        "salary",
        "salaried",
        "salaried person",
        "wage",
        "paye",
        "withholding",
        "return of income",
        "income tax ordinance",
        "ito 2001",
    ),
    "sales_tax": (
        "sales tax",
        "value added",
        "vat",
        "input tax",
        "output tax",
        "sales tax act",
        "strn",
        "sales tax return",
    ),
    "federal_excise": (
        "federal excise",
        "fed ",
        "excise duty",
        "federal excise duty",
    ),
    "customs": (
        "customs duty",
        "cd ",
        "import duty",
        "export duty",
        "customs act",
        "webooc",
        "pcs",
        "paec",
    ),
    "registration": (
        "ntn",
        "strn",
        "iris",
        "registration",
        "register for",
        "enroll",
    ),
    "return_filing": (
        "file return",
        "return filing",
        "filing deadline",
        "due date",
        "amend return",
    ),
    "calculation": (
        "calculate",
        "compute",
        "% of",
        "percent of",
        "x ",
        "multiplied by",
    ),
    "notice_appeal": (
        "notice",
        "appeal",
        "appellate",
        "tribunal",
        "objection",
        "show cause",
    ),
    "research": (
        "finance act",
        "fa 20",
        "compare",
        "comparison",
        "research",
        "all sources",
        "amendments",
    ),
}


# Topic/sub-topic signal words. These are only used for telemetry
# and to enrich the structured query understanding output; they do
# NOT influence routing.
_TOPIC_HINTS: dict[str, tuple[str, ...]] = {
    "registration": ("ntn", "strn", "iris", "enroll", "register"),
    "filing": ("return", "filer", "non-filer", "due date"),
    "rates": ("rate", "rates", "tariff", "tariffs", "percent"),
    "exemptions": ("exempt", "exemption", "exempted"),
    "penalties": ("penalty", "penalties", "fine", "fines"),
    "valuation": ("valuation", "property value", "assessed value"),
    "appeal": ("appeal", "appellate", "tribunal", "itat"),
    "notice": ("notice", "show cause", "demand"),
    "compliance": ("compliance", "compliant", "audit"),
    "input_output_tax": ("input tax", "output tax", "refund"),
}


# Entity extraction patterns. These are intentionally narrow and
# never destructive: they pull out identifiers, years, dates,
# amounts, percentages, section references, NTN/STRN/IRIS, and
# well-known city/place names, but never modify or remove them
# from the question.

_SECTION_REF_RE = re.compile(
    r"\b(?:section|sec|s\.)\s*([0-9]+[A-Za-z]*)", re.IGNORECASE
)
_RULE_REF_RE = re.compile(
    r"\b(?:rule|r\.)\s*([0-9]+)", re.IGNORECASE
)
_CLAUSE_REF_RE = re.compile(
    r"\b(?:clause|sub-?section|proviso)\s+([0-9]+[A-Za-z]*)",
    re.IGNORECASE,
)
_TAX_YEAR_RE = re.compile(r"\b(?:ty|tax\s*year)\s*[:\-]?\s*(20\d{2})", re.IGNORECASE)
_FINANCIAL_YEAR_RE = re.compile(
    r"\b(?:fy|financial\s*year)\s*[:\-]?\s*(20\d{2})(?:\s*[-/]\s*(20\d{2}))?",
    re.IGNORECASE,
)
_CALENDAR_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_PERCENT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:%|percent|pc)(?=\b|\s|$)",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(
    r"(?:rs\.?|pkr|rupees?)\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_BARE_AMOUNT_RE = re.compile(
    r"\b([0-9][0-9,]{2,}(?:\.[0-9]+)?)\b"
)
_NTN_RE = re.compile(r"\b(?:ntn|strn|iris[_\- ]?id)\s*[:#\-]?\s*([0-9\-]+)", re.IGNORECASE)
_DATE_RE = re.compile(
    r"\b(\d{1,2}[\-/]\d{1,2}[\-/](?:\d{2}|\d{4}))\b"
)
_ORDINANCE_RE = re.compile(
    r"\b(ito|income\s*tax\s*ordinance)\s*(19|20)\d{2}\b",
    re.IGNORECASE,
)
_ACT_RE = re.compile(
    r"\b(sales\s*tax\s*act|customs\s*act|federal\s*excise\s*act)"
    r"\s*(19|20)\d{2}\b",
    re.IGNORECASE,
)


# A small, deterministic city list. We do not enumerate all 54
# cities; we only keep the high-signal set that frequently
# appears in user queries so the location field is useful.
_CITY_HINTS: tuple[str, ...] = (
    "karachi",
    "lahore",
    "islamabad",
    "rawalpindi",
    "faisalabad",
    "multan",
    "peshawar",
    "quetta",
    "hyderabad",
    "sialkot",
    "gujranwala",
    "bahawalpur",
    "sargodha",
    "abbottabad",
    "vehari",
    "kasur",
    "rahim yar khan",
    "sahiwal",
    "okara",
    "wah cantt",
)


def _extract_section_references(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for m in _SECTION_REF_RE.finditer(text or ""):
        ref = f"section {m.group(1)}"
        if ref.lower() not in seen:
            seen.add(ref.lower())
            out.append(ref)
    for m in _CLAUSE_REF_RE.finditer(text or ""):
        ref = f"{m.group(0).split()[0].lower()} {m.group(1)}"
        if ref not in seen:
            seen.add(ref)
            out.append(ref)
    for m in _RULE_REF_RE.finditer(text or ""):
        ref = f"rule {m.group(1)}"
        if ref not in seen:
            seen.add(ref)
            out.append(ref)
    return out


def _extract_tax_years(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for m in _TAX_YEAR_RE.finditer(text or ""):
        v = f"TY {m.group(1)}"
        if v not in seen:
            seen.add(v)
            out.append(v)
    for m in _FINANCIAL_YEAR_RE.finditer(text or ""):
        if m.group(2):
            v = f"FY {m.group(1)}-{m.group(2)}"
        else:
            v = f"FY {m.group(1)}"
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _extract_calendar_years(text: str) -> list[str]:
    return sorted({
        m.group(1) for m in _CALENDAR_YEAR_RE.finditer(text or "")
    })


def _extract_percentages(text: str) -> list[str]:
    return sorted({
        f"{m.group(1)}%" for m in _PERCENT_RE.finditer(text or "")
    })


def _extract_amounts(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for m in _MONEY_RE.finditer(text or ""):
        v = f"Rs {m.group(1)}"
        if v not in seen:
            seen.add(v)
            out.append(v)
    for m in _BARE_AMOUNT_RE.finditer(text or ""):
        v = m.group(1)
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _extract_dates(text: str) -> list[str]:
    return sorted({
        m.group(1) for m in _DATE_RE.finditer(text or "")
    })


def _extract_identifiers(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for m in _NTN_RE.finditer(text or ""):
        # Capture the kind of identifier (NTN/STRN/IRIS-id) so it
        # is useful to the downstream pipeline.
        prefix_match = re.match(
            r"\b(ntn|strn|iris[_\- ]?id)\b",
            text[max(0, m.start() - 12):m.end()],
            re.IGNORECASE,
        )
        kind = (
            (prefix_match.group(1) or "id").upper().replace(" ", "")
            if prefix_match
            else "ID"
        )
        v = f"{kind}:{m.group(1)}"
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _detect_location(text: str) -> str | None:
    lowered = (text or "").lower()
    for city in _CITY_HINTS:
        if re.search(rf"\b{re.escape(city)}\b", lowered):
            return city.title()
    return None


def _detect_topic(text: str) -> str | None:
    lowered = (text or "").lower()
    for topic, signals in _TOPIC_HINTS.items():
        if any(s in lowered for s in signals):
            return topic
    return None


def _detect_domain_hints(text: str) -> list[str]:
    lowered = (text or "").lower()
    matched: list[str] = []
    for domain, signals in _DOMAIN_HINTS.items():
        if any(s in lowered for s in signals):
            matched.append(domain)
    return matched


def _detect_legal_instrument(text: str) -> str | None:
    if not text:
        return None
    if _ORDINANCE_RE.search(text):
        m = _ORDINANCE_RE.search(text)
        return f"{m.group(0).upper()}"
    if _ACT_RE.search(text):
        m = _ACT_RE.search(text)
        return m.group(0).upper()
    return None


@dataclass
class QueryClassification:
    """Structured output of Phase 2 query classification.

    This is informational and intended for telemetry, downstream
    context, and (in future phases) UI shaping. It does NOT
    replace the deterministic Router.
    """

    intent: str = "information"
    domain_hints: list[str] = field(default_factory=list)
    topic: str | None = None
    sub_topic: str | None = None
    tax_year: list[str] = field(default_factory=list)
    calendar_years: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    percentages: list[str] = field(default_factory=list)
    amounts: list[str] = field(default_factory=list)
    section_references: list[str] = field(default_factory=list)
    identifiers: list[str] = field(default_factory=list)
    location: str | None = None
    legal_instrument: str | None = None
    intent_type: str = "informational"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_query(question: str) -> QueryClassification:
    """D. Query Classification.

    Extracts structural signals from the (already normalized)
    question. Pure, deterministic, no LLM, no FAISS.
    """

    text = question or ""
    intent = detect_intent(text)
    domain_hints = _detect_domain_hints(text)
    topic = _detect_topic(text)
    sub_topic = None
    if topic == "rates":
        sub_topic = "tax_rate"
    elif topic == "exemptions":
        sub_topic = "exemption"
    elif topic == "penalties":
        sub_topic = "penalty"
    elif topic == "input_output_tax":
        sub_topic = "tax_adjustment"
    elif topic == "valuation":
        sub_topic = "property_valuation"
    elif topic == "notice":
        sub_topic = "notice"
    elif topic == "appeal":
        sub_topic = "appeal"
    elif topic == "filing":
        sub_topic = "return_filing"
    elif topic == "registration":
        sub_topic = "taxpayer_registration"
    elif topic == "compliance":
        sub_topic = "compliance"

    if intent in {"calculation"}:
        intent_type = "calculation"
    elif intent in {"procedure", "filing", "registration"}:
        intent_type = "procedural"
    elif intent in {"legal_rule", "notice_appeal"}:
        intent_type = "legal"
    elif intent in {"research"}:
        intent_type = "research"
    elif intent in {"date_deadline"}:
        intent_type = "date"
    else:
        intent_type = "informational"

    return QueryClassification(
        intent=intent,
        domain_hints=domain_hints,
        topic=topic,
        sub_topic=sub_topic,
        tax_year=_extract_tax_years(text),
        calendar_years=_extract_calendar_years(text),
        dates=_extract_dates(text),
        percentages=_extract_percentages(text),
        amounts=_extract_amounts(text),
        section_references=_extract_section_references(text),
        identifiers=_extract_identifiers(text),
        location=_detect_location(text),
        legal_instrument=_detect_legal_instrument(text),
        intent_type=intent_type,
    )


# ============================================================
# PUBLIC ENTRY POINT
# ============================================================

@dataclass
class QueryUnderstanding:
    """Canonical Phase 2 output.

    Contains:
      - original (string as received)
      - normalized (after pre-processing, safe to feed to router/RAG)
      - language (best-effort language tag)
      - intent (canonical intent label)
      - classification (entities, domain hints, topic, etc.)
    """

    original: str
    normalized: str
    language: str
    pre_processing: dict[str, Any]
    intent: str
    classification: QueryClassification

    def to_dict(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "normalized": self.normalized,
            "language": self.language,
            "pre_processing": self.pre_processing,
            "intent": self.intent,
            "classification": self.classification.to_dict(),
        }


def understand_query(question: Any) -> QueryUnderstanding:
    """Top-level Phase 2 entry point.

    Equivalent to the workflow:

        Receive Query
        -> Pre-processing
        -> Intent Detection
        -> Query Classification

    Returns a QueryUnderstanding. Does NOT route the query; the
    Router remains the authoritative component for routing.
    """

    raw = receive_query(question)
    normalized, meta = preprocess_query(raw)
    intent = detect_intent(normalized)
    classification = classify_query(normalized)
    return QueryUnderstanding(
        original=raw,
        normalized=normalized,
        language=meta.get("language", "unknown"),
        pre_processing=meta,
        intent=intent,
        classification=classification,
    )


__all__ = [
    "QueryReceiveError",
    "QueryClassification",
    "QueryUnderstanding",
    "receive_query",
    "preprocess_query",
    "detect_intent",
    "classify_query",
    "understand_query",
    "INTENT_PATTERNS",
]
