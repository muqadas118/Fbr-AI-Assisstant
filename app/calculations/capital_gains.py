"""
Capital Gains Tax (CGT) Calculator - Production-Grade
=====================================================

CGT on:
- Immovable property (Section 37)
- Securities (Section 37A)
- Capital assets held < or > 4 years
- Filer vs non-filer rates differ
- Holding period affects tax rate

CGT Rates (TY 2025):
- Property held >= 1 year: 10% (filer), 15% (non-filer)
  (the same rate is used for 1-2, 2-3, 3-4 and over 4 years)
- Property held < 1 year: 15% (filer), 20% (non-filer)
- Securities (PSX) held > 1 year: 12.5%
- Securities held < 1 year: 15%
"""

from dataclasses import dataclass, field
from enum import Enum


class AssetType(str, Enum):
    IMMOVABLE_PROPERTY = "immovable_property"
    SECURITIES_PSX = "securities_psx"
    STOCK_FUNDS = "stock_funds"
    BONDS = "bonds"
    OTHER_ASSETS = "other_assets"


@dataclass
class CGTInput:
    """Input for CGT calculation."""
    asset_type: AssetType
    acquisition_cost: float
    sale_value: float
    holding_period_years: float
    filer_status: str = "filer"  # "filer" or "non_filer"
    improvement_cost: float = 0.0  # Capital improvements
    selling_expenses: float = 0.0  # Broker, transfer, etc.


@dataclass
class CGTResult:
    """Result of CGT calculation."""
    asset_type: str
    sale_value: float
    acquisition_cost: float
    improvement_cost: float
    selling_expenses: float
    cost_basis: float
    gain_amount: float
    holding_period: float
    applicable_rate: float
    cgt_payable: float
    notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


class CapitalGainsCalculator:
    """Production-grade Capital Gains Tax calculator."""

    @staticmethod
    def validate_input(inp: CGTInput) -> tuple[bool, str]:
        if inp.acquisition_cost < 0:
            return False, "Acquisition cost cannot be negative."
        if inp.sale_value < 0:
            return False, "Sale value cannot be negative."
        if inp.holding_period_years < 0:
            return False, "Holding period cannot be negative."
        return True, ""

    @staticmethod
    def get_rate(asset_type: AssetType, years: float, filer: bool = True) -> float:
        """Get applicable CGT rate."""
        if asset_type == AssetType.IMMOVABLE_PROPERTY:
            if years < 1:
                return 0.15 if filer else 0.20
            elif years < 2:
                return 0.10 if filer else 0.15
            elif years < 3:
                return 0.10 if filer else 0.15
            elif years < 4:
                return 0.10 if filer else 0.15
            else:  # > 4 years
                return 0.10 if filer else 0.15
        elif asset_type == AssetType.SECURITIES_PSX:
            if years < 1:
                return 0.15
            else:
                return 0.125
        return 0.10 if filer else 0.15

    @staticmethod
    def calculate(inp: CGTInput) -> CGTResult:
        valid, error = CapitalGainsCalculator.validate_input(inp)
        if not valid:
            raise ValueError(error)

        is_filer = inp.filer_status == "filer"
        cost_basis = inp.acquisition_cost + inp.improvement_cost
        gain = inp.sale_value - cost_basis - inp.selling_expenses
        rate = CapitalGainsCalculator.get_rate(
            inp.asset_type, inp.holding_period_years, is_filer
        )

        cgt = max(0, gain) * rate

        notes = [
            f"Asset: {inp.asset_type.value}",
            f"Acquisition cost: PKR {inp.acquisition_cost:,.2f}",
            f"Improvements: PKR {inp.improvement_cost:,.2f}",
            f"Selling expenses: PKR {inp.selling_expenses:,.2f}",
            f"Cost basis: PKR {cost_basis:,.2f}",
            f"Sale value: PKR {inp.sale_value:,.2f}",
            f"Capital gain: PKR {gain:,.2f}",
            f"Holding period: {inp.holding_period_years:.2f} years",
            f"Filer status: {inp.filer_status}",
            f"CGT rate: {rate * 100:.1f}%",
        ]

        sources = [
            "Income Tax Ordinance 2001 - Section 37 (CGT on Property)",
            "Income Tax Ordinance 2001 - Section 37A (CGT on Securities)",
        ]

        return CGTResult(
            asset_type=inp.asset_type.value,
            sale_value=inp.sale_value,
            acquisition_cost=inp.acquisition_cost,
            improvement_cost=inp.improvement_cost,
            selling_expenses=inp.selling_expenses,
            cost_basis=cost_basis,
            gain_amount=round(gain, 2),
            holding_period=inp.holding_period_years,
            applicable_rate=rate,
            cgt_payable=round(cgt, 2),
            notes=notes,
            sources=sources,
        )

    @staticmethod
    def format_result(result: CGTResult, currency: str = "PKR") -> str:
        lines = [
            "=== Capital Gains Tax Calculation ===",
            f"Asset: {result.asset_type}",
            "",
            "--- Cost Basis ---",
            f"Acquisition Cost:        {currency} {result.acquisition_cost:>15,.2f}",
            f"Improvement Cost:        {currency} {result.improvement_cost:>15,.2f}",
            f"Selling Expenses:        {currency} {result.selling_expenses:>15,.2f}",
            f"Total Cost Basis:        {currency} {result.cost_basis:>15,.2f}",
            "",
            "--- Gain Computation ---",
            f"Sale Value:              {currency} {result.sale_value:>15,.2f}",
            f"Less: Cost Basis:        {currency} {result.cost_basis:>15,.2f}",
            f"Capital Gain:            {currency} {result.gain_amount:>15,.2f}",
            "",
            "--- Tax Computation ---",
            f"Holding Period:          {result.holding_period:>14.2f} years",
            f"CGT Rate:                {result.applicable_rate * 100:>14.1f}%",
            f"CGT Payable:             {currency} {result.cgt_payable:>15,.2f}",
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
