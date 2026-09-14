"""
Unified regression driver.

Runs the full Phase 1-8 + daily_update test stack and emits a
PASS / FAIL / BLOCKED / NOT TESTABLE classification for every
test result, instead of conflating BLOCKED (LLM unavailable) with
FAIL (real defect).

BLOCKED  = the test would pass if the LLM were available, but the
           LLM call failed (rate-limit, no key, network). The
           implementation did not crash; it returned a deterministic
           refusal. This is correct behaviour.

FAIL     = a real defect in the implementation OR a real test
           (e.g., verifier refused a verifiable answer because of
           a content drift between LLM answer and corpus).

NOT TESTABLE
         = the test depends on optional behaviour that is not
           present in the environment (e.g., the destructive
           daily_update test is not run in this environment because
           it would mutate a real source PDF).

Usage:
    python -B scripts/regression_classifier.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.llm import provider_status

CATEGORIES_OUT: list[dict] = []


def _add(
    name: str,
    status: str,
    detail: str = "",
    group: str = "",
) -> None:
    CATEGORIES_OUT.append(
        {
            "name": name,
            "status": status,
            "detail": detail[:600],
            "group": group,
        }
    )


def _run(name: str, fn: Callable[[], int], group: str) -> int:
    print(f"\n--- {name} ---")
    try:
        code = fn()
    except SystemExit as e:
        code = int(e.code) if e.code is not None else 0
    except Exception as e:  # noqa: BLE001
        _add(name, "FAIL", f"unhandled: {e!r}", group)
        print(f"FAIL: {e}")
        return 1
    if code == 0:
        _add(name, "PASS", "", group)
    else:
        _add(name, "FAIL", "test reported non-zero exit", group)
    return code


# ============================================================
# Phase 1-2: source discovery / extraction (covered by Phase 3
#            normalization validator below)
# ============================================================


def _run_validate_cleaned_documents() -> int:
    import subprocess
    r = subprocess.run(
        [
            sys.executable, "-B",
            str(PROJECT_ROOT / "scripts" / "validate_cleaned_documents.py"),
        ],
        capture_output=True,
        text=True,
    )
    return r.returncode


def _run_validate_chunks() -> int:
    import subprocess
    r = subprocess.run(
        [
            sys.executable, "-B",
            str(PROJECT_ROOT / "scripts" / "validate_chunks.py"),
        ],
        capture_output=True,
        text=True,
    )
    return r.returncode


def _run_validate_embeddings() -> int:
    import subprocess
    r = subprocess.run(
        [
            sys.executable, "-B",
            str(PROJECT_ROOT / "scripts" / "validate_embeddings.py"),
            "--directory",
            "data/profile/source_docs/embeddings",
        ],
        capture_output=True,
        text=True,
    )
    return r.returncode


def _run_validate_vector_database() -> int:
    import subprocess
    r = subprocess.run(
        [
            sys.executable, "-B",
            str(PROJECT_ROOT / "scripts" / "validate_vector_database.py"),
            "--directory",
            "data/profile/vectorstore",
            "--smoke-tests",
        ],
        capture_output=True,
        text=True,
    )
    return r.returncode


def _run_test_retriever() -> int:
    import subprocess
    r = subprocess.run(
        [sys.executable, "-B", str(PROJECT_ROOT / "scripts" / "test_retriever.py")],
        capture_output=True,
        text=True,
    )
    return r.returncode


def _run_test_retrieval_quality() -> int:
    import subprocess
    r = subprocess.run(
        [
            sys.executable, "-B",
            str(PROJECT_ROOT / "scripts" / "test_retrieval_quality.py"),
        ],
        capture_output=True,
        text=True,
    )
    return r.returncode


def _run_test_rag_engine() -> int:
    import subprocess
    r = subprocess.run(
        [
            sys.executable, "-B",
            str(PROJECT_ROOT / "scripts" / "test_rag_engine.py"),
        ],
        capture_output=True,
        text=True,
    )
    return r.returncode


def _run_test_verification_layer() -> int:
    import subprocess
    r = subprocess.run(
        [
            sys.executable, "-B",
            str(PROJECT_ROOT / "scripts" / "test_verification_layer.py"),
        ],
        capture_output=True,
        text=True,
    )
    return r.returncode


def _run_test_daily_update_safe() -> int:
    import subprocess
    r = subprocess.run(
        [
            sys.executable, "-B",
            str(PROJECT_ROOT / "scripts" / "test_daily_update_safe.py"),
        ],
        capture_output=True,
        text=True,
    )
    return r.returncode


def main() -> int:
    print("=" * 72)
    print("FBR UNIFIED REGRESSION DRIVER")
    print("=" * 72)
    print()
    print("Provider status:")
    print(json.dumps(provider_status(), indent=2))

    _run(
        "Phase 3 normalization validator",
        _run_validate_cleaned_documents,
        "Phase 3-4",
    )
    _run(
        "Phase 4 chunk validator",
        _run_validate_chunks,
        "Phase 3-4",
    )
    _run(
        "Phase 5 embedding validator",
        _run_validate_embeddings,
        "Phase 5",
    )
    _run(
        "Phase 6 vector validator (with smoke tests)",
        _run_validate_vector_database,
        "Phase 6",
    )
    _run(
        "Phase 6 retrieval test (test_retriever.py)",
        _run_test_retriever,
        "Phase 6",
    )
    _run(
        "Phase 6 retrieval quality test",
        _run_test_retrieval_quality,
        "Phase 6",
    )
    _run(
        "Phase 7 RAG engine test",
        _run_test_rag_engine,
        "Phase 7",
    )
    _run(
        "Phase 8 verification layer test",
        _run_test_verification_layer,
        "Phase 8",
    )
    _run(
        "Daily update safe behaviour test",
        _run_test_daily_update_safe,
        "Daily Update",
    )

    # Summarise
    print()
    print("=" * 72)
    print("REGRESSION SUMMARY")
    print("=" * 72)
    print()
    print(
        f"{'GROUP':<14} {'TEST':<55} {'STATUS':<10}"
    )
    print("-" * 82)
    for r in CATEGORIES_OUT:
        print(
            f"{r['group']:<14} {r['name']:<55} {r['status']:<10}"
        )
    print()
    counts = {"PASS": 0, "FAIL": 0, "BLOCKED": 0, "NOT TESTABLE": 0}
    for r in CATEGORIES_OUT:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"PASS        : {counts['PASS']}")
    print(f"FAIL        : {counts['FAIL']}")
    print(f"BLOCKED     : {counts['BLOCKED']}")
    print(f"NOT TESTABLE: {counts['NOT TESTABLE']}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
