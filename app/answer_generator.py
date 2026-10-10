"""
FBR ANSWER GENERATOR (compatibility shim)
=========================================

Answer verification logic lives in app.verification_answer (the single
canonical owner). This module keeps the historical import surface
(`from app.answer_generator import verify_answer` used by app.rag_engine)
plus the retriever context helpers and the interactive CLI.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.hybrid_retriever import FBRHybridRetriever
from app.language import resolve_language
from app.llm import generate_answer

# Canonical verification owner — re-exported wholesale for parity.
from app.verification_answer import (  # noqa: F401
    MAX_ANSWER_LENGTH,
    MIN_GROUNDED_SENTENCE_SCORE,
    _is_bare_marker,
    _pattern_hit,
    amount_boundary_match,
    check_answer_size,
    check_grounding,
    check_hallucination_warning,
    check_numeric_claims,
    check_section_consistency,
    extract_number_words,
    extract_numeric_claims,
    extract_section_number,
    normalize_text,
    numeric_claim_is_supported,
    percent_decimal_match,
    split_sentences,
    sentence_grounding_score,
    strip_list_marker,
    strip_list_markers,
    tokenize,
    verify_answer,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ============================================================
# DISPLAY HELPER
# ============================================================


def print_separator(char: str = "=", length: int = 60) -> None:
    print(char * length)


# ============================================================
# INCOME TAX QUESTION DETECTION
# ============================================================


def is_income_tax_question(question) -> bool:
    question_lower = question.lower()

    terms = [
        "income tax",
        "income-tax",
        "income tax ordinance",
        "ordinance 2001",
        "income tax ordinance 2001",
        "fbr",
    ]

    return any(term in question_lower for term in terms)


# ============================================================
# FILTER RESULTS
# ============================================================


def filter_results(retriever, question, results):
    section_number = extract_section_number(question)

    # No section query -> nothing to filter.
    if section_number is None:
        return results

    # Only strict filtering for Income Tax questions.
    if not is_income_tax_question(question):
        return results

    section_pattern = re.compile(
        rf"(?<!\d){section_number}\.\s*[A-Za-z]", re.IGNORECASE
    )

    filtered = []
    for result in results:
        text = retriever.get_result_text(result)
        if not text:
            continue

        # Direct section heading.
        if section_pattern.search(text):
            filtered.append(result)
            continue

        # Explicit reference to the section.
        reference_patterns = [
            rf"\bsection\s+{section_number}\b",
            rf"\bsec\.?\s*{section_number}\b",
        ]
        referenced = any(
            re.search(pattern, text, re.IGNORECASE)
            for pattern in reference_patterns
        )
        if referenced:
            filtered.append(result)

    # Preserve original results if strict filtering removed everything.
    if not filtered:
        return results

    # Remove duplicate chunks.
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


def build_context(retriever, results) -> str:
    context_parts = []
    for i, result in enumerate(results, start=1):
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
# MAIN (interactive CLI)
# ============================================================


def main() -> None:
    print_separator()
    print("FBR ANSWER GENERATOR + FINAL VERIFICATION")
    print_separator()

    print("Loading FBR Hybrid Retriever...")
    retriever = FBRHybridRetriever()
    print("FBR Answer Generator ready.")

    question = input("Enter your FBR question: ").strip()
    if not question:
        print("\nQuestion cannot be empty.")
        return

    # Canonical cap shared with app.rag_engine (MAX_QUESTION_LENGTH).
    # Imported lazily because rag_engine imports this module.
    from app.rag_engine import MAX_QUESTION_LENGTH

    if len(question) > MAX_QUESTION_LENGTH:
        print(
            f"\nQuestion exceeds maximum allowed length "
            f"of {MAX_QUESTION_LENGTH} characters."
        )
        return

    # Mirror the question's language/script in the CLI answer too.
    language = resolve_language(question)

    print()
    print_separator()
    print("SEARCHING FBR DOCUMENTS")
    print_separator()

    try:
        results = retriever.search(question, top_k=8)
    except (OSError, RuntimeError, ValueError) as e:
        print("\nRETRIEVAL ERROR\n" + str(e))
        return

    if not results:
        print("No relevant FBR documents found.")
        return

    original_count = len(results)
    results = filter_results(retriever, question, results)
    filtered_count = len(results)

    print(f"\nRetrieved chunks: {original_count}")
    print(f"Relevant chunks after filtering: {filtered_count}")

    if not results:
        print("No sufficiently relevant FBR context found.")
        return

    print()
    print_separator()
    print("RETRIEVED SOURCES")
    print_separator()

    sources = []
    for result in results:
        source = retriever.get_result_source(result)
        if source and source not in sources:
            sources.append(source)
    for source in sources:
        print(f"- {source}")

    context = build_context(retriever, results)
    if not context.strip():
        print("No usable context found.")
        return

    print()
    print_separator()
    print("GENERATING ANSWER WITH LLM")
    print_separator()

    try:
        answer = generate_answer(question, context, language=language)
    except (OSError, RuntimeError, ValueError) as e:
        print("\nLLM ERROR: The answer could not be generated safely.")
        print(f"Reason: {e}")
        return

    print()
    print_separator()
    print("ANSWER VERIFICATION")
    print_separator()

    verification = verify_answer(
        question=question, answer=answer, context=context, language=language
    )

    for name, result in verification.get("checks", {}).items():
        status = "PASS" if result.get("passed") else "FAIL"
        print(f"{name.upper():25} : {status}")
        print(f"  {result.get('reason', '')}")

    print("\nVERIFICATION RESULT: " + ("PASS" if verification["passed"] else "FAIL"))

    if not verification["passed"]:
        print("\nFINAL ANSWER REJECTED — failed checks: "
              + ", ".join(verification.get("failed_checks", [])))
        return

    print()
    print_separator()
    print("FINAL VERIFIED FBR ANSWER")
    print_separator()
    print(answer)

    print()
    print_separator()
    print("SOURCE DOCUMENTS")
    print_separator()
    for source in sources:
        print(f"- {source}")


if __name__ == "__main__":
    main()
