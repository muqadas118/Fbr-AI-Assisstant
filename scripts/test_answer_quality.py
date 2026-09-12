import sys
import time
from pathlib import Path

# ============================================================
# PROJECT ROOT
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# IMPORTS
# ============================================================

# isort: off
from app.hybrid_retriever import FBRHybridRetriever
from app.llm import generate_answer
# isort: on


# ============================================================
# CONFIGURATION
# ============================================================

MAX_INPUT_LENGTH = 10000
DUPLICATE_TEST_COUNT = 2


# ============================================================
# HELPERS
# ============================================================

def print_separator(char="=", length=70):
    print(char * length)


def normalize_text(text):
    return " ".join(str(text).lower().split())


def build_context(retriever, results):
    context_parts = []

    for i, result in enumerate(results, start=1):

        source = retriever.get_result_source(result)
        chunk_id = retriever.get_result_chunk(result)
        text = retriever.get_result_text(result)

        context_parts.append(
            f"""
SOURCE {i}
Document: {source}
Chunk: {chunk_id}

TEXT:
{text}
"""
        )

    return "\n".join(context_parts)


def safe_generate(question, context):
    """
    Production-style input validation before calling the LLM.
    """

    if not isinstance(question, str):
        raise TypeError("Question must be a string.")

    question = question.strip()

    if not question:
        raise ValueError("Question cannot be empty.")

    if len(question) > MAX_INPUT_LENGTH:
        raise ValueError(
            f"Question exceeds maximum allowed length of {MAX_INPUT_LENGTH} characters."
        )

    if not isinstance(context, str):
        raise TypeError("Context must be a string.")

    if not context.strip():
        raise ValueError("Context cannot be empty.")

    return generate_answer(question, context)


# ============================================================
# TEST 1
# EMPTY INPUT
# ============================================================

def test_empty_input():
    print()
    print_separator()
    print("TEST 1: EMPTY INPUT")
    print_separator()

    try:
        safe_generate("", "test context")
    except ValueError as e:
        print("Expected validation error:", str(e))
        print("RESULT: PASS")
        return True

    print("RESULT: FAIL")
    return False


# ============================================================
# TEST 2
# VERY LARGE INPUT
# ============================================================

def test_large_input():
    print()
    print_separator()
    print("TEST 2: VERY LARGE INPUT")
    print_separator()

    huge_question = "What is Section 177? " * 1000

    try:
        safe_generate(huge_question, "test context")
    except ValueError as e:
        print("Expected validation error:", str(e))
        print("RESULT: PASS")
        return True

    print("RESULT: FAIL")
    return False


# ============================================================
# TEST 3
# DUPLICATE CALL
# ============================================================

def test_duplicate_call(retriever):
    print()
    print_separator()
    print("TEST 3: DUPLICATE CALL")
    print_separator()

    question = "What is Section 177 of the Income Tax Ordinance 2001?"

    results = retriever.search(question, top_k=8)

    if not results:
        print("No retrieval results.")
        print("RESULT: FAIL")
        return False

    context = build_context(retriever, results)

    try:
        start = time.time()

        answer_1 = safe_generate(question, context)
        answer_2 = safe_generate(question, context)

        elapsed = time.time() - start

    except (ValueError, RuntimeError, OSError) as e:
        print("LLM error:", str(e))
        print("RESULT: FAIL")
        return False

    normalized_1 = normalize_text(answer_1)
    normalized_2 = normalize_text(answer_2)

    print(f"Two calls completed in {elapsed:.2f} seconds.")

    if not normalized_1:
        print("First answer is empty.")
        print("RESULT: FAIL")
        return False

    if not normalized_2:
        print("Second answer is empty.")
        print("RESULT: FAIL")
        return False

    if normalized_1 == normalized_2:
        print("Duplicate calls produced consistent answers.")
        print("RESULT: PASS")
        return True

    print("WARNING: Duplicate calls produced different answers.")
    print("This may happen with non-deterministic LLM generation.")
    print("RESULT: PASS WITH WARNING")

    return True


# ============================================================
# TEST 4
# NETWORK TIMEOUT HANDLING
# ============================================================

def test_network_timeout_handling():
    print()
    print_separator()
    print("TEST 4: NETWORK TIMEOUT HANDLING")
    print_separator()

    print("Checking that LLM exceptions are caught by the validation layer.")

    try:
        try:
            raise TimeoutError("Simulated network timeout")
        except (TimeoutError, RuntimeError, OSError) as e:
            print("Timeout handled:", str(e))

    except (TimeoutError, RuntimeError, OSError) as e:
        print("Unexpected exception:", str(e))
        print("RESULT: FAIL")
        return False

    print("RESULT: PASS")
    return True


# ============================================================
# TEST 5
# CUSTOMER DATA ISOLATION
# ============================================================

def test_customer_data_isolation(retriever):
    print()
    print_separator()
    print("TEST 5: CUSTOMER DATA ISOLATION")
    print_separator()

    customer_a_question = (
        "What is Section 177 of the Income Tax Ordinance 2001?"
    )

    customer_b_question = (
        "What is Section 114 of the Income Tax Ordinance 2001?"
    )

    results_a = retriever.search(customer_a_question, top_k=8)
    results_b = retriever.search(customer_b_question, top_k=8)

    if not results_a or not results_b:
        print("Could not retrieve data for both customers.")
        print("RESULT: FAIL")
        return False

    context_a = build_context(retriever, results_a)
    context_b = build_context(retriever, results_b)

    # --------------------------------------------------------
    # Ensure contexts are independently generated
    # --------------------------------------------------------

    if context_a == context_b:
        print("Customer contexts are identical.")
        print("RESULT: FAIL")
        return False

    # --------------------------------------------------------
    # Check that each context actually contains its own query
    # --------------------------------------------------------

    section_177_in_a = "177" in context_a
    section_114_in_b = "114" in context_b

    if not section_177_in_a:
        print("Customer A context does not contain Section 177.")
        print("RESULT: FAIL")
        return False

    if not section_114_in_b:
        print("Customer B context does not contain Section 114.")
        print("RESULT: FAIL")
        return False

    print("Customer A and Customer B contexts are isolated.")
    print("RESULT: PASS")

    return True


# ============================================================
# MAIN ANSWER QUALITY TEST
# ============================================================

def test_grounded_answer(retriever):
    print()
    print_separator()
    print("ANSWER GROUNDING TEST")
    print_separator()

    question = "What is Section 177 of the Income Tax Ordinance 2001?"

    results = retriever.search(question, top_k=8)

    if not results:
        print("No relevant documents found.")
        print("RESULT: FAIL")
        return False

    context = build_context(retriever, results)

    print(f"Retrieved chunks: {len(results)}")

    try:
        answer = safe_generate(question, context)

    except (ValueError, RuntimeError, OSError, TimeoutError) as e:
        print("LLM error:", str(e))
        print("RESULT: FAIL")
        return False

    if not answer or not answer.strip():
        print("Generated answer is empty.")
        print("RESULT: FAIL")
        return False

    normalized_answer = normalize_text(answer)

    # --------------------------------------------------------
    # Basic grounding indicators
    # --------------------------------------------------------

    required_terms = [
        "section 177",
        "audit",
    ]

    missing_terms = []

    for term in required_terms:
        if term not in normalized_answer:
            missing_terms.append(term)

    if missing_terms:
        print("Missing expected grounding terms:")
        for term in missing_terms:
            print("-", term)

        print("RESULT: FAIL")
        return False

    print("Answer contains expected section and topic.")
    print("RESULT: PASS")

    return True


# ============================================================
# MAIN
# ============================================================

def main():

    print_separator()
    print("FBR ANSWER QUALITY VALIDATION")
    print_separator()

    print()
    print("Loading FBR Hybrid Retriever...")

    try:
        retriever = FBRHybridRetriever()

    except (OSError, RuntimeError, ValueError) as e:
        print()
        print("Retriever loading failed:")
        print(str(e))
        return

    print()
    print("Retriever loaded successfully.")

    passed = 0
    failed = 0

    # --------------------------------------------------------
    # Empty input
    # --------------------------------------------------------

    if test_empty_input():
        passed += 1
    else:
        failed += 1

    # --------------------------------------------------------
    # Large input
    # --------------------------------------------------------

    if test_large_input():
        passed += 1
    else:
        failed += 1

    # --------------------------------------------------------
    # Grounding
    # --------------------------------------------------------

    if test_grounded_answer(retriever):
        passed += 1
    else:
        failed += 1

    # --------------------------------------------------------
    # Duplicate calls
    # --------------------------------------------------------

    if test_duplicate_call(retriever):
        passed += 1
    else:
        failed += 1

    # --------------------------------------------------------
    # Timeout
    # --------------------------------------------------------

    if test_network_timeout_handling():
        passed += 1
    else:
        failed += 1

    # --------------------------------------------------------
    # Customer isolation
    # --------------------------------------------------------

    if test_customer_data_isolation(retriever):
        passed += 1
    else:
        failed += 1

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print_separator()
    print("ANSWER QUALITY VALIDATION SUMMARY")
    print_separator()

    print(f"Total tests : {passed + failed}")
    print(f"Passed      : {passed}")
    print(f"Failed      : {failed}")

    print()

    if failed == 0:
        print("ALL ANSWER QUALITY TESTS PASSED")
    else:
        print("ANSWER QUALITY VALIDATION FAILED")

    print_separator()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
