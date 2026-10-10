"""
Property/Rental Income Tax Calculator - Production-Grade
========================================================

For landlords and property owners receiving rental income.

Property income tax = Tax on rental income (treated as normal income)
Deductions available:
- Repair & maintenance: 1/3 of rent (deemed)
- Insurance premium paid
- Property tax paid
- Mortgage interest (for rented property)
"""

from dataclasses import dataclass, field
from enum import Enum

from app.calculations.income_tax import (
    IncomeTaxCalculator, IncomeTaxInput, FilingStatus, TaxYear
)


class PropertyType(str, Enum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"
    MIXED_USE = "mixed_use"


@dataclass
class PropertyTaxInput:
    """Input for property/rental income tax calculation."""
    annual_rent_received: float
    property_type: PropertyType = PropertyType.RESIDENTIAL
    tax_year: TaxYear = TaxYear.TY_2025
    filing_status: FilingStatus = FilingStatus.INDIVIDUAL

    # Optional deductions
    property_tax_paid: float = 0.0
    insurance_premium: float = 0.0
    mortgage_interest: float = 0.0  # Only for rented out property
    repair_expenses: float = 0.0  # Can be claimed, but 1/3 deemed is automatic

    # Adjustments
    zakat_paid: float = 0.0
    donations: float = 0.0
    investment_in_equity: float = 0.0

    # Other income (combined tax calculation)
    other_income: float = 0.0


@dataclass
class PropertyTaxResult:
    """Result of property tax calculation."""
    annual_rent: float
    deemed_deductions: float  # 1/3 of rent
    actual_deductions: float
    total_deductions: float
    taxable_property_income: float
    combined_gross_income: float
    tax_payable: float
    effective_tax_rate: float
    # Year whose slabs produced every figure below, so a caller can tell
    # which Finance Act schedule was applied without echoing the inputs.
    tax_year: TaxYear
    notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


class PropertyTaxCalculator:
    """Production-grade Property/Rental Income Tax calculator."""

    @staticmethod
    def validate_input(inp: PropertyTaxInput) -> tuple[bool, str]:
        if inp.annual_rent_received < 0:
            return False, "Annual rent cannot be negative."
        return True, ""

    @staticmethod
    def calculate(inp: PropertyTaxInput) -> PropertyTaxResult:
        valid, error = PropertyTaxCalculator.validate_input(inp)
        if not valid:
            raise ValueError(error)

        notes = []
        sources = [
            f"FBR Finance Act {inp.tax_year.value}",
            "Income Tax Ordinance 2001 - Section 15 (Property Income)",
        ]

        # Deemed deduction: 1/3 of rent for repairs/maintenance
        deemed_deduction = inp.annual_rent_received / 3
        notes.append(f"Deemed repair deduction (1/3 of rent): PKR {deemed_deduction:,.2f}")

        # Actual deductions (if higher than deemed, can claim actual)
        actual_deductions = (
            inp.property_tax_paid
            + inp.insurance_premium
            + inp.mortgage_interest
        )
        # Single branch: actual repairs are claimed only when they exceed
        # the deemed 1/3, otherwise the deemed 1/3 applies. (The other
        # deductions are already part of actual_deductions, so they must
        # not be added again — that double-count was fixed here.)
        if inp.repair_expenses > deemed_deduction:
            actual_deductions += inp.repair_expenses
            total_deductions = actual_deductions
            notes.append(f"Actual repair expenses (higher than deemed): PKR {inp.repair_expenses:,.2f}")
        else:
            total_deductions = deemed_deduction + (
                inp.property_tax_paid + inp.insurance_premium + inp.mortgage_interest
            )
            notes.append(f"Using deemed deduction (actual repairs PKR {inp.repair_expenses:,.2f} < deemed)")

        taxable_property = max(0, inp.annual_rent_received - total_deductions)
        combined_gross = taxable_property + inp.other_income

        # Use income tax calculator
        income_input = IncomeTaxInput(
            gross_income=combined_gross,
            filing_status=inp.filing_status,
            tax_year=inp.tax_year,
            zakat_paid=inp.zakat_paid,
            donations=inp.donations,
            investment_in_equity=inp.investment_in_equity,
        )
        income_result = IncomeTaxCalculator.calculate(income_input)

        effective_rate = (income_result.tax_after_credits / inp.annual_rent_received * 100) if inp.annual_rent_received > 0 else 0

        return PropertyTaxResult(
            annual_rent=inp.annual_rent_received,
            deemed_deductions=round(deemed_deduction, 2),
            actual_deductions=round(actual_deductions, 2),
            total_deductions=round(total_deductions, 2),
            taxable_property_income=round(taxable_property, 2),
            combined_gross_income=round(combined_gross, 2),
            tax_payable=income_result.tax_after_credits,
            effective_tax_rate=round(effective_rate, 2),
            tax_year=inp.tax_year,
            notes=notes + income_result.notes,
            sources=sources + income_result.sources,
        )

    @staticmethod
    def format_result(result: PropertyTaxResult, currency: str = "PKR") -> str:
        lines = [
            "=== Property/Rental Income Tax ===",
            f"Tax Year: {result.tax_year.value}",
            "",
            "--- Income ---",
            f"Annual Rent:             {currency} {result.annual_rent:>15,.2f}",
            "",
            "--- Deductions ---",
            f"Deemed (1/3 of rent):    {currency} {result.deemed_deductions:>15,.2f}",
            f"Actual Deductions:       {currency} {result.actual_deductions:>15,.2f}",
            f"Total Deductions:        {currency} {result.total_deductions:>15,.2f}",
            "",
            "--- Taxable Income ---",
            f"Taxable Property:        {currency} {result.taxable_property_income:>15,.2f}",
            f"Combined with Other:     {currency} {result.combined_gross_income:>15,.2f}",
            "",
            "--- Tax ---",
            f"Tax Payable:             {currency} {result.tax_payable:>15,.2f}",
            f"Effective Tax Rate:      {result.effective_tax_rate:>14.2f}%",
            "",
            "--- Notes ---",
        ]
        for note in result.notes:
            lines.append(f"  • {note}")
        lines.append("")
        lines.append("--- Sources ---")
        for src in result.sources:
            lines.append(f"  📄 {src}")
        return "\n".join(lines)
