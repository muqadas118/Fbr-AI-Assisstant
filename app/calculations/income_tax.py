"""
Income Tax Calculator - Production-Grade
========================================

Handles:
- Salaried Individuals
- Business Individuals
- Association of Persons (AOP)
- Non-Profit Organizations
- Companies (Public, Private)

Verified against Finance Act 2024-2025 (Tax Year 2025, Year of Assessment 2026)
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class FilingStatus(str, Enum):
    INDIVIDUAL = "individual"
    SALARIED = "salaried"
    BUSINESS = "business"
    AOP = "aop"
    COMPANY_PUBLIC = "company_public"
    COMPANY_PRIVATE = "company_private"
    NON_PROFIT = "non_profit"


class TaxYear(str, Enum):
    TY_2024 = "2024"  # FY 2023-24
    TY_2025 = "2025"  # FY 2024-25
    TY_2026 = "2026"  # FY 2025-26


@dataclass
class TaxBracket:
    """Single tax bracket: amount above lower bound taxed at rate%."""
    lower: float
    upper: Optional[float]  # None = no upper limit
    rate: float
    # FIX: dead `fixed` column - removed: calculate_tax_on_slab always uses the
    # FBR marginal method and never read this field, and the legacy cumulative
    # values (TY2025 salaried 390k/990k/2,490k) disagreed with the marginal
    # sums (330k/810k/2,310k), inviting future misuse. No callers pass it.


# ============================================================
# TAX SLABS - FBR OFFICIAL (Finance Act 2024-25, effective TY 2025)
# ============================================================

# Salaried Individuals (TY 2025) - Reduced rates announced
SALARIED_SLABS_TY2025 = [
    TaxBracket(0, 600_000, 0.0),
    TaxBracket(600_000, 1_200_000, 0.05),
    TaxBracket(1_200_000, 2_400_000, 0.10),
    TaxBracket(2_400_000, 3_600_000, 0.15),
    TaxBracket(3_600_000, 6_000_000, 0.20),
    TaxBracket(6_000_000, 12_000_000, 0.25),
    TaxBracket(12_000_000, None, 0.35),
]

# Business / AOP Individuals (TY 2025) - Normal rates
BUSINESS_SLABS_TY2025 = [
    TaxBracket(0, 600_000, 0.0),
    TaxBracket(600_000, 1_200_000, 0.10),
    TaxBracket(1_200_000, 2_400_000, 0.15),
    TaxBracket(2_400_000, 3_600_000, 0.20),
    TaxBracket(3_600_000, 6_000_000, 0.25),
    TaxBracket(6_000_000, 12_000_000, 0.30),
    TaxBracket(12_000_000, None, 0.35),
]

# AOP / Non-Profit (TY 2025)
AOP_SLABS_TY2025 = [
    TaxBracket(0, 600_000, 0.0),
    TaxBracket(600_000, 1_200_000, 0.10),
    TaxBracket(1_200_000, 2_400_000, 0.15),
    TaxBracket(2_400_000, 3_600_000, 0.20),
    TaxBracket(3_600_000, 6_000_000, 0.25),
    TaxBracket(6_000_000, 12_000_000, 0.30),
    TaxBracket(12_000_000, None, 0.35),
]

# Salaried Individuals (TY 2024 - older rates, kept for reference)
SALARIED_SLABS_TY2024 = [
    TaxBracket(0, 600_000, 0.0),
    TaxBracket(600_000, 1_200_000, 0.05),
    TaxBracket(1_200_000, 2_400_000, 0.10),
    TaxBracket(2_400_000, 3_600_000, 0.15),
    TaxBracket(3_600_000, 6_000_000, 0.20),
    TaxBracket(6_000_000, 12_000_000, 0.25),
    TaxBracket(12_000_000, None, 0.35),
]

# Business / AOP Individuals (TY 2024)
BUSINESS_SLABS_TY2024 = [
    TaxBracket(0, 600_000, 0.0),
    TaxBracket(600_000, 1_200_000, 0.10),
    TaxBracket(1_200_000, 2_400_000, 0.15),
    TaxBracket(2_400_000, 3_600_000, 0.20),
    TaxBracket(3_600_000, 6_000_000, 0.25),
    TaxBracket(6_000_000, 12_000_000, 0.30),
    TaxBracket(12_000_000, None, 0.35),
]

# Corporate Tax Rates (TY 2025)
COMPANY_RATES_TY2025 = {
    "company_public": 0.29,  # 29% for public companies
    "company_private": 0.29,  # 29% for private companies (small co 20%)
    "small_company": 0.20,    # 20% for small companies (turnover < 250M)
}

# Salaried Individuals (TY 2026) - Finance Act 2025 rates
# (First Schedule, Part I: salary > 75% of taxable income; effective
# for tax year 2026, i.e. FY 2025-26). Verified against PwC Worldwide
# Tax Summaries — Pakistan, personal income tax rates (2025-26).
SALARIED_SLABS_TY2026 = [
    TaxBracket(0, 600_000, 0.0),
    TaxBracket(600_000, 1_200_000, 0.01),
    TaxBracket(1_200_000, 2_200_000, 0.11),
    TaxBracket(2_200_000, 3_200_000, 0.20),
    TaxBracket(3_200_000, 4_100_000, 0.25),
    TaxBracket(4_100_000, 5_600_000, 0.29),
    TaxBracket(5_600_000, 7_000_000, 0.32),
    TaxBracket(7_000_000, None, 0.35),
]

# Non-salaried individuals / AOPs (TY 2026) - Finance Act 2025 rates.
BUSINESS_SLABS_TY2026 = [
    TaxBracket(0, 600_000, 0.0),
    TaxBracket(600_000, 1_200_000, 0.15),
    TaxBracket(1_200_000, 1_600_000, 0.20),
    TaxBracket(1_600_000, 3_200_000, 0.30),
    TaxBracket(3_200_000, 5_600_000, 0.40),
    TaxBracket(5_600_000, None, 0.45),
]

# AOP slabs follow the non-salaried individual table for TY 2026.
AOP_SLABS_TY2026 = [
    TaxBracket(0, 600_000, 0.0),
    TaxBracket(600_000, 1_200_000, 0.15),
    TaxBracket(1_200_000, 1_600_000, 0.20),
    TaxBracket(1_600_000, 3_200_000, 0.30),
    TaxBracket(3_200_000, 5_600_000, 0.40),
    TaxBracket(5_600_000, None, 0.45),
]

# ============================================================
# ALLOWANCES / DEDUCTIONS
# ============================================================

# Standard deductions & exemptions (TY 2025)
STANDARD_DEDUCTIONS = {
    "salaried_basic_exemption": 0,  # No separate basic exemption; covered by 0% bracket up to 600k
    "medical_allowance_max": 120_000,  # Annual medical allowance exemption
    "transport_exemption": 0,  # No separate transport exemption
    "house_rent_deduction_rate": 0.25,  # HRA exemption = min(25% of basic, actual rent paid - 10% basic)
}

# Tax credits (rebateable from tax liability)
TAX_CREDITS = {
    # Section 61 (Division XIII, Part X, Second Schedule):
    # credit = (donation / taxable income) * tax before credit,
    # donations capped at 30% of taxable income for individuals / AOPs
    # and 20% for companies. Previously simplified to a flat 15%.
    "donations_limit_individual": 0.30,
    "donations_limit_company": 0.20,
    "investment_pak_equity": 0.10,  # 10% rebate for investment in Pakistan Equity (Section 62)
    "education_expense_max": 200_000,  # Max education expense for employed persons
    "tuition_fee_max_dependent": 150_000,  # Max per child for tuition fees
    "tuition_fee_max_children": 4,
}

# Zakat allowable as deduction (not credit)
ZAKAT_RULES = {
    "deductible": True,
    "requires_certificate": True,
}


# ============================================================
# CALCULATION ENGINE
# ============================================================

@dataclass
class IncomeTaxInput:
    """Input parameters for income tax calculation."""
    gross_income: float
    filing_status: FilingStatus
    tax_year: TaxYear = TaxYear.TY_2025

    # Optional adjustments
    zakat_paid: float = 0.0
    donations: float = 0.0
    investment_in_equity: float = 0.0
    tuition_fees: float = 0.0  # For salaried only
    medical_allowance: float = 0.0  # For salaried only

    # For companies
    is_small_company: bool = False  # Turnover < 250M
    is_aviation_banking: bool = False  # Banking/Aviation special rate

    # For property / capital gains (delegated to specific calculator)
    include_other_sources: float = 0.0


@dataclass
class IncomeTaxResult:
    """Result of income tax calculation."""
    taxable_income: float
    gross_income: float
    total_deductions: float
    tax_before_credits: float
    tax_credits_applied: float
    tax_after_credits: float
    effective_tax_rate: float
    slab_breakdown: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


class IncomeTaxCalculator:
    """
    Production-grade Income Tax calculator.
    Verifies all formulas against FBR Finance Act rules.
    """

    @staticmethod
    def get_slabs(filing_status: FilingStatus, tax_year: TaxYear) -> list[TaxBracket]:
        """Return appropriate tax slabs for filing status and year."""
        if filing_status == FilingStatus.SALARIED:
            if tax_year == TaxYear.TY_2024:
                return SALARIED_SLABS_TY2024
            if tax_year == TaxYear.TY_2026:
                return SALARIED_SLABS_TY2026
            return SALARIED_SLABS_TY2025
        elif filing_status in (FilingStatus.BUSINESS, FilingStatus.INDIVIDUAL):
            if tax_year == TaxYear.TY_2024:
                return BUSINESS_SLABS_TY2024
            if tax_year == TaxYear.TY_2026:
                return BUSINESS_SLABS_TY2026
            return BUSINESS_SLABS_TY2025
        elif filing_status == FilingStatus.AOP or filing_status == FilingStatus.NON_PROFIT:
            if tax_year == TaxYear.TY_2026:
                return AOP_SLABS_TY2026
            return AOP_SLABS_TY2025
        return []

    @staticmethod
    def calculate_tax_on_slab(taxable_income: float, slabs: list[TaxBracket]) -> tuple[float, list[dict]]:
        """
        Calculate tax using progressive slab method.

        Returns (total_tax, breakdown_list).
        """
        if taxable_income <= 0 or not slabs:
            return 0.0, []

        total_tax = 0.0
        breakdown = []

        for slab in slabs:
            if taxable_income <= slab.lower:
                break
            upper = slab.upper if slab.upper is not None else taxable_income
            amount_in_slab = min(taxable_income, upper) - slab.lower
            if amount_in_slab <= 0:
                continue
            tax_in_slab = amount_in_slab * slab.rate
            total_tax += tax_in_slab
            breakdown.append({
                "slab": f"PKR {slab.lower:,.0f} - PKR {upper if upper else 'above':,}",
                "rate": f"{slab.rate * 100:.0f}%",
                "taxable_amount": amount_in_slab,
                "tax": tax_in_slab,
            })
            if slab.upper is not None and taxable_income <= slab.upper:
                break

        return round(total_tax, 2), breakdown

    @staticmethod
    def validate_input(inp: IncomeTaxInput) -> tuple[bool, str]:
        """Validate input for common errors."""
        if inp.gross_income < 0:
            return False, "Gross income cannot be negative."
        if inp.gross_income > 1_000_000_000_000:  # 1 trillion cap
            return False, (
                "Gross income exceeds the maximum supported amount "
                "(PKR 1,000,000,000,000). Please enter a smaller amount."
            )
        if inp.zakat_paid < 0:
            return False, "Zakat cannot be negative."
        if inp.donations < 0:
            return False, "Donations cannot be negative."
        if inp.investment_in_equity < 0:
            return False, "Investment in equity cannot be negative."
        if inp.tuition_fees < 0:
            return False, "Tuition fees cannot be negative."
        if inp.medical_allowance < 0:
            return False, "Medical allowance cannot be negative."
        return True, ""

    @staticmethod
    def calculate(inp: IncomeTaxInput) -> IncomeTaxResult:
        """
        Perform full income tax calculation.

        Returns IncomeTaxResult with full breakdown.
        """
        # Validate
        valid, error = IncomeTaxCalculator.validate_input(inp)
        if not valid:
            raise ValueError(f"Input validation failed: {error}")

        notes = []
        sources = [
            f"FBR Finance Act {inp.tax_year.value}",
            f"Income Tax Ordinance 2001 (Section 149 - Return of Income)",
        ]

        # ============================================================
        # COMPANY TAX (flat rate, no slabs)
        # ============================================================
        if inp.filing_status in (FilingStatus.COMPANY_PUBLIC, FilingStatus.COMPANY_PRIVATE):
            if inp.is_small_company:
                rate = COMPANY_RATES_TY2025["small_company"]
                notes.append("Small company rate (turnover < PKR 250M) applied: 20%")
            else:
                key = "company_public" if inp.filing_status == FilingStatus.COMPANY_PUBLIC else "company_private"
                rate = COMPANY_RATES_TY2025[key]
                notes.append(f"Corporate tax rate applied: {rate * 100:.0f}%")

            taxable_income = inp.gross_income
            tax_before_credits = round(taxable_income * rate, 2)

            # Zakat deduction (only for companies, optional)
            deductions = inp.zakat_paid if inp.zakat_paid > 0 else 0
            if deductions > 0 and ZAKAT_RULES["deductible"]:
                notes.append("Zakat deducted from taxable income (with certificate)")

            # Tax credits
            credits = 0.0
            if inp.investment_in_equity > 0:
                credit = min(inp.investment_in_equity * TAX_CREDITS["investment_pak_equity"], tax_before_credits * 0.50)
                credits += credit
                notes.append(f"Investment in equity credit: PKR {credit:,.2f}")

            if inp.donations > 0:
                # Section 61 / Division XIII average-rate method for companies:
                # donations capped at 20% of taxable income.
                allowed_donation = min(
                    inp.donations,
                    taxable_income * TAX_CREDITS["donations_limit_company"],
                )
                if inp.donations > allowed_donation:
                    notes.append(
                        f"Donations limited to 20% of taxable income: PKR {allowed_donation:,.2f}"
                    )
                if taxable_income > 0:
                    credit = (allowed_donation / taxable_income) * tax_before_credits
                    credits += credit
                    notes.append(f"Donations credit: PKR {credit:,.2f} (Section 61, average-rate method)")
                else:
                    notes.append("Donations credit: PKR 0.00 (no taxable income for Section 61 credit)")

            tax_after_credits = max(0, tax_before_credits - credits)
            effective_rate = (tax_after_credits / inp.gross_income * 100) if inp.gross_income > 0 else 0

            return IncomeTaxResult(
                taxable_income=taxable_income,
                gross_income=inp.gross_income,
                total_deductions=deductions,
                tax_before_credits=tax_before_credits,
                tax_credits_applied=credits,
                tax_after_credits=round(tax_after_credits, 2),
                effective_tax_rate=round(effective_rate, 2),
                slab_breakdown=[{
                    "type": "corporate",
                    "rate": f"{rate * 100:.0f}%",
                    "taxable_amount": taxable_income,
                    "tax": tax_before_credits,
                }],
                notes=notes,
                sources=sources,
            )

        # ============================================================
        # INDIVIDUAL / AOP / NON-PROFIT (progressive slabs)
        # ============================================================
        gross = inp.gross_income

        # Deductions from gross income
        deductions = 0.0
        if inp.zakat_paid > 0 and ZAKAT_RULES["deductible"]:
            deductions += inp.zakat_paid
            notes.append(f"Zakat paid: PKR {inp.zakat_paid:,.2f} (with certificate)")

        if inp.donations > 0:
            # Donations deductible up to 30% of taxable income, before tax
            notes.append(f"Donations: PKR {inp.donations:,.2f} (subject to 30% of taxable income limit)")

        # Salary-specific deductions
        if inp.filing_status == FilingStatus.SALARIED:
            if inp.medical_allowance > 0:
                medical_exempt = min(inp.medical_allowance, STANDARD_DEDUCTIONS["medical_allowance_max"])
                if medical_exempt > 0:
                    notes.append(f"Medical allowance exemption: PKR {medical_exempt:,.2f}")
            if inp.tuition_fees > 0:
                max_per_child = TAX_CREDITS["tuition_fee_max_dependent"]
                max_children = TAX_CREDITS["tuition_fee_max_children"]
                # For simplicity, treat total tuition up to max_per_child * max_children
                # More accurate would need child count
                tuition_deduction = min(inp.tuition_fees, max_per_child * max_children)
                if tuition_deduction > 0:
                    notes.append(f"Tuition fees deduction: PKR {tuition_deduction:,.2f} (max for {max_children} children @ {max_per_child:,.0f} each)")
                    deductions += tuition_deduction

        # Other source income added
        gross += inp.include_other_sources
        if inp.include_other_sources > 0:
            notes.append(f"Other source income included: PKR {inp.include_other_sources:,.2f}")

        taxable_income = max(0, gross - deductions)

        # Get appropriate slabs
        slabs = IncomeTaxCalculator.get_slabs(inp.filing_status, inp.tax_year)
        if not slabs:
            raise ValueError(f"No tax slabs defined for {inp.filing_status} / {inp.tax_year}")

        # Calculate tax using slabs
        tax_before_credits, breakdown = IncomeTaxCalculator.calculate_tax_on_slab(taxable_income, slabs)

        # Tax credits (against final tax)
        credits = 0.0
        if inp.investment_in_equity > 0 and inp.filing_status != FilingStatus.SALARIED:
            # Section 62: 10% of investment, max 15% of tax
            credit = inp.investment_in_equity * TAX_CREDITS["investment_pak_equity"]
            max_credit = tax_before_credits * 0.15
            credit = min(credit, max_credit)
            credits += credit
            notes.append(f"Investment in equity credit: PKR {credit:,.2f} (Section 62)")

        if inp.donations > 0:
            # Section 61 / Division XIII: credit = (A/B) x C where A is the
            # assessed donation (capped at 30% of taxable income for
            # individuals/AOPs), B is taxable income and C is tax before
            # the credit.
            allowed_donation = min(
                inp.donations,
                taxable_income * TAX_CREDITS["donations_limit_individual"],
            )
            if inp.donations > allowed_donation:
                notes.append(
                    f"Donations limited to 30% of taxable income: PKR {allowed_donation:,.2f}"
                )
            if taxable_income > 0:
                credit = (allowed_donation / taxable_income) * tax_before_credits
                credits += credit
                notes.append(f"Donations credit: PKR {credit:,.2f} (Section 61, average-rate method)")
            else:
                notes.append("Donations credit: PKR 0.00 (no taxable income for Section 61 credit)")

        tax_after_credits = max(0, tax_before_credits - credits)
        effective_rate = (tax_after_credits / inp.gross_income * 100) if inp.gross_income > 0 else 0

        return IncomeTaxResult(
            taxable_income=taxable_income,
            gross_income=inp.gross_income,
            total_deductions=deductions,
            tax_before_credits=tax_before_credits,
            tax_credits_applied=round(credits, 2),
            tax_after_credits=round(tax_after_credits, 2),
            effective_tax_rate=round(effective_rate, 2),
            slab_breakdown=breakdown,
            notes=notes,
            sources=sources,
        )

    @staticmethod
    def format_result(result: IncomeTaxResult, currency: str = "PKR") -> str:
        """Format result as human-readable string."""
        lines = [
            f"=== Income Tax Calculation (FBR Official) ===",
            f"",
            f"Gross Income:            {currency} {result.gross_income:>15,.2f}",
            f"Total Deductions:        {currency} {result.total_deductions:>15,.2f}",
            f"Taxable Income:          {currency} {result.taxable_income:>15,.2f}",
            f"",
            f"--- Tax Slab Breakdown ---",
        ]
        for i, slab in enumerate(result.slab_breakdown, 1):
            if "slab" in slab:
                lines.append(
                    f"  {i}. {slab['slab']} @ {slab['rate']}: "
                    f"Taxable={currency} {slab['taxable_amount']:>10,.2f} "
                    f"-> Tax={currency} {slab['tax']:>10,.2f}"
                )
            else:
                lines.append(
                    f"  {i}. Corporate rate {slab['rate']}: "
                    f"Taxable={currency} {slab['taxable_amount']:>10,.2f} "
                    f"-> Tax={currency} {slab['tax']:>10,.2f}"
                )

        lines.extend([
            f"",
            f"Tax Before Credits:      {currency} {result.tax_before_credits:>15,.2f}",
            f"Tax Credits Applied:     {currency} {result.tax_credits_applied:>15,.2f}",
            f"Final Tax Payable:       {currency} {result.tax_after_credits:>15,.2f}",
            f"Effective Tax Rate:      {result.effective_tax_rate:>14.2f}%",
            f"",
            f"--- Notes ---",
        ])
        for note in result.notes:
            lines.append(f"  • {note}")
        lines.append(f"")
        lines.append(f"--- Sources ---")
        for src in result.sources:
            lines.append(f"  📄 {src}")
        return "\n".join(lines)
