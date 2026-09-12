"""
FBR API tests (offline + mocked).

All tests in this file use the [PASS]/[FAIL] convention so that
scripts/final_regression.py can aggregate them with the rest of
the regression suite.

Coverage:

    [OFFLINE — always run]
    - api[health]_returns_ok
    - api[request]_valid_query_accepted
    - api[request]_missing_query_rejected
    - api[request]_empty_query_rejected
    - api[request]_whitespace_query_rejected
    - api[request]_oversized_query_rejected
    - api[request]_invalid_schema_rejected
    - api[answer]_orchestrator_invoked
    - api[answer]_response_schema_stable
    - api[answer]_safe_refusal_returned_200
    - api[answer]_llmerror_maps_to_503
    - api[answer]_unexpected_error_maps_to_500
    - api[answer]_multi_domain_detected
    - api[answer]_primary_domain_present
    - api[answer]_sources_serialized_correctly
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable
from unittest.mock import AsyncMock, MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# TEST HARNESS
# ============================================================

_RESULTS: list[tuple[str, bool, str]] = []


def _print_separator(char: str = "=", length: int = 72) -> None:
    print(char * length)


def _record(name: str, passed: bool, detail: str = "") -> None:
    _RESULTS.append((name, passed, detail))
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}")
    if detail:
        for line in detail.splitlines():
            print(f"        {line}")


def _assert(name: str, condition: bool, detail: str = "") -> None:
    if not condition:
        if not detail:
            detail = "Assertion failed."
        _record(name, False, detail)
        raise AssertionError(f"{name}: {detail}")
    _record(name, True, detail)


# ============================================================
# OFFLINE TESTS
# ============================================================


def test_health_returns_ok() -> None:
    from fastapi.testclient import TestClient
    from app.api import app

    client = TestClient(app)
    resp = client.get("/health")
    _assert(
        "api[health]_returns_ok",
        resp.status_code == 200
        and resp.json() == {"status": "ok", "version": "1.0.0"},
        f"status={resp.status_code} body={resp.json()}",
    )


def test_valid_query_accepted() -> None:
    from fastapi.testclient import TestClient
    from app.api import app

    with patch("app.api._get_orchestrator") as mock_get_orch:
        mock_orch = MagicMock()
        mock_orch.handle.return_value = {
            "question": "What is income tax?",
            "domains": ["income_tax"],
            "primary_domain": "income_tax",
            "multi_domain": False,
            "routing": {
                "question": "What is income tax?",
                "domains": ["income_tax"],
                "primary_domain": "income_tax",
                "multi_domain": False,
                "matched_signals": {"income_tax": ["income tax"]},
            },
            "domain_results": [],
            "answer": "Income tax is a tax on income.",
            "sources": [],
            "verification": {
                "passed": True,
                "checks": {
                    "answer_size": {"passed": True, "reason": "ok"},
                    "section_consistency": {"passed": True, "reason": "ok"},
                    "grounding": {"passed": True, "reason": "ok"},
                    "speculation": {"passed": True, "reason": "ok"},
                },
                "failed_checks": [],
                "reason": "All verification checks passed.",
            },
            "grounded": True,
        }
        mock_get_orch.return_value = mock_orch

        client = TestClient(app)
        resp = client.post("/answer", json={"query": "What is income tax?"})
        _assert(
            "api[request]_valid_query_accepted",
            resp.status_code == 200,
            f"status={resp.status_code} body={resp.json()}",
        )


def test_missing_query_rejected() -> None:
    from fastapi.testclient import TestClient
    from app.api import app

    client = TestClient(app)
    resp = client.post("/answer", json={})
    _assert(
        "api[request]_missing_query_rejected",
        resp.status_code == 422,
        f"status={resp.status_code} body={resp.json()}",
    )


def test_empty_query_rejected() -> None:
    from fastapi.testclient import TestClient
    from app.api import app

    client = TestClient(app)
    resp = client.post("/answer", json={"query": ""})
    _assert(
        "api[request]_empty_query_rejected",
        resp.status_code == 400,
        f"status={resp.status_code} body={resp.json()}",
    )


def test_whitespace_query_rejected() -> None:
    from fastapi.testclient import TestClient
    from app.api import app

    client = TestClient(app)
    resp = client.post("/answer", json={"query": "   \t\n  "})
    _assert(
        "api[request]_whitespace_query_rejected",
        resp.status_code == 400,
        f"status={resp.status_code} body={resp.json()}",
    )


def test_oversized_query_rejected() -> None:
    from fastapi.testclient import TestClient
    from app.api import app

    client = TestClient(app)
    large_query = "x" * 1001
    resp = client.post("/answer", json={"query": large_query})
    _assert(
        "api[request]_oversized_query_rejected",
        resp.status_code == 422,
        f"status={resp.status_code} body={resp.json()}",
    )


def test_invalid_schema_rejected() -> None:
    from fastapi.testclient import TestClient
    from app.api import app

    client = TestClient(app)
    resp = client.post("/answer", json={"query": 123})
    _assert(
        "api[request]_invalid_schema_rejected",
        resp.status_code == 422,
        f"status={resp.status_code} body={resp.json()}",
    )


def test_orchestrator_invoked() -> None:
    from fastapi.testclient import TestClient
    from app.api import app

    with patch("app.api._get_orchestrator") as mock_get_orch:
        mock_orch = MagicMock()
        mock_orch.handle.return_value = {
            "question": "What is sales tax?",
            "domains": ["sales_tax"],
            "primary_domain": "sales_tax",
            "multi_domain": False,
            "routing": {"domains": ["sales_tax"]},
            "domain_results": [],
            "answer": "Sales tax is a consumption tax.",
            "sources": [],
            "verification": {
                "passed": True,
                "checks": {
                    "answer_size": {"passed": True, "reason": "ok"},
                    "section_consistency": {"passed": True, "reason": "ok"},
                    "grounding": {"passed": True, "reason": "ok"},
                    "speculation": {"passed": True, "reason": "ok"},
                },
                "failed_checks": [],
                "reason": "All verification checks passed.",
            },
            "grounded": True,
        }
        mock_get_orch.return_value = mock_orch

        client = TestClient(app)
        client.post("/answer", json={"query": "What is sales tax?"})
        _assert(
            "api[answer]_orchestrator_invoked",
            mock_orch.handle.called,
            "AgentOrchestrator.handle() was not called",
        )
        called_args = mock_orch.handle.call_args
        _assert(
            "api[answer]_orchestrator_receives_correct_query",
            called_args[0][0] == "What is sales tax?",
            f"called with args={called_args}",
        )


def test_response_schema_stable() -> None:
    from fastapi.testclient import TestClient
    from app.api import app

    with patch("app.api._get_orchestrator") as mock_get_orch:
        mock_orch = MagicMock()
        mock_orch.handle.return_value = {
            "question": "What is FBR?",
            "domains": ["research"],
            "primary_domain": "research",
            "multi_domain": False,
            "routing": {"domains": ["research"]},
            "domain_results": [],
            "answer": "FBR is Federal Board of Revenue.",
            "sources": [
                {
                    "chunk_id": "abc123",
                    "document_id": "doc1",
                    "source": "fbr_overview.pdf",
                    "source_path": "fbr_overview.pdf",
                    "source_sha256": "sha256",
                    "page": 1,
                    "page_start": 1,
                    "page_end": 1,
                    "section": "Overview",
                    "section_reference": "Overview",
                    "section_number": "1",
                    "law_tag": None,
                    "multi_law_candidate": False,
                    "score": 0.95,
                    "semantic_score": 0.9,
                    "bm25_score": 0.8,
                    "exact_match": True,
                }
            ],
            "verification": {
                "passed": True,
                "checks": {
                    "answer_size": {"passed": True, "reason": "ok"},
                    "section_consistency": {"passed": True, "reason": "ok"},
                    "grounding": {"passed": True, "reason": "ok", "weak_sentences": []},
                    "speculation": {"passed": True, "reason": "ok"},
                },
                "failed_checks": [],
                "reason": "All verification checks passed.",
            },
            "grounded": True,
        }
        mock_get_orch.return_value = mock_orch

        client = TestClient(app)
        resp = client.post("/answer", json={"query": "What is FBR?"})
        data = resp.json()
        required_fields = {
            "question",
            "domains",
            "primary_domain",
            "multi_domain",
            "routing",
            "domain_results",
            "answer",
            "sources",
            "verification",
            "grounded",
        }
        _assert(
            "api[answer]_response_schema_stable",
            set(data.keys()) == required_fields,
            f"keys={set(data.keys())} expected={required_fields}",
        )
        _assert(
            "api[answer]_response_types_correct",
            isinstance(data["domains"], list)
            and isinstance(data["primary_domain"], str)
            and isinstance(data["multi_domain"], bool)
            and isinstance(data["answer"], str)
            and isinstance(data["sources"], list)
            and isinstance(data["grounded"], bool),
            f"type mismatch in response",
        )


def test_safe_refusal_returned_200() -> None:
    from fastapi.testclient import TestClient
    from app.api import app

    with patch("app.api._get_orchestrator") as mock_get_orch:
        mock_orch = MagicMock()
        mock_orch.handle.return_value = {
            "question": "Explain quantum entanglement",
            "domains": ["research"],
            "primary_domain": "research",
            "multi_domain": False,
            "routing": {"domains": ["research"]},
            "domain_results": [],
            "answer": "The provided FBR documents do not contain enough information to answer this.",
            "sources": [],
            "verification": {
                "passed": True,
                "checks": {
                    "answer_size": {"passed": True, "reason": "ok"},
                    "section_consistency": {"passed": True, "reason": "ok"},
                    "grounding": {"passed": True, "reason": "ok"},
                    "speculation": {"passed": True, "reason": "ok"},
                },
                "failed_checks": [],
                "reason": "All verification checks passed.",
            },
            "grounded": True,
        }
        mock_get_orch.return_value = mock_orch

        client = TestClient(app)
        resp = client.post("/answer", json={"query": "Explain quantum entanglement"})
        _assert(
            "api[answer]_safe_refusal_returned_200",
            resp.status_code == 200,
            f"status={resp.status_code}",
        )
        _assert(
            "api[answer]_safe_refusal_answer_phrase",
            "do not contain enough information" in resp.json()["answer"].lower(),
            f"answer={resp.json()['answer']}",
        )


def test_llmerror_maps_to_503() -> None:
    from fastapi.testclient import TestClient
    from app.api import app
    from app.llm import LLMError

    with patch("app.api._get_orchestrator") as mock_get_orch:
        mock_orch = MagicMock()
        mock_orch.handle.side_effect = LLMError("No LLM provider configured")
        mock_get_orch.return_value = mock_orch

        client = TestClient(app)
        resp = client.post("/answer", json={"query": "What is tax?"})
        _assert(
            "api[answer]_llmerror_maps_to_503",
            resp.status_code == 503,
            f"status={resp.status_code} body={resp.json()}",
        )
        _assert(
            "api[answer]_llmerror_no_secrets_in_response",
            "api_key" not in str(resp.json()).lower()
            and "traceback" not in str(resp.json()).lower(),
            f"body={resp.json()}",
        )


def test_unexpected_error_maps_to_500() -> None:
    from fastapi.testclient import TestClient
    from app.api import app

    with patch("app.api._get_orchestrator") as mock_get_orch:
        mock_orch = MagicMock()
        mock_orch.handle.side_effect = RuntimeError("Unexpected internal error")
        mock_get_orch.return_value = mock_orch

        client = TestClient(app)
        resp = client.post("/answer", json={"query": "What is tax?"})
        _assert(
            "api[answer]_unexpected_error_maps_to_500",
            resp.status_code == 500,
            f"status={resp.status_code} body={resp.json()}",
        )
        _assert(
            "api[answer]_internal_error_no_stack_trace",
            "traceback" not in str(resp.json()).lower(),
            f"body={resp.json()}",
        )


def test_multi_domain_detected() -> None:
    from fastapi.testclient import TestClient
    from app.api import app

    with patch("app.api._get_orchestrator") as mock_get_orch:
        mock_orch = MagicMock()
        mock_orch.handle.return_value = {
            "question": "Penalty for not filing income and sales tax?",
            "domains": ["calculation", "income_tax", "sales_tax"],
            "primary_domain": "calculation",
            "multi_domain": True,
            "routing": {
                "domains": ["calculation", "income_tax", "sales_tax"],
                "primary_domain": "calculation",
                "multi_domain": True,
            },
            "domain_results": [],
            "answer": "Calculation agent response...",
            "sources": [],
            "verification": {
                "passed": True,
                "checks": {
                    "answer_size": {"passed": True, "reason": "ok"},
                    "section_consistency": {"passed": True, "reason": "ok"},
                    "grounding": {"passed": True, "reason": "ok"},
                    "speculation": {"passed": True, "reason": "ok"},
                },
                "failed_checks": [],
                "reason": "All verification checks passed.",
            },
            "grounded": True,
        }
        mock_get_orch.return_value = mock_orch

        client = TestClient(app)
        resp = client.post("/answer", json={"query": "Penalty for not filing income and sales tax?"})
        data = resp.json()
        _assert(
            "api[answer]_multi_domain_detected",
            data["multi_domain"] is True
            and "calculation" in data["domains"]
            and "income_tax" in data["domains"]
            and "sales_tax" in data["domains"],
            f"domains={data['domains']} multi_domain={data['multi_domain']}",
        )


def test_primary_domain_present() -> None:
    from fastapi.testclient import TestClient
    from app.api import app

    with patch("app.api._get_orchestrator") as mock_get_orch:
        mock_orch = MagicMock()
        mock_orch.handle.return_value = {
            "question": "What is customs duty?",
            "domains": ["customs"],
            "primary_domain": "customs",
            "multi_domain": False,
            "routing": {"domains": ["customs"], "primary_domain": "customs"},
            "domain_results": [],
            "answer": "Customs duty is...",
            "sources": [],
            "verification": {
                "passed": True,
                "checks": {
                    "answer_size": {"passed": True, "reason": "ok"},
                    "section_consistency": {"passed": True, "reason": "ok"},
                    "grounding": {"passed": True, "reason": "ok"},
                    "speculation": {"passed": True, "reason": "ok"},
                },
                "failed_checks": [],
                "reason": "All verification checks passed.",
            },
            "grounded": True,
        }
        mock_get_orch.return_value = mock_orch

        client = TestClient(app)
        resp = client.post("/answer", json={"query": "What is customs duty?"})
        data = resp.json()
        _assert(
            "api[answer]_primary_domain_present",
            data["primary_domain"] == "customs"
            and isinstance(data["primary_domain"], str)
            and len(data["primary_domain"]) > 0,
            f"primary_domain={data['primary_domain']}",
        )


def test_sources_serialized_correctly() -> None:
    from fastapi.testclient import TestClient
    from app.api import app

    with patch("app.api._get_orchestrator") as mock_get_orch:
        mock_orch = MagicMock()
        mock_orch.handle.return_value = {
            "question": "What is FBR?",
            "domains": ["research"],
            "primary_domain": "research",
            "multi_domain": False,
            "routing": {"domains": ["research"]},
            "domain_results": [],
            "answer": "FBR is...",
            "sources": [
                {
                    "chunk_id": "abc123",
                    "document_id": "doc1",
                    "source": "fbr_overview.pdf",
                    "source_path": "fbr_overview.pdf",
                    "source_sha256": "sha256",
                    "page": 1,
                    "page_start": 1,
                    "page_end": 1,
                    "section": "Overview",
                    "section_reference": "Overview",
                    "section_number": "1",
                    "law_tag": None,
                    "multi_law_candidate": False,
                    "score": 0.95,
                    "semantic_score": 0.9,
                    "bm25_score": 0.8,
                    "exact_match": True,
                }
            ],
            "verification": {
                "passed": True,
                "checks": {
                    "answer_size": {"passed": True, "reason": "ok"},
                    "section_consistency": {"passed": True, "reason": "ok"},
                    "grounding": {"passed": True, "reason": "ok", "weak_sentences": []},
                    "speculation": {"passed": True, "reason": "ok"},
                },
                "failed_checks": [],
                "reason": "All verification checks passed.",
            },
            "grounded": True,
        }
        mock_get_orch.return_value = mock_orch

        client = TestClient(app)
        resp = client.post("/answer", json={"query": "What is FBR?"})
        data = resp.json()
        _assert(
            "api[answer]_sources_serialized_correctly",
            len(data["sources"]) == 1
            and data["sources"][0]["chunk_id"] == "abc123"
            and data["sources"][0]["source"] == "fbr_overview.pdf"
            and data["sources"][0]["score"] == 0.95
            and "semantic_score" in data["sources"][0]
            and "bm25_score" in data["sources"][0],
            f"sources={data['sources']}",
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    _print_separator()
    print("FBR API TESTS")
    _print_separator()

    tests = [
        test_health_returns_ok,
        test_valid_query_accepted,
        test_missing_query_rejected,
        test_empty_query_rejected,
        test_whitespace_query_rejected,
        test_oversized_query_rejected,
        test_invalid_schema_rejected,
        test_orchestrator_invoked,
        test_response_schema_stable,
        test_safe_refusal_returned_200,
        test_llmerror_maps_to_503,
        test_unexpected_error_maps_to_500,
        test_multi_domain_detected,
        test_primary_domain_present,
        test_sources_serialized_correctly,
    ]

    for test_fn in tests:
        try:
            test_fn()
        except AssertionError:
            pass
        except Exception as e:
            _record(test_fn.__name__, False, f"Unexpected error: {type(e).__name__}: {e}")

    _print_separator()
    passed = sum(1 for _, p, _ in _RESULTS if p)
    total = len(_RESULTS)
    print(f"SUMMARY: {passed}/{total} tests passed")
    if passed < total:
        sys.exit(1)