"""
FBR ANSWER VERIFICATION LAYER
=============================

Single canonical owner of answer verification. All other modules
(`app.answer_generator`, legacy `app.verification`) re-export from
here; the parity-checked test suite (`scripts/test_verification_layer.py`)
pins this module and `app.answer_generator` to identical behavior.
"""

import re

from app.language import LANG_EN, detect_language, normalize_language

# ============================================================
# SHARED CONSTANTS
# ============================================================

MAX_ANSWER_LENGTH = 20000
MIN_GROUNDED_SENTENCE_SCORE = 0.10

# ============================================================
# COMMON DOCUMENT YEARS
# ============================================================

COMMON_DOCUMENT_YEARS = {
    str(year)
    for year in range(2001, 2031)
}

# ============================================================
# NUMBER WORDS
# ============================================================

NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
    "thirty": "30",
    "forty": "40",
    "fifty": "50",
    "sixty": "60",
    "seventy": "70",
    "eighty": "80",
    "ninety": "90",
    "hundred": "100",
    "thousand": "1000",
    "million": "1000000",
}

# ============================================================
# TEXT NORMALIZATION
# ============================================================


def normalize_text(text: str) -> str:
    """Normalize text for comparison (lowercase, alphanumeric + spaces)."""
    if not isinstance(text, str):
        return ""

    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def tokenize(text: str) -> set:
    """Convert text into normalized tokens (>= 3 chars)."""
    normalized = normalize_text(text)

    if not normalized:
        return set()

    return {token for token in normalized.split() if len(token) >= 3}


# ============================================================
# SECTION DETECTION
# ============================================================


def extract_section_number(question: str):
    """Detect section numbers ("Section 177", "sec. 177", "s.177")."""
    if not question:
        return None

    patterns = [
        r"\bsection\s+(\d{1,3})\b",
        r"\bsec\.?\s*(\d{1,3})\b",
        r"\bs\.?\s*(\d{1,3})\b",
    ]

    question_lower = question.lower()

    for pattern in patterns:
        match = re.search(pattern, question_lower)
        if match:
            return int(match.group(1))

    return None


# ============================================================
# SENTENCE SPLITTING
# ============================================================


def split_sentences(text: str) -> list[str]:
    """Split answer into meaningful sentences."""
    if not text:
        return []

    sentences = re.split(r"(?<=[.!?])\s+|\n+", text.strip())

    return [sentence.strip() for sentence in sentences if sentence.strip()]


# ============================================================
# NUMERIC CLAIM EXTRACTION
# ============================================================


def extract_numbers(text: str) -> set:
    """Extract digit-based numeric values ("500,000", "10.5", "177")."""
    if not text:
        return set()

    # Ordinals denote the same number as cardinals ("29th October" vs
    # "29 October"), so strip ordinal suffixes before matching.
    normalized = re.sub(
        r"\b(\d+)(st|nd|rd|th)\b", r"\1", text, flags=re.IGNORECASE
    )

    matches = re.findall(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b", normalized)

    return {value.replace(",", "") for value in matches}


def extract_number_words(text: str) -> set:
    """Extract simple written number words ("seventy-five" -> "75")."""
    if not text:
        return set()

    normalized = normalize_text(text)
    tokens = normalized.split()

    values = set()
    for token in tokens:
        if token in NUMBER_WORDS:
            values.add(NUMBER_WORDS[token])

    _TENS = {
        "twenty": 20,
        "thirty": 30,
        "forty": 40,
        "fifty": 50,
        "sixty": 60,
        "seventy": 70,
        "eighty": 80,
        "ninety": 90,
    }
    _UNITS = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
    }

    for first, second in zip(tokens, tokens[1:]):
        tens = _TENS.get(first)
        units = _UNITS.get(second)
        if tens is not None and units is not None:
            values.add(str(tens + units))

    return values


def numeric_values(text: str) -> set:
    """Return both digit-based and simple word-based numeric values."""
    return extract_numbers(text) | extract_number_words(text)


def _to_float(value: str):
    """Parse a numeric string, returning None when not parseable."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value: str):
    """Parse a plain integer string (no decimals), else None."""
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    if not re.fullmatch(r"\d+", text):
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def amount_boundary_match(number: str, context_numbers: set) -> bool:
    """
    Off-by-one tolerance for large rupee amounts (range boundaries).

    An integer answer differing by exactly 1 from a context integer is
    supported only for amounts of 1,000+ outside 1900-2100 (document
    years), so "600,001" for context "600,000" passes while a wrong
    rate, wrong year, or invented figure still fails.
    """
    n = _parse_int(number)
    if n is None or n < 1000 or 1900 <= n <= 2100:
        return False

    for raw in context_numbers:
        m = _parse_int(raw)
        if m is None or m < 1000 or 1900 <= m <= 2100:
            continue
        if abs(n - m) == 1:
            return True

    return False


def percent_decimal_match(number: str, context_numbers) -> bool:
    """
    Percent/decimal equivalence for rate tables ("0.09" <-> "9%").

    Document years are excluded so a value like 20.25 never "matches"
    the year 2025.
    """
    n = _to_float(number)
    if n is None or abs(n) > 100:
        return False

    for raw in context_numbers:
        m = _to_float(str(raw).replace(",", ""))
        if m is None:
            continue
        if 2001 <= m <= 2030 and m.is_integer():
            continue
        if m != 0 and abs(n / m - 100) < 1e-9:
            return True
        if n != 0 and abs(m / n - 100) < 1e-9:
            return True

    return False


# ============================================================
# LIST MARKERS
# ============================================================

_LIST_MARKER_RE = re.compile(r"^\s*(?:#+\s*)?\d{1,3}[.)]\s*")

# Trailing structural ordinal after a colon — e.g. "Steps: 1."
_TRAILING_MARKER_RE = re.compile(r":\s*\d{1,3}[.)]?\s*$")


def strip_list_marker(sentence: str) -> str:
    """Remove a leading ordered-list marker ("2. ", "### 1. ")."""
    return _LIST_MARKER_RE.sub("", sentence, count=1)


def strip_list_markers(sentence: str) -> str:
    """Strip leading and trailing structural list ordinals."""
    s = strip_list_marker(sentence)
    return _TRAILING_MARKER_RE.sub(".", s)


def _is_bare_marker(sentence: str) -> bool:
    """True when the sentence is only a structural marker ("2.", "### 1.")."""
    core = re.sub(r"[*#`>]", "", sentence).strip()
    if re.fullmatch(r"\d{1,3}[.)]?", core):
        return True
    return bool(_TRAILING_MARKER_RE.search(sentence))


def extract_numeric_claims(text: str) -> list[str]:
    """Extract numeric claims in sentence order (for claim attribution)."""
    if not text:
        return []

    # Ordinals denote the same number as cardinals ("29th October" vs
    # "29 October"), so strip ordinal suffixes before matching.
    normalized = re.sub(
        r"\b(\d+)(st|nd|rd|th)\b", r"\1", text, flags=re.IGNORECASE
    )

    return re.findall(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b", normalized)


# ============================================================
# WHOLE-ANSWER NUMERIC CLAIM CHECK (attribution form)
# ============================================================


def numeric_claim_is_supported(
    number: str,
    sentence: str,
    context: str,
) -> bool:
    """True when a single numeric claim is supported by the context."""
    # Normalize commas so: 500,000 == 500000
    normalized_number = number.replace(",", "")

    context_numbers = extract_numeric_claims(context)

    for context_number in context_numbers:
        if context_number.replace(",", "") == normalized_number:
            return True

    if percent_decimal_match(normalized_number, context_numbers):
        return True

    # Section number is also supported when the sentence
    # explicitly identifies the requested section.
    section_number = extract_section_number(sentence)

    return section_number is not None and str(section_number) == normalized_number


def check_numeric_claims(
    answer: str,
    context: str,
    question: str,
) -> dict:
    """Whole-answer numeric check with per-claim attribution."""
    if not answer.strip():
        return {"passed": False, "reason": "Answer is empty."}

    if not context.strip():
        return {"passed": False, "reason": "Verification context is empty."}

    question_numbers = {
        number.replace(",", "")
        for number in extract_numeric_claims(question)
    }

    context_numbers = {
        number.replace(",", "")
        for number in extract_numeric_claims(context)
    } | extract_number_words(context)

    unsupported = []

    for sentence in split_sentences(answer):
        # Bare structural ordinals ("1.", "### 2") carry no claim.
        if _is_bare_marker(sentence):
            continue

        # Ordered-list markers ("2. Pay by the 18th") are structural
        # ordinals, not factual numeric claims.
        content_sentence = strip_list_markers(sentence)

        sentence_numbers = extract_numeric_claims(content_sentence)

        for number in sentence_numbers:
            normalized_number = number.replace(",", "")

            # Numbers explicitly present in the user question are allowed.
            if normalized_number in question_numbers:
                continue

            # Numbers present in retrieved source context are supported.
            if normalized_number in context_numbers:
                continue

            # Percent/decimal equivalence for rate tables.
            if percent_decimal_match(normalized_number, context_numbers):
                continue

            # Whole-rupee range-boundary reformulation.
            if amount_boundary_match(normalized_number, context_numbers):
                continue

            # Section number explicitly requested by the user is allowed.
            requested_section = extract_section_number(question)
            if (
                requested_section is not None
                and normalized_number == str(requested_section)
            ):
                continue

            unsupported.append({"sentence": sentence, "number": number})

    if unsupported:
        return {
            "passed": False,
            "reason": (
                "Answer contains numeric claims that are not "
                "supported by the retrieved context."
            ),
            "unsupported_numeric_claims": [
                item["number"] for item in unsupported
            ],
        }

    return {"passed": True, "reason": "All numeric claims are supported."}


# ============================================================
# NUMBER / DOCUMENT IDENTIFIER CLASSIFICATION
# ============================================================


def number_is_document_identifier(
    number: str,
    sentence: str,
    question: str,
) -> bool:
    """True when a number is a legal document identifier, not a claim."""
    normalized_sentence = normalize_text(sentence)
    normalized_question = normalize_text(question)

    # Number already occurs in user's question.
    if re.search(rf"\b{re.escape(number)}\b", normalized_question):
        return True

    # Section number is an identifier.
    section_number = extract_section_number(question)
    if section_number is not None and number == str(section_number):
        return True

    # Legal document identifiers ("Finance Act 2025", "Ordinance 2001").
    document_patterns = [
        rf"\bincome\s+tax\s+ordinance\s+{re.escape(number)}\b",
        rf"\bfinance\s+act\s+{re.escape(number)}\b",
        rf"\bsales\s+tax\s+act\s+{re.escape(number)}\b",
        rf"\bcustoms\s+act\s+{re.escape(number)}\b",
        rf"\bfederal\s+excise\s+act\s+{re.escape(number)}\b",
        rf"\bordinance\s+{re.escape(number)}\b",
        rf"\bact\s+{re.escape(number)}\b",
    ]
    if any(re.search(p, normalized_sentence) for p in document_patterns):
        return True

    # Common year in legal context.
    if number in COMMON_DOCUMENT_YEARS:
        legal_context_terms = {
            "ordinance",
            "act",
            "finance",
            "tax",
            "law",
            "rules",
            "regulation",
            "regulations",
            "fbr",
        }
        sentence_tokens = set(normalized_sentence.split())
        if sentence_tokens.intersection(legal_context_terms):
            return True

    return False


# ============================================================
# SENTENCE GROUNDING SCORE
# ============================================================


def sentence_grounding_score(sentence: str, context_tokens: set) -> float:
    """Lexical overlap between an answer sentence and the context."""
    sentence_tokens = tokenize(sentence)

    if not sentence_tokens:
        return 0.0

    overlap = sentence_tokens.intersection(context_tokens)
    return len(overlap) / len(sentence_tokens)


# ============================================================
# NUMERIC GROUNDING (per sentence)
# ============================================================


def check_numeric_grounding(
    sentence: str,
    context: str,
    question: str,
) -> dict:
    """Verify the numeric claims of one sentence against the context."""
    # Bare structural ordinals ("1.", "### 2") carry no factual claim.
    core = re.sub(r"[*#`>]", "", sentence).strip()
    if re.fullmatch(r"\d{1,3}[.)]?", core):
        return {
            "passed": True,
            "reason": "Structural list marker — no numeric claim.",
            "unsupported_numeric_claims": [],
        }

    sentence_numbers = numeric_values(strip_list_marker(sentence))

    if not sentence_numbers:
        return {
            "passed": True,
            "reason": "No numeric claims detected.",
            "unsupported_numeric_claims": [],
        }

    context_numbers = numeric_values(context)

    unsupported = []

    for number in sentence_numbers:
        # 1. Explicitly supported by context.
        if number in context_numbers:
            continue

        # 1b. Percent/decimal equivalence (rate tables).
        if percent_decimal_match(number, context_numbers):
            continue

        # 1c. Whole-rupee range-boundary reformulation.
        if amount_boundary_match(number, context_numbers):
            continue

        # 2. Legal/document identifier.
        if number_is_document_identifier(number, sentence, question):
            continue

        # 3. Legal section/subsection references ("sub-section (2)").
        normalized_sentence = normalize_text(sentence)
        normalized_context = normalize_text(context)

        subsection_patterns = [
            rf"\bsub\s+section\s+{re.escape(number)}\b",
            rf"\bsubsection\s+{re.escape(number)}\b",
        ]
        if any(
            re.search(pattern, normalized_sentence)
            for pattern in subsection_patterns
        ):
            context_subsection_patterns = [
                rf"\bsub\s+section\s+{re.escape(number)}\b",
                rf"\bsubsection\s+{re.escape(number)}\b",
                rf"\bsub\s+section\s+\(?{re.escape(number)}\)?\b",
            ]
            if any(
                re.search(pattern, normalized_context)
                for pattern in context_subsection_patterns
            ):
                continue

        unsupported.append(number)

    if unsupported:
        return {
            "passed": False,
            "reason": (
                "Answer contains numeric claims that are not "
                "supported by the retrieved context."
            ),
            "unsupported_numeric_claims": unsupported,
        }

    return {
        "passed": True,
        "reason": (
            "Numeric claims are grounded or are valid "
            "legal/document identifiers."
        ),
        "unsupported_numeric_claims": [],
    }


# ============================================================
# CHECK SOURCE GROUNDING (whole answer)
# ============================================================


def check_grounding(
    answer: str,
    context: str,
    question: str = "",
    language: str | None = None,
) -> dict:
    """Lexical + numeric grounding for the whole answer.

    Language-aware rule: the lexical score is over English tokens of the
    FBR context, so a faithful Roman-Urdu or Urdu-script answer shares
    almost no tokens with that context and would score ~0. When the
    answer is not English (``language`` or ``detect_language(answer)``)
    the lexical weak-sentence ratio must NOT reject the answer; only the
    numeric grounding (numbers / sections / identifiers must still be
    supported by the context) can fail. English answers are judged
    exactly as before — weak lexical overlap still fails.
    """
    if not isinstance(answer, str) or not answer.strip():
        return {"passed": False, "reason": "Generated answer is empty."}

    if not isinstance(context, str) or not context.strip():
        return {"passed": False, "reason": "Verification context is empty."}

    lang = language or detect_language(answer)
    enforce_lexical = normalize_language(lang) == LANG_EN

    context_tokens = tokenize(context)
    sentences = split_sentences(answer)

    if not sentences:
        return {
            "passed": False,
            "reason": "No verifiable sentences found in answer.",
        }

    weak_sentences = []
    numeric_failures = []
    meaningful_sentences = []

    for sentence in sentences:
        sentence_tokens = tokenize(sentence)

        if len(sentence_tokens) < 4:
            continue

        meaningful_sentences.append(sentence)

        # Lexical grounding
        score = sentence_grounding_score(sentence, context_tokens)
        if score < MIN_GROUNDED_SENTENCE_SCORE:
            weak_sentences.append(
                {"sentence": sentence, "score": round(score, 3)}
            )

        # Numeric grounding
        numeric_result = check_numeric_grounding(
            sentence=sentence, context=context, question=question
        )
        if not numeric_result["passed"]:
            numeric_failures.append(
                {"sentence": sentence, "details": numeric_result}
            )

    if numeric_failures:
        return {
            "passed": False,
            "reason": "Answer contains unsupported numeric claims.",
            "weak_sentences": weak_sentences,
            "numeric_failures": numeric_failures,
        }

    if enforce_lexical and meaningful_sentences:
        weak_ratio = len(weak_sentences) / len(meaningful_sentences)
        if weak_ratio > 0.50:
            return {
                "passed": False,
                "reason": (
                    "Too much of the generated answer "
                    "cannot be grounded in the retrieved context."
                ),
                "weak_sentences": weak_sentences,
                "numeric_failures": [],
            }

    return {
        "passed": True,
        "reason": "Answer is sufficiently grounded in retrieved context.",
        "weak_sentences": weak_sentences,
        "numeric_failures": [],
    }


# ============================================================
# CHECK SECTION CONSISTENCY
# ============================================================


def check_section_consistency(
    question: str,
    answer: str,
    context: str,
) -> dict:
    """Section-specific questions must be answered with the same section."""
    section_number = extract_section_number(question)

    if section_number is None:
        return {
            "passed": True,
            "reason": "Question does not specify a section number.",
        }

    expected = str(section_number)

    answer_lower = normalize_text(answer)
    context_lower = normalize_text(context)

    answer_mentions = bool(
        re.search(rf"\bsection\s+{re.escape(expected)}\b", answer_lower)
    )
    context_mentions = bool(
        re.search(rf"\b{re.escape(expected)}\s+[a-z]", context_lower)
        or re.search(rf"\bsection\s+{re.escape(expected)}\b", context_lower)
    )

    if not context_mentions:
        return {
            "passed": False,
            "reason": (
                f"Retrieved context does not clearly contain "
                f"Section {section_number}."
            ),
        }

    if not answer_mentions:
        return {
            "passed": False,
            "reason": (
                f"Generated answer does not clearly identify "
                f"Section {section_number}."
            ),
        }

    return {
        "passed": True,
        "reason": (
            f"Question, context and answer consistently "
            f"refer to Section {section_number}."
        ),
    }


# ============================================================
# CHECK ANSWER SIZE
# ============================================================


def check_answer_size(answer: str) -> dict:
    """Protect against empty or excessively large generated answers."""
    if not isinstance(answer, str) or not answer.strip():
        return {"passed": False, "reason": "Answer is empty."}

    if len(answer) > MAX_ANSWER_LENGTH:
        return {
            "passed": False,
            "reason": (
                f"Answer exceeds maximum allowed length "
                f"of {MAX_ANSWER_LENGTH} characters."
            ),
        }

    return {
        "passed": True,
        "reason": "Answer length is within safe limits.",
    }


# ============================================================
# CHECK SPECULATIVE / HALLUCINATION WARNING
# ============================================================


def _pattern_hit(normalized: str, phrase: str) -> bool:
    """Single words match on word boundaries; phrases on substrings."""
    if " " not in phrase:
        return (
            re.search(rf"\b{re.escape(phrase)}\b", normalized) is not None
        )
    return phrase in normalized


def check_hallucination_warning(answer: str) -> dict:
    """Detect obvious speculative language."""
    dangerous_patterns = [
        "according to my knowledge",
        "i believe",
        "i think",
        "probably",
        "possibly",
        "likely",
        "it may be",
        "it might be",
        "might allow",
        "may possibly",
        "could possibly",
    ]

    normalized = normalize_text(answer)

    detected = [
        phrase for phrase in dangerous_patterns if _pattern_hit(normalized, phrase)
    ]

    if detected:
        return {
            "passed": False,
            "reason": (
                "Answer contains speculative language: " + ", ".join(detected)
            ),
            "detected": detected,
        }

    return {
        "passed": True,
        "reason": "No obvious speculative language detected.",
    }


# ============================================================
# MASTER VERIFICATION
# ============================================================


def verify_answer(
    question: str,
    answer: str,
    context: str,
    language: str | None = None,
) -> dict:
    """
    Run the complete FBR answer verification pipeline.

    Order: answer_size -> section_consistency -> grounding -> speculation.
    The answer is accepted only if all checks pass.

    Language-aware grounding: the lexical (English-token) overlap check
    is decisive only for English answers. For a non-English answer
    (``language`` or ``detect_language(answer)``) the grounding check
    still enforces numeric/section/identifier grounding, but a faithful
    Roman-Urdu or Urdu-script answer is not rejected merely for having
    no English token overlap with the English context.
    """
    checks = {}

    checks["answer_size"] = check_answer_size(answer)

    if not checks["answer_size"]["passed"]:
        return {
            "passed": False,
            "checks": checks,
            "failed_checks": ["answer_size"],
            "reason": checks["answer_size"]["reason"],
        }

    checks["section_consistency"] = check_section_consistency(
        question, answer, context
    )

    checks["grounding"] = check_grounding(
        answer=answer, context=context, question=question, language=language
    )

    checks["speculation"] = check_hallucination_warning(answer)

    failed_checks = [
        name for name, result in checks.items() if not result["passed"]
    ]

    if failed_checks:
        return {
            "passed": False,
            "checks": checks,
            "failed_checks": failed_checks,
            "reason": "Answer verification failed: " + ", ".join(failed_checks),
        }

    return {
        "passed": True,
        "checks": checks,
        "failed_checks": [],
        "reason": "All verification checks passed.",
    }
