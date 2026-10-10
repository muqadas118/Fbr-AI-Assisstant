"""Canonical, dependency-free language detection and reply-language policy.

The rest of the app imports this module so the assistant always replies in
the user's own language/script:

    * Roman Urdu (Urdu written in Latin letters) -> Roman Urdu (WhatsApp-style)
    * pure Urdu script                           -> Urdu script (اردو)
    * English                                    -> English
    * default                                    -> English

This module is intentionally stdlib-only (no app imports) so it can be
unit-tested in isolation and imported from anywhere without cycles. It
supersets the word lists / regexes previously duplicated in
``app.query_understanding._ROMAN_URDU_TOKENS`` /
``app.query_understanding._detect_language`` and
``app.learning.profile._ROMAN_URDU_WORDS`` /
``app.learning.profile._extract_language``; those originals are left
untouched for backwards compatibility.
"""

from __future__ import annotations

import re

# ------------------------------------------------------------------
# Canonical language identifiers
# ------------------------------------------------------------------

LANG_EN = "en"
LANG_ROMAN_UR = "roman_ur"
LANG_UR = "ur"

LANGUAGES = (LANG_EN, LANG_ROMAN_UR, LANG_UR)

# ------------------------------------------------------------------
# Script / token regexes
# ------------------------------------------------------------------

# Arabic/Urdu script blocks (one or more consecutive script characters).
_URDU_SCRIPT_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]+"
)

# Latin word tokens (letters + apostrophe, e.g. "kya", "nahi'n").
_LATIN_WORD_RE = re.compile(r"[A-Za-z']+")

# Any single Latin letter (used to decide whether a query is a real signal).
_LATIN_LETTER_RE = re.compile(r"[A-Za-z]")

# ------------------------------------------------------------------
# Roman-Urdu lexicon
# ------------------------------------------------------------------
# Superset of:
#   * app.query_understanding._ROMAN_URDU_TOKENS
#   * app.learning.profile._ROMAN_URDU_WORDS
#   * ultra-common WhatsApp Roman-Urdu tokens
_ROMAN_URDU_TOKENS: tuple[str, ...] = (
    # query_understanding._ROMAN_URDU_TOKENS
    "kya", "kaise", "kaisay", "kese", "kesey", "kitne", "kitnay", "kab",
    "kahan", "kaun", "kaunsa", "hai", "hain", "hun", "mein", "se", "ko",
    "ke", "ka", "ki", "wala", "wali", "walay", "ap", "aap", "mujhe", "mujh",
    "tumhe", "tum", "hum", "humne", "kar", "karein", "karna", "zaroor",
    "zaruri", "chahti", "chahta", "chahte", "lagta", "lagti", "lagte",
    # learning.profile._ROMAN_URDU_WORDS
    "kyun", "kaisa", "kaisi", "kitna", "kitni", "nahi", "nahin", "nai",
    "aur", "ya", "ye", "wo", "woh", "mujhko", "apna", "apni", "apne",
    "karo", "liye", "dena", "daina", "batao", "bataein", "samajh", "theek",
    "mushkil", "asaan", "barra", "chota", "paisa", "paisay", "kam", "zyada",
    "taxi", "aadha", "poora", "saal", "mahina", "mahine",
    # ultra-common WhatsApp tokens
    "hoon", "yeh", "mera", "meri", "mere", "karen", "do", "dein", "chahiye",
    "chahiyay", "bataen", "samjhao", "samjhaen", "milay", "milega", "hota",
    "hoti", "hote", "tha", "thi", "the", "main", "per", "par", "pe", "koi",
    "kuch", "sab", "abhi", "phir", "lekin", "magar", "is", "us", "in", "un",
    "bhai", "zarurat", "lagega", "karen",
)

_ROMAN_URDU_SET: frozenset[str] = frozenset(_ROMAN_URDU_TOKENS)

# Plain English words that also appear in the Roman-Urdu lexicon above. They
# only count as Roman-Urdu hits when the query also contains at least one
# clearly Roman-Urdu token, so a plain English sentence is never mis-flagged.
_AMBIGUOUS_ENGLISH: frozenset[str] = frozenset(
    {"main", "may", "is", "us", "the", "a", "i", "no", "so", "do"}
)

# Tokens that can only be Roman Urdu (never ordinary English here). Their
# presence unlocks the ambiguous-English tokens above.
_CLEAR_ROMAN_URDU: frozenset[str] = frozenset(
    {
        "hai", "hain", "nahi", "kya", "kitna", "chahiye", "batao", "karo",
        "karna", "kaise", "mujhe", "mera", "meri", "aur", "mein", "ko",
        "se", "ka", "ki", "ke",
    }
)

# ------------------------------------------------------------------
# Detection
# ------------------------------------------------------------------


def _roman_urdu_hits(tokens: list[str]) -> int:
    token_set = set(tokens)
    has_clear = bool(token_set & _CLEAR_ROMAN_URDU)
    hits = 0
    for token in tokens:
        if token not in _ROMAN_URDU_SET:
            continue
        if token in _AMBIGUOUS_ENGLISH and not has_clear:
            continue
        hits += 1
    return hits


def detect_language(text: str) -> str:
    """Return one of ``LANGUAGES``.

    Urdu script -> ``'ur'``; Roman-Urdu -> ``'roman_ur'``; else ``'en'``.
    """

    if not text or not isinstance(text, str):
        return LANG_EN

    tokens = [t.lower() for t in _LATIN_WORD_RE.findall(text)]
    tokens = [t for t in tokens if t.strip("'")]

    urdu_words = _URDU_SCRIPT_RE.findall(text)
    if urdu_words and len(tokens) <= 2 * len(urdu_words):
        return LANG_UR

    if not tokens:
        return LANG_EN

    hits = _roman_urdu_hits(tokens)
    if hits >= 2:
        return LANG_ROMAN_UR
    if hits >= 1 and len(tokens) <= 12:
        return LANG_ROMAN_UR
    return LANG_EN


# ------------------------------------------------------------------
# Tag normalization
# ------------------------------------------------------------------

_LANGUAGE_ALIASES: dict[str, str] = {
    "en": LANG_EN,
    "eng": LANG_EN,
    "english": LANG_EN,
    "roman_ur": LANG_ROMAN_UR,
    "roman_urdu": LANG_ROMAN_UR,
    "romanurdu": LANG_ROMAN_UR,
    "ur": LANG_UR,
    "urdu": LANG_UR,
}


def _canonical_or_none(tag: str | None) -> str | None:
    """Map a loose tag to a canonical value, or ``None`` when unrecognized."""

    if not tag or not isinstance(tag, str):
        return None
    key = tag.strip().lower().replace("-", "_").replace(" ", "_")
    return _LANGUAGE_ALIASES.get(key)


def normalize_language(tag: str | None) -> str:
    """Map any legacy/loose tag to a canonical ``LANGUAGES`` value.

    ``'roman_urdu'|'roman-ur'|'roman_ur'`` -> ``'roman_ur'``;
    ``'urdu'|'ur'`` -> ``'ur'``; ``'english'|'en'`` -> ``'en'``;
    ``None``/``''``/``'unknown'``/anything else -> ``'en'``.
    """

    return _canonical_or_none(tag) or LANG_EN


# ------------------------------------------------------------------
# Resolution policy
# ------------------------------------------------------------------


def resolve_language(
    query: str,
    *,
    profile_language: str | None = None,
    preferred: str | None = None,
) -> str:
    """Resolve the reply language for a query. Never raises.

    Precedence:

    1. explicit ``preferred`` (a real ``'en'``/``'roman_ur'``/``'ur'`` tag,
       NOT ``'auto'``/``None``);
    2. the detected language of the *current* query, when it is a real
       signal (always for ``'roman_ur'``/``'ur'``; for ``'en'`` only when
       the query has at least 2 Latin letters, so empty/greeting-only input
       falls through);
    3. ``profile_language``;
    4. ``'en'`` (default).
    """

    explicit = _canonical_or_none(preferred)
    if explicit is not None:
        return explicit

    detected = detect_language(query or "")
    if detected in (LANG_ROMAN_UR, LANG_UR):
        return detected
    if detected == LANG_EN and len(_LATIN_LETTER_RE.findall(query or "")) >= 2:
        return LANG_EN

    profile = _canonical_or_none(profile_language)
    if profile is not None:
        return profile
    return LANG_EN


# ------------------------------------------------------------------
# Script / output helpers
# ------------------------------------------------------------------


def is_rtl(lang: str) -> bool:
    """True for ``'ur'`` (right-to-left Urdu script)."""

    return normalize_language(lang) == LANG_UR


_DIRECTIVE_FIGURES_RULE = (
    "Numbers and FBR citations must appear exactly as in the retrieved "
    "evidence — never translate, round or reformat them."
)

_OUTPUT_DIRECTIVES: dict[str, str] = {
    LANG_EN: (
        "Answer entirely in English (this is the default).\n"
        f"{_DIRECTIVE_FIGURES_RULE}"
    ),
    LANG_ROMAN_UR: (
        "Answer entirely in Roman Urdu (Urdu written in Latin letters) in a "
        "natural WhatsApp-style conversational tone. Keep every tax/legal "
        "term, law name, section number, form name, amount, percentage and "
        "citation exactly as written in English; do not write Urdu script and "
        "do not switch to English prose.\n"
        f"{_DIRECTIVE_FIGURES_RULE}"
    ),
    LANG_UR: (
        "Answer entirely in proper Urdu script (اردو). Keep every tax/legal "
        "term, law name, section number, form name, amount, percentage and "
        "citation exactly as written in English; do not romanize and do not "
        "switch to English prose.\n"
        f"{_DIRECTIVE_FIGURES_RULE}"
    ),
}


def output_directive(lang: str) -> str:
    """Short prompt block telling the LLM which language/script to answer in."""

    return _OUTPUT_DIRECTIVES[normalize_language(lang)]


# ------------------------------------------------------------------
# Localized constant text
# ------------------------------------------------------------------

_LOCALIZED: dict[str, dict[str, str]] = {
    "no_evidence": {
        LANG_EN: (
            "The provided FBR documents do not contain enough information to "
            "answer this. Please rephrase with a section number, tax type or "
            "form name."
        ),
        LANG_ROMAN_UR: (
            "Diye gaye FBR documents mein is sawal ka jawab dene ke liye kaafi "
            "maloomat nahi hai. Baraye meharbani section number, tax type ya "
            "form name ke saath dobara likhein."
        ),
        LANG_UR: (
            "دیے گئے FBR دستاویزات میں اس سوال کا جواب دینے کے لیے کافی "
            "معلومات نہیں ہیں۔ براہِ کرم section number، tax type یا form name "
            "کے ساتھ دوبارہ لکھیں۔"
        ),
    },
    "ambiguous_section": {
        LANG_EN: (
            "This question mentions a section number but does not specify "
            "which FBR law you are asking about. Please rephrase and include "
            "the specific law, e.g. \"Section 177 of the Income Tax Ordinance "
            "2001\" or \"Section 177 of the Sales Tax Act 1990\"."
        ),
        LANG_ROMAN_UR: (
            "Is sawal mein section number to hai lekin ye nahi bataya gaya ke "
            "aap kis FBR law ke baare mein pooch rahe hain. Baraye meharbani "
            "specific law likh kar dobara poochein, jaise \"Section 177 of the "
            "Income Tax Ordinance 2001\" ya \"Section 177 of the Sales Tax Act "
            "1990\"."
        ),
        LANG_UR: (
            "اس سوال میں section number تو موجود ہے لیکن یہ نہیں بتایا گیا کہ "
            "آپ کس FBR law کے بارے میں پوچھ رہے ہیں۔ براہِ کرم مخصوص law لکھ کر "
            "دوبارہ پوچھیں، مثلاً \"Section 177 of the Income Tax Ordinance "
            "2001\" یا \"Section 177 of the Sales Tax Act 1990\"۔"
        ),
    },
    "unverified": {
        LANG_EN: (
            "I could not verify an answer against the official FBR corpus "
            "right now. Please rephrase with specific legal terms (section "
            "number, tax type or form name) and try again."
        ),
        LANG_ROMAN_UR: (
            "Abhi main official FBR corpus ke against jawab verify nahi kar "
            "saka. Baraye meharbani section number, tax type ya form name "
            "jaise specific legal terms ke saath dobara koshish karein."
        ),
        LANG_UR: (
            "میں ابھی official FBR corpus کے خلاف کوئی جواب verify نہیں کر "
            "سکا۔ براہِ کرم section number، tax type یا form name جیسی مخصوص "
            "legal terms کے ساتھ دوبارہ کوشش کریں۔"
        ),
    },
    "llm_unavailable": {
        LANG_EN: (
            "The answer service is temporarily unavailable. Please try again "
            "in a moment."
        ),
        LANG_ROMAN_UR: (
            "Answer service abhi thori der ke liye band hai. Baraye meharbani "
            "kuch der baad dobara koshish karein."
        ),
        LANG_UR: (
            "جواب دینے کی خدمت فی الحال عارضی طور پر دستیاب نہیں ہے۔ براہِ کرم "
            "تھوڑی دیر بعد دوبارہ کوشش کریں۔"
        ),
    },
    "placeholder": {
        LANG_EN: "The retrieved evidence does not support a verified answer.",
        LANG_ROMAN_UR: (
            "Retrieved evidence is jawab ko verify nahi karta."
        ),
        LANG_UR: (
            "حاصل شدہ evidence اس جواب کی تصدیق نہیں کرتا۔"
        ),
    },
    "quota_exceeded": {
        LANG_EN: (
            "You have used all your messages for today. Your limit resets "
            "at {reset}."
        ),
        LANG_ROMAN_UR: (
            "Aaj aap ne apne saare messages istemal kar liye hain. Aap ki "
            "limit {reset} par reset ho jaye gi."
        ),
        LANG_UR: (
            "آج آپ نے اپنے تمام پیغامات استعمال کر لیے ہیں۔ آپ کی حد {reset} "
            "پر دوبارہ بحال ہو جائے گی۔"
        ),
    },
    "quota_upload_exceeded": {
        LANG_EN: "You have used all your file uploads for today.",
        LANG_ROMAN_UR: "Aaj aap ne apni saari file uploads istemal kar li hain.",
        LANG_UR: "آج آپ نے اپنی تمام فائل اپلوڈز استعمال کر لی ہیں۔",
    },
}


def localize(kind: str, lang: str) -> str:
    """Return localized constant text for ``kind``.

    ``kind`` in ``'no_evidence' | 'ambiguous_section' | 'unverified' |
    'llm_unavailable' | 'placeholder' | 'quota_exceeded' |
    'quota_upload_exceeded'``. An unknown ``kind`` raises ``KeyError``;
    an unknown ``lang`` is normalized to ``'en'``.

    ``'quota_exceeded'`` carries a ``{reset}`` placeholder: the caller
    fills it via ``.format(reset=...)`` with the reset time from the quota
    snapshot. The daily limit number is deliberately NOT baked into the
    string (it is configured via env and changes per deployment).
    """

    return _LOCALIZED[kind][normalize_language(lang)]


__all__ = [
    "LANG_EN",
    "LANG_ROMAN_UR",
    "LANG_UR",
    "LANGUAGES",
    "detect_language",
    "normalize_language",
    "resolve_language",
    "is_rtl",
    "output_directive",
    "localize",
]
