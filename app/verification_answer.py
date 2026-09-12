import re

# ============================================================
# FBR ANSWER VERIFICATION LAYER
# Production-oriented verification for grounded FBR answers
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
    """
    Normalize text for comparison.

    Keeps alphanumeric information while removing punctuation
    differences that should not affect grounding.
    """

    if not isinstance(text, str):
        return ""

    text = text.lower()

    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def tokenize(text: str) -> set:
    """
    Convert text into normalized tokens.
    """

    normalized = normalize_text(text)

    if not normalized:
        return set()

    return {
        token
        for token in normalized.split()
        if len(token) >= 3
    }


# ============================================================
# SECTION DETECTION
# ============================================================

def extract_section_number(question: str):
    """
    Detect section numbers from questions such as:

    Section 177
    section 177 of Income Tax Ordinance
    Sec. 177
    S.177
    """

    if not question:
        return None

    patterns = [
        r"\bsection\s+(\d{1,3})\b",
        r"\bsec\.?\s*(\d{1,3})\b",
        r"\bs\.?\s*(\d{1,3})\b",
    ]

    question_lower = question.lower()

    for pattern in patterns:
        match = re.search(
            pattern,
            question_lower
        )

        if match:
            return int(match.group(1))

    return None


# ============================================================
# SENTENCE SPLITTING
# ============================================================

def split_sentences(text: str) -> list[str]:
    """
    Split answer into meaningful sentences.
    """

    if not text:
        return []

    sentences = re.split(
        r"(?<=[.!?])\s+|\n+",
        text.strip()
    )

    return [
        sentence.strip()
        for sentence in sentences
        if sentence.strip()
    ]


# ============================================================
# NUMERIC CLAIM EXTRACTION
# ============================================================

def extract_numbers(text: str) -> set:
    """
    Extract numeric values from text.

    Examples:
        177
        2001
        500,000
        10.5
        25%
        1A
    """

    if not text:
        return set()

    matches = re.findall(
        r"\b\d+(?:,\d{3})*(?:\.\d+)?\b",
        text
    )

    return {
        value.replace(",", "")
        for value in matches
    }


def extract_number_words(text: str) -> set:
    """
    Extract simple written number words.

    Example:
        "six years" -> {"6"}
        "five percent" -> {"5"}
    """

    if not text:
        return set()

    normalized = normalize_text(text)
    tokens = normalized.split()

    values = set()

    for token in tokens:
        if token in NUMBER_WORDS:
            values.add(NUMBER_WORDS[token])

    return values


def numeric_values(text: str) -> set:
    """
    Return both digit-based and simple word-based numeric values.
    """

    return (
        extract_numbers(text)
        |
        extract_number_words(text)
    )


# ============================================================
# NUMBER / DOCUMENT IDENTIFIER CLASSIFICATION
# ============================================================

def number_is_document_identifier(
    number: str,
    sentence: str,
    question: str
) -> bool:
    """
    Determine whether a number is being used as a document /
    legislation identifier rather than an unsupported factual claim.
    """

    normalized_sentence = normalize_text(sentence)
    normalized_question = normalize_text(question)

    # --------------------------------------------------------
    # Number already occurs in user's question.
    # --------------------------------------------------------

    if re.search(
        rf"\b{re.escape(number)}\b",
        normalized_question
    ):
        return True

    # --------------------------------------------------------
    # Section number is an identifier.
    # --------------------------------------------------------

    section_number = extract_section_number(question)

    if section_number is not None:
        if number == str(section_number):
            return True

    # --------------------------------------------------------
    # Legal document identifiers.
    # --------------------------------------------------------

    document_patterns = [
        rf"\bincome\s+tax\s+ordinance\s+{re.escape(number)}\b",
        rf"\bfinance\s+act\s+{re.escape(number)}\b",
        rf"\bsales\s+tax\s+act\s+{re.escape(number)}\b",
        rf"\bcustoms\s+act\s+{re.escape(number)}\b",
        rf"\bfederal\s+excise\s+act\s+{re.escape(number)}\b",
        rf"\bordinance\s+{re.escape(number)}\b",
        rf"\bact\s+{re.escape(number)}\b",
    ]

    if any(
        re.search(
            pattern,
            normalized_sentence
        )
        for pattern in document_patterns
    ):
        return True

    # --------------------------------------------------------
    # Common year in legal context.
    # --------------------------------------------------------

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

        sentence_tokens = set(
            normalized_sentence.split()
        )

        if sentence_tokens.intersection(
            legal_context_terms
        ):
            return True

    return False


# ============================================================
# NUMERIC GROUNDING
# ============================================================

def check_numeric_grounding(
    sentence: str,
    context: str,
    question: str
) -> dict:
    """
    Verify numeric claims separately.

    Handles:

    1. Numbers explicitly present in context.
    2. Numbers written as words in context.
    3. Section / subsection identifiers.
    4. Legal document years.
    5. Common percentage formatting.
    """

    sentence_numbers = numeric_values(sentence)

    if not sentence_numbers:
        return {
            "passed": True,
            "reason": "No numeric claims detected.",
            "unsupported_numeric_claims": []
        }

    context_numbers = numeric_values(context)

    unsupported = []

    for number in sentence_numbers:

        # ----------------------------------------------------
        # 1. Explicitly supported by context.
        # ----------------------------------------------------

        if number in context_numbers:
            continue

        # ----------------------------------------------------
        # 2. Legal/document identifier.
        # ----------------------------------------------------

        if number_is_document_identifier(
            number,
            sentence,
            question
        ):
            continue

        # ----------------------------------------------------
        # 3. Handle common legal section/subsection references.
        #
        # Example:
        # context: "sub-section (2)"
        # answer: "sub-section 2"
        # ----------------------------------------------------

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
            "unsupported_numeric_claims": unsupported
        }

    return {
        "passed": True,
        "reason": (
            "Numeric claims are grounded or are valid "
            "legal/document identifiers."
        ),
        "unsupported_numeric_claims": []
    }


# ============================================================
# SENTENCE GROUNDING SCORE
# ============================================================

def sentence_grounding_score(
    sentence: str,
    context_tokens: set
) -> float:
    """
    Calculate lexical overlap between answer sentence
    and retrieved context.
    """

    sentence_tokens = tokenize(sentence)

    if not sentence_tokens:
        return 0.0

    overlap = sentence_tokens.intersection(
        context_tokens
    )

    return len(overlap) / len(sentence_tokens)


# ============================================================
# CHECK SOURCE GROUNDING
# ============================================================

def check_grounding(
    answer: str,
    context: str,
    question: str = ""
) -> dict:
    """
    Verify that the generated answer is grounded in
    retrieved FBR context.

    Checks:

    1. Answer exists.
    2. Context exists.
    3. Sentences have sufficient lexical grounding.
    4. Numeric claims are supported.
    """

    if not isinstance(answer, str) or not answer.strip():
        return {
            "passed": False,
            "reason": "Generated answer is empty."
        }

    if not isinstance(context, str) or not context.strip():
        return {
            "passed": False,
            "reason": "Verification context is empty."
        }

    context_tokens = tokenize(context)

    sentences = split_sentences(answer)

    if not sentences:
        return {
            "passed": False,
            "reason": "No verifiable sentences found in answer."
        }

    weak_sentences = []
    numeric_failures = []
    meaningful_sentences = []

    for sentence in sentences:

        sentence_tokens = tokenize(sentence)

        if len(sentence_tokens) < 4:
            continue

        meaningful_sentences.append(sentence)

        # ----------------------------------------------------
        # Lexical grounding
        # ----------------------------------------------------

        score = sentence_grounding_score(
            sentence,
            context_tokens
        )

        if score < MIN_GROUNDED_SENTENCE_SCORE:
            weak_sentences.append({
                "sentence": sentence,
                "score": round(score, 3)
            })

        # ----------------------------------------------------
        # Numeric grounding
        # ----------------------------------------------------

        numeric_result = check_numeric_grounding(
            sentence=sentence,
            context=context,
            question=question
        )

        if not numeric_result["passed"]:

            numeric_failures.append({
                "sentence": sentence,
                "details": numeric_result
            })

    # ========================================================
    # NUMERIC FAILURE HAS HIGH PRIORITY
    # ========================================================

    if numeric_failures:
        return {
            "passed": False,
            "reason": (
                "Answer contains unsupported numeric claims."
            ),
            "weak_sentences": weak_sentences,
            "numeric_failures": numeric_failures
        }

    # ========================================================
    # LEXICAL GROUNDING RATIO
    # ========================================================

    if meaningful_sentences:

        weak_ratio = (
            len(weak_sentences)
            /
            len(meaningful_sentences)
        )

        if weak_ratio > 0.50:
            return {
                "passed": False,
                "reason": (
                    "Too much of the generated answer "
                    "cannot be grounded in the retrieved context."
                ),
                "weak_sentences": weak_sentences,
                "numeric_failures": []
            }

    return {
        "passed": True,
        "reason": (
            "Answer is sufficiently grounded in retrieved context."
        ),
        "weak_sentences": weak_sentences,
        "numeric_failures": []
    }


# ============================================================
# CHECK SECTION CONSISTENCY
# ============================================================

def check_section_consistency(
    question: str,
    answer: str,
    context: str
) -> dict:
    """
    Ensure that a section-specific question is answered
    using the same section.
    """

    section_number = extract_section_number(
        question
    )

    if section_number is None:
        return {
            "passed": True,
            "reason": (
                "Question does not specify a section number."
            )
        }

    expected = str(section_number)

    answer_lower = normalize_text(answer)
    context_lower = normalize_text(context)

    answer_mentions = bool(
        re.search(
            rf"\bsection\s+{re.escape(expected)}\b",
            answer_lower
        )
    )

    context_mentions = bool(
        re.search(
            rf"\b{re.escape(expected)}\s+[a-z]",
            context_lower
        )
        or
        re.search(
            rf"\bsection\s+{re.escape(expected)}\b",
            context_lower
        )
    )

    if not context_mentions:
        return {
            "passed": False,
            "reason": (
                f"Retrieved context does not clearly contain "
                f"Section {section_number}."
            )
        }

    if not answer_mentions:
        return {
            "passed": False,
            "reason": (
                f"Generated answer does not clearly identify "
                f"Section {section_number}."
            )
        }

    return {
        "passed": True,
        "reason": (
            f"Question, context and answer consistently "
            f"refer to Section {section_number}."
        )
    }


# ============================================================
# CHECK ANSWER SIZE
# ============================================================

def check_answer_size(answer: str) -> dict:
    """
    Protect against empty or excessively large generated answers.
    """

    if not isinstance(answer, str) or not answer.strip():
        return {
            "passed": False,
            "reason": "Answer is empty."
        }

    if len(answer) > MAX_ANSWER_LENGTH:
        return {
            "passed": False,
            "reason": (
                f"Answer exceeds maximum allowed length "
                f"of {MAX_ANSWER_LENGTH} characters."
            )
        }

    return {
        "passed": True,
        "reason": (
            "Answer length is within safe limits."
        )
    }


# ============================================================
# CHECK SPECULATIVE / HALLUCINATION WARNING
# ============================================================

def check_hallucination_warning(
    answer: str
) -> dict:
    """
    Detect obvious speculative language.
    """

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

    normalized = normalize_text(
        answer
    )

    detected = [
        phrase
        for phrase in dangerous_patterns
        if phrase in normalized
    ]

    if detected:
        return {
            "passed": False,
            "reason": (
                "Answer contains speculative language: "
                + ", ".join(detected)
            ),
            "detected": detected
        }

    return {
        "passed": True,
        "reason": (
            "No obvious speculative language detected."
        )
    }


# ============================================================
# MASTER VERIFICATION
# ============================================================

def verify_answer(
    question: str,
    answer: str,
    context: str
) -> dict:
    """
    Run the complete FBR answer verification pipeline.

    Verification order:

    1. Answer size
    2. Section consistency
    3. Grounding
    4. Speculation detection

    The answer is accepted only if all checks pass.
    """

    checks = {}

    # --------------------------------------------------------
    # 1. ANSWER SIZE
    # --------------------------------------------------------

    checks["answer_size"] = check_answer_size(
        answer
    )

    if not checks["answer_size"]["passed"]:

        return {
            "passed": False,
            "checks": checks,
            "failed_checks": ["answer_size"],
            "reason": (
                checks["answer_size"]["reason"]
            )
        }

    # --------------------------------------------------------
    # 2. SECTION CONSISTENCY
    # --------------------------------------------------------

    checks["section_consistency"] = (
        check_section_consistency(
            question,
            answer,
            context
        )
    )

    # --------------------------------------------------------
    # 3. GROUNDING
    # --------------------------------------------------------

    checks["grounding"] = check_grounding(
        answer=answer,
        context=context,
        question=question
    )

    # --------------------------------------------------------
    # 4. SPECULATION
    # --------------------------------------------------------

    checks["speculation"] = (
        check_hallucination_warning(
            answer
        )
    )

    # --------------------------------------------------------
    # COLLECT FAILURES
    # --------------------------------------------------------

    failed_checks = [
        name
        for name, result in checks.items()
        if not result["passed"]
    ]

    if failed_checks:

        return {
            "passed": False,
            "checks": checks,
            "failed_checks": failed_checks,
            "reason": (
                "Answer verification failed: "
                + ", ".join(failed_checks)
            )
        }

    # --------------------------------------------------------
    # ALL CHECKS PASSED
    # --------------------------------------------------------

    return {
        "passed": True,
        "checks": checks,
        "failed_checks": [],
        "reason": "All verification checks passed."
    }
