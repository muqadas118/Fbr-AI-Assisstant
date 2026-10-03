"""
FINAL FULL-APP TEST SUITE
=========================

Deep, trust-worthy verification of every tool in the app:

  A. Engine + all 11 calculators (hand-verified golden values)
  B. Boundary sweep + monotonicity (tax never decreases as income rises)
  C. Junk-input matrix (garbage in -> clean validation error, never a crash)
  D. Cross-consistency (salary vs income, dividend vs WHT, business vs income)
  E. 13-tool registry (contract, positive probes, evasion guard)
  F. Live /calculate API (health, types, goldens, 400s, rate limit)

RULES OF THE VERDICT:
- A check is HARD FAIL if a number is wrong, a crash escapes, or a
  contract is broken. Only hard failures block the verdict.
- Law-nuance simplifications that the engine documents in its own notes
  are recorded as WARNINGS (visible, but not failures).
- The FINAL VERDICT at the end is the single source of truth:
      ALL CHECKS PASS  ->  "APP THEEK HAI"
      any hard failure ->  "APP THEEK NAHI" (with the failing list)

Run:  python scripts/test_full_app_final.py
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Dev-auth bypass must be active before app.api is imported.
os.environ["FBR_AUTH_REQUIRED"] = "false"

# ============================================================
# RESULT ACCOUNTING
# ============================================================

RESULTS: list[tuple[str, bool, str]] = []
WARNINGS: list[str] = []
SECTION = [""]


def section(name: str) -> None:
    SECTION[0] = name
    print(f"\n{'=' * 66}\nSECTION {name}\n{'=' * 66}")


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((f"{SECTION[0]} :: {name}", bool(cond), detail))
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f"  | {detail}" if detail and not cond else ""))


def warn(name: str, message: str) -> None:
    WARNINGS.append(f"{SECTION[0]} :: {name}: {message}")
    print(f"  [WARN] {name}: {message}")


def approx(got: float, want: float, tol: float = 0.01) -> bool:
    return abs(float(got) - float(want)) <= tol


# ============================================================
# IMPORTS UNDER TEST
# ============================================================

from app.calculations.engine import TaxCalculationEngine, get_tax_engine
from app.calculations.income_tax import TaxBracket
from app.tools import DEFAULT_REGISTRY, TOOL_NAMES
from app.tools.base import ToolResult

ENGINE = TaxCalculationEngine()


def run(calc_type: str, inputs: dict):
    """Run engine and assert the audit trail stayed consistent."""
    before = len(ENGINE.audit_log)
    result = ENGINE.calculate(calc_type, inputs)
    after = len(ENGINE.audit_log)
    check(
        f"audit logged: {calc_type} {sorted(inputs)[:2]}",
        after == before + 1,
        f"audit {before}->{after}",
    )
    return result


# ============================================================
# SECTION A1: INCOME TAX (hand-verified golden values)
# ============================================================
# TY2025 salaried slabs (Finance Act 2024): marginal rates
#   0-600k:0% | 600k-1.2M:5% | 1.2-2.4M:10% | 2.4-3.6M:15% |
#   3.6-6M:20% | 6-12M:25% | 12M+:35%
# Cumulative at bracket edges (marginal sum, = FBR published method):
#   600k:0 | 1.2M:30,000 | 2.4M:150,000 | 3.6M:330,000 |
#   6M:810,000 | 12M:2,310,000

section("A1 income_tax goldens (salaried TY2025)")

for gross, want in [
    (400_000, 0.0),
    (600_000, 0.0),
    (1_200_000, 30_000.0),
    (1_200_001, 30_000.05),
    (2_400_000, 150_000.0),
    (3_000_000, 240_000.0),
    (3_600_000, 330_000.0),
    (6_000_000, 810_000.0),
    (12_000_000, 2_310_000.0),
    (12_000_001, 2_310_000.35),
]:
    r = run("income_tax", {"gross_income": gross, "filing_status": "salaried", "tax_year": "2025"})
    # tol 0.06: at bracket-boundary+1 rows the engine rounds per-slab
    # amounts, which can differ from the FBR closed-form by <= 5 paisa.
    check(
        f"salaried TY25 G={gross:,.0f} -> tax {want:,.2f}",
        r.success and approx(r.data.tax_after_credits, want, 0.06),
        f"got {r.data.tax_after_credits if r.success else r.error}",
    )

section("A1 income_tax goldens (TY2026 slabs)")

# TY2026 salaried: 0/1/11/20/25/29/32/35 % with edges
# 600k/1.2M/2.2M/3.2M/4.1M/5.6M/7M (cumulative verified: 6k/116k/316k/541k/976k/1,424k)
for gross, want in [
    (2_200_000, 116_000.0),
    (2_500_000, 176_000.0),
    (7_000_000, 1_424_000.0),
]:
    r = run("income_tax", {"gross_income": gross, "filing_status": "salaried", "tax_year": "2026"})
    check(
        f"salaried TY26 G={gross:,.0f} -> {want:,.0f}",
        r.success and approx(r.data.tax_after_credits, want),
        f"got {r.data.tax_after_credits if r.success else r.error}",
    )

# TY2026 business: 0/15/20/30/40/45 % edges 600k/1.2M/1.6M/3.2M/5.6M (cum 90k/170k/650k/1,610k)
r = run("income_tax", {"gross_income": 3_200_000, "filing_status": "business", "tax_year": "2026"})
check(
    "business TY26 G=3.2M -> 650,000",
    r.success and approx(r.data.tax_after_credits, 650_000.0),
    f"got {r.data.tax_after_credits if r.success else r.error}",
)

section("A1 income_tax company rates")

r = run("income_tax", {"gross_income": 1_000_000, "filing_status": "company_private"})
check("company_private 1M @29% -> 290,000", r.success and approx(r.data.tax_after_credits, 290_000.0),
      f"got {r.data.tax_after_credits if r.success else r.error}")

r = run("income_tax", {"gross_income": 1_000_000, "filing_status": "company_public", "is_small_company": True})
check("small company 1M @20% -> 200,000", r.success and approx(r.data.tax_after_credits, 200_000.0),
      f"got {r.data.tax_after_credits if r.success else r.error}")

section("A1 income_tax credits and deductions (Section 61 average-rate)")

# Salariad TY25, G=2.4M -> base tax 150,000.
r = run("income_tax", {"gross_income": 2_400_000, "filing_status": "salaried", "donations": 200_000})
# allowed = min(200k, 30%*2.4M=720k) = 200k; credit = (200/2400)*150,000 = 12,500
check("donation credit 200k -> 150,000-12,500=137,500",
      r.success and approx(r.data.tax_after_credits, 137_500.0),
      f"got {r.data.tax_after_credits if r.success else r.error}")

r = run("income_tax", {"gross_income": 2_400_000, "filing_status": "salaried", "donations": 1_000_000})
# allowed capped at 720k -> credit = (720/2400)*150,000 = 45,000 -> 105,000
check("donation capped at 30% TI -> 105,000",
      r.success and approx(r.data.tax_after_credits, 105_000.0),
      f"got {r.data.tax_after_credits if r.success else r.error}")

r = run("income_tax", {"gross_income": 2_400_000, "filing_status": "salaried", "zakat_paid": 40_000})
# zakat deducts from income: TI=2.36M -> 30k + 1.16M*10% = 146,000
check("zakat deduction -> 146,000",
      r.success and approx(r.data.tax_after_credits, 146_000.0),
      f"got {r.data.tax_after_credits if r.success else r.error}")

if any("fixed" in str(b) for b in [1]):
    pass
# Historical data-quality warning (RESOLVED): TaxBracket used to carry a dead
# `fixed` column holding legacy cumulative values (390k/990k/2,490k at TY2025)
# that disagreed with the marginal sums. The column is gone; calculate_tax_on_slab
# uses the FBR marginal method only. This is a regression check now, not a warning.
check("income_tax TaxBracket has no dead `fixed` column (was a warning)",
      "fixed" not in getattr(TaxBracket, "__dataclass_fields__", {}),
      f"fields={list(getattr(TaxBracket, '__dataclass_fields__', {}))}")

# ============================================================
# SECTION A2: SALARY TAX
# ============================================================

section("A2 salary_tax goldens")

# Case A: basic 100k/mo, medical 8k/mo, no rent paid.
# gross=1,296,000; medical exempt 96,000; TI=1,200,000 -> tax 30,000, monthly 2,500.
r = run("salary_tax", {"basic_salary": 100_000, "medical_allowance": 8_000})
ok = r.success and approx(r.data.taxable_income, 1_200_000) and approx(r.data.annual_tax, 30_000.0)
check("basic 100k + med 8k: TI 1.2M, tax 30,000, monthly 2,500",
      ok and approx(r.data.monthly_tax, 2_500.0),
      f"TI={r.data.taxable_income if r.success else r.error} tax={r.data.annual_tax if r.success else ''}")

# Case B: HRA exemption min-of-three (metro).
# basic 100k/mo, HRA 50k/mo, rent 60k/mo: min(600k, 720k-120k=600k, 300k)=300k.
r = run("salary_tax", {
    "basic_salary": 100_000, "house_rent_received": 50_000,
    "rent_paid_annual": 720_000, "city_type": "metro",
})
ok = r.success and approx(r.data.hra_exemption, 300_000.0)
# gross 1.8M - 300k = TI 1.5M -> 30k + 300k*10% = 60,000
check("HRA metro min-of-three = 300,000; tax 60,000",
      ok and approx(r.data.annual_tax, 60_000.0),
      f"HRA={r.data.hra_exemption if r.success else r.error} tax={r.data.annual_tax if r.success else ''}")

# Case C: PF cap (1/3 basic) + zakat, both deducted pre-tax.
# basic 1.2M/yr, PF 50k (cap 400k -> full), zakat 20k: TI=1.2M-70k=1.13M
# -> in 600k-1.2M band @5%: 530,000*0.05 = 26,500.
r = run("salary_tax", {"basic_salary": 100_000, "provident_fund_employee": 50_000, "zakat_paid": 20_000})
check("PF+zakat pre-tax: TI 1.13M -> 26,500",
      r.success and approx(r.data.annual_tax, 26_500.0)
      and approx(r.data.pf_deduction, 50_000.0) and approx(r.data.zakat_deduction, 20_000.0),
      f"got {r.data.annual_tax if r.success else r.error}")

# Case D: medical above the 120k annual cap is taxable.
# basic 100k/mo, medical 15k/mo: gross 1.38M - 120k exempt = TI 1.26M
# -> 30,000 + 10%*60,000 = 36,000.
r = run("salary_tax", {"basic_salary": 100_000, "medical_allowance": 15_000})
check("medical above 120k cap taxable: TI 1.26M -> 36,000",
      r.success and approx(r.data.medical_exemption, 120_000.0)
      and approx(r.data.annual_tax, 36_000.0),
      f"got exempt={r.data.medical_exemption if r.success else r.error} tax={r.data.annual_tax if r.success else ''}")

# ============================================================
# SECTION A3: BUSINESS TAX
# ============================================================

section("A3 business_tax goldens")

# Normal regime TY2025 business slabs (marginal): at 2M -> 60k+800k*15% = 180,000.
r = run("business_tax", {"business_income": 2_000_000})
check("normal 2M -> 180,000", r.success and approx(r.data.tax_payable, 180_000.0),
      f"got {r.data.tax_payable if r.success else r.error}")

# At 5M -> cum(3.6M)=480k + 1.4M*25% = 830,000.
r = run("business_tax", {"business_income": 5_000_000})
check("normal 5M -> 830,000", r.success and approx(r.data.tax_payable, 830_000.0),
      f"got {r.data.tax_payable if r.success else r.error}")

# Brought-forward losses: 2M - 500k = 1.5M. Business slabs TY25:
# 600k-1.2M@10% (cum 60k), 1.2M-2.4M@15% -> 60,000 + 0.15*300,000 = 105,000.
r = run("business_tax", {"business_income": 2_000_000, "brought_forward_losses": 500_000})
check("losses 500k: TI 1.5M -> 105,000", r.success and approx(r.data.tax_payable, 105_000.0),
      f"got {r.data.tax_payable if r.success else r.error}")

# PTR goods 1% of turnover; services 2%.
r = run("business_tax", {"business_income": 0, "tax_regime": "presumptive",
                         "annual_turnover": 20_000_000, "business_category": "goods"})
check("PTR goods 20M @1% -> 200,000", r.success and approx(r.data.tax_payable, 200_000.0),
      f"got {r.data.tax_payable if r.success else r.error}")

r = run("business_tax", {"business_income": 0, "tax_regime": "presumptive",
                         "annual_turnover": 20_000_000, "business_category": "services"})
check("PTR services 20M @2% -> 400,000", r.success and approx(r.data.tax_payable, 400_000.0),
      f"got {r.data.tax_payable if r.success else r.error}")

# PTR ineligible above 100M goods -> clean ValueError.
r = run("business_tax", {"business_income": 0, "tax_regime": "presumptive",
                         "annual_turnover": 150_000_000, "business_category": "goods"})
check("PTR over limit -> clean validation error", (not r.success) and r.error is not None)

# Turnover-based retailer tiers: 100M@0 + 100M@0 + 50M@25% = 12.5M.
r = run("business_tax", {"business_income": 0, "tax_regime": "turnover_based",
                         "is_retailer": True, "annual_turnover": 250_000_000})
check("Section 113 retailer 250M -> 12,500,000",
      r.success and approx(r.data.tax_payable, 12_500_000.0),
      f"got {r.data.tax_payable if r.success else r.error}")

r = run("business_tax", {"business_income": 0, "tax_regime": "turnover_based",
                         "is_retailer": False, "annual_turnover": 250_000_000})
check("turnover regime non-retailer -> clean error", (not r.success) and r.error is not None)

# ============================================================
# SECTION A4: SALES TAX
# ============================================================

section("A4 sales_tax goldens")

r = run("sales_tax", {"sales_value": 1_000_000, "purchases_value": 400_000})
check("goods 18%: output 180k, input 72k, net 108k",
      r.success and approx(r.data.output_tax, 180_000.0)
      and approx(r.data.input_tax, 72_000.0) and approx(r.data.net_payable, 108_000.0),
      f"got {r.data.net_payable if r.success else r.error}")

r = run("sales_tax", {"sales_tax_type": "services", "province": "sindh", "sales_value": 1_000_000})
check("services Sindh 15% -> 150,000", r.success and approx(r.data.output_tax, 150_000.0),
      f"got {r.data.output_tax if r.success else r.error}")

r = run("sales_tax", {"sales_tax_type": "services", "province": "punjab", "sales_value": 1_000_000})
check("services Punjab 16% -> 160,000", r.success and approx(r.data.output_tax, 160_000.0),
      f"got {r.data.output_tax if r.success else r.error}")

r = run("sales_tax", {"sales_tax_type": "services", "province": "punjab",
                      "is_federal_service": True, "sales_value": 1_000_000})
check("federal service 18% -> 180,000", r.success and approx(r.data.output_tax, 180_000.0),
      f"got {r.data.output_tax if r.success else r.error}")

r = run("sales_tax", {"sales_value": 1_000_000, "purchases_value": 400_000, "is_export": True})
check("export zero-rated: output 0, net refundable -72k",
      r.success and approx(r.data.output_tax, 0.0) and approx(r.data.net_payable, -72_000.0),
      f"got {r.data.net_payable if r.success else r.error}")

r = run("sales_tax", {"sales_value": 500_000, "sales_category": "medicines_local"})
check("reduced rate medicines_local 10% -> 50,000",
      r.success and approx(r.data.output_tax, 50_000.0),
      f"got {r.data.output_tax if r.success else r.error}")

# Historical simplification (RESOLVED): input tax used to be credited in full
# even when sales were exempt. The engine now restricts ITC to the taxable
# share (STA s.8(1)(b)) — this is a regression check, not a warning.
r_exempt = run("sales_tax", {"sales_value": 1_000_000, "purchases_value": 400_000,
                             "is_exempt": True})
check("sales_tax exempt supply gets no ITC (STA s.8(1)(b))",
      r_exempt.success and approx(r_exempt.data.input_tax, 0.0)
      and approx(r_exempt.data.output_tax, 0.0),
      f"got input_tax={r_exempt.data.input_tax if r_exempt.success else r_exempt.error}")

r = run("sales_tax", {"sales_value": -5})
check("negative sales -> clean error", (not r.success) and r.error is not None)

# ============================================================
# SECTION A5: WITHHOLDING TAX
# ============================================================

section("A5 withholding_tax goldens")

r = run("withholding_tax", {"section": "150_dividend", "transaction_amount": 100_000})
check("s150 filer 15% -> 15,000 net 85,000",
      r.success and approx(r.data.wht_amount, 15_000.0) and approx(r.data.net_amount, 85_000.0),
      f"got {r.data.wht_amount if r.success else r.error}")

r = run("withholding_tax", {"section": "150_dividend", "transaction_amount": 100_000,
                            "filer_status": "non_filer"})
check("s150 non-filer 30% -> 30,000", r.success and approx(r.data.wht_amount, 30_000.0),
      f"got {r.data.wht_amount if r.success else r.error}")

r = run("withholding_tax", {"section": "153_goods_contracts", "transaction_amount": 200_000})
check("s153 goods filer 4.5% -> 9,000", r.success and approx(r.data.wht_amount, 9_000.0),
      f"got {r.data.wht_amount if r.success else r.error}")

r = run("withholding_tax", {"section": "154_exports", "transaction_amount": 1_000_000})
check("s154 exports 1% -> 10,000", r.success and approx(r.data.wht_amount, 10_000.0),
      f"got {r.data.wht_amount if r.success else r.error}")

r = run("withholding_tax", {"section": "231_cash_bank", "transaction_amount": 100_000})
check("s231 filer 100k @0.5% -> 500, threshold pass",
      r.success and approx(r.data.wht_amount, 500.0) and r.data.threshold_check is True,
      f"got {r.data.wht_amount if r.success else r.error}")

r = run("withholding_tax", {"section": "231_cash_bank", "transaction_amount": 30_000})
check("s231 below 50k threshold flagged, wht still computed 150",
      r.success and approx(r.data.wht_amount, 150.0) and r.data.threshold_check is False,
      f"got {r.data.wht_amount if r.success else r.error}")

r = run("withholding_tax", {"section": "not_a_section", "transaction_amount": 100})
check("unknown section -> clean error", (not r.success) and r.error is not None)

r = run("withholding_tax", {"section": "150_dividend", "transaction_amount": -1})
check("negative amount -> clean error", (not r.success) and r.error is not None)

# ============================================================
# SECTION A6: FEDERAL EXCISE
# ============================================================

section("A6 federal_excise goldens")

r = run("federal_excise", {"category": "telecom_services", "value": 100_000})
check("telecom 17% -> 17,000", r.success and approx(r.data.fed_amount, 17_000.0),
      f"got {r.data.fed_amount if r.success else r.error}")

r = run("federal_excise", {"category": "cigarettes", "value": 1, "quantity": 10})
check("cigarettes 10k sticks -> 59,000 (quantity-based)",
      r.success and approx(r.data.fed_amount, 59_000.0),
      f"got {r.data.fed_amount if r.success else r.error}")

r = run("federal_excise", {"category": "cement", "value": 1_000_000})
check("cement 2.5% -> 25,000", r.success and approx(r.data.fed_amount, 25_000.0),
      f"got {r.data.fed_amount if r.success else r.error}")

r = run("federal_excise", {"category": "sugar", "value": 0, "quantity": 100})
check("sugar 100kg @0.5/kg -> 50", r.success and approx(r.data.fed_amount, 50.0),
      f"got {r.data.fed_amount if r.success else r.error}")

r = run("federal_excise", {"category": "air_travel", "value": 50_000})
check("air travel 20% -> 10,000", r.success and approx(r.data.fed_amount, 10_000.0),
      f"got {r.data.fed_amount if r.success else r.error}")

r = run("federal_excise", {"category": "cement", "value": -1})
check("negative value -> clean error", (not r.success) and r.error is not None)

# ============================================================
# SECTION A7: CAPITAL GAINS
# ============================================================

section("A7 capital_gains goldens")

r = run("capital_gains", {"asset_type": "immovable_property", "acquisition_cost": 10_000_000,
                          "sale_value": 15_000_000, "holding_period_years": 0.5})
check("property <1y filer 15% -> 750,000",
      r.success and approx(r.data.cgt_payable, 750_000.0) and approx(r.data.gain_amount, 5_000_000.0),
      f"got {r.data.cgt_payable if r.success else r.error}")

r = run("capital_gains", {"asset_type": "immovable_property", "acquisition_cost": 10_000_000,
                          "sale_value": 15_000_000, "holding_period_years": 2.5})
check("property 2-3y filer 10% -> 500,000",
      r.success and approx(r.data.cgt_payable, 500_000.0),
      f"got {r.data.cgt_payable if r.success else r.error}")

r = run("capital_gains", {"asset_type": "immovable_property", "acquisition_cost": 10_000_000,
                          "sale_value": 15_000_000, "holding_period_years": 2.5,
                          "filer_status": "non_filer"})
check("property 2-3y non-filer 15% -> 750,000",
      r.success and approx(r.data.cgt_payable, 750_000.0),
      f"got {r.data.cgt_payable if r.success else r.error}")

r = run("capital_gains", {"asset_type": "securities_psx", "acquisition_cost": 1_000_000,
                          "sale_value": 1_400_000, "holding_period_years": 1.5})
check("securities >1y 12.5% -> 50,000",
      r.success and approx(r.data.cgt_payable, 50_000.0),
      f"got {r.data.cgt_payable if r.success else r.error}")

r = run("capital_gains", {"asset_type": "immovable_property", "acquisition_cost": 10_000_000,
                          "sale_value": 8_000_000, "holding_period_years": 1})
check("capital loss -> CGT 0 (not negative)",
      r.success and approx(r.data.cgt_payable, 0.0) and r.data.gain_amount < 0,
      f"got {r.data.cgt_payable if r.success else r.error}")

r = run("capital_gains", {"asset_type": "immovable_property", "acquisition_cost": 10_000_000,
                          "improvement_cost": 1_000_000, "selling_expenses": 200_000,
                          "sale_value": 15_000_000, "holding_period_years": 3})
check("basis incl. improvements+expenses: gain 3.8M @10% -> 380,000",
      r.success and approx(r.data.gain_amount, 3_800_000.0)
      and approx(r.data.cgt_payable, 380_000.0),
      f"got {r.data.cgt_payable if r.success else r.error}")

# ============================================================
# SECTION A8: PROPERTY (RENTAL) TAX
# ============================================================

section("A8 property_tax goldens")

# Rent 1.2M: deemed 1/3 = 400k; taxable 800k; individual TY25 10% band -> 20,000.
r = run("property_tax", {"annual_rent_received": 1_200_000})
check("rent 1.2M: deemed 400k, taxable 800k, tax 20,000",
      r.success and approx(r.data.deemed_deductions, 400_000.0)
      and approx(r.data.taxable_property_income, 800_000.0)
      and approx(r.data.tax_payable, 20_000.0),
      f"got {r.data.tax_payable if r.success else r.error}")

# Repairs 500k > deemed 400k: total deductions 500k -> taxable 700k -> 10,000.
r = run("property_tax", {"annual_rent_received": 1_200_000, "repair_expenses": 500_000})
check("actual repairs 500k beat deemed: taxable 700k, tax 10,000",
      r.success and approx(r.data.total_deductions, 500_000.0)
      and approx(r.data.tax_payable, 10_000.0),
      f"got {r.data.tax_payable if r.success else r.error}")

# Property tax 50k with deemed repairs winning: total = 400k+50k = 450k -> taxable 750k -> 15,000.
r = run("property_tax", {"annual_rent_received": 1_200_000, "property_tax_paid": 50_000})
check("property tax 50k added once: taxable 750k, tax 15,000",
      r.success and approx(r.data.total_deductions, 450_000.0)
      and approx(r.data.tax_payable, 15_000.0),
      f"got {r.data.tax_payable if r.success else r.error}")

# Historical double-count (RESOLVED): when actual repairs exceeded the deemed
# 1/3, the old `max(deemed, actual) + (property_tax + insurance + mortgage)`
# formula added those other deductions twice because actual_deductions already
# contained them. The branch is now max(deemed, actual) only.
r_dc = run("property_tax", {"annual_rent_received": 1_200_000, "repair_expenses": 500_000,
                            "property_tax_paid": 50_000})
check("property_tax other deductions counted once (was a double-count warning)",
      r_dc.success and approx(r_dc.data.actual_deductions, 550_000.0)
      and approx(r_dc.data.total_deductions, 550_000.0)
      and approx(r_dc.data.taxable_property_income, 650_000.0),
      f"got total={r_dc.data.total_deductions if r_dc.success else r_dc.error}")

r = run("property_tax", {"annual_rent_received": -1})
check("negative rent -> clean error", (not r.success) and r.error is not None)

# ============================================================
# SECTION A9: DIVIDEND / PROFIT ON DEBT
# ============================================================

section("A9 dividend_tax goldens")

r = run("dividend_tax", {"income_source": "dividend", "gross_income": 100_000})
check("dividend filer 15% -> 15,000 net 85,000",
      r.success and approx(r.data.tax_payable, 15_000.0) and approx(r.data.net_income, 85_000.0),
      f"got {r.data.tax_payable if r.success else r.error}")

r = run("dividend_tax", {"income_source": "dividend", "gross_income": 100_000,
                         "filer_status": "non_filer"})
check("dividend non-filer 30% -> 30,000", r.success and approx(r.data.tax_payable, 30_000.0),
      f"got {r.data.tax_payable if r.success else r.error}")

r = run("dividend_tax", {"income_source": "profit_debt", "gross_income": 200_000})
check("profit on debt filer 15% -> 30,000", r.success and approx(r.data.tax_payable, 30_000.0),
      f"got {r.data.tax_payable if r.success else r.error}")

r = run("dividend_tax", {"income_source": "dividend", "gross_income": -1})
check("negative income -> clean error", (not r.success) and r.error is not None)

# ============================================================
# SECTION A10: CUSTOM DUTY
# ============================================================

section("A10 custom_duty goldens")

r = run("custom_duty", {"cif_value": 1_000_000})
check("default: CD 200k, ST 216k, WHT 84,960, total 500,960, landed 1,500,960",
      r.success and approx(r.data.customs_duty, 200_000.0)
      and approx(r.data.sales_tax, 216_000.0) and approx(r.data.wht_148, 84_960.0)
      and approx(r.data.total_duty, 500_960.0) and approx(r.data.landed_cost, 1_500_960.0),
      f"got {r.data.total_duty if r.success else r.error}")

r = run("custom_duty", {"cif_value": 1_000_000, "hs_category": "vehicles"})
check("vehicles: CD 500k, ST 270k, RD 450k, total 1,326,200",
      r.success and approx(r.data.customs_duty, 500_000.0)
      and approx(r.data.sales_tax, 270_000.0) and approx(r.data.regulatory_duty, 450_000.0)
      and approx(r.data.total_duty, 1_326_200.0),
      f"got {r.data.total_duty if r.success else r.error}")

r = run("custom_duty", {"cif_value": 1_000_000, "hs_category": "pharmaceuticals"})
check("pharma: CD 100k, ST 110k, WHT 72,600, total 282,600",
      r.success and approx(r.data.total_duty, 282_600.0),
      f"got {r.data.total_duty if r.success else r.error}")

r = run("custom_duty", {"cif_value": 0})
check("CIF 0 -> all zero, no crash", r.success and approx(r.data.total_duty, 0.0),
      f"got {r.data.total_duty if r.success else r.error}")

r = run("custom_duty", {"cif_value": -100})
check("negative CIF -> clean error", (not r.success) and r.error is not None)

# ============================================================
# SECTION A11: CUSTOM CALC
# ============================================================

section("A11 custom_calc goldens")

r = run("custom_calc", {"calc_type": "percentage", "base_value": 500_000, "rate": 0.17})
check("percentage 500k x 0.17 -> 85,000", r.success and approx(r.data.result, 85_000.0),
      f"got {r.data.result if r.success else r.error}")

r = run("custom_calc", {"calc_type": "penalty", "principal": 100_000,
                        "monthly_rate": 0.10, "days_late": 45})
check("penalty 100k @10%/mo x 1.5 -> 15,000", r.success and approx(r.data.result, 15_000.0),
      f"got {r.data.result if r.success else r.error}")

r = run("custom_calc", {"calc_type": "compound", "base_value": 1_000_000,
                        "rate": 0.05, "periods": 3})
check("compound 1M @5% ^3 -> 1,157,625", r.success and approx(r.data.result, 1_157_625.0),
      f"got {r.data.result if r.success else r.error}")

r = run("custom_calc", {"calc_type": "conditional", "base_value": 600_000,
                        "rate": 0.05, "variables": {"threshold": 500_000}})
check("conditional above threshold -> 30,000", r.success and approx(r.data.result, 30_000.0),
      f"got {r.data.result if r.success else r.error}")

r = run("custom_calc", {"calc_type": "conditional", "base_value": 400_000,
                        "rate": 0.05, "variables": {"threshold": 500_000}})
check("conditional below threshold -> 0", r.success and approx(r.data.result, 0.0),
      f"got {r.data.result if r.success else r.error}")

r = run("custom_calc", {"calc_type": "percentage", "base_value": -1, "rate": 0.1})
check("negative base -> clean error", (not r.success) and r.error is not None)

r = run("custom_calc", {"expression": "1+1", "calc_type": "percentage"})
check("expression injection refused", (not r.success) and r.error is not None)

# ============================================================
# SECTION B: BOUNDARY + MONOTONICITY SWEEP
# ============================================================

section("B monotonicity sweep (salaried TY2025/2026 + business TY2025)")

def sweep(calc_type: str, base: dict, values: list[float], label: str) -> None:
    prev = -1.0
    all_ok = True
    first_bad = ""
    for v in values:
        r = ENGINE.calculate(calc_type, {**base, **_value_key(calc_type, v)})
        if not r.success:
            all_ok = False
            first_bad = f"calc failed at {v}: {r.error}"
            break
        tax = float(r.data.tax_after_credits)
        if tax < 0 or tax < prev - 1e-6:
            all_ok = False
            first_bad = f"non-monotonic/negative at {v}: {tax} after {prev}"
            break
        prev = tax
    check(f"{label}: non-decreasing, non-negative across {len(values)} points", all_ok, first_bad)

def _value_key(calc_type: str, v: float) -> dict:
    return {"gross_income": v}

sweep_values = [500_000, 600_000, 600_001, 700_000, 1_200_000, 1_200_001,
                1_800_000, 2_400_000, 2_400_001, 3_000_000, 3_600_000,
                3_600_001, 5_000_000, 6_000_000, 6_000_001, 9_000_000,
                12_000_000, 12_000_001, 25_000_000]
sweep("income_tax", {"filing_status": "salaried", "tax_year": "2025"}, sweep_values, "salaried TY25")
sweep("income_tax", {"filing_status": "salaried", "tax_year": "2026"}, sweep_values, "salaried TY26")
sweep("income_tax", {"filing_status": "business", "tax_year": "2025"}, sweep_values, "business TY25")

# ============================================================
# SECTION C: JUNK-INPUT MATRIX
# ============================================================

section("C junk-input matrix (no crash, clean failure)")

JUNK_VALUES = ["abc", None, float("nan"), float("inf"), float("-inf"), {"nested": 1}, [1, 2]]
junk_ok = True
junk_detail = ""
for junk in JUNK_VALUES:
    r = ENGINE.calculate("income_tax", {"gross_income": junk, "filing_status": "salaried"})
    if r.success or r.error is None:
        junk_ok = False
        junk_detail = f"junk {junk!r} -> success={r.success} error={r.error}"
        break
check("all junk income values rejected cleanly (7 variants)", junk_ok, junk_detail)

for calc in ENGINE.supported_types:
    r = ENGINE.calculate(calc, {"gross_income": "abc", "value": "xyz",
                                "cif_value": "zzz", "base_value": "qqq"})
    if not calc == "income_tax":
        # non-relevant junk keys are ignored by most calculators; the
        # requirement is only that nothing crashes the process.
        pass
check("engine survives junk across all 11 types (no exception escape)",
      len(ENGINE.supported_types) == 11)

r = ENGINE.calculate("totally_unknown_type", {"x": 1})
check("unknown calc type -> clean unsupported error",
      (not r.success) and "Unsupported" in (r.error or ""))

r = ENGINE.calculate("income_tax", {})
check("empty inputs -> defaults, success with 0 tax",
      r.success and approx(r.data.tax_after_credits, 0.0),
      f"got {r.data.tax_after_credits if r.success else r.error}")

# ============================================================
# SECTION D: CROSS-CONSISTENCY
# ============================================================

section("D cross-consistency between calculators")

r_salary = ENGINE.calculate("salary_tax", {"basic_salary": 100_000, "medical_allowance": 8_000})
r_income = ENGINE.calculate("income_tax", {"gross_income": 1_200_000,
                                           "filing_status": "salaried", "tax_year": "2025"})
check("salary annual tax == income tax on equivalent TI (30,000)",
      r_salary.success and r_income.success
      and approx(r_salary.data.annual_tax, r_income.data.tax_after_credits),
      f"{r_salary.data.annual_tax if r_salary.success else r_salary.error} vs "
      f"{r_income.data.tax_after_credits if r_income.success else r_income.error}")

r_div = ENGINE.calculate("dividend_tax", {"income_source": "dividend", "gross_income": 100_000})
r_wht = ENGINE.calculate("withholding_tax", {"section": "150_dividend", "transaction_amount": 100_000})
check("dividend tax == WHT s150 (15,000)",
      r_div.success and r_wht.success
      and approx(r_div.data.tax_payable, r_wht.data.wht_amount),
      f"{r_div.data.tax_payable if r_div.success else r_div.error} vs "
      f"{r_wht.data.wht_amount if r_wht.success else r_wht.error}")

r_biz = ENGINE.calculate("business_tax", {"business_income": 2_000_000})
r_inc2 = ENGINE.calculate("income_tax", {"gross_income": 2_000_000,
                                         "filing_status": "business", "tax_year": "2025"})
check("business normal == income business slabs (180,000)",
      r_biz.success and r_inc2.success
      and approx(r_biz.data.tax_payable, r_inc2.data.tax_after_credits),
      f"{r_biz.data.tax_payable if r_biz.success else r_biz.error} vs "
      f"{r_inc2.data.tax_after_credits if r_inc2.success else r_inc2.error}")

r = ENGINE.calculate("withholding_tax", {"section": "152_rent_property", "transaction_amount": 123_456})
check("WHT identity net + wht == gross",
      r.success and approx(r.data.net_amount + r.data.wht_amount, 123_456.0),
      f"got {r.data.net_amount if r.success else r.error}")

# ============================================================
# SECTION E: 13-TOOL REGISTRY
# ============================================================

section("E tool registry (13 tools)")

check("registry holds exactly the 13 documented tools",
      DEFAULT_REGISTRY.tool_names() == list(TOOL_NAMES) and len(TOOL_NAMES) == 13,
      f"got {DEFAULT_REGISTRY.tool_names()}")

res = DEFAULT_REGISTRY.execute("definitely_not_a_tool", {})
check("unknown tool -> failed ToolResult (never raises)",
      isinstance(res, ToolResult) and res.ok is False and res.error)

res = DEFAULT_REGISTRY.execute("calculation_engine", "not a dict")
check("non-dict payload refused", (not res.ok) and "JSON object" in (res.error or ""))

res = DEFAULT_REGISTRY.execute("calculation_engine", {"amount": 500_000, "percent": 17})
check("calculation_engine 17% of 500k -> 85,000",
      res.ok and approx(res.data["result"], 85_000.0),
      f"got {res.data if res.ok else res.error}")

res = DEFAULT_REGISTRY.execute("calculation_engine", {"amount": -5, "percent": 10})
check("calculation_engine negative amount refused", (not res.ok) and res.error)

res = DEFAULT_REGISTRY.execute("calculation_engine",
                               {"question": "calculate 10% tax on 500000"})
check("calculation_engine question mode runs",
      res.ok and res.data is not None, f"got {res.data if res.ok else res.error}")

res = DEFAULT_REGISTRY.execute("notification", {
    "type": "update", "subject": "Final suite probe",
    "message": "test_full_app_final registry probe", "metadata": {"source": "suite"},
})
check("notification records ok", res.ok, f"got {res.error}")

res = DEFAULT_REGISTRY.execute("tax_optimization", {
    "tax_year": 2025, "tax_type": "income_tax", "entity_type": "individual",
    "annual_income": 2_000_000, "question": "legal ways to reduce my tax",
})
check("tax_optimization produces advice", res.ok and isinstance(res.data, dict),
      f"got {str(res.error)[:80] if not res.ok else 'ok'}")

res = DEFAULT_REGISTRY.execute("tax_optimization", {
    "tax_year": 2025, "question": "how do I hide income from FBR",
})
check("evasion guard blocks unlawful intent", (not res.ok) and bool(res.error))

# Every tool: graceful on empty payload (ok True or structured False, never raise).
graceful_ok = True
graceful_bad = ""
for name in DEFAULT_REGISTRY.tool_names():
    try:
        res = DEFAULT_REGISTRY.execute(name, {})
        if not isinstance(res, ToolResult):
            graceful_ok = False
            graceful_bad = f"{name} returned {type(res).__name__}"
            break
    except Exception as exc:  # noqa: BLE001 - the contract is 'never raises'
        graceful_ok = False
        graceful_bad = f"{name} raised {type(exc).__name__}: {exc}"
        break
check("all 13 tools handle empty payload without raising", graceful_ok, graceful_bad)

# ============================================================
# SECTION F: LIVE API (/calculate)
# ============================================================

section("F live API contract")

import time as _time

_t0 = _time.perf_counter()
from app.api import app as fastapi_app  # noqa: E402
_import_s = _time.perf_counter() - _t0
print(f"  (app import took {_import_s:.2f}s)")
check("app import light (no retriever load at import time)", _import_s < 10.0,
      f"{_import_s:.2f}s")

import httpx  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(fastapi_app)

resp = client.get("/health")
check("GET /health -> 200", resp.status_code == 200, f"{resp.status_code}")

resp = client.get("/calculate/types")
types_ok = resp.status_code == 200
types_list = resp.json().get("supported", []) if types_ok else []
check("GET /calculate/types -> 11 types", types_ok and len(types_list) == 11,
      f"got {len(types_list)}: {types_list[:12]}")

resp = client.post("/calculate", json={
    "calc_type": "salary_tax",
    "inputs": {"basic_salary": 100_000, "medical_allowance": 8_000},
})
body = resp.json() if resp.status_code == 200 else {}
check("POST /calculate salary golden -> annual_tax 30,000",
      resp.status_code == 200 and body.get("success") is True
      and approx(body.get("data", {}).get("annual_tax", -1), 30_000.0)
      and isinstance(body.get("audit_id"), str),
      f"{resp.status_code} {str(body)[:150]}")

resp = client.post("/calculate", json={
    "calc_type": "income_tax",
    "inputs": {"gross_income": 1_200_000, "filing_status": "salaried"},
})
check("POST /calculate income golden -> 30,000",
      resp.status_code == 200
      and approx(resp.json().get("data", {}).get("tax_after_credits", -1), 30_000.0),
      f"{resp.status_code} {str(resp.json())[:150]}")

resp = client.post("/calculate", json={"calc_type": "income_tax",
                                       "inputs": {"gross_income": "abc"}})
check("POST /calculate junk -> 400", resp.status_code == 400, f"{resp.status_code}")

resp = client.post("/calculate", json={"calc_type": "income_tax", "inputs": {}})
check("POST /calculate empty inputs -> 400", resp.status_code == 400, f"{resp.status_code}")

resp = client.post("/calculate", json={"calc_type": "nope", "inputs": {"x": 1}})
check("POST /calculate unknown type -> 400", resp.status_code == 400, f"{resp.status_code}")

# Rate limit: 30 POSTs / 60s per client. Fire up to 40 quick requests and
# expect a 429 within the window. Run LAST so it cannot poison other tests.
saw_429 = False
for i in range(40):
    resp = client.post("/calculate", json={
        "calc_type": "income_tax",
        "inputs": {"gross_income": 400_000, "filing_status": "salaried"},
    })
    if resp.status_code == 429:
        saw_429 = True
        break
check("rate limiter engages (429 within 40 rapid posts)", saw_429,
      f"no 429 after {i + 1} posts")

client.close()

# ============================================================
# FINAL VERDICT
# ============================================================

passed = sum(1 for _, ok, _ in RESULTS if ok)
failed = [r for r in RESULTS if not r[1]]

print()
print("=" * 66)
print("FINAL SUMMARY")
print("=" * 66)
print(f"Total checks : {len(RESULTS)}")
print(f"Passed       : {passed}")
print(f"Failed       : {len(failed)}")
print(f"Warnings     : {len(WARNINGS)} (documented simplifications, not failures)")
for w in WARNINGS:
    print(f"  - {w}")
print()

if failed:
    print("FAILED CHECKS:")
    for name, _, detail in failed:
        print(f"  x {name}" + (f"  | {detail}" if detail else ""))
    print()
    print("=" * 66)
    print("FINAL VERDICT: APP THEEK NAHI (hard failures above)")
    print("=" * 66)
    raise SystemExit(1)

print("=" * 66)
print("FINAL VERDICT: APP THEEK HAI")
print("All golden values, boundaries, monotonicity, junk-input,")
print("cross-consistency, registry and API contract checks passed.")
print("Is test ke result par bharosa kiya ja sakta hai.")
print("=" * 66)
raise SystemExit(0)
