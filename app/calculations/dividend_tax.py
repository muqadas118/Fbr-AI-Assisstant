"""
Dividend/Profit on Debt Tax Calculator - Production-Grade
==========================================================

Two ways dividends are taxed:
1. WHT at source (Section 150) - 15% for filers, 30% for non-filers
2. Final tax regime - 15% on gross dividend (deemed income for filers)

For profit on debt (interest, profit on bank deposits):
- Section 151 WHT: 15% filer, 30% non-filer
- Final tax regime available for some
"""

from dataclasses import dataclass, field
from enum import Enum


class IncomeSource(str, Enum):
    DIVIDEND = "dividend"
    PROFIT_DEBT = "profit_debt"  # Interest, profit on bank deposits
    BOND_YIELD = "bond_yield"
    MUTUAL_FUND = "mutual_fund"


@dataclass
class DividendTaxInput:
    """Input for dividend/interest tax calculation."""
    income_source: IncomeSource
    gross_income: float
    filer_status: str = "filer"  # "filer" or "non_filer"


@dataclass
class DividendTaxResult:
    """Result of dividend/interest tax calculation."""
    income_source: str
    gross_income: float
    rate_applied: float
    tax_payable: float
    net_income: float
    # Dividend / profit on debt is always charged as WHT at source
    # (final tax); the "add to normal income" method was never
    # implemented in this calculator, so the dead TaxMethod /
    # other_income inputs were removed.
    tax_method: str = "wht"
    notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


class DividendTaxCalculator:
    """Production-grade Dividend/Profit on Debt Tax calculator."""

    # Section 150: Dividend WHT
    DIVIDEND_WHT_FILER = 0.15
    DIVIDEND_WHT_NON_FILER = 0.30

    # Section 151: Profit on Debt
    PROFIT_DEBT_WHT_FILER = 0.15
    PROFIT_DEBT_WHT_NON_FILER = 0.30

    @staticmethod
    def validate_input(inp: DividendTaxInput) -> tuple[bool, str]:
        if inp.gross_income < 0:
            return False, "Income cannot be negative."
        return True, ""

    @staticmethod
    def calculate(inp: DividendTaxInput) -> DividendTaxResult:
        valid, error = DividendTaxCalculator.validate_input(inp)
        if not valid:
            raise ValueError(error)

        notes = []
        sources = [
            f"Income Tax Ordinance 2001 - {inp.income_source.value.title()} Tax",
            "FBR Finance Act 2024-25",
        ]

        is_filer = inp.filer_status == "filer"

        # Get rate
        if inp.income_source == IncomeSource.DIVIDEND:
            rate = DividendTaxCalculator.DIVIDEND_WHT_FILER if is_filer else DividendTaxCalculator.DIVIDEND_WHT_NON_FILER
            notes.append(f"Dividend WHT (Section 150): {rate * 100:.0f}%")
        elif inp.income_source in (IncomeSource.PROFIT_DEBT, IncomeSource.BOND_YIELD, IncomeSource.MUTUAL_FUND):
            rate = DividendTaxCalculator.PROFIT_DEBT_WHT_FILER if is_filer else DividendTaxCalculator.PROFIT_DEBT_WHT_NON_FILER
            notes.append(f"Profit on Debt WHT (Section 151): {rate * 100:.0f}%")
        else:
            rate = 0.15
            notes.append(f"Default rate: {rate * 100:.0f}%")

        tax = inp.gross_income * rate
        net = inp.gross_income - tax

        notes.append(f"Gross income: PKR {inp.gross_income:,.2f}")
        notes.append(f"Tax (WHT): PKR {tax:,.2f}")
        notes.append(f"Net received: PKR {net:,.2f}")

        return DividendTaxResult(
            income_source=inp.income_source.value,
            gross_income=inp.gross_income,
            rate_applied=rate,
            tax_payable=round(tax, 2),
            net_income=round(net, 2),
            tax_method="wht",
            notes=notes,
            sources=sources,
        )

    @staticmethod
    def format_result(result: DividendTaxResult, currency: str = "PKR") -> str:
        lines = [
            f"=== {result.income_source.replace('_', ' ').title()} Tax ===",
            f"Tax Method: {result.tax_method}",
            "",
            f"Gross Income:            {currency} {result.gross_income:>15,.2f}",
            f"Rate Applied:            {result.rate_applied * 100:>14.1f}%",
            f"Tax Payable:             {currency} {result.tax_payable:>15,.2f}",
            f"Net Income:              {currency} {result.net_income:>15,.2f}",
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
