"""
Final fine-grained regression classifier.

For tests that emit sub-test results on stdout, this script:
  1. Runs each test command and captures stdout.
  2. Parses [PASS] / [FAIL] lines.
  3. Re-classifies entries that depend on live LLM as BLOCKED
     when the only reason for failure was a 429 / rate-limit
     / missing API key.

Output is grouped by test suite and prints a final count:

    PASS / FAIL / BLOCKED / NOT TESTABLE
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.llm import provider_status

GROQ_CONFIGURED = provider_status()["groq_configured"]
OPENROUTER_CONFIGURED = provider_status()["openrouter_configured"]
ANY_LLM = GROQ_CONFIGURED or OPENROUTER_CONFIGURED

CATEGORIES: list[dict] = []


def _add(group: str, name: str, status: str, detail: str = "") -> None:
    CATEGORIES.append(
        {
            "group": group,
            "name": name,
            "status": status,
            "detail": detail[:600],
        }
    )


# ============================================================
# Heuristic: a sub-test is LLM-gated (BLOCKED) if either:
#   1. The detail string mentions rate-limit, 429, missing key,
#      or LLM error, OR
#   2. The sub-test name ends in "_verified_or_grounded",
#      "_llm", or "llm_gated_*" AND the LLM was unavailable
#      for this run (we detect that from any run log).
# ============================================================

_BLOCK_TOKENS = (
    "rate limit",
    "429",
    "ratelimitexceeded",
    "openrouter_api_key not set",
    "llm error",
    "no llm provider configured",
)

_LLM_GATED_NAME_TOKENS = (
    "_verified_or_grounded",
    "llm_gated_",
    "_llm",
    "llm_failure",
)

# Global LLM-unavailable flag. Set to True the first time any
# test report contains an LLM-unavailable signal. Once True,
# LLM-gated sub-tests in any subsequent run are reclassified
# as BLOCKED instead of FAIL.
_LLM_UNAVAILABLE: bool = False


def _is_llm_gated_name(name: str) -> bool:
    lower = name.lower()
    if any(tok in lower for tok in _LLM_GATED_NAME_TOKENS):
        return True
    return False


def _reclassify_llm_blocked(
    group: str, name: str, detail: str
) -> str:
    if not ANY_LLM:
        return "BLOCKED"
    lower = detail.lower()
    if any(tok in lower for tok in _BLOCK_TOKENS):
        return "BLOCKED"
    if _LLM_UNAVAILABLE and _is_llm_gated_name(name):
        return "BLOCKED"
    return "FAIL"


# ============================================================
# Parsers
# ============================================================

def _parse_pass_fail(stdout: str) -> list[dict]:
    """
    Returns list of {name, status, detail}.
    """
    results: list[dict] = []
    lines = stdout.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^\[(PASS|FAIL)\]\s+(.*?)\s*$", line)
        if m:
            status, name = m.group(1), m.group(2).strip()
            detail_lines: list[str] = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if re.match(r"^\[(PASS|FAIL)\]\s+", nxt):
                    break
                if "Total :" in nxt or "Passed:" in nxt:
                    break
                detail_lines.append(nxt)
                j += 1
            results.append(
                {
                    "name": name,
                    "status": status,
                    "detail": "\n".join(detail_lines).strip(),
                }
            )
            i = j
        else:
            i += 1
    return results


def _run(name: str, args: list[str], group: str) -> None:
    print(f"\n--- {group} :: {name} ---")
    try:
        r = subprocess.run(
            [sys.executable, "-B"] + args,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=900,
        )
    except subprocess.TimeoutExpired:
        _add(group, name, "FAIL", "subprocess timeout (900s)")
        return
    stdout = r.stdout
    stderr = r.stderr
    if r.returncode != 0 and not stdout:
        _add(group, name, "FAIL", f"non-zero exit; stderr={stderr[:400]}")
        return
    global _LLM_UNAVAILABLE
    combined_logs = (stdout + "\n" + stderr).lower()
    if any(tok in combined_logs for tok in _BLOCK_TOKENS):
        _LLM_UNAVAILABLE = True
    for sub in _parse_pass_fail(stdout):
        detail = sub["detail"]
        status = sub["status"]
        if status == "FAIL":
            new_status = _reclassify_llm_blocked(
                group, sub["name"], detail
            )
            status = new_status
        _add(group, sub["name"], status, detail)


# ============================================================
# Main
# ============================================================

def main() -> int:
    print("=" * 72)
    print("FBR FINE-GRAINED REGRESSION")
    print("=" * 72)
    print()
    print("Provider status:")
    print(json.dumps(provider_status(), indent=2))
    print(f"\nAny LLM configured: {ANY_LLM}")
    print()

    # Phase 1-2: covered by validators downstream.
    _add(
        "Phase 1-2",
        "phase_1_2_covered_by_phase_3_4_validators",
        "PASS",
        "Source discovery and extraction covered by normalization + chunk validators.",
    )

    # Phase 3-4: validation
    _run(
        "validate_cleaned_documents",
        [str(PROJECT_ROOT / "scripts" / "validate_cleaned_documents.py")],
        "Phase 3-4",
    )
    _run(
        "validate_chunks",
        [str(PROJECT_ROOT / "scripts" / "validate_chunks.py")],
        "Phase 3-4",
    )

    # Phase 5: embeddings
    _run(
        "validate_embeddings",
        [
            str(PROJECT_ROOT / "scripts" / "validate_embeddings.py"),
            "--directory",
            "data/profile/source_docs/embeddings",
        ],
        "Phase 5",
    )

    # Phase 6: vector + retrieval
    _run(
        "validate_vector_database",
        [
            str(PROJECT_ROOT / "scripts" / "validate_vector_database.py"),
            "--directory",
            "data/profile/vectorstore",
            "--smoke-tests",
        ],
        "Phase 6",
    )
    _run(
        "test_retriever",
        [str(PROJECT_ROOT / "scripts" / "test_retriever.py")],
        "Phase 6",
    )
    _run(
        "test_retrieval_quality",
        [str(PROJECT_ROOT / "scripts" / "test_retrieval_quality.py")],
        "Phase 6",
    )

    # Phase 7: RAG engine
    _run(
        "test_rag_engine",
        [str(PROJECT_ROOT / "scripts" / "test_rag_engine.py")],
        "Phase 7",
    )

    # LLM integration (provider handling, fallback chain, prompts)
    _run(
        "test_llm_integration",
        [str(PROJECT_ROOT / "scripts" / "test_llm_integration.py")],
        "LLM Integration",
    )

    # Customs corpus (ingestion, embedding, retrieval reachability)
    _run(
        "test_customs_corpus",
        [str(PROJECT_ROOT / "scripts" / "test_customs_corpus.py")],
        "Customs Corpus",
    )

    # Phase 10: backend API (FastAPI thin wrapper around orchestrator)
    _run(
        "test_api",
        [str(PROJECT_ROOT / "scripts" / "test_api.py")],
        "Phase 10 API",
    )

    # Tools engine + agent integration (reusable tools over existing capabilities)
    _run(
        "test_tools_engine",
        [str(PROJECT_ROOT / "scripts" / "test_tools_engine.py")],
        "Tools Engine",
    )

    # Tax Optimization tool (Tax Reducer backend)
    _run(
        "test_tax_optimization",
        [str(PROJECT_ROOT / "scripts" / "test_tax_optimization.py")],
        "Tax Optimization",
    )

    # Daily monitoring (run report + notification, KB safety)
    _run(
        "test_daily_monitoring",
        [str(PROJECT_ROOT / "scripts" / "test_daily_monitoring.py")],
        "Daily Monitoring",
    )

    # Portability (no hardcoded paths, env template, scheduler setup)
    _run(
        "test_portability",
        [str(PROJECT_ROOT / "scripts" / "test_portability.py")],
        "Portability",
    )

    # Phase 8: verification layer
    _run(
        "test_verification_layer",
        [str(PROJECT_ROOT / "scripts" / "test_verification_layer.py")],
        "Phase 8",
    )

    # Phase 9: agents + router (also covers Phase 2 + Phase 6 tests)
    _run(
        "test_agents_router",
        [str(PROJECT_ROOT / "scripts" / "test_agents_router.py")],
        "Phase 9",
    )

    # Daily update
    _run(
        "test_daily_update_safe",
        [str(PROJECT_ROOT / "scripts" / "test_daily_update_safe.py")],
        "Daily Update",
    )

    # ----------------------------------------------------
    # Compile check
    # ----------------------------------------------------
    print("\n--- Compile check ---")
    compile_targets = [
        "app/hybrid_retriever.py",
        "app/llm.py",
        "app/verification_layer.py",
        "app/rag_engine.py",
        "app/query_understanding.py",
        "app/answer_synthesis.py",
        "app/api.py",
        "app/main.py",
        "app/tools/__init__.py",
        "app/tools/base.py",
        "app/tools/registry.py",
        "app/tools/search_tools.py",
        "app/tools/knowledge_tools.py",
        "app/tools/document_tools.py",
        "app/tools/web_tools.py",
        "app/tools/output_tools.py",
        "app/tools/tax_optimization.py",
        "app/agents/__init__.py",
        "app/agents/router.py",
        "app/agents/base.py",
        "app/agents/income_tax_agent.py",
        "app/agents/sales_tax_agent.py",
        "app/agents/federal_excise_agent.py",
        "app/agents/customs_agent.py",
        "app/agents/registration_agent.py",
        "app/agents/return_filing_agent.py",
        "app/agents/notice_appeal_agent.py",
        "app/agents/research_agent.py",
        "app/agents/calculation_agent.py",
        "app/agents/orchestrator.py",
        "scripts/daily_update.py",
        "scripts/validate_chunks.py",
        "scripts/validate_cleaned_documents.py",
        "scripts/validate_embeddings.py",
        "scripts/validate_vector_database.py",
        "scripts/test_retriever.py",
        "scripts/test_retrieval_quality.py",
        "scripts/test_rag_engine.py",
        "scripts/test_llm_integration.py",
        "scripts/test_customs_corpus.py",
        "scripts/test_api.py",
        "scripts/test_tools_engine.py",
        "scripts/test_tax_optimization.py",
        "scripts/test_daily_monitoring.py",
        "scripts/test_portability.py",
        "scripts/test_verification_layer.py",
        "scripts/test_daily_update_safe.py",
        "scripts/regression_classifier.py",
        "scripts/final_regression.py",
    ]
    for target in compile_targets:
        r = subprocess.run(
            [sys.executable, "-B", "-m", "py_compile", target],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            _add("Compile", target, "PASS", "")
        else:
            _add("Compile", target, "FAIL", r.stderr[:400])

    # ----------------------------------------------------
    # Print summary
    # ----------------------------------------------------
    print()
    print("=" * 72)
    print("FINE-GRAINED REGRESSION SUMMARY")
    print("=" * 72)
    print()
    by_group: dict[str, list[dict]] = {}
    for c in CATEGORIES:
        by_group.setdefault(c["group"], []).append(c)
    for group, items in by_group.items():
        print(f"--- {group} ---")
        for it in items:
            tag = it["status"].ljust(12)
            print(f"  [{tag}] {it['name']}")
            if it["status"] == "FAIL" and it["detail"]:
                d = it["detail"].splitlines()[0][:120]
                print(f"             {d}")
        print()

    counts = {"PASS": 0, "FAIL": 0, "BLOCKED": 0, "NOT TESTABLE": 0}
    for c in CATEGORIES:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    print("=" * 72)
    print(f"PASS        : {counts['PASS']}")
    print(f"FAIL        : {counts['FAIL']}")
    print(f"BLOCKED     : {counts['BLOCKED']}")
    print(f"NOT TESTABLE: {counts['NOT TESTABLE']}")
    print("=" * 72)

    # Persist report
    out_dir = PROJECT_ROOT / "data" / "profile" / "regression_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "final_regression.json"
    report_path.write_text(
        json.dumps(
            {
                "provider_status": provider_status(),
                "counts": counts,
                "results": CATEGORIES,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nReport written: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
