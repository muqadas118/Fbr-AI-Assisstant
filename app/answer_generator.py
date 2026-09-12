import re
import sys
from pathlib import Path

# ============================================================
# MAKE PROJECT ROOT AVAILABLE
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# IMPORTS
# ============================================================

from app.hybrid_retriever import FBRHybridRetriever
from app.llm import generate_answer

# ============================================================
# VERIFICATION CONFIGURATION
# ============================================================

MAX_ANSWER_LENGTH = 20000
MIN_GROUNDED_SENTENCE_SCORE = 0.10


# ============================================================
# DISPLAY HELPERS
# ============================================================

def print_separator(char="=", length=60):
    print(char * length)


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        return ""

    text = text.lower()

    # Preserve digits and letters.
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def tokenize(text: str) -> set:
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
# SENTENCE GROUNDING
# ============================================================

def sentence_grounding_score(
    sentence: str,
    context_tokens: set
) -> float:

    sentence_tokens = tokenize(sentence)

    if not sentence_tokens:
        return 0.0

    overlap = sentence_tokens.intersection(context_tokens)

    return len(overlap) / len(sentence_tokens)


# ============================================================
# NUMERIC CLAIM EXTRACTION
# ============================================================

def extract_numeric_claims(text: str) -> list[str]:
    if not text:
        return []

    return re.findall(
        r"\b\d+(?:,\d{3})*(?:\.\d+)?\b",
        text
    )


def numeric_claim_is_supported(
    number: str,
    sentence: str,
    context: str
) -> bool:

    # Normalize commas so:
    # 500,000 == 500000
    normalized_number = number.replace(",", "")

    context_numbers = extract_numeric_claims(context)

    for context_number in context_numbers:
        if context_number.replace(",", "") == normalized_number:
            return True

    # Section number is also supported when the question/context
    # explicitly identifies the requested section.
    section_number = extract_section_number(sentence)

    return section_number is not None and str(section_number) == normalized_number


# ============================================================
# CHECK NUMERIC CLAIMS
# ============================================================

def check_numeric_claims(
    answer: str,
    context: str,
    question: str
) -> dict:

    if not answer.strip():
        return {
            "passed": False,
            "reason": "Answer is empty."
        }

    if not context.strip():
        return {
            "passed": False,
            "reason": "Verification context is empty."
        }

    question_numbers = {
        number.replace(",", "")
        for number in extract_numeric_claims(question)
    }

    context_numbers = {
        number.replace(",", "")
        for number in extract_numeric_claims(context)
    }

    unsupported = []

    for sentence in split_sentences(answer):

        sentence_numbers = extract_numeric_claims(sentence)

        for number in sentence_numbers:

            normalized_number = number.replace(",", "")

            # Numbers explicitly present in the user question
            # are allowed.
            if normalized_number in question_numbers:
                continue

            # Numbers present in retrieved source context
            # are supported.
            if normalized_number in context_numbers:
                continue

            # Section number explicitly requested by the user
            # is allowed.
            requested_section = extract_section_number(question)

            if (
                requested_section is not None
                and normalized_number == str(requested_section)
            ):
                continue

            unsupported.append({
                "sentence": sentence,
                "number": number
            })

    if unsupported:
        return {
            "passed": False,
            "reason": (
                "Answer contains numeric claims that are not "
                "supported by the retrieved context."
            ),
            "unsupported_numeric_claims": [
                item["number"]
                for item in unsupported
            ]
        }

    return {
        "passed": True,
        "reason": "All numeric claims are supported."
    }


# ============================================================
# CHECK SOURCE GROUNDING
# ============================================================

def check_grounding(
    answer: str,
    context: str,
    question: str = ""
) -> dict:

    if not answer.strip():
        return {
            "passed": False,
            "reason": "Generated answer is empty."
        }

    if not context.strip():
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

    for sentence in sentences:

        score = sentence_grounding_score(
            sentence,
            context_tokens
        )

        if score < MIN_GROUNDED_SENTENCE_SCORE:

            weak_sentences.append({
                "sentence": sentence,
                "score": round(score, 3)
            })

    # --------------------------------------------------------
    # Numeric grounding
    # --------------------------------------------------------

    numeric_check = check_numeric_claims(
        answer=answer,
        context=context,
        question=question
    )

    if not numeric_check["passed"]:

        return {
            "passed": False,
            "reason": numeric_check["reason"],
            "weak_sentences": weak_sentences,
            "numeric_failures": [
                {
                    "sentence": item["sentence"],
                    "details": numeric_check
                }
                for item in [
                    {
                        "sentence": sentence,
                        "number": number
                    }
                    for sentence in split_sentences(answer)
                    for number in extract_numeric_claims(sentence)
                    if number in numeric_check.get(
                        "unsupported_numeric_claims",
                        []
                    )
                ]
            ]
        }

    # --------------------------------------------------------
    # Ignore very short structural fragments.
    # --------------------------------------------------------

    meaningful_sentences = [
        sentence
        for sentence in sentences
        if len(tokenize(sentence)) >= 4
    ]

    if meaningful_sentences:

        weak_ratio = (
            len(weak_sentences)
            / len(meaningful_sentences)
        )

        if weak_ratio > 0.50:

            return {
                "passed": False,
                "reason": (
                    "Too much of the generated answer "
                    "cannot be grounded in the retrieved context."
                ),
                "weak_sentences": weak_sentences
            }

    return {
        "passed": True,
        "reason": "Answer is sufficiently grounded in retrieved context.",
        "weak_sentences": weak_sentences
    }


# ============================================================
# CHECK SECTION CONSISTENCY
# ============================================================

def check_section_consistency(
    question: str,
    answer: str,
    context: str
) -> dict:

    section_number = extract_section_number(question)

    if section_number is None:

        return {
            "passed": True,
            "reason": (
                "Question does not specify a section number."
            )
        }

    expected = str(section_number)

    answer_lower = answer.lower()
    context_lower = context.lower()

    answer_mentions = bool(
        re.search(
            rf"\bsection\s+{re.escape(expected)}\b",
            answer_lower
        )
    )

    context_mentions = bool(
        re.search(
            rf"\b{re.escape(expected)}\.\s*[a-z]",
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

    if not answer.strip():

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
        "reason": "Answer length is within safe limits."
    }


# ============================================================
# CHECK SPECULATIVE LANGUAGE
# ============================================================

def check_hallucination_warning(answer: str) -> dict:

    dangerous_patterns = [

        "according to my knowledge",
        "i believe",
        "i think",
        "probably",
        "likely",
        "it may be",
        "it might be",
        "possibly",
        "perhaps",
        "maybe",
        "i assume",
        "i suspect",
    ]

    normalized = normalize_text(answer)

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
        "reason": "No obvious speculative language detected."
    }


# ============================================================
# MASTER ANSWER VERIFICATION
# ============================================================

def verify_answer(
    question: str,
    answer: str,
    context: str
) -> dict:

    checks = {}

    # --------------------------------------------------------
    # 1. ANSWER SIZE
    # --------------------------------------------------------

    checks["answer_size"] = check_answer_size(answer)

    if not checks["answer_size"]["passed"]:

        return {
            "passed": False,
            "checks": checks,
            "failed_checks": ["answer_size"],
            "reason": checks["answer_size"]["reason"]
        }

    # --------------------------------------------------------
    # 2. SECTION CONSISTENCY
    # --------------------------------------------------------

    checks["section_consistency"] = check_section_consistency(
        question=question,
        answer=answer,
        context=context
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

    checks["speculation"] = check_hallucination_warning(
        answer
    )

    # --------------------------------------------------------
    # FAILED CHECKS
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

    return {
        "passed": True,
        "checks": checks,
        "failed_checks": [],
        "reason": "All verification checks passed."
    }


# ============================================================
# INCOME TAX QUESTION DETECTION
# ============================================================

def is_income_tax_question(question):

    question_lower = question.lower()

    terms = [
        "income tax",
        "income-tax",
        "income tax ordinance",
        "ordinance 2001",
        "income tax ordinance 2001",
        "fbr",
    ]

    return any(
        term in question_lower
        for term in terms
    )


# ============================================================
# FILTER RESULTS
# ============================================================

def filter_results(
    retriever,
    question,
    results
):

    section_number = extract_section_number(question)

    # --------------------------------------------------------
    # No section query
    # --------------------------------------------------------

    if section_number is None:
        return results

    # --------------------------------------------------------
    # Only strict filtering for Income Tax questions
    # --------------------------------------------------------

    if not is_income_tax_question(question):
        return results

    section_pattern = re.compile(
        rf"(?<!\d){section_number}\.\s*[A-Za-z]",
        re.IGNORECASE
    )

    filtered = []

    for result in results:

        text = retriever.get_result_text(result)

        if not text:
            continue

        # ----------------------------------------------------
        # Direct section heading
        # ----------------------------------------------------

        if section_pattern.search(text):

            filtered.append(result)
            continue

        # ----------------------------------------------------
        # Explicit reference to section
        # ----------------------------------------------------

        reference_patterns = [

            rf"\bsection\s+{section_number}\b",

            rf"\bsec\.?\s*{section_number}\b",

        ]

        referenced = any(
            re.search(
                pattern,
                text,
                re.IGNORECASE
            )
            for pattern in reference_patterns
        )

        if referenced:
            filtered.append(result)

    # --------------------------------------------------------
    # Preserve original results if strict filtering
    # accidentally removes everything.
    # --------------------------------------------------------

    if not filtered:
        return results

    # --------------------------------------------------------
    # Remove duplicate chunks
    # --------------------------------------------------------

    final_results = []

    seen = set()

    for result in filtered:

        idx = result.get("index")

        if idx in seen:
            continue

        seen.add(idx)

        final_results.append(result)

    return final_results


# ============================================================
# BUILD CONTEXT
# ============================================================

def build_context(
    retriever,
    results
):

    context_parts = []

    for i, result in enumerate(
        results,
        start=1
    ):

        source = retriever.get_result_source(result)

        chunk_id = retriever.get_result_chunk(result)

        text = retriever.get_result_text(result)

        if not text.strip():
            continue

        context_parts.append(
            f"""
================================================================================
SOURCE {i}

Document: {source}

Chunk: {chunk_id}

TEXT:

{text}
"""
        )

    return "\n".join(context_parts)


# ============================================================
# MAIN
# ============================================================

def main():

    print_separator()

    print(
        "FBR ANSWER GENERATOR + FINAL VERIFICATION"
    )

    print_separator()

    # --------------------------------------------------------
    # LOAD RETRIEVER
    # --------------------------------------------------------

    print("Loading FBR Hybrid Retriever...")

    retriever = FBRHybridRetriever()

    print("FBR Answer Generator ready.")

    print()

    # --------------------------------------------------------
    # USER QUESTION
    # --------------------------------------------------------

    question = input(
        "Enter your FBR question: "
    ).strip()

    # --------------------------------------------------------
    # EMPTY INPUT PROTECTION
    # --------------------------------------------------------

    if not question:

        print()
        print("Question cannot be empty.")

        return

    # --------------------------------------------------------
    # LARGE INPUT PROTECTION
    # --------------------------------------------------------

    MAX_QUESTION_LENGTH = 10000

    if len(question) > MAX_QUESTION_LENGTH:

        print()

        print(
            "Question exceeds maximum allowed length "
            f"of {MAX_QUESTION_LENGTH} characters."
        )

        return

    print()

    print_separator()

    print("SEARCHING FBR DOCUMENTS")

    print_separator()

    # --------------------------------------------------------
    # RETRIEVE
    # --------------------------------------------------------

    try:

        results = retriever.search(
            question,
            top_k=8
        )

    except (OSError, RuntimeError, ValueError) as e:

        print()

        print_separator()

        print("RETRIEVAL ERROR")

        print_separator()

        print(str(e))

        return

    if not results:

        print(
            "No relevant FBR documents found."
        )

        return

    # --------------------------------------------------------
    # FILTER
    # --------------------------------------------------------

    original_count = len(results)

    results = filter_results(
        retriever,
        question,
        results
    )

    filtered_count = len(results)

    print()

    print(
        f"Retrieved chunks: {original_count}"
    )

    print(
        f"Relevant chunks after filtering: "
        f"{filtered_count}"
    )

    if not results:

        print(
            "No sufficiently relevant FBR context found."
        )

        return

    # --------------------------------------------------------
    # SOURCES
    # --------------------------------------------------------

    print()

    print_separator()

    print("RETRIEVED SOURCES")

    print_separator()

    sources = []

    for result in results:

        source = retriever.get_result_source(
            result
        )

        if source and source not in sources:

            sources.append(source)

    for source in sources:

        print(f"- {source}")

    # --------------------------------------------------------
    # CONTEXT
    # --------------------------------------------------------

    context = build_context(
        retriever,
        results
    )

    if not context.strip():

        print(
            "No usable context found."
        )

        return

    print()

    print_separator()

    print("RETRIEVED CONTEXT")

    print_separator()

    print(context)

    # --------------------------------------------------------
    # GENERATE ANSWER
    # --------------------------------------------------------

    print()

    print_separator()

    print("GENERATING ANSWER WITH LLM")

    print_separator()

    try:

        answer = generate_answer(
            question,
            context
        )

    except (OSError, RuntimeError, ValueError) as e:

        print()

        print_separator()

        print("LLM ERROR")

        print_separator()

        print(
            "The answer could not be generated safely."
        )

        print(
            f"Reason: {e}"
        )

        return

    # --------------------------------------------------------
    # VERIFY ANSWER
    # --------------------------------------------------------

    print()

    print_separator()

    print("ANSWER VERIFICATION")

    print_separator()

    verification = verify_answer(
        question=question,
        answer=answer,
        context=context
    )

    checks = verification.get(
        "checks",
        {}
    )

    # --------------------------------------------------------
    # DISPLAY VERIFICATION DETAILS
    # --------------------------------------------------------

    for name, result in checks.items():

        status = (
            "PASS"
            if result.get("passed")
            else "FAIL"
        )

        print(
            f"{name.upper():25} : {status}"
        )

        print(
            f"  {result.get('reason', '')}"
        )

    print()

    print(
        "VERIFICATION RESULT: "
        + (
            "PASS"
            if verification["passed"]
            else "FAIL"
        )
    )

    # --------------------------------------------------------
    # HARD VERIFICATION GATE
    # --------------------------------------------------------

    if not verification["passed"]:

        print()

        print_separator()

        print(
            "FINAL ANSWER REJECTED"
        )

        print_separator()

        print(
            "The generated answer failed the verification layer "
            "and will NOT be returned as a verified FBR answer."
        )

        failed_checks = verification.get(
            "failed_checks",
            []
        )

        if failed_checks:

            print()

            print(
                "Failed checks: "
                + ", ".join(failed_checks)
            )

        print()

        return

    # --------------------------------------------------------
    # FINAL VERIFIED ANSWER
    # --------------------------------------------------------

    print()

    print_separator()

    print("FINAL VERIFIED FBR ANSWER")

    print_separator()

    print(answer)

    # --------------------------------------------------------
    # SOURCE DOCUMENTS
    # --------------------------------------------------------

    print()

    print_separator()

    print("SOURCE DOCUMENTS")

    print_separator()

    for source in sources:

        print(f"- {source}")

    print()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()