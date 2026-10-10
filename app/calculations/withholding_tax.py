"""
Withholding Tax (WHT) Calculator - Production-Grade
====================================================

FBR WHT Sections - 40+ categories:
- Section 148: Imports
- Section 149: Salaries
- Section 150: Dividends
- Section 151: Profit on debt
- Section 152: Rent
- Section 153: Payments for goods/contracts
- Section 154: Exports
- Section 155: Utility bills
- Section 156: Petroleum products
- Section 156A: Services
- Section 158: Withdrawal of balance by company
- Section 159: Cash withdrawal from banks
- Section 160: Prize bonds, lottery
- Section 161: Indirect exports
- Section 162: Purchase of immovable property
- Section 163: Sale of immovable property
- Section 164: Purchase of vehicle
- Section 165: Functions/gatherings
- Section 168: Deemed income for non-filers (advance tax)
- Section 169: Telephone/internet bills
- Section 176: Transport business
- Section 230: Cash transactions
- Section 231: Banking instruments
- Section 233: Education
- Section 233A: Private vehicles registration
- Section 236: Real estate transactions
- Section 236A: Benami transactions
- Section 236G: Advance tax on sale/purchase of immovable property
- Section 236H: Advance tax on property for non-filers
- Section 236K: Advance tax on purchase of vehicles
- Section 236L: Functions/gatherings (advance)

Rates vary based on:
- Filer/non-filer status
- Active/non-active taxpayer
- Transaction type
- Amount thresholds
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

from app.calculations.income_tax import (
    FilingStatus, IncomeTaxCalculator, TaxYear
)


class FilerStatus(str, Enum):
    FILER = "filer"
    NON_FILER = "non_filer"
    LATE_FILER = "late_filer"


class WHTSection(str, Enum):
    SALARY_149 = "149_salary"
    DIVIDEND_150 = "150_dividend"
    PROFIT_DEBT_151 = "151_profit_debt"
    RENT_PROPERTY_152 = "152_rent_property"
    GOODS_CONTRACTS_153 = "153_goods_contracts"
    EXPORTS_154 = "154_exports"
    UTILITIES_155 = "155_utilities"
    SERVICES_156A = "156A_services"
    CASH_BANK_231 = "231_cash_bank"
    VEHICLE_236K = "236K_vehicle"
    PROPERTY_236G = "236G_property"
    EDUCATION_233 = "233_education"
    TELEPHONE_169 = "169_telephone"
    FUNCTIONS_165 = "165_functions"
    PRIZE_BONDS_160 = "160_prize_bonds"
    VEHICLE_REG_233A = "233A_vehicle_reg"


# ============================================================
# WHT RATES (FBR Rules, 2024-25)
# ============================================================

# Filer vs non-filer rates for key sections
# Format: section -> {filer_rate, non_filer_rate}
WHT_RATES = {
    # Section 150: Dividends
    WHTSection.DIVIDEND_150: {
        "filer": 0.15,
        "non_filer": 0.30,  # Double rate for non-filers
        "applies_to": "dividend_income",
    },
    # Section 151: Profit on debt (interest)
    WHTSection.PROFIT_DEBT_151: {
        "filer": 0.15,
        "non_filer": 0.30,
        "applies_to": "interest_income",
    },
    # Section 152: Rent
    WHTSection.RENT_PROPERTY_152: {
        "filer": 0.10,
        "non_filer": 0.15,
        "applies_to": "rent_payment",
        "threshold": 100_000,  # Annual minimum
    },
    # Section 153: Goods/Contracts
    WHTSection.GOODS_CONTRACTS_153: {
        "filer": 0.045,  # 4.5% for goods, varies for contracts
        "non_filer": 0.10,  # 10% or 0.6x higher
        "applies_to": "goods_purchase",
    },
    # Section 154: Exports
    WHTSection.EXPORTS_154: {
        "filer": 0.01,  # 1%
        "non_filer": 0.01,  # 1%
        "applies_to": "export_proceeds",
    },
    # Section 155: Utilities
    WHTSection.UTILITIES_155: {
        "filer": 0.10,
        "non_filer": 0.15,
        "applies_to": "utility_bills",
    },
    # Section 156A: Services
    WHTSection.SERVICES_156A: {
        "filer": 0.10,  # 10% for filers
        "non_filer": 0.15,  # 15% for non-filers
        "applies_to": "services",
    },
    # Section 231: Cash banking
    WHTSection.CASH_BANK_231: {
        "filer": 0.005,  # 0.5% for filers
        "non_filer": 0.01,  # 1% for non-filers
        "applies_to": "cash_withdrawal",
        "threshold": 50_000,  # Per transaction
    },
    # Section 236K: Vehicle purchase
    WHTSection.VEHICLE_236K: {
        "filer": 0.05,  # 5%
        "non_filer": 0.10,  # 10%
        "applies_to": "vehicle_purchase",
    },
    # Section 236G: Property purchase
    WHTSection.PROPERTY_236G: {
        "filer": 0.03,  # 3%
        "non_filer": 0.06,  # 6% (10.5% in some cases)
        "applies_to": "property_purchase",
    },
    # Section 233: Education
    WHTSection.EDUCATION_233: {
        "filer": 0.05,
        "non_filer": 0.10,
        "applies_to": "education_fees",
    },
    # Section 169: Telephone/internet
    WHTSection.TELEPHONE_169: {
        "filer": 0.075,
        "non_filer": 0.15,
        "applies_to": "telephone_bills",
    },
    # Section 165: Functions/gatherings
    WHTSection.FUNCTIONS_165: {
        "filer": 0.05,  # 5%
        "non_filer": 0.10,  # 10%
        "applies_to": "function_expenses",
        "threshold": 100_000,  # Per function
    },
    # Section 160: Prize bonds
    WHTSection.PRIZE_BONDS_160: {
        "filer": 0.15,
        "non_filer": 0.30,
        "applies_to": "prize_bonds",
    },
    # Section 233A: Vehicle registration
    WHTSection.VEHICLE_REG_233A: {
        "filer": 0.05,
        "non_filer": 0.10,
        "applies_to": "vehicle_registration",
    },
    # Section 149: Salaries — no flat rate. WHT on salary follows the
    # salaried slabs of the authoritative income_tax module, so the
    # rate is derived at calculation time (see calculate()) instead of
    # being tabulated here.
    WHTSection.SALARY_149: {
        "filer": 0.0,  # derived from the salaried slabs
        "non_filer": 0.0,  # derived from the salaried slabs
        "applies_to": "salary_income",
        "basis": "salary_slabs",
    },
}


def _default_wht_tax_year() -> TaxYear:
    """Default tax year for a WHTInput that omits one.

    Convention: the current calendar year, clamped to the nearest year the
    slab tables actually support — exactly what
    ``app/routers/assistant.py::_extract_tax_year`` does for a year named
    in a query. ``IncomeTaxCalculator.get_slabs`` only has 2024/2025/2026
    schedules, so an out-of-range year (e.g. 2027) must fall back to the
    closest supported one rather than raise a ValueError with no
    fallback.

    A dynamic default (rather than a hardcoded ``TaxYear.TY_2025``) is the
    point: without it, Section 149 salary withholding was priced on the
    2025 slabs forever and a 2026 caller silently got 2025 rates.
    """
    return min(TaxYear, key=lambda y: abs(int(y.value) - date.today().year))


@dataclass
class WHTInput:
    """Input for WHT calculation."""
    section: WHTSection
    filer_status: FilerStatus
    transaction_amount: float
    description: str = ""
    custom_rate: Optional[float] = None  # Override rate if needed
    # Year whose slabs price a Section 149 (salary) deduction. Defaulted
    # (not required) so the callers that omit the year — app/calculations/
    # engine.py._calc_wht builds WHTInput from a plain dict — keep
    # working; see _default_wht_tax_year() for the default choice.
    tax_year: TaxYear = field(default_factory=lambda: _default_wht_tax_year())


@dataclass
class WHTResult:
    """Result of WHT calculation."""
    section: str
    filer_status: str
    transaction_amount: float
    rate_applied: float
    wht_amount: float
    net_amount: float  # After WHT deduction
    # Year whose slabs produced every figure above, so a caller can tell
    # which Finance Act schedule was applied without echoing the inputs.
    tax_year: TaxYear
    threshold_check: bool = True
    notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


class WithholdingTaxCalculator:
    """
    Production-grade Withholding Tax calculator.

    Covers 40+ WHT sections with proper filer/non-filer rate differentiation.
    """

    @staticmethod
    def validate_input(inp: WHTInput) -> tuple[bool, str]:
        """Validate WHT input."""
        if inp.transaction_amount < 0:
            return False, "Transaction amount cannot be negative."
        if inp.section not in WHT_RATES:
            return False, f"Unknown WHT section: {inp.section}"
        return True, ""

    @staticmethod
    def get_rate(section: WHTSection, filer_status: FilerStatus, custom_rate: Optional[float] = None) -> float:
        """Get applicable WHT rate."""
        if custom_rate is not None:
            return custom_rate
        rates = WHT_RATES.get(section, {})
        if rates.get("basis") == "salary_slabs":
            # Section 149 has no flat rate — WHT follows the salaried
            # slabs, see calculate(). Never fall back to 0%.
            raise ValueError(
                "WHT Section 149 (salary) has no flat rate: tax follows the "
                "salaried slabs, use WithholdingTaxCalculator.calculate()."
            )
        if filer_status == FilerStatus.FILER:
            return rates.get("filer", 0.0)
        return rates.get("non_filer", rates.get("filer", 0.0))

    @staticmethod
    def check_threshold(section: WHTSection, amount: float) -> tuple[bool, str]:
        """Check if transaction meets minimum threshold."""
        rates = WHT_RATES.get(section, {})
        threshold = rates.get("threshold")
        if threshold and amount < threshold:
            return False, f"Amount {amount:,.0f} below threshold of {threshold:,.0f} for this section"
        return True, ""

    @staticmethod
    def calculate(inp: WHTInput) -> WHTResult:
        """Calculate WHT for a single transaction."""
        valid, error = WithholdingTaxCalculator.validate_input(inp)
        if not valid:
            raise ValueError(error)

        notes = []
        sources = [
            "Income Tax Ordinance 2001",
            f"WHT Section: {inp.section.value}",
            f"FBR Finance Act {inp.tax_year.value}",
        ]

        # Threshold check — below the threshold no WHT is due at all
        # (the threshold was previously only noted while the FULL
        # amount was still taxed).
        threshold_ok, threshold_note = WithholdingTaxCalculator.check_threshold(inp.section, inp.transaction_amount)
        if not threshold_ok:
            notes.append(f"⚠️  {threshold_note}")
            notes.append(
                f"No WHT deducted: amount PKR {inp.transaction_amount:,.2f} is below the threshold."
            )
            return WHTResult(
                section=inp.section.value,
                filer_status=inp.filer_status.value,
                transaction_amount=inp.transaction_amount,
                rate_applied=0.0,
                wht_amount=0.0,
                net_amount=inp.transaction_amount,
                tax_year=inp.tax_year,
                threshold_check=False,
                notes=notes,
                sources=sources,
            )

        if inp.section == WHTSection.SALARY_149 and inp.custom_rate is None:
            # Section 149 (salary) has no flat WHT rate — tax follows the
            # salaried slabs of the authoritative income_tax module.
            # Assumption: transaction_amount is ANNUAL salary.
            slabs = IncomeTaxCalculator.get_slabs(FilingStatus.SALARIED, inp.tax_year)
            salary_tax, _ = IncomeTaxCalculator.calculate_tax_on_slab(inp.transaction_amount, slabs)
            rate = salary_tax / inp.transaction_amount if inp.transaction_amount > 0 else 0.0
            wht_amount = salary_tax
            notes.append(
                f"Salary slabs applied (annual salary basis): effective {rate * 100:.2f}%"
            )
        else:
            # Get rate
            rate = WithholdingTaxCalculator.get_rate(inp.section, inp.filer_status, inp.custom_rate)
            notes.append(f"Rate applied: {rate * 100:.2f}% ({inp.filer_status.value})")

            # Calculate
            wht_amount = inp.transaction_amount * rate

        net_amount = inp.transaction_amount - wht_amount

        notes.append(f"Gross Amount: PKR {inp.transaction_amount:,.2f}")
        notes.append(f"WHT Deducted: PKR {wht_amount:,.2f}")
        notes.append(f"Net Payable: PKR {net_amount:,.2f}")

        return WHTResult(
            section=inp.section.value,
            filer_status=inp.filer_status.value,
            transaction_amount=inp.transaction_amount,
            rate_applied=rate,
            wht_amount=round(wht_amount, 2),
            net_amount=round(net_amount, 2),
            tax_year=inp.tax_year,
            threshold_check=threshold_ok,
            notes=notes,
            sources=sources,
        )

    @staticmethod
    def calculate_multiple(inputs: list[WHTInput]) -> list[WHTResult]:
        """Calculate WHT for multiple transactions."""
        return [WithholdingTaxCalculator.calculate(inp) for inp in inputs]

    @staticmethod
    def format_result(result: WHTResult, currency: str = "PKR") -> str:
        """Format result as human-readable string."""
        lines = [
            f"=== WHT Calculation (Section {result.section}) ===",
            f"Tax Year: {result.tax_year.value}",
            f"Filer Status: {result.filer_status}",
            "",
            f"Transaction Amount:      {currency} {result.transaction_amount:>15,.2f}",
            f"Rate Applied:            {result.rate_applied * 100:>14.2f}%",
            f"WHT Deducted:            {currency} {result.wht_amount:>15,.2f}",
            f"Net Payable:             {currency} {result.net_amount:>15,.2f}",
            "",
            f"Threshold Check:         {'✓ Pass' if result.threshold_check else '⚠️ Below threshold'}",
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
