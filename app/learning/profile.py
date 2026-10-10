"""
Personalization Profile & Signal Extraction
===========================================

Behavioural personalization building blocks. This module performs
**behavioural personalization, NOT model training**: it only aggregates
derived, per-user signals from that user's own interaction history to
shape recommendations. No model weights are read, written, or changed.

Everything here is self-contained (Python stdlib plus the dependency-free
``app.language`` detector) and imports no other app module, so it can be
unit-tested in isolation and reused by the store and recommender without
creating import cycles.

Privacy by design:
    * Raw query text is never stored here. `extract_signals` turns free
      text into small derived signals (amounts, tax year, NTN, notice
      type, document type, language hint, entity type, filing status).
    * Signals are deterministic keyword/regex extraction for a single
      user's text; nothing is aggregated across users.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.language import detect_language

# ------------------------------------------------------------------
# Time helpers
# ------------------------------------------------------------------


def _now() -> datetime:
    """Timezone-aware UTC now (datetime.utcnow is deprecated in 3.12+)."""
    return datetime.now(timezone.utc)


def _parse_iso(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp; naive values are treated as UTC."""
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


# ------------------------------------------------------------------
# Signal model
# ------------------------------------------------------------------


@dataclass
class Signal:
    """One deterministic signal derived from a single user's query text.

    A signal is a small, privacy-preserving fact (e.g. "the query named
    tax year 2025" or "the query looked like Roman-Urdu"). Raw text is
    never retained on a Signal.
    """

    key: str
    value: Any
    weight: float = 1.0

    def dict(self) -> dict:
        return {"key": self.key, "value": self.value, "weight": self.weight}


# ------------------------------------------------------------------
# Deterministic extraction patterns (self-contained regex)
# ------------------------------------------------------------------

_AMOUNT_RE = re.compile(
    r"(?:rs\.?|pkr|rupees)\s*([0-9][0-9,]*(?:\.[0-9]+)?)"
    r"|([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:rs\.?|pkr|rupees)",
    re.IGNORECASE,
)
_TAX_YEAR_RE = re.compile(r"\b(20[0-9]{2})\b")
_NTN_RE = re.compile(r"\b(\d{7}|\d{4}-\d{3}-\d{3}|\d{9})\b")

# Arabic/Urdu script block (used to distinguish Urdu vs Roman-Urdu vs English).
_URDU_SCRIPT_RE = re.compile(r"[\u0600-\u06FF]")

# Common Roman-Urdu function words written in the Latin script.
_ROMAN_URDU_WORDS = (
    "kya", "kyun", "kaise", "kaisa", "kaisi", "kitna", "kitne", "kitni",
    "hai", "hain", "nahi", "nahin", "nai", "aur", "ya", "ye", "wo", "woh",
    "mujhe", "mujhko", "apna", "apni", "apne", "karo", "karna", "karein",
    "liye", "dena", "daina", "batao", "bataein", "samajh", "theek",
    "mushkil", "asaan", "barra", "chota", "paisa", "paisay", "kam", "zyada",
    "taxi", "aadha", "poora", "saal", "mahina", "mahine",
)

# Notice section numbers -> human label (Income Tax Ordinance 2001).
_NOTICE_SECTIONS = {
    "114": "notice_114_nonfiling",
    "122": "notice_122_best_judgment",
    "161": "notice_161_intimation",
    "177": "notice_177_rectification",
    "182": "notice_182_appeal_demand",
}
_NOTICE_PHRASES = (
    "show cause", "show-cause", "demand notice", "penalty notice",
    "legal notice", "appear before", "hearing notice",
)

# Document-type keyword -> canonical label.
_DOC_KEYWORDS = (
    (("salary certificate", "salary slip", "pay slip", "payslip"), "Salary Certificate"),
    (("bank statement", "account statement"), "Bank Statement"),
    (("withholding certificate", "wht certificate", "tax deducted certificate"), "WHT Certificate"),
    (("form 16a", "form 16"), "Form 16A"),
    (("invoice", "tax invoice", "sales invoice"), "Invoice"),
    (("sales tax return",), "Sales Tax Return"),
    (("income tax return", "tax return", "itr"), "Tax Return"),
    (("contract", "agreement"), "Contract"),
)

# Entity-type keywords (order matters: most specific first).
_ENTITY_KEYWORDS = (
    (("salaried", "salary", "employee", "employment"), "salaried"),
    (("private limited", "pvt", "company", "incorporation", "corporate"), "company"),
    (("aop", "association of persons", "firm", "partnership"), "aop"),
    (("business", "sole proprietor", "self-employed", "self employed"), "business"),
)

# Filing-status keywords (most specific first).
_FILING_KEYWORDS = (
    (("late filer", "late-filer", "defaulter", "default"), "late_filer"),
    (("non filer", "non-filer", "nonfiler", "not an active taxpayer", "inactive"), "non_filer"),
    (("filer", "active taxpayer", "atl", "on atl"), "filer"),
)


def _to_num(token: str) -> float:
    return float(token.replace(",", ""))


def _extract_money_amounts(text: str) -> list[float]:
    amounts: list[float] = []
    for m in _AMOUNT_RE.finditer(text):
        tok = m.group(1) or m.group(2)
        try:
            amounts.append(_to_num(tok))
        except ValueError:
            continue
    return amounts


def _extract_tax_year(text: str) -> Optional[int]:
    years = [int(y) for y in _TAX_YEAR_RE.findall(text)]
    return max(years) if years else None


def _extract_ntn(text: str) -> Optional[str]:
    m = _NTN_RE.search(text)
    if not m:
        return None
    digits = m.group(1).replace("-", "")
    if len(digits) == 9:
        return f"{digits[:4]}-{digits[4:7]}-{digits[7:]}"
    return digits


def _extract_notice_type(text: str) -> Optional[str]:
    lowered = text.lower()
    for sec, label in _NOTICE_SECTIONS.items():
        if re.search(rf"\b{sec}\b", lowered):
            return label
    if any(phrase in lowered for phrase in _NOTICE_PHRASES):
        return "notice_generic"
    return None


def _extract_doc_type(text: str) -> Optional[str]:
    lowered = text.lower()
    for keywords, label in _DOC_KEYWORDS:
        if any(k in lowered for k in keywords):
            return label
    return None


def _extract_language(text: str) -> Optional[str]:
    # Delegates to the canonical detector; the vocabulary is unchanged
    # ("ur"/"roman_ur"/"en"), and empty input still resolves to "en".
    return detect_language(text or "")


def _extract_entity_type(text: str) -> Optional[str]:
    lowered = text.lower()
    for keywords, label in _ENTITY_KEYWORDS:
        if any(k in lowered for k in keywords):
            return label
    return None


def _extract_filing_status(text: str) -> Optional[str]:
    lowered = text.lower()
    for keywords, label in _FILING_KEYWORDS:
        if any(k in lowered for k in keywords):
            return label
    return None


def extract_signal_objects(text: str, tools: Optional[list[str]] = None) -> list[Signal]:
    """Deterministic keyword/regex extraction of a single user's query.

    Returns a list of `Signal` objects; raw text is NOT retained on any
    signal, only the derived fact. Reuses no other app module.
    """
    text = text or ""
    signals: list[Signal] = []

    amounts = _extract_money_amounts(text)
    if amounts:
        signals.append(Signal(key="money_amounts", value=amounts, weight=1.0))

    tax_year = _extract_tax_year(text)
    if tax_year is not None:
        signals.append(Signal(key="tax_year", value=tax_year))

    ntn = _extract_ntn(text)
    if ntn:
        signals.append(Signal(key="ntn", value=ntn))

    notice = _extract_notice_type(text)
    if notice:
        signals.append(Signal(key="notice_type", value=notice))

    doc = _extract_doc_type(text)
    if doc:
        signals.append(Signal(key="doc_type", value=doc))

    language = _extract_language(text)
    if language:
        signals.append(Signal(key="language", value=language))

    entity = _extract_entity_type(text)
    if entity:
        signals.append(Signal(key="entity_type", value=entity))

    filing = _extract_filing_status(text)
    if filing:
        signals.append(Signal(key="filing_status", value=filing))

    # Tools are already tracked separately; `tools` is accepted for a
    # symmetric signature but does not influence keyword extraction.
    _ = tools
    return signals


def extract_signals(text: str, tools: Optional[list[str]] = None) -> dict:
    """Deterministic keyword/entity extraction for one user's query.

    Self-contained (no other app module imported). Returns a small dict
    of derived signals with keys:
        money_amounts, tax_year, ntn, notice_type, doc_type,
        language, entity_type, filing_status
    Empty categories are omitted so callers store only what was found.
    """
    return {s.key: s.value for s in extract_signal_objects(text, tools)}


# ------------------------------------------------------------------
# UserProfile
# ------------------------------------------------------------------


@dataclass
class UserProfile:
    """Aggregated, per-user behavioural profile.

    Behavioural personalization only — this is a summary of one user's
    own derived signals used to shape recommendations. No model weights
    take part, and nothing here is aggregated across users.
    """

    top_domains: list[tuple[str, float]] = field(default_factory=list)
    tax_year: Optional[int] = None
    entity_type: Optional[str] = None
    language: Optional[str] = None
    filing_status: Optional[str] = None
    frequent_tools: list[str] = field(default_factory=list)
    document_types_seen: list[str] = field(default_factory=list)
    total_interactions: int = 0
    last_active: Optional[str] = None

    def signals(self) -> dict:
        """The derived, privacy-safe signal summary for this user."""
        return {
            "tax_year": self.tax_year,
            "entity_type": self.entity_type,
            "language": self.language,
            "filing_status": self.filing_status,
            "frequent_tools": list(self.frequent_tools),
            "document_types_seen": list(self.document_types_seen),
        }

    def dict(self) -> dict:
        return {
            "signals": self.signals(),
            "top_domains": [[domain, round(float(score), 4)] for domain, score in self.top_domains],
            "total_interactions": self.total_interactions,
            "last_active": self.last_active,
        }


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    """Read a field from a dict-like or sqlite3.Row-like row."""
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def build_profile(rows: list, decay_days: int = 30) -> UserProfile:
    """Aggregate a single user's interaction rows into a UserProfile.

    Per-user only: `rows` are that one user's interactions. Domain
    interest uses exponential time decay (weight halves every
    `decay_days`); categorical fields use a recency-weighted mode;
    tools are counted by frequency; document types are de-duplicated.

    Behavioural personalization, NOT model training.
    """
    if decay_days <= 0:
        decay_days = 30

    now = _now()
    domain_scores: dict[str, float] = defaultdict(float)
    categorical_weights: dict[str, Counter] = {
        "tax_year": Counter(),
        "entity_type": Counter(),
        "language": Counter(),
        "filing_status": Counter(),
    }
    tool_counter: Counter = Counter()
    docs_seen: Counter = Counter()
    last_active: Optional[str] = None

    for row in rows or []:
        created_raw = _row_get(row, "created_at")
        created = _parse_iso(created_raw)
        if created is None:
            age_days = 0.0
            weight = 1.0
        else:
            age_days = max(0.0, (now - created).total_seconds() / 86400.0)
            weight = 0.5 ** (age_days / decay_days)

        # Keep the newest timestamp seen.
        if isinstance(created_raw, str) and created_raw:
            if last_active is None or created_raw > last_active:
                last_active = created_raw

        # Domain interest with recency decay and feedback nudge.
        domain = _row_get(row, "domain") or ""
        if domain:
            interest = weight
            rating = _row_get(row, "rating")
            if rating == 1:
                interest *= 1.5
            elif rating == -1:
                interest *= 0.5
            domain_scores[domain] += interest

        # Categorical (weighted) modes from derived signals.
        signals = _row_get(row, "signals") or {}
        if isinstance(signals, dict):
            for cat_key in categorical_weights:
                value = signals.get(cat_key)
                if value is not None:
                    categorical_weights[cat_key][value] += weight
            doc = signals.get("doc_type")
            if doc:
                docs_seen[doc] += 1

        # Tool frequency (counted once per interaction row).
        tools = _row_get(row, "tools") or []
        if isinstance(tools, (list, tuple)):
            for tool in set(tools):
                if tool:
                    tool_counter[tool] += 1

    top_domains = sorted(domain_scores.items(), key=lambda kv: kv[1], reverse=True)

    def _mode(cat_key: str) -> Any:
        counter = categorical_weights[cat_key]
        if not counter:
            return None
        return counter.most_common(1)[0][0]

    frequent_tools = [tool for tool, _ in tool_counter.most_common()]
    document_types_seen = [doc for doc, _ in docs_seen.most_common()]

    return UserProfile(
        top_domains=[(d, s) for d, s in top_domains],
        tax_year=_mode("tax_year"),
        entity_type=_mode("entity_type"),
        language=_mode("language"),
        filing_status=_mode("filing_status"),
        frequent_tools=frequent_tools,
        document_types_seen=document_types_seen,
        total_interactions=len(rows or []),
        last_active=last_active,
    )
