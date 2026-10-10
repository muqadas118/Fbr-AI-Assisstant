"""
Federal Excise Duty (FED) Calculator - Production-Grade
========================================================

FED is charged on:
- Goods (Schedule I - specific rates)
- Services (Schedule II - specific rates)
- Sugar, beverages, cigarettes
- Cement, fertilizers (selective)
- Steel, petroleum products
- Mobile phone usage, etc.

Key sections:
- Federal Excise Act 2005
- Various SROs specifying rates
"""

from dataclasses import dataclass, field
from enum import Enum


class FEDCategory(str, Enum):
    CIGARETTES = "cigarettes"
    BEVERAGES_AERATED = "beverages_aerated"
    BEVERAGES_NON_AERATED = "beverages_non_aerated"
    SUGAR = "sugar"
    CEMENT = "cement"
    FERTILIZER = "fertilizer"
    STEEL = "steel"
    PETROLEUM = "petroleum"
    MOBILE_PHONE = "mobile_phone"
    TELECOM_SERVICES = "telecom_services"
    INSURANCE = "insurance"
    AIR_TRAVEL = "air_travel"
    FILTER_CIGARETTE = "filter_cigarette"
    JEWELLERY = "jewellery"
    COSMETICS = "cosmetics"
    LUBRICANTS = "lubricants"


# FED rates (per Finance Act 2024-25, latest SROs)
# Format: category -> {rate, basis, unit}
FED_RATES = {
    FEDCategory.CIGARETTES: {"rate": 5_900, "basis": "per_1000_sticks", "unit": "PKR"},
    FEDCategory.FILTER_CIGARETTE: {"rate": 1_650, "basis": "per_kg", "unit": "PKR"},
    FEDCategory.BEVERAGES_AERATED: {"rate": 0.20, "basis": "ad_valorem", "unit": "percentage"},
    FEDCategory.BEVERAGES_NON_AERATED: {"rate": 0.10, "basis": "ad_valorem", "unit": "percentage"},
    FEDCategory.SUGAR: {"rate": 0.50, "basis": "per_kg", "unit": "PKR"},
    FEDCategory.CEMENT: {"rate": 0.025, "basis": "ad_valorem", "unit": "percentage"},
    FEDCategory.FERTILIZER: {"rate": 0.05, "basis": "ad_valorem", "unit": "percentage"},
    FEDCategory.STEEL: {"rate": 0.05, "basis": "ad_valorem", "unit": "percentage"},
    FEDCategory.PETROLEUM: {"rate": 0.10, "basis": "ad_valorem", "unit": "percentage"},
    FEDCategory.MOBILE_PHONE: {"rate": 0.10, "basis": "ad_valorem", "unit": "percentage"},
    FEDCategory.TELECOM_SERVICES: {"rate": 0.17, "basis": "ad_valorem", "unit": "percentage"},
    FEDCategory.INSURANCE: {"rate": 0.16, "basis": "ad_valorem", "unit": "percentage"},
    FEDCategory.AIR_TRAVEL: {"rate": 0.20, "basis": "ad_valorem", "unit": "percentage"},
    FEDCategory.JEWELLERY: {"rate": 0.03, "basis": "ad_valorem", "unit": "percentage"},
    FEDCategory.COSMETICS: {"rate": 0.20, "basis": "ad_valorem", "unit": "percentage"},
    FEDCategory.LUBRICANTS: {"rate": 0.20, "basis": "ad_valorem", "unit": "percentage"},
}


@dataclass
class FEDInput:
    """Input for FED calculation."""
    category: FEDCategory
    value: float  # Price/value in PKR
    # Quantity for per-unit (non ad-valorem) categories. Unit
    # convention: number of taxed units — THOUSANDS of sticks for
    # `per_1000_sticks` and KILOGRAMS for `per_kg`.
    quantity: float = 0.0
    description: str = ""


@dataclass
class FEDResult:
    """Result of FED calculation."""
    category: str
    basis: str
    value: float
    rate: float
    fed_amount: float
    notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


class FederalExciseCalculator:
    """Production-grade Federal Excise Duty calculator."""

    @staticmethod
    def validate_input(inp: FEDInput) -> tuple[bool, str]:
        if inp.value < 0:
            return False, "Value cannot be negative."
        if inp.quantity < 0:
            return False, "Quantity cannot be negative."
        if inp.category not in FED_RATES:
            return False, f"Unknown FED category: {inp.category}"
        if FED_RATES[inp.category]["basis"] != "ad_valorem" and inp.quantity < 1:
            # Per-unit FED is quantity x rate with `value` ignored, so
            # a zero quantity would silently return 0 FED.
            return False, (
                f"Quantity must be at least 1 for the {inp.category.value} category "
                f"({FED_RATES[inp.category]['basis']}); the FED value is computed "
                "from quantity only, `value` is used for ad-valorem categories."
            )
        return True, ""

    @staticmethod
    def calculate(inp: FEDInput) -> FEDResult:
        valid, error = FederalExciseCalculator.validate_input(inp)
        if not valid:
            raise ValueError(error)

        config = FED_RATES[inp.category]
        notes = []
        sources = [
            "Federal Excise Act 2005",
            f"Schedule: {inp.category.value}",
            "FBR SROs (latest)",
        ]

        if config["basis"] == "ad_valorem":
            fed = inp.value * config["rate"]
            notes.append(f"FED @ {config['rate'] * 100:.1f}% on value PKR {inp.value:,.2f}")
        elif config["basis"] == "per_1000_sticks":
            fed = inp.quantity * config["rate"]  # quantity in 1000s
            notes.append(f"FED @ PKR {config['rate']:,} per 1000 sticks × {inp.quantity}")
        elif config["basis"] == "per_kg":
            fed = inp.quantity * config["rate"]
            notes.append(f"FED @ PKR {config['rate']} per kg × {inp.quantity} kg")
        else:
            fed = 0.0
            notes.append(f"Unknown basis: {config['basis']}")

        return FEDResult(
            category=inp.category.value,
            basis=config["basis"],
            value=inp.value,
            rate=config["rate"],
            fed_amount=round(fed, 2),
            notes=notes,
            sources=sources,
        )

    @staticmethod
    def format_result(result: FEDResult, currency: str = "PKR") -> str:
        lines = [
            "=== Federal Excise Duty (FED) ===",
            f"Category: {result.category}",
            f"Basis: {result.basis}",
            "",
            f"Value/Quantity:          {currency} {result.value:>15,.2f}",
            f"Rate Applied:            {result.rate:>15}",
            f"FED Payable:             {currency} {result.fed_amount:>15,.2f}",
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
