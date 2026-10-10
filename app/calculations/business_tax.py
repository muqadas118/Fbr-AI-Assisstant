"""
Business Tax Calculator - Production-Grade
==========================================

For Sole Proprietorships, Partnerships, AOPs:
- Business income under normal tax regime
- Presumptive Tax Regime (PTR) for small businesses
- Revenue thresholds: 10M (services), 100M (goods)
- Turnover-based tax for small retailers/shops
"""

from dataclasses import dataclass, field
from enum import Enum

from app.calculations.income_tax import (
    IncomeTaxCalculator, IncomeTaxInput,
    FilingStatus, TaxYear
)


class BusinessType(str, Enum):
    SOLE_PROPRIETORSHIP = "sole_proprietorship"
    PARTNERSHIP = "partnership"
    AOP = "aop"
    INDIVIDUAL_BUSINESS = "individual_business"


class TaxRegime(str, Enum):
    NORMAL = "normal"  # Progressive slabs
    PRESUMPTIVE = "presumptive"  # Fixed rate for small businesses
    TURNOVER_BASED = "turnover_based"  # For retailers (1.5% / 1% etc.)


# Presumptive Tax Regime (Section 100A) - TY 2025
# Keys MUST match BusinessTaxInput.business_category values
# ("goods" | "services" | "manufacturer") - the PTR lookup uses the
# same field, so mismatched keys silently fall back to the 1% default.
PTR_RATES_TY2025 = {
    "goods": 1.0,   # 1% of turnover (goods)
    "services": 2.0,  # 2% of turnover (services)
    "manufacturer": 1.5,  # 1.5% (manufacturing)
}

# Turnover limits for PTR eligibility
PTR_TURNOVER_LIMITS = {
    "goods": 100_000_000,    # 100M for goods
    "services": 50_000_000,  # 50M for services
}

# Presumptive rates per tax year. Only tabulated years are listed, so a
# year without a table raises instead of silently borrowing another
# year's rates.
PTR_RATES_BY_YEAR: dict[TaxYear, dict] = {
    TaxYear.TY_2025: PTR_RATES_TY2025,
}

# Turnover-based regime (Section 113) for small retailers
TURNOVER_BASED_RATES = {
    "tier_1": {"threshold": 100_000_000, "rate": 0.0},  # First 100M = 0%
    "tier_2": {"threshold": 200_000_000, "rate": 0.0},  # Next 100M = 0% (under conditions)
    "tier_3": {"threshold": None, "rate": 0.25},  # Above = 25% (presumptive)
}


@dataclass
class BusinessTaxInput:
    """Input for business tax calculation."""
    business_income: float  # Net business income (revenue - expenses)
    business_type: BusinessType = BusinessType.INDIVIDUAL_BUSINESS
    tax_year: TaxYear = TaxYear.TY_2025
    tax_regime: TaxRegime = TaxRegime.NORMAL

    # Presumptive regime input
    annual_turnover: float = 0.0
    business_category: str = "goods"  # "goods" | "services" | "manufacturer"

    # Turnover-based regime input
    is_retailer: bool = False  # For Section 113 turnover-based regime

    # Optional adjustments
    zakat_paid: float = 0.0
    donations: float = 0.0
    investment_in_equity: float = 0.0
    brought_forward_losses: float = 0.0  # Business losses from prior years
    accounting_profit: float = 0.0  # For reconciliation


@dataclass
class BusinessTaxResult:
    """Result of business tax calculation."""
    regime_applied: str
    taxable_income: float
    tax_before_credits: float
    tax_credits_applied: float
    tax_payable: float
    effective_tax_rate: float
    # Year whose slabs produced every figure below, so a caller can tell
    # which Finance Act schedule was applied without echoing the inputs.
    tax_year: TaxYear
    slab_breakdown: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    regime_details: dict = field(default_factory=dict)


class BusinessTaxCalculator:
    """
    Production-grade business tax calculator.

    Supports three regimes:
    1. Normal (progressive slabs)
    2. Presumptive Tax Regime (Section 100A) for small businesses
    3. Turnover-based regime (Section 113) for small retailers
    """

    @staticmethod
    def validate_input(inp: BusinessTaxInput) -> tuple[bool, str]:
        """Validate business tax input."""
        if inp.business_income < 0:
            return False, "Business income cannot be negative."
        if inp.annual_turnover < 0:
            return False, "Annual turnover cannot be negative."
        if inp.brought_forward_losses < 0:
            return False, "Brought forward losses cannot be negative."
        if inp.business_category not in ("goods", "services", "manufacturer"):
            return False, "Invalid business category."
        return True, ""

    @staticmethod
    def is_ptr_eligible(inp: BusinessTaxInput) -> tuple[bool, str]:
        """
        Check if business is eligible for Presumptive Tax Regime.

        PTR (Sec 100A) eligibility:
        - Turnover <= 100M (goods) or 50M (services)
        - Not a company
        - Resident taxpayer
        """
        if inp.business_type == BusinessType.AOP:
            return False, "AOPs not eligible for PTR"
        if inp.business_category in ("goods", "manufacturer"):
            if inp.annual_turnover > PTR_TURNOVER_LIMITS["goods"]:
                return False, f"Turnover exceeds PTR limit (PKR {PTR_TURNOVER_LIMITS['goods']:,})"
        elif inp.business_category == "services":
            if inp.annual_turnover > PTR_TURNOVER_LIMITS["services"]:
                return False, f"Turnover exceeds PTR limit (PKR {PTR_TURNOVER_LIMITS['services']:,})"
        return True, "PTR eligible"

    @staticmethod
    def calculate(inp: BusinessTaxInput) -> BusinessTaxResult:
        """Calculate business tax based on chosen regime."""
        valid, error = BusinessTaxCalculator.validate_input(inp)
        if not valid:
            raise ValueError(error)

        notes = []
        sources = [
            f"FBR Finance Act {inp.tax_year.value}",
            "Income Tax Ordinance 2001 - Section 100A (Presumptive Tax)",
            "Income Tax Ordinance 2001 - Section 113 (Small Retailers)",
        ]

        # ============================================================
        # REGIME 1: Presumptive Tax Regime
        # ============================================================
        if inp.tax_regime == TaxRegime.PRESUMPTIVE:
            eligible, reason = BusinessTaxCalculator.is_ptr_eligible(inp)
            if not eligible:
                raise ValueError(f"PTR not applicable: {reason}")

            # Per-year PTR rates: a tax year without a tabulated table
            # raises instead of silently substituting another year's.
            ptr_rates = PTR_RATES_BY_YEAR.get(inp.tax_year)
            if ptr_rates is None:
                raise ValueError(
                    f"No Presumptive Tax Regime (Section 100A) rates defined for tax year "
                    f"{inp.tax_year.value}. Supported: "
                    f"{', '.join(y.value for y in PTR_RATES_BY_YEAR)}."
                )
            rate = ptr_rates.get(inp.business_category, 1.0)
            tax_payable = inp.annual_turnover * (rate / 100)
            tax_payable = round(tax_payable, 2)

            notes.append(f"Presumptive Tax Regime applied: {rate}% of turnover")
            notes.append(f"Turnover: PKR {inp.annual_turnover:,.2f}")
            notes.append(f"Category: {inp.business_category}")

            effective_rate = (tax_payable / inp.annual_turnover * 100) if inp.annual_turnover > 0 else 0

            return BusinessTaxResult(
                regime_applied="presumptive",
                taxable_income=inp.annual_turnover,  # For display
                tax_before_credits=tax_payable,
                tax_credits_applied=0,
                tax_payable=tax_payable,
                effective_tax_rate=round(effective_rate, 2),
                tax_year=inp.tax_year,
                slab_breakdown=[{
                    "type": "presumptive",
                    "rate": f"{rate}%",
                    "base": "turnover",
                    "tax": tax_payable,
                }],
                notes=notes,
                sources=sources,
                regime_details={
                    "turnover": inp.annual_turnover,
                    "rate": rate,
                    "eligibility": reason,
                },
            )

        # ============================================================
        # REGIME 2: Turnover-Based Regime (Section 113)
        # ============================================================
        if inp.tax_regime == TaxRegime.TURNOVER_BASED:
            if not inp.is_retailer:
                raise ValueError("Turnover-based regime only for retailers (Section 113)")
            if inp.business_income != 0:
                notes.append("Note: For turnover-based regime, business_income is ignored. Use annual_turnover.")

            # Tiered calculation
            tax = 0.0
            remaining_turnover = inp.annual_turnover
            tier_breakdown = []

            tier1_limit = TURNOVER_BASED_RATES["tier_1"]["threshold"]
            tier2_limit = TURNOVER_BASED_RATES["tier_2"]["threshold"]
            tier3_rate = TURNOVER_BASED_RATES["tier_3"]["rate"]

            if remaining_turnover <= tier1_limit:
                tier_tax = 0.0
                tax += tier_tax
                tier_breakdown.append({
                    "tier": "Tier 1 (up to 100M)",
                    "amount": remaining_turnover,
                    "rate": "0%",
                    "tax": 0.0,
                })
            else:
                tier1_amount = tier1_limit
                tax += 0.0
                tier_breakdown.append({
                    "tier": "Tier 1 (up to 100M)",
                    "amount": tier1_amount,
                    "rate": "0%",
                    "tax": 0.0,
                })
                remaining_turnover -= tier1_amount

                if remaining_turnover <= (tier2_limit - tier1_limit):
                    tier_breakdown.append({
                        "tier": "Tier 2 (100M-200M)",
                        "amount": remaining_turnover,
                        "rate": "0%",
                        "tax": 0.0,
                    })
                else:
                    tier2_amount = tier2_limit - tier1_limit
                    tier_breakdown.append({
                        "tier": "Tier 2 (100M-200M)",
                        "amount": tier2_amount,
                        "rate": "0%",
                        "tax": 0.0,
                    })
                    remaining_turnover -= tier2_amount

                    tier3_tax = remaining_turnover * tier3_rate
                    tax += tier3_tax
                    tier_breakdown.append({
                        "tier": "Tier 3 (above 200M)",
                        "amount": remaining_turnover,
                        "rate": "25%",
                        "tax": round(tier3_tax, 2),
                    })

            tax = round(tax, 2)
            effective_rate = (tax / inp.annual_turnover * 100) if inp.annual_turnover > 0 else 0

            return BusinessTaxResult(
                regime_applied="turnover_based",
                taxable_income=inp.annual_turnover,
                tax_before_credits=tax,
                tax_credits_applied=0,
                tax_payable=tax,
                effective_tax_rate=round(effective_rate, 2),
                tax_year=inp.tax_year,
                slab_breakdown=tier_breakdown,
                notes=notes + ["Turnover-based regime (Section 113) for small retailers"],
                sources=sources,
                regime_details={"turnover": inp.annual_turnover, "tiers": len(tier_breakdown)},
            )

        # ============================================================
        # REGIME 3: Normal (Progressive Slabs)
        # ============================================================
        # Use income tax calculator with appropriate filing status
        if inp.business_type == BusinessType.INDIVIDUAL_BUSINESS:
            filing_status = FilingStatus.BUSINESS
        elif inp.business_type == BusinessType.AOP:
            filing_status = FilingStatus.AOP
        else:
            filing_status = FilingStatus.BUSINESS

        # Apply brought forward losses
        taxable = max(0, inp.business_income - inp.brought_forward_losses)
        if inp.brought_forward_losses > 0:
            notes.append(f"Brought forward losses: PKR {inp.brought_forward_losses:,.2f}")

        income_input = IncomeTaxInput(
            gross_income=taxable,
            filing_status=filing_status,
            tax_year=inp.tax_year,
            zakat_paid=inp.zakat_paid,
            donations=inp.donations,
            investment_in_equity=inp.investment_in_equity,
        )
        income_result = IncomeTaxCalculator.calculate(income_input)

        notes.append("Normal tax regime (progressive slabs) applied")

        return BusinessTaxResult(
            regime_applied="normal",
            taxable_income=taxable,
            tax_before_credits=income_result.tax_before_credits,
            tax_credits_applied=income_result.tax_credits_applied,
            tax_payable=income_result.tax_after_credits,
            effective_tax_rate=income_result.effective_tax_rate,
            tax_year=inp.tax_year,
            slab_breakdown=income_result.slab_breakdown,
            notes=notes + income_result.notes,
            sources=sources + income_result.sources,
            regime_details={"filing_status": filing_status.value, "tax_year": inp.tax_year.value},
        )

    @staticmethod
    def format_result(result: BusinessTaxResult, currency: str = "PKR") -> str:
        """Format result as human-readable string."""
        lines = [
            "=== Business Tax Calculation (FBR Compliant) ===",
            f"Tax Year: {result.tax_year.value}",
            f"Regime: {result.regime_applied.upper()}",
            "",
            "--- Tax Computation ---",
            f"Taxable Income/Base:     {currency} {result.taxable_income:>15,.2f}",
            f"Tax Before Credits:      {currency} {result.tax_before_credits:>15,.2f}",
            f"Tax Credits:             {currency} {result.tax_credits_applied:>15,.2f}",
            f"Tax Payable:             {currency} {result.tax_payable:>15,.2f}",
            f"Effective Tax Rate:      {result.effective_tax_rate:>14.2f}%",
            "",
            "--- Breakdown ---",
        ]
        for i, item in enumerate(result.slab_breakdown, 1):
            if "tier" in item:
                lines.append(
                    f"  {i}. {item['tier']}: "
                    f"Amount={currency} {item['amount']:>10,.2f} @ {item['rate']} -> "
                    f"Tax={currency} {item['tax']:>10,.2f}"
                )
            elif "slab" in item:
                lines.append(
                    f"  {i}. {item['slab']} @ {item['rate']}: "
                    f"Taxable={currency} {item['taxable_amount']:>10,.2f} -> "
                    f"Tax={currency} {item['tax']:>10,.2f}"
                )
            elif "type" in item:
                lines.append(
                    f"  {i}. {item.get('type', '').title()} rate {item['rate']} "
                    f"on {item.get('base', 'base')}: "
                    f"Tax={currency} {item['tax']:>10,.2f}"
                )

        lines.append("")
        lines.append("--- Notes ---")
        for note in result.notes:
            lines.append(f"  • {note}")
        lines.append("")
        lines.append("--- Sources ---")
        for src in result.sources:
            lines.append(f"  📄 {src}")
        return "\n".join(lines)
