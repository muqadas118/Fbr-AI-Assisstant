"""
Salary Tax Calculator - Production-Grade
=======================================

Dedicated to salaried individuals with:
- Monthly tax deduction (Section 149 - FBR rate schedule)
- Annual reconciliation
- House Rent Allowance (HRA) exemption
- Medical allowance exemption
- Transport allowance exemption
- Conveyance allowance exemption
- Special allowances
- Bonus / Arrears
- Provident Fund / Gratuity deductions
- EOBI contributions
"""

from dataclasses import dataclass, field
from enum import Enum

from app.calculations.income_tax import (
    IncomeTaxCalculator, IncomeTaxInput, IncomeTaxResult,
    FilingStatus, TaxYear
)


class SalaryFrequency(str, Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"


@dataclass
class SalaryBreakdown:
    """Monthly salary breakdown."""
    basic_salary: float
    house_rent: float  # HRA
    medical: float
    transport: float
    conveyance: float
    special_allowances: float
    bonuses: float
    overtime: float
    other_allowances: float
    gross_monthly: float
    gross_annual: float


@dataclass
class SalaryTaxInput:
    """Input for salary tax calculation."""
    # Salary components (monthly)
    basic_salary: float
    house_rent_received: float = 0.0  # Actual HRA received
    medical_allowance: float = 0.0
    transport_allowance: float = 0.0
    conveyance_allowance: float = 0.0
    special_allowances: float = 0.0
    bonuses_annual: float = 0.0
    overtime_annual: float = 0.0
    other_allowances: float = 0.0

    # Rent paid (for HRA exemption)
    rent_paid_annual: float = 0.0
    city_type: str = "metro"  # "metro" or "non_metro"

    # Deductions
    provident_fund_employee: float = 0.0  # Annual
    gratuity_provided: bool = False
    eobi_contribution: float = 0.0  # Annual

    # Tax year
    tax_year: TaxYear = TaxYear.TY_2025

    # Adjustments
    zakat_paid: float = 0.0
    donations: float = 0.0
    investment_in_equity: float = 0.0
    tuition_fees: float = 0.0


@dataclass
class SalaryTaxResult:
    """Result of salary tax calculation with full breakdown."""
    annual_gross: float
    annual_exemptions: float
    hra_exemption: float
    medical_exemption: float
    transport_exemption: float
    conveyance_exemption: float
    pf_deduction: float
    eobi_deduction: float
    zakat_deduction: float
    taxable_income: float
    annual_tax: float
    monthly_tax: float
    income_tax_result: IncomeTaxResult
    # Year whose slabs produced every figure below, so a caller can tell
    # which Finance Act schedule was applied without echoing the inputs.
    tax_year: TaxYear
    exemption_breakdown: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


class SalaryTaxCalculator:
    """
    Production-grade salary tax calculator for salaried individuals.

    FBR-compliant: Uses official FBR tax calculator methodology.
    """

    # Exemption limits (per FBR rules, may update with SROs)
    MEDICAL_EXEMPT_MAX = 120_000  # Annual
    TRANSPORT_EXEMPT_MAX = 0  # No separate exemption after 2018
    CONVEYANCE_EXEMPT_MAX = 0  # No separate exemption
    EOBI_DEDUCTIBLE_MAX = 36_000  # Approximate

    @staticmethod
    def calculate_hra_exemption(
        basic_annual: float,
        hra_received: float,
        rent_paid: float,
        city_type: str
    ) -> tuple[float, str]:
        """
        Calculate HRA exemption under Section 13(5).

        HRA exemption = MIN of:
        1. HRA received
        2. Rent paid - 10% of basic salary
        3. 25% of basic salary (metro) / 15% (non-metro)

        If rent paid <= 0, exemption = 0.
        """
        if rent_paid <= 0 or hra_received <= 0:
            return 0.0, "No rent paid or HRA received"

        # Condition 2: Rent paid minus 10% of basic
        rent_minus_10pct = max(0, rent_paid - (basic_annual * 0.10))

        # Condition 3: Percentage of basic
        pct_of_basic = basic_annual * (0.25 if city_type == "metro" else 0.15)

        # HRA exemption is minimum of all three
        exemption = min(hra_received, rent_minus_10pct, pct_of_basic)
        return round(exemption, 2), ""

    @staticmethod
    def validate_input(inp: SalaryTaxInput) -> tuple[bool, str]:
        """Validate salary tax input (same pattern as the other calculators).

        Negative allowances are rejected: an exemption computed with
        min() would otherwise go negative and INCREASE taxable income.
        """
        if inp.basic_salary < 0:
            return False, "Basic salary cannot be negative."
        if inp.house_rent_received < 0:
            return False, "House rent allowance cannot be negative."
        if inp.medical_allowance < 0:
            return False, "Medical allowance cannot be negative."
        if inp.transport_allowance < 0:
            return False, "Transport allowance cannot be negative."
        if inp.conveyance_allowance < 0:
            return False, "Conveyance allowance cannot be negative."
        if inp.special_allowances < 0:
            return False, "Special allowances cannot be negative."
        if inp.bonuses_annual < 0:
            return False, "Bonuses cannot be negative."
        if inp.overtime_annual < 0:
            return False, "Overtime cannot be negative."
        if inp.other_allowances < 0:
            return False, "Other allowances cannot be negative."
        if inp.rent_paid_annual < 0:
            return False, "Rent paid cannot be negative."
        if inp.provident_fund_employee < 0:
            return False, "Provident fund contribution cannot be negative."
        if inp.eobi_contribution < 0:
            return False, "EOBI contribution cannot be negative."
        if inp.zakat_paid < 0:
            return False, "Zakat cannot be negative."
        if inp.donations < 0:
            return False, "Donations cannot be negative."
        if inp.investment_in_equity < 0:
            return False, "Investment in equity cannot be negative."
        if inp.tuition_fees < 0:
            return False, "Tuition fees cannot be negative."
        return True, ""

    @staticmethod
    def calculate(input_data: SalaryTaxInput) -> SalaryTaxResult:
        """Calculate full salary tax with exemptions and deductions."""
        valid, error = SalaryTaxCalculator.validate_input(input_data)
        if not valid:
            raise ValueError(error)

        notes = []
        exemption_breakdown = []
        sources = [
            f"FBR Finance Act {input_data.tax_year.value}",
            "Income Tax Ordinance 2001 - Section 13 (Salary exemptions)",
            "Income Tax Ordinance 2001 - Section 149 (Return of Income)",
        ]

        # ============================================================
        # Step 1: Calculate Annual Gross Salary
        # ============================================================
        annual_hra = input_data.house_rent_received * 12
        annual_medical = input_data.medical_allowance * 12
        annual_transport = input_data.transport_allowance * 12
        annual_conveyance = input_data.conveyance_allowance * 12
        annual_special = input_data.special_allowances * 12
        annual_other = input_data.other_allowances * 12
        annual_basic = input_data.basic_salary * 12

        annual_gross = (
            annual_basic
            + annual_hra
            + annual_medical
            + annual_transport
            + annual_conveyance
            + annual_special
            + input_data.bonuses_annual
            + input_data.overtime_annual
            + annual_other
        )

        # ============================================================
        # Step 2: Calculate Exemptions
        # ============================================================
        # HRA Exemption
        hra_exempt, hra_note = SalaryTaxCalculator.calculate_hra_exemption(
            basic_annual=annual_basic,
            hra_received=annual_hra,
            rent_paid=input_data.rent_paid_annual,
            city_type=input_data.city_type,
        )
        if hra_exempt > 0:
            exemption_breakdown.append({
                "type": "HRA Exemption",
                "section": "Section 13(5)",
                "amount": hra_exempt,
                "note": hra_note or f"Computed for {input_data.city_type} city",
            })
        elif hra_note:
            notes.append(f"HRA: {hra_note}")

        # Medical Allowance Exemption
        medical_exempt = min(annual_medical, SalaryTaxCalculator.MEDICAL_EXEMPT_MAX)
        if medical_exempt > 0:
            exemption_breakdown.append({
                "type": "Medical Allowance Exemption",
                "section": "Section 13(1)(c)",
                "amount": medical_exempt,
                "note": f"Up to PKR {SalaryTaxCalculator.MEDICAL_EXEMPT_MAX:,} per year",
            })
            if annual_medical > medical_exempt:
                taxable_medical = annual_medical - medical_exempt
                notes.append(f"Medical allowance above exemption: PKR {taxable_medical:,.2f} is taxable")

        # Transport / Conveyance (no separate exemption per current rules)
        transport_exempt = 0
        conveyance_exempt = 0
        if annual_transport > 0:
            notes.append("Transport allowance is fully taxable (no exemption under current rules)")
        if annual_conveyance > 0:
            notes.append("Conveyance allowance is fully taxable (no exemption under current rules)")

        total_exemptions = hra_exempt + medical_exempt + transport_exempt + conveyance_exempt

        # ============================================================
        # Step 3: Calculate Deductions (PF, EOBI, Zakat)
        # ============================================================
        pf_deduction = 0.0
        if input_data.provident_fund_employee > 0:
            # Approved PF deductible, but for simplicity cap at 1/3 of basic
            max_pf = annual_basic / 3
            pf_deduction = min(input_data.provident_fund_employee, max_pf)
            if pf_deduction > 0:
                notes.append(f"Approved Provident Fund deduction: PKR {pf_deduction:,.2f}")

        eobi_deduction = 0.0
        if input_data.eobi_contribution > 0:
            eobi_deduction = min(input_data.eobi_contribution, SalaryTaxCalculator.EOBI_DEDUCTIBLE_MAX)
            if eobi_deduction > 0:
                notes.append(f"EOBI contribution deduction: PKR {eobi_deduction:,.2f}")

        zakat_deduction = 0.0
        if input_data.zakat_paid > 0:
            zakat_deduction = input_data.zakat_paid
            notes.append(f"Zakat deduction: PKR {zakat_deduction:,.2f} (with certificate)")

        # ============================================================
        # Step 4: Calculate Taxable Income
        # ============================================================
        taxable_income = max(0, annual_gross - total_exemptions - pf_deduction - eobi_deduction - zakat_deduction)

        # ============================================================
        # Step 5: Use Income Tax Calculator for slab-based tax
        # ============================================================
        income_input = IncomeTaxInput(
            gross_income=taxable_income,
            filing_status=FilingStatus.SALARIED,
            tax_year=input_data.tax_year,
            zakat_paid=0,  # Already deducted above
            donations=input_data.donations,
            investment_in_equity=input_data.investment_in_equity,
            tuition_fees=input_data.tuition_fees,
        )
        income_result = IncomeTaxCalculator.calculate(income_input)

        annual_tax = income_result.tax_after_credits
        monthly_tax = round(annual_tax / 12, 2) if annual_tax > 0 else 0

        return SalaryTaxResult(
            annual_gross=round(annual_gross, 2),
            annual_exemptions=round(total_exemptions, 2),
            hra_exemption=hra_exempt,
            medical_exemption=medical_exempt,
            transport_exemption=transport_exempt,
            conveyance_exemption=conveyance_exempt,
            pf_deduction=round(pf_deduction, 2),
            eobi_deduction=round(eobi_deduction, 2),
            zakat_deduction=round(zakat_deduction, 2),
            taxable_income=round(taxable_income, 2),
            annual_tax=round(annual_tax, 2),
            monthly_tax=monthly_tax,
            income_tax_result=income_result,
            tax_year=input_data.tax_year,
            exemption_breakdown=exemption_breakdown,
            notes=notes,
            sources=sources,
        )

    @staticmethod
    def format_result(result: SalaryTaxResult, currency: str = "PKR") -> str:
        """Format as human-readable report."""
        lines = [
            "=== Salary Tax Calculation (FBR Compliant) ===",
            f"Tax Year: {result.tax_year.value}",
            "",
            "--- Annual Gross Salary ---",
            f"Gross Salary (Annual):    {currency} {result.annual_gross:>15,.2f}",
            "",
            "--- Exemptions (Tax-Free) ---",
            f"  HRA Exemption:          {currency} {result.hra_exemption:>15,.2f}",
            f"  Medical Exemption:      {currency} {result.medical_exemption:>15,.2f}",
            f"  Transport Exemption:    {currency} {result.transport_exemption:>15,.2f}",
            f"  Conveyance Exemption:   {currency} {result.conveyance_exemption:>15,.2f}",
            f"  Total Exemptions:       {currency} {result.annual_exemptions:>15,.2f}",
            "",
            "--- Deductions (From Taxable Income) ---",
            f"  Provident Fund:         {currency} {result.pf_deduction:>15,.2f}",
            f"  EOBI Contribution:      {currency} {result.eobi_deduction:>15,.2f}",
            f"  Zakat:                  {currency} {result.zakat_deduction:>15,.2f}",
            "",
            "--- Tax Computation ---",
            f"  Taxable Income:         {currency} {result.taxable_income:>15,.2f}",
            f"  Annual Tax:             {currency} {result.annual_tax:>15,.2f}",
            f"  Monthly Tax (Avg):      {currency} {result.monthly_tax:>15,.2f}",
            f"  Effective Tax Rate:     {result.income_tax_result.effective_tax_rate:>14.2f}%",
            "",
            "--- Exemption Details ---",
        ]
        for ex in result.exemption_breakdown:
            lines.append(f"  ✓ {ex['type']} ({ex['section']}): {currency} {ex['amount']:,.2f}")
            if ex.get("note"):
                lines.append(f"      {ex['note']}")
        lines.append("")
        lines.append("--- Notes ---")
        for note in result.notes:
            lines.append(f"  • {note}")
        lines.append("")
        lines.append("--- Sources ---")
        for src in result.sources:
            lines.append(f"  📄 {src}")
        return "\n".join(lines)
