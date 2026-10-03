import sys
from pathlib import Path

# ============================================================
# MAKE PROJECT ROOT AVAILABLE
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# IMPORT
# ============================================================

from app.hybrid_retriever import FBRHybridRetriever

# ============================================================
# TEST QUESTIONS
# ============================================================

TEST_CASES = [
    {
        "name": "Section 177",
        "question": "What is Section 177 of the Income Tax Ordinance 2001?",
        # Family marker: the corpus legitimately holds several ordinance
        # versions (2019-final, upto-2025, 2026). Any Income Tax
        # Ordinance 2001 edition satisfies the expectation; a distinct
        # act (e.g. Sales Tax) does not.
        "expected_source_markers": ["incometaxordinance2001"],
        "expected_terms": [
            "177",
            "Audit",
            "Commissioner",
        ],
    },
    {
        "name": "Section 114",
        "question": "What is Section 114 of the Income Tax Ordinance 2001?",
        "expected_source_markers": ["incometaxordinance2001"],
        "expected_terms": [
            "114",
        ],
    },
    {
        "name": "Section 120",
        "question": "What is Section 120 of the Income Tax Ordinance 2001?",
        "expected_source_markers": ["incometaxordinance2001"],
        "expected_terms": [
            "120",
        ],
    },
]


# ============================================================
# HELPERS
# ============================================================

def normalize(text):
    return str(text).lower().strip()


def contains_expected_term(text, terms):
    text = normalize(text)

    for term in terms:
        if normalize(term) in text:
            return True

    return False


# ============================================================
# SINGLE TEST
# ============================================================

def run_test(retriever, test_case):

    question = test_case["question"]
    expected_source_markers = test_case["expected_source_markers"]
    expected_terms = test_case["expected_terms"]

    print()
    print("=" * 70)
    print(f"TEST: {test_case['name']}")
    print("=" * 70)

    print(f"Question: {question}")

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    results = retriever.search(
        question,
        top_k=5
    )

    if not results:
        print("RESULT: FAIL")
        print("Reason: No retrieval results.")
        return False

    print(f"Retrieved chunks: {len(results)}")

    # --------------------------------------------------------
    # CHECK RESULTS
    # --------------------------------------------------------

    source_found = False
    relevant_found = False

    for position, result in enumerate(results, start=1):

        source = retriever.get_result_source(result)
        text = retriever.get_result_text(result)

        print()
        print(f"Result {position}")
        print(f"Source: {source}")
        print(f"Score: {result.get('score', 0.0):.4f}")
        print(f"Exact match: {result.get('exact_match', False)}")

        # Expected source family (normalized substring match)
        normalized_source = normalize(source).replace(" ", "").replace("_", "")
        if any(
            normalize(marker) in normalized_source
            for marker in expected_source_markers
        ):
            source_found = True

        # Expected section/content terms
        if contains_expected_term(text, expected_terms):
            relevant_found = True

    # --------------------------------------------------------
    # FINAL TEST RESULT
    # --------------------------------------------------------

    if source_found and relevant_found:

        print()
        print("RESULT: PASS")
        return True

    print()
    print("RESULT: FAIL")

    if not source_found:
        print("Reason: Expected source family was not retrieved.")

    if not relevant_found:
        print("Reason: Expected section/content terms were not found.")

    return False


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("FBR RETRIEVAL QUALITY VALIDATION")
    print("=" * 70)

    print()
    print("Loading FBR Hybrid Retriever...")

    retriever = FBRHybridRetriever()

    print()
    print("Retriever loaded successfully.")

    passed = 0
    failed = 0

    # --------------------------------------------------------
    # RUN ALL TESTS
    # --------------------------------------------------------

    for test_case in TEST_CASES:

        try:

            result = run_test(
                retriever,
                test_case
            )

            if result:
                passed += 1
            else:
                failed += 1

        except (ImportError, OSError, RuntimeError, TypeError, ValueError) as e:

            failed += 1

            print()
            print("RESULT: FAIL")
            print(f"Unexpected error: {e}")

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("RETRIEVAL VALIDATION SUMMARY")
    print("=" * 70)

    print(f"Total tests : {len(TEST_CASES)}")
    print(f"Passed      : {passed}")
    print(f"Failed      : {failed}")

    print()

    if failed == 0:
        print("ALL RETRIEVAL TESTS PASSED")
    else:
        print("RETRIEVAL VALIDATION FAILED")

    print("=" * 70)

    # Gate contract: a failed validation must fail the run so the daily
    # pipeline treats this stage honestly.
    if failed:
        raise SystemExit(1)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()