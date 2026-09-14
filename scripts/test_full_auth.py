"""
FULL-AUTH regression tests (2026-09-13).

Verifies per-route Depends(require_user) across the 9 feature routers:
  - unauthenticated sensitive requests -> 401/403 when FBR_AUTH_REQUIRED=true
  - intentionally-public routes -> 200 without any token
  - mocked require_user -> authed routes return 200
  - FBR_AUTH_REQUIRED=false bypass still works (require_user handles it)

Uses the [PASS]/[FAIL] convention so scripts/final_regression.py can
aggregate results with the rest of the suite.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


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


def _get_app():
    from app.api import app

    return app


def _unauth_client():
    from fastapi.testclient import TestClient
    from app.supabase_auth import require_user

    app = _get_app()
    app.dependency_overrides.pop(require_user, None)
    return TestClient(app)


def _authed_client():
    from fastapi.testclient import TestClient
    from app.supabase_auth import require_user

    async def _mock_user():
        return {
            "id": "test-user",
            "email": "test@example.com",
            "full_name": "Test User",
            "role": "authenticated",
        }

    app = _get_app()
    app.dependency_overrides[require_user] = _mock_user
    return TestClient(app)


def test_unauth_calendar_reminders_rejected() -> None:
    os.environ["FBR_AUTH_REQUIRED"] = "true"
    client = _unauth_client()
    resp = client.post("/calendar/reminders", json={"event_id": "evt-1"})
    _assert(
        "fullauth[unauth]_calendar_reminders_401",
        resp.status_code in (401, 403),
        f"status={resp.status_code} body={resp.text[:300]}",
    )


def test_unauth_verify_ntn_rejected() -> None:
    os.environ["FBR_AUTH_REQUIRED"] = "true"
    client = _unauth_client()
    resp = client.post("/verify/ntn", json={"ntn": "1234567"})
    _assert(
        "fullauth[unauth]_verify_ntn_401",
        resp.status_code in (401, 403),
        f"status={resp.status_code} body={resp.text[:300]}",
    )


def test_public_health() -> None:
    client = _unauth_client()
    resp = client.get("/health")
    _assert(
        "fullauth[public]_health_200",
        resp.status_code == 200 and resp.json().get("status") == "ok",
        f"status={resp.status_code} body={resp.text[:300]}",
    )


def test_public_auth_config() -> None:
    client = _unauth_client()
    resp = client.get("/api/auth/config")
    _assert(
        "fullauth[public]_auth_config_200",
        resp.status_code == 200 and "configured" in resp.json(),
        f"status={resp.status_code} body={resp.text[:300]}",
    )


def test_public_auth_status() -> None:
    client = _unauth_client()
    resp = client.get("/api/auth/status")
    _assert(
        "fullauth[public]_auth_status_200",
        resp.status_code == 200 and resp.json().get("authenticated") is False,
        f"status={resp.status_code} body={resp.text[:300]}",
    )


def test_public_team_register_and_login() -> None:
    client = _unauth_client()
    email = f"fullauth-{uuid.uuid4().hex[:8]}@example.com"
    reg = client.post(
        "/team/register",
        json={"email": email, "password": "password123", "name": "Full Auth"},
    )
    _assert(
        "fullauth[public]_team_register_200",
        reg.status_code == 200,
        f"status={reg.status_code} body={reg.text[:300]}",
    )
    login = client.post(
        "/team/login", json={"email": email, "password": "password123"}
    )
    _assert(
        "fullauth[public]_team_login_200",
        login.status_code == 200,
        f"status={login.status_code} body={login.text[:300]}",
    )


def test_public_workspaces_health() -> None:
    client = _unauth_client()
    resp = client.get("/workspaces/health")
    _assert(
        "fullauth[public]_workspaces_health_200",
        resp.status_code == 200 and resp.json().get("status") == "ok",
        f"status={resp.status_code} body={resp.text[:300]}",
    )


def test_public_calendar_types() -> None:
    client = _unauth_client()
    resp = client.get("/calendar/types")
    _assert(
        "fullauth[public]_calendar_types_200",
        resp.status_code == 200 and "event_types" in resp.json(),
        f"status={resp.status_code} body={resp.text[:300]}",
    )


def test_public_metadata_routes() -> None:
    client = _unauth_client()
    for path, key in [
        ("/notices/types", "notice_types"),
        ("/documents/types", "document_types"),
        ("/monitor/event-types", "event_types"),
        ("/tax/health/score-guide", "score_ranges"),
        ("/team/roles", "roles"),
    ]:
        resp = client.get(path)
        name = "fullauth[public]" + path.replace("/", "_") + "_200"
        _assert(
            name,
            resp.status_code == 200 and key in resp.json(),
            f"path={path} status={resp.status_code} body={resp.text[:300]}",
        )


def test_authed_penalties() -> None:
    client = _authed_client()
    resp = client.post("/tax/health/penalties", json={})
    _assert(
        "fullauth[authed]_penalties_200",
        resp.status_code == 200,
        f"status={resp.status_code} body={resp.text[:300]}",
    )


def test_authed_calendar_reminders() -> None:
    client = _authed_client()
    mock_api = MagicMock()
    mock_api.schedule_reminders.return_value = {
        "event_id": "evt-1",
        "reminders_scheduled": 1,
        "reminder_ids": ["r-1"],
    }
    with patch(
        "app.routers.calendar.get_compliance_calendar", return_value=mock_api
    ):
        resp = client.post("/calendar/reminders", json={"event_id": "evt-1"})
    _assert(
        "fullauth[authed]_calendar_reminders_200",
        resp.status_code == 200 and resp.json().get("event_id") == "evt-1",
        f"status={resp.status_code} body={resp.text[:300]}",
    )


def test_bypass_disabled_allows_unauth() -> None:
    os.environ["FBR_AUTH_REQUIRED"] = "false"
    try:
        client = _unauth_client()
        resp = client.post("/tax/health/penalties", json={})
        _assert(
            "fullauth[bypass]_disabled_allows_unauth",
            resp.status_code == 200,
            f"status={resp.status_code} body={resp.text[:300]}",
        )
    finally:
        os.environ["FBR_AUTH_REQUIRED"] = "true"


if __name__ == "__main__":
    _print_separator()
    print("FULL-AUTH TESTS")
    _print_separator()

    tests = [
        test_unauth_calendar_reminders_rejected,
        test_unauth_verify_ntn_rejected,
        test_public_health,
        test_public_auth_config,
        test_public_auth_status,
        test_public_team_register_and_login,
        test_public_workspaces_health,
        test_public_calendar_types,
        test_public_metadata_routes,
        test_authed_penalties,
        test_authed_calendar_reminders,
        test_bypass_disabled_allows_unauth,
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
