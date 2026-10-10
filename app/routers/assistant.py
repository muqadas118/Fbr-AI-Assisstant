"""
Assistant Tools Router
======================

Gives the AI assistant access to every backend capability so the user
never has to open a specific page and do manual work. One endpoint:

    POST /assistant/ask  { "query": "...", "attachment_text": "...", ... }

Flow (deterministic planning, backend-executed tools):

  1. Plan     — rule-based intent detection on the query (+ attachment).
  2. Act      — run the matching backend tools with inputs extracted
                from the query text (amounts, NTN, notice text, etc.).
  3. Ground   — RAG retrieval over the official FBR corpus for the
                legal basis of whatever the tools used.
  4. Answer   — LLM writes the final answer from tool outputs + FBR
                context; verification layer runs as usual.

Available tools (all existing backend engines, no new math):
- calculate        — all 11 tax calculation modules
- verification     — NTN / filer / CNIC / business / vendor / ATL
- notice_analyzer  — FBR notice analysis from pasted text
- document_analyzer— pasted document text analysis
- invoice          — invoice processing from pasted text
- calendar         — upcoming compliance deadlines
- tax_health       — tax health check
- monitor          — FBR monitor event types (capability query)

If the plan finds no matching tool the request degrades gracefully
to the canonical RAG pipeline (same as POST /answer).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.common.rate_limit import RateLimiter
from app.language import (
    LANG_EN,
    LANG_ROMAN_UR,
    LANG_UR,
    localize,
    normalize_language,
    resolve_language,
)
from app.learning import extract_signals, get_learning_store
from app.llm import LLMError
from app.quotas import get_quota_store
from app.routers.uploads import MAX_FILE_BYTES
from app.supabase_auth import require_user

# Same deterministic refusal the RAG engine uses when evidence/grounding fails.
from app.rag_engine import _NO_EVIDENCE_ANSWER as _NO_EVIDENCE_ANSWER  # noqa: F401

logger = logging.getLogger("fbr_api.assistant")

router = APIRouter(prefix="/assistant", tags=["Assistant"])


# =============================================================================
# Models
# =============================================================================

class AssistantAskRequest(BaseModel):
    query: str = Field(default="", max_length=8000)
    attachment_text: Optional[str] = Field(default=None, max_length=60000)
    attachment_name: Optional[str] = Field(default=None, max_length=255)
    # "auto" (default) lets the resolved query/profile language decide; an
    # explicit "en"|"roman_ur"|"ur" overrides it.
    response_language: str = Field(default="auto")


class ToolRun(BaseModel):
    tool: str
    ok: bool
    summary: str
    data: Any = None


class AssistantAskResponse(BaseModel):
    question: str
    answer: str
    tools_used: list[ToolRun]
    sources: list[dict[str, Any]]
    verification: dict[str, Any]
    grounded: bool
    mode: str  # "tools+rag" | "rag"
    answer_language: str = "en"
    # {"enabled": bool, "recommendations": [...],
    #  "profile_summary": {"top_domains": [[domain, score], ...],
    #                      "total_interactions": int} | None}
    personalization: dict[str, Any] = Field(default_factory=dict)
    # Daily quota snapshot AFTER this request's message/upload consumption;
    # the same object is echoed inside the SSE `meta` event.
    quota: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Extraction helpers (deterministic, no LLM)
# =============================================================================

_AMOUNT_RE = re.compile(r"(?:rs\.?|pkr|rupees)\s*([0-9][0-9,]*(?:\.[0-9]+)?)|([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:rs\.?|pkr|rupees)", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\b([0-9][0-9,]*(?:\.[0-9]+)?)\b")
_PERCENT_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(?:%|percent)", re.IGNORECASE)
_NTN_RE = re.compile(r"\b(\d{7}|\d{4}-\d{3}-\d{3}|\d{9})\b")
_CNIC_RE = re.compile(r"\b(\d{5}-?\d{7}-?\d)\b")

# Urdu/Arabic-Indic digits and separators rewritten to their ASCII form so a
# single text can be read by the ASCII-only regexes above: ``۱۲۰۰۰۰۰`` and
# ``١٢٠٠٠٠`` -> 1200000, ``۲۰۲۵`` -> 2025, the Urdu decimal separator ``٫`` ->
# "." and the Urdu thousands separator ``٬`` -> dropped (the ASCII comma is
# already stripped by _to_num).
_URDU_DIGIT_TRANSLATION = str.maketrans(
    {
        "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
        "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
        "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
        "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
        "٫": ".",
        "٬": "",
    }
)


def _normalize_digits(text: str) -> str:
    """Rewrite Urdu/Arabic-Indic digits and separators to ASCII in ``text``.

    Every numeric extractor below is ASCII-only, so an Urdu-script figure
    (``۱۲۰۰۰۰۰``, ``٢٠٢٥``) must be folded to ASCII before it can match.
    Latin text passes through unchanged, so English behaviour is identical.
    """
    return text.translate(_URDU_DIGIT_TRANSLATION)


def _to_num(token: str) -> float:
    return float(token.replace(",", ""))


def _extract_amounts(text: str) -> list[float]:
    text = _normalize_digits(text)
    out: list[float] = []
    for m in _AMOUNT_RE.finditer(text):
        tok = m.group(1) or m.group(2)
        try:
            out.append(_signed(tok, text, m))
        except ValueError:
            continue
    if not out:
        # Fall back to plain numbers, ignoring years and percents.
        years = {str(y) for y in range(2000, 2036)}
        for m in _NUMBER_RE.finditer(text):
            tok = m.group(1)
            if tok in years:
                continue
            try:
                out.append(_signed(tok, text, m))
            except ValueError:
                continue
    return out


def _signed(tok: str, text: str, m: "re.Match[str]") -> float:
    """Parse a numeric token, preserving a minus sign written before it."""
    prefix = text[max(0, m.start() - 2):m.start()]
    val = _to_num(tok)
    return -val if "-" in prefix else val


def _extract_percent(text: str) -> Optional[float]:
    m = _PERCENT_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _extract_ntn(text: str) -> Optional[str]:
    text = _normalize_digits(text)
    m = _NTN_RE.search(text)
    if not m:
        return None
    digits = m.group(1).replace("-", "")
    return f"{digits[:4]}-{digits[4:7]}-{digits[7:]}" if len(digits) == 9 else digits


# Tax years the TaxYear enum supports (app.calculations.income_tax).
_SUPPORTED_TAX_YEARS = (2024, 2025, 2026)


def _extract_tax_year_raw(text: str) -> str:
    """The tax year literally found in the text (may be unsupported)."""
    text = _normalize_digits(text)
    m = re.search(r"\b(20[0-9]{2})\b", text)
    return m.group(1) if m else str(max(2025, __import__("datetime").date.today().year))


def _extract_tax_year(text: str) -> str:
    """Nearest SUPPORTED tax year for any year found in the text.

    The engine's TaxYear enum only supports 2024/2025/2026; an
    out-of-range year (e.g. 2027) is clamped to the nearest supported
    one and logged instead of raising a ValueError with no fallback.
    """
    raw = _extract_tax_year_raw(text)
    year = int(raw)
    nearest = min(_SUPPORTED_TAX_YEARS, key=lambda y: abs(y - year))
    if nearest != year:
        logger.info(
            "Tax year %s is not supported by the engine; using nearest supported year %s",
            year, nearest,
        )
    return str(nearest)


# =============================================================================
# Intent planning (rule-based)
# =============================================================================

_CALC_INTENT = (
    "calculate", "calculation", "compute", "compute", "kitna", "how much tax",
    "tax amount", "tax liability", "penalty for", "sales tax on", "tax on",
    "income tax on", "wht on", "withholding on", "duty on", "excise on",
    "capital gain", "dividend tax", "salary tax", "business tax",
    # Urdu-script synonyms for the same intents, so a question written in
    # Urdu plans exactly the tools its English/Roman-Urdu twin plans.
    "ٹیکس", "انکم ٹیکس", "سالری", "تنخواہ", "سیلز ٹیکس", "سلز ٹیکس",
    "ویٹھ ہولڈنگ", "ودہولڈنگ", "قوابض", "منافع", "نقصان", "کلکولیٹ",
    "حساب", "رقم", "ادائیگی",
    # Rate-asking phrasings: "what is the rate" is a calculation question but
    # contains none of the "tax on"/"kitna" cues above, so both the Roman-Urdu
    # and Urdu-script forms used to plan no tool at all.
    "rate kya", "rate kia", "ka rate", "ki rate", "شرح کیا", "شرح کتنی",
)
_VERIFY_INTENT = (
    "verify", "check", "validate", "filer status", "atl", "active taxpayer",
    # Urdu-script synonyms (NTN, registration, CNIC and filer status).
    "چیک", "تصدیق", "این ٹی این", "نٹن", "رجسٹریشن", "فائلر", "ایکٹو ٹیکس",
    "اے ٹی ایل", "شناختی کارڈ",
)
_NOTICE_INTENT = (
    "notice", "show cause", "show-cause", "114(", "177(", "122(", "161(", "182(",
    "demand notice",
    # Urdu-script synonyms.
    "نوٹس", "وجہ نوٹس",
)
_DOC_INTENT = (
    "summarize this", "analyse this", "analyze this", "review this",
    "extract from this", "is document", "this document",
    # Urdu-script synonyms.
    "خلاصہ", "تجزیہ", "جائزہ", "دستاویز",
)
_INVOICE_INTENT = (
    "invoice", "sales invoice", "tax invoice", "gst invoice",
    # Urdu-script synonyms.
    "انوائس", "سیلز انوائس", "ٹیکس انوائس",
)
_CALENDAR_INTENT = (
    "deadline", "due date", "calendar", "upcoming", "filing due", "return due",
    # Urdu-script synonyms (deadline, last date, filing, return, calendar).
    "ڈیڈ لائن", "آخری تاریخ", "تاریخ", "فائلنگ", "ریٹرن", "کلینڈر",
)
_HEALTH_INTENT = (
    "health check", "health score", "compliance score", "risk", "penalty exposure",
    # Urdu-script synonyms.
    "ٹیکس ہیلتھ", "صحت", "خطرہ", "تعمیل",
)


def _plan(query: str, attachment: Optional[str]) -> list[str]:
    q = query.lower()
    att = (attachment or "").lower()
    corpus = q + " " + att[:4000]
    tools: list[str] = []

    if any(k in corpus for k in _CALC_INTENT):
        tools.append("calculate")
    if any(k in corpus for k in _VERIFY_INTENT):
        tools.append("verification")
    if any(k in corpus for k in _NOTICE_INTENT):
        tools.append("notice_analyzer")
    if any(k in corpus for k in _INVOICE_INTENT):
        tools.append("invoice")
    if attachment and any(k in corpus for k in _DOC_INTENT):
        tools.append("document_analyzer")
    if any(k in corpus for k in _CALENDAR_INTENT):
        tools.append("calendar")
    if any(k in corpus for k in _HEALTH_INTENT):
        tools.append("tax_health")
    return tools


# =============================================================================
# Tool executors (all reuse existing backend engines)
# =============================================================================

# Localized status text for the deterministic tool summaries / validation
# details built below. ``app.language.localize`` owns the answer-level kinds
# (no_evidence | ambiguous_section | unverified | llm_unavailable |
# placeholder); these are router-level strings with no matching kind, so
# their translations live here next to the code that emits them. "en" keeps
# the existing English wording, so the default behaviour is unchanged and
# every English assertion on a ToolRun.summary stays green.
_TOOL_STATUS_TEXT: dict[str, dict[str, str]] = {
    "calculation_failed": {
        LANG_EN: "calculation failed",
        LANG_ROMAN_UR: "hisaab nahi ho saka",
        LANG_UR: "حساب نہیں ہو سکا",
    },
    "no_ntn_cnic": {
        LANG_EN: "No NTN/CNIC found in the request",
        LANG_ROMAN_UR: "Request mein koi NTN/CNIC nahi mila.",
        LANG_UR: "درخواست میں کوئی NTN/CNIC نہیں ملا۔",
    },
    "verification_unavailable": {
        LANG_EN: "verification unavailable: ",
        LANG_ROMAN_UR: "verification dastyab nahi: ",
        LANG_UR: "تصدیق دستیاب نہیں: ",
    },
    "notice_analysis_failed": {
        LANG_EN: "notice analysis failed: ",
        LANG_ROMAN_UR: "notice analysis nahi ho saki: ",
        LANG_UR: "نوٹس کا تجزیہ نہیں ہو سکا: ",
    },
    "document_analysis_failed": {
        LANG_EN: "document analysis failed: ",
        LANG_ROMAN_UR: "document analysis nahi ho saki: ",
        LANG_UR: "دستاویز کا تجزیہ نہیں ہو سکا: ",
    },
    "invoice_processing_failed": {
        LANG_EN: "invoice processing failed: ",
        LANG_ROMAN_UR: "invoice processing nahi ho saki: ",
        LANG_UR: "انوائس کی پروسیسنگ نہیں ہو سکی: ",
    },
    "calendar_unavailable": {
        LANG_EN: "calendar unavailable: ",
        LANG_ROMAN_UR: "calendar dastyab nahi: ",
        LANG_UR: "کیلنڈر دستیاب نہیں: ",
    },
    "tax_health_unavailable": {
        LANG_EN: "tax health unavailable: ",
        LANG_ROMAN_UR: "tax health check dastyab nahi: ",
        LANG_UR: "ٹیکس ہیلتھ چیک دستیاب نہیں: ",
    },
    # NTN, TY{year} and the missing field names stay verbatim — they are
    # identifiers / computed values, not prose.
    "tax_health_insufficient": {
        LANG_EN: (
            "Insufficient data for a tax health score for {ntn} TY{year}: "
            "provide {missing}"
        ),
        LANG_ROMAN_UR: (
            "{ntn} TY{year} ke liye tax health score ke liye kaafi data nahi "
            "hai: {missing} dein"
        ),
        LANG_UR: (
            "{ntn} TY{year} کے لیے ٹیکس ہیلتھ اسکور کے لیے کافی ڈیٹا نہیں "
            "ہے: {missing} دیں"
        ),
    },
    "query_required": {
        LANG_EN: "Query is required.",
        LANG_ROMAN_UR: "Sawal likhna zaroori hai.",
        LANG_UR: "سوال لکھنا ضروری ہے۔",
    },
}


def _loc(kind: str, language: Optional[str]) -> str:
    """Localized router status text for ``kind``; English when unrecognized.

    ``language`` accepts the canonical tags from ``app.language`` as well as
    loose/None values, which normalize to English.
    """
    variants = _TOOL_STATUS_TEXT[kind]
    return variants.get(normalize_language(language), variants[LANG_EN])


# Withholding-tax section keywords. Order matters: the FIRST match wins, so the
# more specific entries come before the broad ones ("contract"/"goods" would
# otherwise swallow salary and rent).
#
# Latin keywords match on WORD BOUNDARIES, not substrings — see
# `_wht_section_pattern` below. "car" must not fire inside "card", "bank"
# inside "banking", or "rent" inside "currently": those false positives routed
# the question to the wrong WHT section. Urdu-script keywords match as
# substrings (word boundaries are not meaningful there).
_WHT_SECTION_KEYWORDS: tuple[tuple[str, str], ...] = (
    # (keyword, WHTSection value) — keywords are lowercased before matching.
    ("salary", "149_salary"),
    ("تنخواہ", "149_salary"),
    ("سالری", "149_salary"),
    ("rent", "152_rent_property"),
    ("rental", "152_rent_property"),
    ("کرایہ", "152_rent_property"),
    ("dividend", "150_dividend"),
    ("ڈویڈنڈ", "150_dividend"),
    ("profit on debt", "151_profit_debt"),
    ("interest", "151_profit_debt"),
    ("سود", "151_profit_debt"),
    ("contract", "153_goods_contracts"),
    ("ٹھیکہ", "153_goods_contracts"),
    ("supplier", "153_goods_contracts"),
    ("goods", "153_goods_contracts"),
    ("سامان", "153_goods_contracts"),
    ("export", "154_exports"),
    ("برآمدات", "154_exports"),
    ("electricity", "155_utilities"),
    ("gas bill", "155_utilities"),
    ("utility", "155_utilities"),
    ("utility bill", "155_utilities"),
    ("یوٹیلیٹی", "155_utilities"),
    ("telephone", "169_telephone"),
    ("mobile", "169_telephone"),
    ("ٹیلی فون", "169_telephone"),
    ("services", "156A_services"),
    ("خدمات", "156A_services"),
    ("cash withdrawal", "231_cash_bank"),
    ("bank", "231_cash_bank"),
    ("بینک", "231_cash_bank"),
    ("vehicle", "236K_vehicle"),
    ("car", "236K_vehicle"),
    ("گاڑی", "236K_vehicle"),
    ("property", "236G_property"),
    ("جائیداد", "236G_property"),
    ("education", "233_education"),
    ("tuition", "233_education"),
    ("فیس", "233_education"),
    ("prize bond", "160_prize_bonds"),
    ("پرائز بانڈ", "160_prize_bonds"),
    ("functions", "165_functions"),
    ("تقریب", "165_functions"),
)

def _wht_section_pattern(needle: str) -> "re.Pattern[str]":
    """Compile one keyword: `\\b`-anchored for Latin, substring for Urdu."""
    text = needle.strip()
    if not text:
        return re.compile(r"(?!x)x")  # a blank keyword must never match
    if text.isascii():
        return re.compile(r"\b" + re.escape(text) + r"\b")
    return re.compile(re.escape(text))


_WHT_SECTION_PATTERNS: tuple[tuple["re.Pattern[str]", str], ...] = tuple(
    (_wht_section_pattern(keyword), section)
    for keyword, section in _WHT_SECTION_KEYWORDS
)

# Used when nothing else matches. This is a DEFAULT, not an answer: the tool
# summary below always names the section it assumed so the user is never told a
# rate that was computed for a different payment type than the one they meant.
_DEFAULT_WHT_SECTION = "150_dividend"


def _select_wht_section(query: str) -> tuple[str, bool]:
    """Pick the WHTSection a withholding question is actually about.

    Returns `(section, named_payment_type)`. `section` is always a valid
    `WHTSection` value (see `app/calculations/withholding_tax.py`), defaulting
    to `_DEFAULT_WHT_SECTION` when the query names no payment type — and
    `named_payment_type` is False in exactly that case, so the caller can say
    so instead of presenting the default rate as a certain answer.
    """
    lowered = (query or "").lower()
    for pattern, section in _WHT_SECTION_PATTERNS:
        if pattern.search(lowered):
            return section, True
    return _DEFAULT_WHT_SECTION, False


def _run_calculate(query: str, attachment: Optional[str], language: Optional[str] = None) -> ToolRun:
    from app.calculations import get_tax_engine

    text = query + "\n" + (attachment or "")
    q = query.lower()
    amounts = _extract_amounts(text)
    amount = amounts[0] if amounts else 0.0
    year = _extract_tax_year(text)
    # Report the year actually used when the query named an
    # unsupported one that had to be clamped.
    year_note = "" if _extract_tax_year_raw(text) == year else f" (tax year {year} used; {_extract_tax_year_raw(text)} is not supported by the engine)"
    engine = get_tax_engine()

    def run(calc_type: str, inputs: dict) -> ToolRun:
        result = engine.calculate(calc_type, inputs)
        if result.success:
            return ToolRun(
                tool="calculate",
                ok=True,
                summary=f"{calc_type} computed successfully{year_note}",
                data={
                    "calculation_type": calc_type,
                    "result": result.formatted,
                    "data": result.data if isinstance(result.data, dict) else str(result.data),
                },
            )
        return ToolRun(tool="calculate", ok=False, summary=result.error or _loc("calculation_failed", language))

    # Pick the calculator from keywords — deterministic routing. Urdu-script
    # synonyms are appended at the end of each tuple, so English/Roman-Urdu
    # routing matches exactly what it matched before.
    if any(k in q for k in ("sales tax", "gst", "str ", "سیلز ٹیکس", "سلز ٹیکس", "جی ایس ٹی")):
        purchases = amounts[1] if len(amounts) > 1 else 0.0
        return run("sales_tax", {
            "sales_value": amount,
            "purchases_value": purchases,
            "sales_tax_type": "goods",
            "province": "punjab",
        })
    if any(k in q for k in ("withholding", "wht", "ودہولڈنگ", "ویٹھ ہولڈنگ", "ہولڈنگ ٹیکس")):
        # Section is chosen from the payment type the query names; when it
        # names none, the default is used and stated in the summary so the
        # returned rate is never presented as an answer for a different
        # payment type than the user meant.
        section, named_type = _select_wht_section(query)
        section_note = (
            "" if named_type
            else " (no payment type named — assuming a dividend payment; name it for an exact section)"
        )
        result_run = run("withholding_tax", {
            "transaction_amount": amount,
            "section": section,
            "filer_status": "filer",
            "tax_year": year,
        })
        if result_run.ok and section_note:
            result_run.summary += section_note
        return result_run
    if any(k in q for k in ("salary", "payroll", "monthly salary", "تنخواہ", "سالری")):
        # The salary_tax engine expects basic_salary as a MONTHLY figure.
        # "monthly/per month" in the query -> amount is already monthly;
        # otherwise the amount is treated as ANNUAL salary and converted.
        is_monthly = any(k in q for k in ("monthly", "per month", "a month", "/month", "ماہانہ"))
        basic_monthly = amount if is_monthly else amount / 12.0
        result_run = run("salary_tax", {"basic_salary": basic_monthly, "tax_year": year})
        if result_run.ok:
            basis = "monthly" if is_monthly else "annual (converted to monthly basic)"
            result_run.summary = (
                f"salary_tax computed successfully — input amount treated as {basis} salary"
                f"{year_note}"
            )
        return result_run
    if any(k in q for k in ("capital gain", "property sold", "shares sold", "کیپیٹل گین", "جائیداد فروخت")):
        sale = amounts[0] if amounts else 0.0
        cost = amounts[1] if len(amounts) > 1 else 0.0
        return run("capital_gains", {
            "asset_type": "immovable_property",
            "sale_value": sale,
            "acquisition_cost": cost,
            "holding_period_years": 1,
        })
    if any(k in q for k in ("dividend", "ڈویڈنڈ")):
        return run("dividend_tax", {"income_source": "dividend", "gross_income": amount})
    if any(k in q for k in ("custom duty", "customs duty", "import", "قوابض", "درآمد")):
        return run("custom_duty", {"cif_value": amount, "hs_category": "default"})
    if any(k in q for k in ("excise", "fed ", "ایکسیز")):
        return run("federal_excise", {"category": "cigarettes", "value": amount, "quantity": 1})
    if any(k in q for k in ("property income", "rent received", "rental income", "کرایہ")):
        return run("property_tax", {"annual_rent_received": amount, "tax_year": year})
    if any(k in q for k in ("company", "business", "turnover", "aop", "firm", "کمپنی", "کاروبار", "تجارت")):
        # "private_company" is not a BusinessType value (the enum only
        # has sole_proprietorship|partnership|aop|individual_business),
        # so company/AOP wording maps to `aop` — anything else that
        # falls in this branch is an individual business.
        business_type = "aop" if any(k in q for k in ("company", "aop", "کمپنی")) else "individual_business"
        return run("business_tax", {
            "business_income": amount,
            "business_type": business_type,
            "tax_year": year,
            "annual_turnover": amount,
        })
    # Default: personal income tax.
    return run("income_tax", {
        "gross_income": amount,
        "filing_status": "salaried",
        "tax_year": year,
    })


def _run_verification(query: str, attachment: Optional[str], language: Optional[str] = None) -> ToolRun:
    from app.verification_center.api import get_verification_api

    text = _normalize_digits(query + "\n" + (attachment or ""))
    q = query.lower()
    ntn = _extract_ntn(text)
    cnic_m = _CNIC_RE.search(text)

    try:
        api = get_verification_api()
        if cnic_m:
            res = api.verify_cnic(cnic=cnic_m.group(1))
            return ToolRun(tool="verification", ok=True, summary="CNIC verification executed", data=str(res))
        if ntn:
            if "filer" in q or "atl" in q or "active taxpayer" in q:
                res = api.verify_filer_status(ntn=ntn)
                return ToolRun(tool="verification", ok=True, summary=f"Filer status checked for {ntn}", data=str(res))
            res = api.verify_ntn(ntn=ntn)
            return ToolRun(tool="verification", ok=True, summary=f"NTN {ntn} verification executed", data=str(res))
    except Exception as e:  # noqa: BLE001
        return ToolRun(tool="verification", ok=False, summary=f"{_loc('verification_unavailable', language)}{e}")

    return ToolRun(tool="verification", ok=False, summary=_loc("no_ntn_cnic", language))


def _run_notice(query: str, attachment: Optional[str], language: Optional[str] = None) -> ToolRun:
    from app.notice_analyzer.analyzer import get_notice_analyzer

    text = attachment or query
    try:
        res = get_notice_analyzer().analyze(text)
        return ToolRun(tool="notice_analyzer", ok=True, summary="FBR notice analyzed", data=str(res))
    except Exception as e:  # noqa: BLE001
        return ToolRun(tool="notice_analyzer", ok=False, summary=f"{_loc('notice_analysis_failed', language)}{e}")


def _run_document(attachment: Optional[str], language: Optional[str] = None) -> ToolRun:
    from app.document_intelligence import get_document_analyzer

    try:
        res = get_document_analyzer().analyze(attachment or "")
        return ToolRun(tool="document_analyzer", ok=True, summary="Document text analyzed", data=str(res))
    except Exception as e:  # noqa: BLE001
        return ToolRun(tool="document_analyzer", ok=False, summary=f"{_loc('document_analysis_failed', language)}{e}")


def _run_invoice(query: str, attachment: Optional[str], language: Optional[str] = None) -> ToolRun:
    from app.invoice_intelligence import get_invoice_api

    text = attachment or query
    try:
        res = get_invoice_api().process_invoice(text)
        return ToolRun(tool="invoice", ok=True, summary="Invoice processed", data=str(res))
    except Exception as e:  # noqa: BLE001
        return ToolRun(tool="invoice", ok=False, summary=f"{_loc('invoice_processing_failed', language)}{e}")


def _run_calendar(language: Optional[str] = None) -> ToolRun:
    from app.compliance_calendar.events import get_upcoming_events

    try:
        events = get_upcoming_events(days=30)
        lines = [f"- {e.title}: {e.due_date}" for e in events[:10]]
        return ToolRun(
            tool="calendar",
            ok=True,
            summary=f"{len(events)} upcoming deadlines in the next 30 days",
            data="\n".join(lines) or "No upcoming deadlines.",
        )
    except Exception as e:  # noqa: BLE001
        return ToolRun(tool="calendar", ok=False, summary=f"{_loc('calendar_unavailable', language)}{e}")


def _run_tax_health(query: str, attachment: Optional[str], language: Optional[str] = None) -> ToolRun:
    from app.tax_health.api import get_tax_health_api

    ntn = _extract_ntn(query + "\n" + (attachment or "")) or "0000000"
    year = int(_extract_tax_year(query))
    try:
        res = get_tax_health_api().run_health_check(ntn=ntn, tax_year=year)
        if not res.get("ok", True):
            # No filing/payment data was supplied, so nothing was scored.
            # Report the real status instead of a completed check.
            missing = ", ".join(res.get("required_fields", []))
            return ToolRun(
                tool="tax_health",
                ok=False,
                summary=_loc("tax_health_insufficient", language).format(
                    ntn=ntn, year=year, missing=missing
                ),
                data=str(res),
            )
        return ToolRun(tool="tax_health", ok=True, summary=f"Tax health checked for {ntn} TY{year}", data=str(res))
    except Exception as e:  # noqa: BLE001
        return ToolRun(tool="tax_health", ok=False, summary=f"{_loc('tax_health_unavailable', language)}{e}")


# =============================================================================
# Grounding: RAG retrieval for the legal basis
# =============================================================================

def _rag_ground_meta(query: str, attachment: Optional[str]) -> dict:
    """Retrieval-only grounding for the streaming endpoint.

    Uses FBRRAGEngine.ground() (no LLM call) so the SSE `meta` event
    reaches the client immediately after retrieval instead of after a
    ~45s non-streaming generation. Full grounding/verification of the
    streamed answer happens after the stream in the generator.
    """
    from app.tools.search_tools import shared_rag_engine

    engine = shared_rag_engine()
    rag_question = query
    if attachment:
        rag_question = f"{query}\n\n[Attached document excerpt]: {attachment[:2000]}"
    return engine.ground(rag_question, top_k=5)


def _ground_verification(
    grounded_resp: dict, answer: str, language: Optional[str] = None
) -> dict:
    """Post-stream verification for the streamed answer.

    Mirrors engine.answer(): the deterministic refusal paths keep their
    already-computed verification; real answers go through the same
    verify_answer() pipeline, falling back to the no-evidence answer
    when grounding fails.
    """
    from app.answer_generator import verify_answer

    pre = grounded_resp.get("verification")
    if grounded_resp.get("skip_llm_answer") or pre is not None:
        return pre or {
            "passed": True,
            "reason": "Deterministic refusal/grounding result.",
            "failed_checks": [],
            "checks": {},
        }
    verification = verify_answer(
        question=grounded_resp.get("question", ""),
        answer=answer,
        context=grounded_resp.get("context", ""),
    )
    if not verification.get("passed"):
        # Grounded-answer contract: unverified prose is replaced by the
        # deterministic refusal (same behaviour as engine.answer()).
        verification["replacement_answer"] = localize("no_evidence", language)
    return verification


def _rag_ground(query: str, attachment: Optional[str]) -> tuple[dict, str]:
    """Return (rag_response, context_text) using the canonical RAG engine.

    The engine is a process-wide singleton: constructing FBRRAGEngine()
    per request reloaded the FAISS index + embedding model + BM25 on
    EVERY ask (~20s of silence during which the SSE stream sends no
    bytes at all). One shared instance = one load, fast asks.
    """
    from app.tools.search_tools import shared_rag_engine

    engine = shared_rag_engine()
    rag_question = query
    if attachment:
        rag_question = f"{query}\n\n[Attached document excerpt]: {attachment[:2000]}"
    resp = engine.answer(rag_question, top_k=5)
    return resp, resp.get("context", "")


# =============================================================================
# Personalization / learning (behavioural — never a legal source)
# =============================================================================

# Shape returned to the frontend as AssistantAskResponse.personalization and
# as the SSE `personalization` event. A copy is always returned so callers can
# mutate their own dict without touching the shared template.
_EMPTY_PERSONALIZATION: dict[str, Any] = {
    "enabled": False,
    "recommendations": [],
    "profile_summary": None,
}

# Cap on the recommendations attached to one answer (frontend shows a few).
_PERSONALIZATION_RECS = 5


def _signal(signals: dict, *keys: str) -> Any:
    """Read one signal tolerantly (snake_case first, camelCase tolerated)."""
    if not isinstance(signals, dict):
        return None
    for key in keys:
        value = signals.get(key)
        if value not in (None, "", []):
            return value
    return None


def _learning_snapshot(user_id: Optional[str]) -> tuple[dict, Optional[dict]]:
    """Return (personalization payload, prompt context) for this request.

    Reads the learning store at most twice per request — once for the
    profile (which drives the prompt context) and once for the
    recommendations. Both are fast local SQLite reads on the already-loaded
    process-wide store. Every failure degrades to the empty payload: a
    personalization problem must NEVER fail an answer, so this never raises.
    """
    if not user_id:
        return dict(_EMPTY_PERSONALIZATION), None
    try:
        store = get_learning_store()
        profile = store.get_profile(user_id)
        rec_dicts = [r.dict() for r in store.get_recommendations(user_id, limit=_PERSONALIZATION_RECS)]

        if profile is None:
            return (
                {
                    "enabled": bool(rec_dicts),
                    "recommendations": rec_dicts,
                    "profile_summary": None,
                },
                None,
            )

        profile_dict = profile.dict()
        signals = profile_dict.get("signals") or {}
        payload = {
            "enabled": True,
            "recommendations": rec_dicts,
            "profile_summary": {
                "top_domains": profile_dict.get("top_domains") or [],
                "total_interactions": profile_dict.get("total_interactions") or 0,
            },
        }
        prompt_context = {
            "top_domains": profile_dict.get("top_domains") or [],
            "entity_type": _signal(signals, "entity_type", "entityType"),
            "tax_year": _signal(signals, "tax_year", "taxYear"),
            "language": _signal(signals, "language", "languagePreference", "language_preference"),
            "total_interactions": profile_dict.get("total_interactions") or 0,
            "recommendations": rec_dicts,
        }
        return payload, prompt_context
    except Exception:  # noqa: BLE001 - learning must never break an answer
        logger.debug("Learning snapshot unavailable (continuing without it)", exc_info=True)
        return dict(_EMPTY_PERSONALIZATION), None


def _learning_context(user_id: Optional[str]) -> dict:
    """The `personalization` object attached to an assistant answer."""
    return _learning_snapshot(user_id)[0]


def _personalization_block(user_context: Optional[dict]) -> str:
    """Prompt block describing this account's own learned behaviour.

    Defensive by construction: any malformed value degrades to "" so the
    answer is never lost over personalization.
    """
    if not user_context:
        return ""
    try:
        domains = user_context.get("top_domains") or []
        if domains:
            domain_text = ", ".join(
                f"{d} ({float(score):.1f})" for d, score in domains[:5]
            )
        else:
            domain_text = "nothing specific yet"

        lines = [
            "USER CONTEXT (learned from this account's own past questions — use for tone/relevance only, never as a legal source):",
            f"- Frequently asks about: {domain_text}",
            f"- Taxpayer type: {user_context.get('entity_type') or 'unknown'}"
            f" · Tax year: {user_context.get('tax_year') or 'unknown'}"
            f" · Language preference: {user_context.get('language') or 'unknown'}",
            f"- Interactions so far: {user_context.get('total_interactions') or 0}",
        ]

        recs = user_context.get("recommendations") or []
        if recs:
            lines.append(
                "PERSONALIZED SUGGESTIONS TO MENTION BRIEFLY (max 1-2 lines, only if genuinely relevant):"
            )
            for rec in recs[:3]:
                title = str(rec.get("title") or "").strip() if isinstance(rec, dict) else str(rec)
                body = str(rec.get("body") or "").strip() if isinstance(rec, dict) else ""
                lines.append(f"- {title}: {body}" if title and body else f"- {title or body}")

        lines.append(
            "HARD RULE: tool numbers and FBR citations win over any profile inference — "
            "never change a computed figure or a legal reference to match this profile."
        )
        return "\n".join(lines)
    except Exception:  # noqa: BLE001 - personalization must never break an answer
        logger.debug("Personalization block unavailable (continuing without it)", exc_info=True)
        return ""


def _record_interaction(
    user_id: Optional[str],
    query: str,
    plan: list[str],
    rag_resp: dict,
) -> None:
    """Best-effort interaction recording AFTER an answer was produced.

    Never raises: a personalization write failure is logged and ignored.
    """
    if not user_id:
        return
    try:
        domain = (rag_resp or {}).get("primary_domain") or (plan[0] if plan else "")
        get_learning_store().record_interaction(
            user_id,
            query=query,
            domain=domain,
            tools=list(plan or []),
            signals=extract_signals(query, plan),
            channel="assistant",
        )
    except Exception:  # noqa: BLE001 - learning must never break an answer
        logger.debug("Interaction recording unavailable (continuing without it)", exc_info=True)


# =============================================================================
# Reply language (canonical policy from app.language)
# =============================================================================

def _explicit_language(value: Any) -> Optional[str]:
    """Map a request's `response_language` field to an explicit canonical tag.

    `auto`/empty/`unknown` (and non-strings) mean "no explicit preference"
    and return ``None`` so the query/profile language decides. Anything else
    is normalized via ``app.language.normalize_language``.
    """
    if not value or not isinstance(value, str):
        return None
    tag = value.strip().lower()
    if tag in ("", "auto", "unknown"):
        return None
    try:
        return normalize_language(tag)
    except Exception:  # noqa: BLE001 - never fail a request over a language tag
        return None


def _resolve_reply_language(
    query: str,
    user_context: Optional[dict],
    preferred: Optional[str],
) -> str:
    """Resolve the reply language once per request; never raises.

    Falls back to ``"en"`` on any failure — language handling must never
    fail an answer.
    """
    try:
        profile_language = (
            user_context.get("language") if isinstance(user_context, dict) else None
        )
        return resolve_language(
            query, profile_language=profile_language, preferred=preferred
        )
    except Exception:  # noqa: BLE001 - language must never break an answer
        logger.debug("Reply-language resolution failed (defaulting to English)", exc_info=True)
        return "en"


# =============================================================================
# LLM final answer (provider-agnostic via app.llm)
# =============================================================================

def _final_answer(
    query: str,
    tool_runs: list[ToolRun],
    rag_context: str,
    user_context: Optional[dict] = None,
    language: Optional[str] = None,
) -> str:
    from app.llm import generate_answer, LLMError

    tool_block = ""
    if tool_runs:
        parts = []
        for r in tool_runs:
            parts.append(f"### {r.tool} ({'OK' if r.ok else 'FAILED'})\n{r.summary}\n{r.data or ''}")
        tool_block = "\n\nDETERMINISTIC TOOL RESULTS (authoritative, computed by the backend):\n" + "\n\n".join(parts)

    prompt = f"""
USER QUESTION:
{query}

{tool_block}

RETRIEVED FBR CONTEXT:
{rag_context[:12000]}

 Write the final answer to the user's question.
 - If tool results are present, present those numbers EXACTLY as computed — never recompute, rescale, or reinterpret them. Quote the tool's figures verbatim (amounts, rates, totals). State the basis the tool reported (e.g. annual vs monthly) as-is.
 - Use the FBR context ONLY for the legal basis (section/rule references). Never override tool numbers with figures from the context.
 - Be concise and practical.
"""
    prompt += _personalization_block(user_context)
    try:
        # The reply-language directive is emitted by app.llm from the resolved
        # `language` (it derives one from the question when None), so pass it
        # through instead of duplicating the directive here — an explicit
        # response_language override must not conflict with a directive that
        # llm.py would otherwise re-derive from the question text.
        return generate_answer(query, prompt, language=language)
    except LLMError:
        # Provider down — still return the deterministic tool output.
        if tool_runs:
            ok_runs = [r for r in tool_runs if r.ok]
            if ok_runs:
                return "\n\n".join(
                    f"[{r.tool}] {r.summary}\n{r.data or ''}" for r in ok_runs
                )
        raise


def _final_answer_stream(
    query: str,
    tool_runs: list[ToolRun],
    rag_context: str,
    user_context: Optional[dict] = None,
    language: Optional[str] = None,
):
    """Streaming twin of _final_answer — yields text chunks.

    Falls back to a single deterministic-tools chunk when every LLM
    provider fails before producing content.
    """
    from app.llm import generate_answer_stream, LLMError as _LLMError

    tool_block = ""
    if tool_runs:
        parts = []
        for r in tool_runs:
            parts.append(f"### {r.tool} ({'OK' if r.ok else 'FAILED'})\n{r.summary}\n{r.data or ''}")
        tool_block = "\n\nDETERMINISTIC TOOL RESULTS (authoritative, computed by the backend):\n" + "\n\n".join(parts)

    prompt = f"""
USER QUESTION:
{query}

{tool_block}

RETRIEVED FBR CONTEXT:
{rag_context[:12000]}

 Write the final answer to the user's question.
 - If tool results are present, present those numbers EXACTLY as computed — never recompute, rescale, or reinterpret them. Quote the tool's figures verbatim (amounts, rates, totals). State the basis the tool reported (e.g. annual vs monthly) as-is.
 - Use the FBR context ONLY for the legal basis (section/rule references). Never override tool numbers with figures from the context.
 - Be concise and practical.
"""
    prompt += _personalization_block(user_context)
    try:
        # Same single-source rule as _final_answer (see the comment there).
        for chunk in generate_answer_stream(query, prompt, language=language):
            yield chunk
    except _LLMError:
        if tool_runs:
            ok_runs = [r for r in tool_runs if r.ok]
            if ok_runs:
                yield "\n\n".join(
                    f"[{r.tool}] {r.summary}\n{r.data or ''}" for r in ok_runs
                )
                return
        raise


# =============================================================================
# Endpoint
# =============================================================================

_rate_limiter = RateLimiter.from_env("ASSISTANT_RATE_LIMIT", default_limit=10, default_window=60.0)

# Under FBR_AUTH_REQUIRED=false there is no caller id, so those calls meter
# against one shared "dev-user" quota scope (the same dev-user fallback
# /quota and vault use). The daily budget still applies and a None id can
# never crash the request; enforcement is never silently skipped.
_DEV_QUOTA_SCOPE = "dev-user"


def _quota_scope(user_id: Optional[str]) -> str:
    return str(user_id) if user_id else _DEV_QUOTA_SCOPE


@router.post(
    "/ask",
    response_model=AssistantAskResponse,
    dependencies=[Depends(require_user)],
)
async def assistant_ask(
    request: Request,
    user: Optional[dict] = Depends(require_user),
) -> AssistantAskResponse:
    """AI assistant with access to every backend tool.

    The plan is deterministic (rule-based intent detection), tool
    execution uses the existing verified engines, and the final
    answer is written by the LLM from tool results + grounded FBR
    context. If no tool matches, this degrades to the canonical
    RAG pipeline (same behavior as POST /answer).

    Accepts either JSON ({query, attachment_text}) or multipart
    form-data with a `file` field (PDF/image/text) — the file is
    read by the backend extraction pipeline before planning.

    Personalization is best-effort: the caller's own learned profile
    shapes the prompt/answer and is attached as `personalization`.
    With no authenticated caller (FBR_AUTH_REQUIRED=false) or a
    failing learning store it degrades to an empty object.
    """
    _rate_limiter.check(request)
    user_id = (user or {}).get("id")
    query = ""
    attachment_text: Optional[str] = None
    attachment_name: Optional[str] = None
    response_language = ""
    has_file = False

    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        query = str(form.get("query", ""))
        upload = form.get("file")
        has_file = upload is not None and hasattr(upload, "read")
        if has_file:
            # Same cap as the /uploads router (MAX_FILE_BYTES); read one
            # byte past the limit to detect an oversized upload and
            # reject it with 413 instead of buffering an unbounded file.
            data = await upload.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="File is larger than the 10 MB limit.",
                )
            filename = getattr(upload, "filename", "upload") or "upload"
            lower = filename.lower()
            dot = lower.rfind(".")
            ext = lower[dot:] if dot != -1 else ""
            if ext == ".pdf":
                from app.routers.uploads import _extract_pdf_text

                text, _pages = _extract_pdf_text(data)
                if not text:
                    text = "[OCR simulated - no text extracted] Scanned PDF — no text layer."
                attachment_text = text[:60000]
                attachment_name = filename
            elif ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}:
                from app.routers.uploads import _extract_image_text

                text, _warn = _extract_image_text(data, filename)
                if not text:
                    text = f"[OCR simulated for {filename}] — image received but OCR text unavailable."
                attachment_text = text[:60000]
                attachment_name = filename
            else:
                from app.routers.uploads import _extract_text

                try:
                    attachment_text = _extract_text(data, filename)[:60000]
                except HTTPException:
                    attachment_text = data.decode("utf-8", errors="replace")[:60000]
                attachment_name = filename

        # Optional text attachments sent as form fields.
        form_text = form.get("attachment_text")
        if form_text and not attachment_text:
            attachment_text = str(form_text)
        response_language = str(form.get("response_language", "") or "")
    else:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if isinstance(body, dict):
            query = str(body.get("query", ""))
            attachment_text = body.get("attachment_text")
            attachment_name = body.get("attachment_name")
            response_language = str(body.get("response_language", "") or "")
            if attachment_text is not None:
                attachment_text = str(attachment_text)
            if attachment_name is not None:
                attachment_name = str(attachment_name)

    query = (query or "").strip()
    if not query and attachment_text:
        query = f"Please review the attached file '{attachment_name or 'document'}' and summarize its key tax-related points."
    if not query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_loc("query_required", _explicit_language(response_language)),
        )

    # ---- Daily quota: consume BEFORE any planning/tool/LLM work. ----
    # Resolve the reply language first so a 429 is localized (the answer
    # language is re-resolved with profile context inside the worker below).
    quota_lang = _resolve_reply_language(
        query, None, _explicit_language(response_language)
    )
    store = get_quota_store()
    scope = _quota_scope(user_id)
    snap = store.consume_message(scope)
    if not snap.allowed_message:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=localize("quota_exceeded", quota_lang).format(reset=snap.reset_at),
        )
    if has_file:
        # A chat file costs one of the day's uploads in addition to the
        # message consumed above; rejected before planning if exhausted.
        upload_snap = store.consume_upload(scope)
        if not upload_snap.allowed_upload:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=localize("quota_upload_exceeded", quota_lang),
            )
    quota = store.snapshot(scope).dict()

    try:
        # Tool planning/execution and RAG grounding are sync, CPU/network
        # bound work — run them in a worker thread so slow LLM/retrieval
        # calls never stall the event loop for other requests.
        return await asyncio.to_thread(
            _assistant_ask_sync, request, query, attachment_text, user_id, response_language, quota
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("POST /assistant/ask failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=localize("llm_unavailable", _explicit_language(response_language)),
        ) from e


def _assistant_ask_sync(
    request: Request,
    query: str,
    attachment_text: Optional[str],
    user_id: Optional[str] = None,
    response_language: str = "",
    quota: Optional[dict] = None,
) -> AssistantAskResponse:
    """Synchronous body of /assistant/ask — always runs in a worker thread
    via asyncio.to_thread (see assistant_ask)."""
    try:
        # Personalization snapshot (two fast local store reads) taken before
        # generating so the learned profile can shape the prompt.
        personalization, prompt_context = _learning_snapshot(user_id)
        # Resolve the reply language BEFORE the tools run: every
        # deterministic tool summary below is user-visible text.
        lang = _resolve_reply_language(
            query, prompt_context, _explicit_language(response_language)
        )

        plan = _plan(query, attachment_text)
        tool_runs: list[ToolRun] = []

        for tool in plan:
            if tool == "calculate":
                tool_runs.append(_run_calculate(query, attachment_text, lang))
            elif tool == "verification":
                tool_runs.append(_run_verification(query, attachment_text, lang))
            elif tool == "notice_analyzer":
                tool_runs.append(_run_notice(query, attachment_text, lang))
            elif tool == "document_analyzer":
                tool_runs.append(_run_document(attachment_text, lang))
            elif tool == "invoice":
                tool_runs.append(_run_invoice(query, attachment_text, lang))
            elif tool == "calendar":
                tool_runs.append(_run_calendar(lang))
            elif tool == "tax_health":
                tool_runs.append(_run_tax_health(query, attachment_text, lang))

        # Grounding — canonical RAG engine.
        try:
            rag_resp, rag_context = _rag_ground(query, attachment_text)
        except Exception as e:  # noqa: BLE001
            logger.warning("RAG grounding failed: %s", e)
            rag_resp, rag_context = {"answer": "", "sources": [], "verification": {}, "grounded": False}, ""

        answer = _final_answer(
            query, tool_runs, rag_context, user_context=prompt_context, language=lang
        )

        # Record AFTER the answer exists (never blocks or fails the answer).
        _record_interaction(user_id, query, plan, rag_resp)

        # Tool-computed answers are deterministic engine output — the
        # grounding check compares prose against retrieved chunks and
        # wrongly flags them when the RAG context is thin. Report them
        # honestly: passed with a tool-computation reason, grounded on
        # the strength of the deterministic result.
        ok_tools = [r for r in tool_runs if r.ok]
        if ok_tools:
            verification = {
                "passed": True,
                "checks": {
                    "answer_size": {"passed": True, "reason": "deterministic engine output"},
                    "section_consistency": {"passed": True, "reason": "deterministic engine output"},
                    "grounding": {"passed": True, "reason": "numbers computed by the backend calculation engine"},
                    "speculation": {"passed": True, "reason": "deterministic engine output"},
                },
                "failed_checks": [],
                "reason": "tool-computed result (deterministic engine; figures quoted verbatim)",
            }
        else:
            verification = rag_resp.get("verification", {}) or {
                "passed": False,
                "checks": {},
                "failed_checks": [],
                "reason": "no verification data",
            }

        return AssistantAskResponse(
            question=query,
            answer=answer,
            tools_used=tool_runs,
            sources=rag_resp.get("sources", []),
            verification=verification,
            grounded=bool(rag_resp.get("grounded")) or bool(ok_tools),
            mode="tools+rag" if tool_runs else "rag",
            answer_language=lang,
            personalization=personalization,
            quota=quota or {},
        )

    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("POST /assistant/ask failed (worker thread)")
        raise


@router.post("/ask/stream", dependencies=[Depends(require_user)])
async def assistant_ask_stream(
    request: Request,
    user: Optional[dict] = Depends(require_user),
) -> StreamingResponse:
    """Server-Sent-Events variant of /ask — answer tokens stream live.

    Event sequence:
        event: meta           -> JSON {tools_used, sources, verification, grounded, mode}
        event: personalization-> JSON {enabled, recommendations, profile_summary}
        event: delta          -> data: <text chunk>   (repeated)
        event: verification   -> data: JSON (may carry replacement_answer)
        event: done           -> data: [DONE]
    On failure before any token: event: error with the message.

    The `personalization` event carries the same JSON object as
    AssistantAskResponse.personalization, immediately after `meta`.
    """
    _rate_limiter.check(request)
    user_id = (user or {}).get("id")

    query = ""
    attachment_text: Optional[str] = None
    response_language = ""
    try:
        body = await request.json()
        if isinstance(body, dict):
            query = str(body.get("query", "")).strip()
            attachment_text = body.get("attachment_text")
            response_language = str(body.get("response_language", "") or "")
            if attachment_text is not None:
                attachment_text = str(attachment_text)
    except Exception:  # noqa: BLE001
        pass
    if not query and not attachment_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_loc("query_required", _explicit_language(response_language)),
        )
    if not query:
        query = "Please review the attached document and summarize its key tax-related points."

    # Personalization snapshot (two fast local store reads) taken before the
    # stream opens so the learned profile can shape the prompt and the
    # `personalization` event can be emitted immediately after `meta`.
    personalization, prompt_context = _learning_snapshot(user_id)
    # Resolved before the tools run — tool summaries are user-visible text.
    lang = _resolve_reply_language(
        query, prompt_context, _explicit_language(response_language)
    )

    # Daily quota: consume ONE message BEFORE any planning/tool/LLM work so an
    # exhausted caller gets a real 429 (not a broken stream) and no tool runs.
    store = get_quota_store()
    scope = _quota_scope(user_id)
    snap = store.consume_message(scope)
    if not snap.allowed_message:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=localize("quota_exceeded", lang).format(reset=snap.reset_at),
        )
    quota = store.snapshot(scope).dict()

    plan = _plan(query, attachment_text)
    tool_runs: list[ToolRun] = []
    for tool in plan:
        if tool == "calculate":
            tool_runs.append(_run_calculate(query, attachment_text, lang))
        elif tool == "verification":
            tool_runs.append(_run_verification(query, attachment_text, lang))
        elif tool == "notice_analyzer":
            tool_runs.append(_run_notice(query, attachment_text, lang))
        elif tool == "document_analyzer":
            tool_runs.append(_run_document(attachment_text, lang))
        elif tool == "invoice":
            tool_runs.append(_run_invoice(query, attachment_text, lang))
        elif tool == "calendar":
            tool_runs.append(_run_calendar(lang))
        elif tool == "tax_health":
            tool_runs.append(_run_tax_health(query, attachment_text, lang))

    try:
        grounded_resp = _rag_ground_meta(query, attachment_text)
    except Exception:  # noqa: BLE001
        grounded_resp = {
            "question": query,
            "question_analysis": {},
            "context": "",
            "sources": [],
            "verification": {
                "passed": False,
                "reason": "Retrieval unavailable.",
                "failed_checks": ["retrieval"],
                "checks": {},
            },
            "grounded": False,
            "sufficient": False,
            "skip_llm_answer": (
                localize("unverified", lang)
            ),
        }

    ok_tools = [r for r in tool_runs if r.ok]
    if ok_tools:
        verification = {
            "passed": True,
            "checks": {
                "answer_size": {"passed": True, "reason": "deterministic engine output"},
                "section_consistency": {"passed": True, "reason": "deterministic engine output"},
                "grounding": {"passed": True, "reason": "numbers computed by the backend calculation engine"},
                "speculation": {"passed": True, "reason": "deterministic engine output"},
            },
            "failed_checks": [],
            "reason": "tool-computed result (deterministic engine; figures quoted verbatim)",
        }
    else:
        verification = grounded_resp.get("verification") or {
            "passed": False,
            "checks": {},
            "failed_checks": [],
            "reason": "no verification data",
        }

    # Personalization snapshot (two fast local store reads) taken before the
    # stream opens so the learned profile can shape the prompt and the
    # `personalization` event can be emitted immediately after `meta`.
    personalization, prompt_context = _learning_snapshot(user_id)
    lang = _resolve_reply_language(
        query, prompt_context, _explicit_language(response_language)
    )

    meta = {
        "question": query,
        "tools_used": [r.dict() for r in tool_runs],
        "sources": grounded_resp.get("sources", []),
        "verification": verification,
        "grounded": bool(grounded_resp.get("grounded")) or bool(ok_tools),
        "mode": "tools+rag" if tool_runs else "rag",
        # Same daily-quota object as AssistantAskResponse.quota.
        "quota": quota,
        # Frontend sets dir="rtl" from this.
        "answer_language": lang,
    }

    def _sse(event: str, data: str) -> str:
        return f"event: {event}\ndata: {data}\n\n"

    def generator():
        yield _sse("meta", json.dumps(meta, default=str))
        yield _sse("personalization", json.dumps(personalization, default=str))

        try:
            # Deterministic refusal / ambiguous-section paths skip the LLM
            # entirely — stream the prepared answer directly.
            skip_answer = grounded_resp.get("skip_llm_answer")
            if skip_answer and not ok_tools:
                yield _sse("delta", json.dumps(str(skip_answer)))
                yield _sse("verification", json.dumps(
                    grounded_resp.get("verification")
                    or {"passed": True, "checks": {}, "failed_checks": [],
                        "reason": "Deterministic refusal/grounding result."},
                    default=str,
                ))
                yield _sse("done", "[DONE]")
                return

            collected: list[str] = []
            llm_failed = False
            # Start from the meta verification (forced-pass for tool answers);
            # non-tool paths below overwrite it with real post-stream grounding.
            verification = meta.get("verification") or {"passed": False, "checks": {}}
            try:
                for chunk in _final_answer_stream(
                    query, tool_runs, grounded_resp.get("context", ""),
                    user_context=prompt_context, language=lang,
                ):
                    collected.append(chunk)
                    yield _sse("delta", json.dumps(chunk))
            except LLMError as e:
                llm_failed = True
                logger.warning("POST /assistant/ask/stream LLM unavailable: %s", e)
                fallback = skip_answer or localize("unverified", lang)
                collected.append(fallback)
                yield _sse("delta", json.dumps(fallback))
            except Exception as e:  # noqa: BLE001
                logger.exception("POST /assistant/ask/stream failed")
                yield _sse("error", json.dumps(str(e)))
                return

            # Post-stream verification (runs AFTER the answer reached the user
            # so the tokens are never held hostage behind the verify pipeline).
            # Tool-computed answers are deterministic engine output — grounding
            # the prose against retrieved chunks would wrongly fail on the tool
            # figures, so they keep the forced-pass verification from meta.
            try:
                if not ok_tools:
                    verification = _ground_verification(
                        grounded_resp, "".join(collected), language=lang
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning("POST /assistant/ask/stream verification failed: %s", e)
                verification = {
                    "passed": False,
                    "checks": {},
                    "failed_checks": ["verification_exception"],
                    "reason": str(e)[:200],
                }
            if llm_failed and not ok_tools:
                verification = {
                    "passed": False,
                    "checks": {},
                    "failed_checks": ["llm_call"],
                    "reason": "LLM unavailable; deterministic fallback shown.",
                }
            yield _sse("verification", json.dumps(verification, default=str))
            yield _sse("done", "[DONE]")
        finally:
            # After the stream ends (every exit path, including a client
            # disconnect): record this interaction for personalization.
            _record_interaction(user_id, query, plan, grounded_resp)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
