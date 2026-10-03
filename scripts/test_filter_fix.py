"""TASK 2 verification: normalized source comparison logic (no RAG load)."""


def norm(s: str) -> str:
    return s.replace("\\", "/").replace(".pdf", "").lower().strip()


def hit_check(expected: str, top3: list) -> bool:
    e = norm(expected)
    t3 = [norm(s) for s in top3]
    return any(e in s or s in e for s in t3)


if __name__ == "__main__":
    # Case 1: windows path vs plain name
    ok1 = hit_check("customs\\customs-penalties-depth.jsonl",
                    ["customs/customs-penalties-depth", "Budget2026-27_SalientFeatures", "IT3_Form"])
    print("Case1 windows-path vs normalized:", "PASS" if ok1 else "FAIL")

    # Case 2: .pdf extension mismatch
    ok2 = hit_check("Budget2026-27_SalientFeatures.pdf", ["Budget2026-27_SalientFeatures"])
    print("Case2 .pdf vs no-ext:", "PASS" if ok2 else "FAIL")

    # Case 3: genuinely different source should NOT hit
    ok3 = not hit_check("FinanceAct2026.pdf", ["FinanceAct2025", "IT3_Form"])
    print("Case3 different-source (expect no hit):", "PASS" if ok3 else "FAIL")

    assert ok1 and ok2 and ok3, "TASK 2 filter verification FAILED"
    print("ALL FILTER CASES PASS")
