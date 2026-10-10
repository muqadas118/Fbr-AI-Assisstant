"""
Feature sweep: exercises every API endpoint group with sample data AND
invalid inputs, so behavior is proven against the live surface instead
of assumed. Run with the backend up:

    python scripts/feature_sweep.py --base http://127.0.0.1:8000

Output: one line per probe -> [OK] / [WARN] / [FAIL] with a short note.
Exit code is non-zero when any FAIL exists.
"""

from __future__ import annotations

import argparse
import json
import sys

import requests

RESULTS: list[tuple[str, str, str]] = []


def _short(value, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = text.replace("\n", " ")
    return text[:limit]


def probe(name: str, ok_fn, method: str, path: str, **kwargs) -> None:
    """Run one HTTP probe and classify the result with ok_fn(resp)."""
    try:
        resp = requests.request(method, BASE + path, timeout=TIMEOUT, **kwargs)
        verdict, note = ok_fn(resp)
    except Exception as exc:  # noqa: BLE001
        verdict, note = "FAIL", f"{type(exc).__name__}: {exc}"
    RESULTS.append((verdict, name, note))
    print(f"[{verdict}] {name}: {note}")


def expect_http(status: int):
    def check(resp) -> tuple[str, str]:
        if resp.status_code == status:
            return "OK", f"HTTP {status}"
        return "FAIL", f"expected {status}, got {resp.status_code}: {_short(resp.text)}"
    return check


def expect_http_with(status: int, contains: str):
    def check(resp) -> tuple[str, str]:
        if resp.status_code != status:
            return "FAIL", f"expected {status}, got {resp.status_code}: {_short(resp.text)}"
        if contains.lower() in resp.text.lower():
            return "OK", f"HTTP {status} + '{contains}'"
        return "WARN", f"HTTP {status} but '{contains}' missing: {_short(resp.text)}"
    return check


def expect_2xx_with(contains: str, not_contains: str | None = None):
    def check(resp) -> tuple[str, str]:
        if not (200 <= resp.status_code < 300):
            return "FAIL", f"expected 2xx, got {resp.status_code}: {_short(resp.text)}"
        if contains.lower() not in resp.text.lower():
            return "WARN", f"2xx but '{contains}' missing: {_short(resp.text)}"
        if not_contains and not_contains.lower() in resp.text.lower():
            return "WARN", f"'{not_contains}' unexpectedly present: {_short(resp.text)}"
        return "OK", f"HTTP {resp.status_code} + '{contains}'"
    return check


def expect_rejected(*snippets: str):
    """Validation rejection: FastAPI 422 or a hand-rolled 400 — both fine.
    A 200 that actually processed the bad input is a FAIL. A 429 rate
    limit is treated as UNPROVEN (the limiter fired first), not a pass."""
    def check(resp) -> tuple[str, str]:
        if resp.status_code in (400, 422):
            return "OK", f"rejected with HTTP {resp.status_code}"
        if resp.status_code == 429:
            return "WARN", "rate-limited before the input could be judged"
        if resp.status_code >= 500:
            return "FAIL", f"invalid input caused HTTP {resp.status_code}: {_short(resp.text)}"
        return "FAIL", f"invalid input accepted (HTTP {resp.status_code}): {_short(resp.text)}"
    return check


def expect_ok_or_rejected(*snippets: str):
    """Soft behavior: 200 (processed with marker) or 400/422 (rejected)."""
    def check(resp) -> tuple[str, str]:
        if resp.status_code in (400, 422):
            return "OK", f"rejected with HTTP {resp.status_code}"
        if resp.status_code == 200 and any(s.lower() in resp.text.lower() for s in snippets):
            return "OK", "processed with marker"
        if resp.status_code >= 500:
            return "FAIL", f"HTTP {resp.status_code}: {_short(resp.text)}"
        return "WARN", f"HTTP {resp.status_code} without marker: {_short(resp.text)}"
    return check


def expect_any_2xx_or_400_with(*snippets: str):
    """Accept 200 (processed) or 400 (rejected) as long as a marker appears."""
    def check(resp) -> tuple[str, str]:
        if resp.status_code not in (200, 400):
            return "FAIL", f"expected 200/400, got {resp.status_code}: {_short(resp.text)}"
        body = resp.text.lower()
        if any(s.lower() in body for s in snippets):
            return "OK", f"HTTP {resp.status_code} with marker"
        return "WARN", f"HTTP {resp.status_code} without marker: {_short(resp.text)}"
    return check


def main() -> int:
    global BASE, TIMEOUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    BASE = args.base.rstrip("/")
    TIMEOUT = args.timeout

    # ------------------------------------------------------------------
    # Health & calculators
    # ------------------------------------------------------------------
    probe("health", expect_http_with(200, "ok"), "GET", "/health")
    probe("calc/types", expect_http_with(200, "supported"), "GET", "/calculate/types")

    probe("calc/income_tax valid TY2026",
          expect_http_with(200, "176000"), "POST", "/calculate",
          json={"calc_type": "income_tax",
                "inputs": {"gross_income": 2500000, "filing_status": "salaried",
                           "tax_year": "2026"}})
    probe("calc/invalid type",
          expect_http(400), "POST", "/calculate",
          json={"calc_type": "bogus_type", "inputs": {}})
    probe("calc/invalid year",
          expect_http(400), "POST", "/calculate",
          json={"calc_type": "income_tax",
                "inputs": {"gross_income": 100, "tax_year": "1999"}})
    probe("calc/negative income",
          expect_any_2xx_or_400_with("error", "validation", "invalid", "gross"),
          "POST", "/calculate",
          json={"calc_type": "income_tax",
                "inputs": {"gross_income": -5000, "filing_status": "salaried"}})
    probe("calc/empty body",
          expect_ok_or_rejected("error", "validation"), "POST", "/calculate",
          json={})
    probe("calc/sales_tax sample",
          expect_http(200), "POST", "/calculate",
          json={"calc_type": "sales_tax",
                "inputs": {"sales_value": 1000000, "sales_tax_type": "goods",
                           "province": "punjab"}})
    probe("calc/withholding sample",
          expect_http(200), "POST", "/calculate",
          json={"calc_type": "withholding_tax",
                "inputs": {"transaction_amount": 500000, "wht_rate": 4}})

    # ------------------------------------------------------------------
    # Calendar
    # ------------------------------------------------------------------
    probe("calendar/dashboard individual",
          expect_http_with(200, "compliance_score"), "GET",
          "/calendar/dashboard?taxpayer_type=individual")
    probe("calendar/dashboard business",
          expect_http_with(200, "compliance_score"), "GET",
          "/calendar/dashboard?taxpayer_type=business")
    probe("calendar/upcoming",
          expect_http(200), "GET", "/calendar/upcoming?taxpayer_type=individual&days=30")
    probe("calendar/invalid taxpayer_type",
          expect_rejected(),
          "GET", "/calendar/dashboard?taxpayer_type=bogus")
    probe("calendar/types",
          expect_http(200), "GET", "/calendar/types")

    # ------------------------------------------------------------------
    # Tax health
    # ------------------------------------------------------------------
    health_payload = {"ntn": "1234567", "tax_year": 2025,
                      "declared_income": 1200000, "tax_assessed": 50000,
                      "tax_paid": 30000}
    probe("tax-health/check sample",
          expect_http_with(200, "health_score"), "POST", "/tax/health/check",
          json=health_payload)
    probe("tax-health/risks",
          expect_http(200), "POST", "/tax/health/risks", json=health_payload)
    probe("tax-health/penalties",
          expect_http(200), "POST", "/tax/health/penalties", json=health_payload)
    probe("tax-health/negative income",
          expect_rejected(),
          "POST", "/tax/health/check", json={**health_payload, "declared_income": -1})
    probe("tax-health/empty body",
          expect_rejected(), "POST",
          "/tax/health/check", json={})

    # ------------------------------------------------------------------
    # Notices / documents / invoices
    # ------------------------------------------------------------------
    probe("notices/types",
          expect_http(200), "GET", "/notices/types")
    probe("notices/analyze-text invalid",
          expect_rejected(),
          "POST", "/notices/analyze/text", json={"text": "x"})
    probe("notices/analyze-text sample",
          expect_http(200), "POST", "/notices/analyze/text",
          json={"text": "OFFICE OF THE CHIEF COMMISSIONER INLAND REVENUE. "
                        "NOTICE U/S 174 OF THE INCOME TAX ORDINANCE 2001. "
                        "Tax Year 2025. NTN 1234567. Filing of return required."})
    probe("documents/types",
          expect_http(200), "GET", "/documents/types")
    probe("documents/verify invalid text",
          expect_rejected(),
          "POST", "/documents/verify", json={"text": "abc"})
    probe("invoices/dashboard",
          expect_http(200), "GET", "/invoices/dashboard")

    # ------------------------------------------------------------------
    # Verification Center — truth contract
    # ------------------------------------------------------------------
    probe("verify/ntn honest-unavailable",
          expect_http_with(200, "unavailable"), "POST", "/verify/ntn",
          json={"ntn": "1234567"})
    probe("verify/ntn no fabricated name",
          expect_2xx_with("unavailable", "Premier Trading"), "POST", "/verify/ntn",
          json={"ntn": "1234567"})
    probe("verify/filer unavailable",
          expect_2xx_with("unavailable"), "POST", "/verify/filer",
          json={"ntn": "1234567"})
    probe("verify/vendor unavailable",
          expect_2xx_with("unavailable"), "POST", "/verify/vendor",
          json={"vendor_ntn": "1234567"})
    probe("verify/cnic invalid format",
          expect_any_2xx_or_400_with("unavailable", "invalid", "error"),
          "POST", "/verify/cnic", json={"cnic": "123"})
    probe("verify/atl unavailable",
          expect_http_with(200, "unavailable"), "GET", "/verify/atl/1234567")
    probe("verify/batch mixed",
          expect_http(200), "POST", "/verify/batch",
          json={"requests": [
              {"type": "ntn", "value": "1234567"},
              {"type": "filer", "value": "7654321"},
          ]})
    probe("verify/batch bogus type",
          expect_any_2xx_or_400_with("error", "validation", "unknown", "unsupported",
                                     "expected one of"),
          "POST", "/verify/batch",
          json={"requests": [{"type": "bogus", "value": "x"}]})

    # ------------------------------------------------------------------
    # Monitor / team / workspaces
    # ------------------------------------------------------------------
    probe("monitor/event-types",
          expect_http(200), "GET", "/monitor/event-types")
    probe("team/roles",
          expect_http_with(200, "admin"), "GET", "/team/roles")
    probe("team/register+login sample",
          expect_ok_or_rejected("token", "already", "exists", "user_id", "error"),
          "POST", "/team/register",
          json={"email": "sweep-user@example.com", "password": "Sweep!pass1",
                "name": "Sweep User"})
    probe("workspaces/health",
          expect_http_with(200, "ok"), "GET", "/workspaces/health")

    # ------------------------------------------------------------------
    # RAG answer (live LLM, slow) — valid + invalid
    # ------------------------------------------------------------------
    probe("answer/section query",
          expect_2xx_with("grounded"), "POST", "/answer",
          json={"query": "What is Section 177 of the Income Tax Ordinance?"})
    probe("answer/safe-refusal off-topic",
          expect_2xx_with("answer"), "POST", "/answer",
          json={"query": "What is the weather in Karachi today?"})
    probe("answer/empty query",
          expect_rejected(), "POST", "/answer",
          json={"query": "   "})
    probe("answer/oversized query",
          expect_rejected(), "POST", "/answer",
          json={"query": "tax " * 300})

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    fails = [r for r in RESULTS if r[0] == "FAIL"]
    warns = [r for r in RESULTS if r[0] == "WARN"]
    print("=" * 72)
    print(f"FEATURE SWEEP SUMMARY: {len(RESULTS)} probes | "
          f"OK {len(RESULTS) - len(fails) - len(warns)} | "
          f"WARN {len(warns)} | FAIL {len(fails)}")
    print("=" * 72)
    for verdict, name, note in fails + warns:
        print(f"[{verdict}] {name}: {note}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
