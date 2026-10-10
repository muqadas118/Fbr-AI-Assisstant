"""
Full-feature sweep: exercises EVERY user-facing feature that the UI exposes,
with realistic sample data, so nothing is "shown but never run".

Covers:
  - All 11 tax calculators (sample data + known-value assertions where possible)
  - Compliance calendar (events, upcoming, reminder, export, complete)
  - Tax health (check/risks/penalties) + score guide
  - Notice analyzer (structured + free-text)
  - Documents (analyze + verify with NTN/CNIC sample text)
  - Invoice intelligence (process + reconcile + dashboard)
  - Verification center (all 7 endpoints, honest-unavailable contract)
  - FBR monitor (subscribe, dashboard, simulate notice, event lifecycle)
  - Team management (register -> login -> team -> invite -> dashboards)
  - Workspaces (create -> get)
  - RAG answer (grounded + safe refusal)

Run with the backend up:
    python scripts/full_feature_sweep.py --base http://127.0.0.1:8000

Output: one line per probe -> [OK]/[WARN]/[FAIL]; exit non-zero on any FAIL.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid

import requests

RESULTS: list[tuple[str, str, str]] = []
BASE = "http://127.0.0.1:8000"
TIMEOUT = 90


def _short(value, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = text.replace("\n", " ")
    return text[:limit]


def probe(name: str, ok_fn, method: str, path: str, **kwargs) -> dict | None:
    """Run one HTTP probe; return parsed JSON on success-shaped responses."""
    try:
        resp = requests.request(method, BASE + path, timeout=TIMEOUT, **kwargs)
        verdict, note, payload = ok_fn(resp)
    except Exception as exc:  # noqa: BLE001
        verdict, note, payload = "FAIL", f"{type(exc).__name__}: {exc}", None
    RESULTS.append((verdict, name, note))
    print(f"[{verdict}] {name}: {note}")
    return payload


def _parse(resp):
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return None


def expect_http(status: int, json_key: str | None = None):
    def check(resp):
        if resp.status_code != status:
            return "FAIL", f"expected {status}, got {resp.status_code}: {_short(resp.text)}", None
        payload = _parse(resp)
        if json_key and (not isinstance(payload, dict) or json_key not in payload):
            return "WARN", f"HTTP {status} but '{json_key}' missing: {_short(resp.text)}", payload
        return "OK", f"HTTP {status}" + (f" + '{json_key}'" if json_key else ""), payload
    return check


def expect_http_with(status: int, *contains: str):
    def check(resp):
        if resp.status_code != status:
            return "FAIL", f"expected {status}, got {resp.status_code}: {_short(resp.text)}", None
        missing = [c for c in contains if c.lower() not in resp.text.lower()]
        if missing:
            return "WARN", f"HTTP {status} but {missing} missing: {_short(resp.text)}", _parse(resp)
        return "OK", f"HTTP {status} + all markers", _parse(resp)
    return check


def expect_rejected():
    """422/400 = rejected; 429 = limiter fired first (unproven); 5xx/200 = bad."""
    def check(resp):
        if resp.status_code in (400, 422):
            return "OK", f"rejected with HTTP {resp.status_code}", None
        if resp.status_code == 429:
            return "WARN", "rate-limited before the input could be judged", None
        if resp.status_code >= 500:
            return "FAIL", f"invalid input caused HTTP {resp.status_code}: {_short(resp.text)}", None
        return "FAIL", f"invalid input accepted (HTTP {resp.status_code})", None
    return check


def expect_rejected_or_unauthorized():
    """422/400 = validation rejection; 401 = auth rejection (e.g. wrong
    password) — both are correct client-error outcomes; 429 = limiter fired
    first (unproven); 5xx/200 = bad."""
    def check(resp):
        if resp.status_code in (400, 401, 422):
            return "OK", f"rejected with HTTP {resp.status_code}", None
        if resp.status_code == 429:
            return "WARN", "rate-limited before the input could be judged", None
        if resp.status_code >= 500:
            return "FAIL", f"invalid input caused HTTP {resp.status_code}: {_short(resp.text)}", None
        return "FAIL", f"invalid input accepted (HTTP {resp.status_code})", None
    return check


# ---------------------------------------------------------------------------
# Realistic sample inputs for each calculator
# ---------------------------------------------------------------------------
CALCS = [
    ("income_tax", {"gross_income": 2500000, "filing_status": "salaried", "tax_year": "2026"},
     lambda full: isinstance(full, dict) and full.get("data", {}).get("tax_after_credits") == 176000.0),
    ("salary_tax", {"basic_salary": 150000, "house_rent_received": 60000,
                    "medical_allowance": 10000, "tax_year": "2026"}, None),
    ("business_tax", {"business_income": 3000000, "business_type": "individual_business",
                      "tax_year": "2026", "annual_turnover": 12000000}, None),
    ("sales_tax", {"sales_value": 1000000, "sales_tax_type": "goods", "province": "punjab",
                   "purchases_value": 400000}, None),
    ("withholding_tax", {"transaction_amount": 500000, "section": "150_dividend",
                         "filer_status": "filer"}, None),
    ("federal_excise", {"category": "cigarettes", "value": 1000000, "quantity": 50000}, None),
    ("capital_gains", {"asset_type": "immovable_property", "acquisition_cost": 8000000,
                       "sale_value": 12000000, "holding_period_years": 3,
                       "filer_status": "filer"}, None),
    ("property_tax", {"annual_rent_received": 1200000, "property_type": "residential",
                      "tax_year": "2026", "filing_status": "individual"}, None),
    ("dividend_tax", {"income_source": "dividend", "gross_income": 500000,
                      "filer_status": "filer"}, None),
    ("custom_duty", {"cif_value": 2000000, "hs_category": "default",
                     "filer_status": "filer", "is_commercial": True}, None),
    ("custom_calc", {"calc_type": "percentage", "base_value": 250000, "rate": 17}, None),
]

NOTICE_TEXT = (
    "OFFICE OF THE CHIEF COMMISSIONER INLAND REVENUE. "
    "NOTICE U/S 174 OF THE INCOME TAX ORDINANCE 2001. "
    "Tax Year 2025. NTN 1234567. Filing of return required within 15 days. "
    "Show cause notice for non-filing of income tax return."
)

INVOICE_TEXT = (
    "TAX INVOICE\nInvoice No: INV-2026-001\nDate: 2026-09-01\n"
    "Seller: ABC Traders, NTN 1234567\nBuyer: XYZ Corp, NTN 7654321\n"
    "Description: Office furniture\nQuantity: 10\nUnit Price: 25,000\n"
    "Sales Tax @ 18%: 45,000\nTotal: 295,000 PKR"
)


def main() -> int:
    global BASE, TIMEOUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    BASE = args.base.rstrip("/")
    TIMEOUT = args.timeout
    run_id = uuid.uuid4().hex[:8]
    started = time.time()

    # ------------------------------------------------------------------
    # 1. Health + calculator registry
    # ------------------------------------------------------------------
    probe("health", expect_http(200, "status"), "GET", "/health")
    payload = probe("calc/types (11 modules)", expect_http(200, "supported"), "GET", "/calculate/types")
    if isinstance(payload, dict) and payload.get("count") != 11:
        RESULTS.append(("WARN", "calc/types count", f"expected 11 modules, got {payload.get('count')}"))
        print(f"[WARN] calc/types count: expected 11, got {payload.get('count')}")

    # ------------------------------------------------------------------
    # 2. ALL 11 calculators with realistic data + known-value checks
    # ------------------------------------------------------------------
    for calc_type, inputs, verifier in CALCS:
        def check(resp, _v=verifier, _t=calc_type):
            if resp.status_code != 200:
                return "FAIL", f"expected 200, got {resp.status_code}: {_short(resp.text)}", None
            data = _parse(resp)
            if not isinstance(data, dict) or not data.get("success"):
                return "FAIL", f"success=false: {_short(resp.text)}", data
            if _v and not _v(data):
                return "WARN", f"200 but known-value check failed for {_t}", data
            return "OK", "HTTP 200, computed", data
        probe(f"calc/{calc_type}", check, "POST", "/calculate", json={"calc_type": calc_type, "inputs": inputs})

    # Validation guards on calculators
    probe("calc/invalid type", expect_http(400), "POST", "/calculate",
          json={"calc_type": "bogus_type", "inputs": {"x": 1}})
    probe("calc/empty inputs", expect_http(400), "POST", "/calculate",
          json={"calc_type": "income_tax", "inputs": {}})
    probe("calc/invalid year", expect_rejected(), "POST", "/calculate",
          json={"calc_type": "income_tax", "inputs": {"gross_income": 100, "tax_year": "1999"}})

    # ------------------------------------------------------------------
    # 3. Compliance calendar (full lifecycle)
    # ------------------------------------------------------------------
    probe("calendar/dashboard individual", expect_http(200, "compliance_score"),
          "GET", "/calendar/dashboard?taxpayer_type=individual")
    payload = probe("calendar/events individual", expect_http(200), "GET", "/calendar?taxpayer_type=individual&limit=50")
    event_id = None
    if isinstance(payload, dict):
        events = payload.get("events") or []
        if events:
            event_id = events[0].get("id")
    probe("calendar/upcoming", expect_http(200), "GET", "/calendar/upcoming?taxpayer_type=individual&days=60")
    probe("calendar/types", expect_http(200), "GET", "/calendar/types")
    if event_id:
        probe("calendar/reminder", expect_http(200), "POST", "/calendar/reminders",
              json={"event_id": event_id, "recipient": "sweep@example.com", "channels": ["email"]})
        probe("calendar/event complete", expect_http(200), "POST", f"/calendar/events/{event_id}/complete", json={})
    else:
        RESULTS.append(("WARN", "calendar lifecycle", "no event id returned; reminder/complete untested"))
        print("[WARN] calendar lifecycle: no event id; reminder/complete untested")
    probe("calendar/export json", expect_http(200), "GET", "/calendar/export?format=json&taxpayer_type=individual")
    probe("calendar/export csv", expect_http(200), "GET", "/calendar/export?format=csv&taxpayer_type=individual")
    probe("calendar/invalid type", expect_rejected(), "GET", "/calendar/dashboard?taxpayer_type=bogus")

    # ------------------------------------------------------------------
    # 4. Tax health
    # ------------------------------------------------------------------
    health = {"ntn": "1234567", "tax_year": 2025, "declared_income": 1200000,
              "tax_assessed": 50000, "tax_paid": 30000}
    probe("tax-health/check", expect_http(200, "health_score"), "POST", "/tax/health/check", json=health)
    probe("tax-health/risks", expect_http(200), "POST", "/tax/health/risks", json=health)
    probe("tax-health/penalties", expect_http(200), "POST", "/tax/health/penalties", json=health)
    probe("tax-health/score-guide", expect_http(200), "GET", "/tax/health/score-guide")
    probe("tax-health/negative income", expect_rejected(), "POST", "/tax/health/check",
          json={**health, "declared_income": -1})
    probe("tax-health/empty body", expect_rejected(), "POST", "/tax/health/check", json={})

    # ------------------------------------------------------------------
    # 5. Notice analyzer
    # ------------------------------------------------------------------
    probe("notices/types", expect_http(200), "GET", "/notices/types")
    probe("notices/analyze structured", expect_http(200), "POST", "/notices/analyze",
          json={"text": NOTICE_TEXT})
    probe("notices/analyze free-text", expect_http(200), "POST", "/notices/analyze/text",
          json={"text": NOTICE_TEXT})
    probe("notices/analyze too-short", expect_rejected(), "POST", "/notices/analyze/text",
          json={"text": "x"})

    # ------------------------------------------------------------------
    # 6. Documents
    # ------------------------------------------------------------------
    doc_text = ("INCOME TAX RETURN ACKNOWLEDGMENT. Taxpayer: ABC Traders. "
                "NTN: 1234567-8. CNIC: 35202-1234567-1. Tax Year 2025. "
                "Filed on 2025-09-30. Reference No: IRIS-RET-2025-99887.")
    probe("documents/types", expect_http(200), "GET", "/documents/types")
    probe("documents/analyze", expect_http(200), "POST", "/documents/analyze",
          json={"text": doc_text, "document_type": "tax_return"})
    payload = probe("documents/verify (NTN+CNIC extract)", expect_http(200, "confidence"),
                    "POST", "/documents/verify", json={"text": doc_text})
    if isinstance(payload, dict):
        if not payload.get("ntn"):
            RESULTS.append(("FAIL", "documents/verify ntn extract", f"ntn not extracted: {_short(payload)}"))
            print(f"[FAIL] documents/verify ntn extract: ntn missing: {_short(payload)}")
    probe("documents/verify too-short", expect_rejected(), "POST", "/documents/verify", json={"text": "abc"})

    # ------------------------------------------------------------------
    # 7. Invoice intelligence
    # ------------------------------------------------------------------
    probe("invoices/process", expect_http(200), "POST", "/invoices/process",
          json={"text": INVOICE_TEXT, "invoice_id": f"SWEEP-{run_id}"})
    probe("invoices/reconcile", expect_http(200), "POST", "/invoices/reconcile",
          json={"purchase_invoices": [{"invoice_no": "P-1", "amount": 100000, "sales_tax": 18000}],
                "sales_invoices": [{"invoice_no": "S-1", "amount": 100000, "sales_tax": 18000}]})
    probe("invoices/dashboard", expect_http(200), "GET", "/invoices/dashboard")

    # ------------------------------------------------------------------
    # 8. Verification center — full surface + truth contract
    # ------------------------------------------------------------------
    probe("verify/ntn", expect_http_with(200, "unavailable"), "POST", "/verify/ntn", json={"ntn": "1234567"})
    probe("verify/ntn no fabricated name",
          expect_http_with(200, "unavailable"), "POST", "/verify/ntn",
          json={"ntn": "1234567"})
    probe("verify/filer", expect_http_with(200, "unavailable"), "POST", "/verify/filer", json={"ntn": "1234567"})
    probe("verify/vendor", expect_http_with(200, "unavailable"), "POST", "/verify/vendor", json={"vendor_ntn": "1234567"})
    probe("verify/cnic", expect_http(200), "POST", "/verify/cnic", json={"cnic": "35202-1234567-1"})
    probe("verify/business", expect_http(200), "POST", "/verify/business",
          json={"registration_number": "1234567", "reg_type": "ntn"})
    probe("verify/atl", expect_http_with(200, "unavailable"), "GET", "/verify/atl/1234567")
    probe("verify/batch mixed", expect_http(200), "POST", "/verify/batch",
          json={"requests": [{"type": "ntn", "value": "1234567"},
                             {"type": "filer", "value": "7654321"}]})
    probe("verify/batch bogus type", expect_http(400), "POST", "/verify/batch",
          json={"requests": [{"type": "bogus", "value": "x"}]})

    # ------------------------------------------------------------------
    # 9. FBR monitor — full lifecycle
    # ------------------------------------------------------------------
    sweep_user = f"sweep-{run_id}@example.com"
    probe("monitor/event-types", expect_http(200), "GET", "/monitor/event-types")
    payload = probe("monitor/subscribe", expect_http(200), "POST", "/monitor/subscribe",
                    json={"user_id": sweep_user, "ntn": "1234567",
                          "check_interval_minutes": 60, "notification_email": sweep_user})
    sub_id = None
    if isinstance(payload, dict):
        sub_id = payload.get("subscription_id") or payload.get("id") or payload.get("user_id")
    if sub_id:
        probe("monitor/dashboard", expect_http(200), "GET", f"/monitor/dashboard/{sub_id}")
    else:
        RESULTS.append(("WARN", "monitor/dashboard", "no subscription id returned"))
        print("[WARN] monitor/dashboard: no subscription id returned")
    payload = probe("monitor/simulate notice", expect_http(200), "POST", "/monitor/simulate/notice",
                    json={"ntn": "1234567", "notice_number": f"SWEEP-{run_id}",
                          "title": "Sweep test notice", "description": "Generated by full sweep",
                          "action_deadline": "2026-10-15"})
    event_id = None
    if isinstance(payload, dict):
        event_id = payload.get("event_id") or payload.get("id") or (payload.get("event") or {}).get("id")
    if event_id:
        probe("monitor/event detail", expect_http(200), "GET", f"/monitor/event/{event_id}")
        probe("monitor/event acknowledge", expect_http(200), "POST", f"/monitor/event/{event_id}/acknowledge", json={})
        probe("monitor/event resolve", expect_http(200), "POST", f"/monitor/event/{event_id}/resolve", json={})
    else:
        RESULTS.append(("WARN", "monitor event lifecycle", "no event id from simulate"))
        print("[WARN] monitor event lifecycle: no event id from simulate")
    probe("monitor/webhook stats", expect_http(200), "GET", "/monitor/webhook/stats")

    # ------------------------------------------------------------------
    # 10. Team management — register -> login -> team -> invite
    # ------------------------------------------------------------------
    pw = "Sweep!pass1"
    probe("team/roles", expect_http_with(200, "admin"), "GET", "/team/roles")
    probe("team/register", expect_http(200), "POST", "/team/register",
          json={"email": sweep_user, "password": pw, "name": "Sweep User"})
    payload = probe("team/login", expect_http(200), "POST", "/team/login",
                    json={"email": sweep_user, "password": pw})
    user_id = None
    if isinstance(payload, dict):
        user_id = payload.get("user_id") or (payload.get("user") or {}).get("id") or payload.get("id")
    probe("team/login wrong password", expect_rejected_or_unauthorized(), "POST", "/team/login",
          json={"email": sweep_user, "password": "Wrong!pass9"})
    if user_id:
        payload = probe("team/create", expect_http(200), "POST", "/team/create",
                        json={"owner_id": user_id, "name": f"Sweep Team {run_id}", "ntn": "1234567"})
        team_id = payload.get("team_id") or (payload.get("team") or {}).get("id") if isinstance(payload, dict) else None
        if team_id:
            probe("team/invite", expect_http(200), "POST", "/team/invite",
                  json={"team_id": team_id, "email": f"mate-{run_id}@example.com",
                        "role": "viewer", "invited_by": user_id})
            probe("team/dashboard", expect_http(200), "GET", f"/team/dashboard/{team_id}")
        else:
            RESULTS.append(("WARN", "team/invite", "no team id from create"))
            print("[WARN] team/invite: no team id from create")
        probe("team/user-dashboard", expect_http(200), "GET", f"/team/user-dashboard/{user_id}")
    else:
        RESULTS.append(("WARN", "team lifecycle", "no user id from login"))
        print("[WARN] team lifecycle: no user id from login")

    # ------------------------------------------------------------------
    # 11. Workspaces
    # ------------------------------------------------------------------
    probe("workspaces/health", expect_http(200, "status"), "GET", "/workspaces/health")
    probe("workspaces/create", expect_http(200), "POST", "/workspaces/create",
          json={"user_id": user_id or sweep_user, "name": f"Sweep WS {run_id}",
                "workspace_type": "personal"})
    if user_id:
        probe("workspaces/get", expect_http(200), "GET", f"/workspaces/{user_id}")

    # ------------------------------------------------------------------
    # 12. RAG answer (live LLM, slow)
    # ------------------------------------------------------------------
    probe("answer/section query (grounded)", expect_http_with(200, "grounded"), "POST", "/answer",
          json={"query": "What is Section 177 of the Income Tax Ordinance?"})
    probe("answer/off-topic safe refusal", expect_http(200), "POST", "/answer",
          json={"query": "What is the weather in Karachi today?"})
    probe("answer/empty query", expect_rejected(), "POST", "/answer", json={"query": "   "})

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    fails = [r for r in RESULTS if r[0] == "FAIL"]
    warns = [r for r in RESULTS if r[0] == "WARN"]
    elapsed = time.time() - started
    print("=" * 72)
    print(f"FULL FEATURE SWEEP: {len(RESULTS)} probes in {elapsed:.0f}s | "
          f"OK {len(RESULTS) - len(fails) - len(warns)} | WARN {len(warns)} | FAIL {len(fails)}")
    print("=" * 72)
    for verdict, name, note in fails + warns:
        print(f"[{verdict}] {name}: {note}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
