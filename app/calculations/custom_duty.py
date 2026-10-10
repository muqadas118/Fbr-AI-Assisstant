"""
Custom/Import Duty Calculator - Production-Grade
=================================================

For goods imported into Pakistan:
1. Customs Duty (CD) - Section 18, based on HS code
2. Sales Tax (ST) - Section 3
3. Income Tax (WHT under Section 148) - on imports
4. Additional Customs Duty (ACD) - 0-4% (mostly 0% in FY24-25)
5. Regulatory Duty (RD) - varies by item

Approach: Simplified - based on common HS code categories
Real implementation would query Pakistan Customs tariff database.
"""

from dataclasses import dataclass, field
from enum import Enum


class HSCategory(str, Enum):
    """Common HS code categories for simplified duty calculation."""
    ELECTRONICS = "electronics"  # Smartphones, laptops
    VEHICLES = "vehicles"  # Cars
    TEXTILES = "textiles"  # Cloth, garments
    FOOD = "food"  # Food items
    MACHINERY = "machinery"  # Industrial
    CHEMICALS = "chemicals"
    PHARMA = "pharmaceuticals"
    COSMETICS = "cosmetics"
    JEWELLERY = "jewellery"
    FURNITURE = "furniture"
    DEFAULT = "default"


# Custom duty rates (simplified, based on common tariff)
# Format: {category: {cd_rate, st_rate, wht_rate, acd_rate, rd_rate}}
CUSTOMS_RATES = {
    HSCategory.ELECTRONICS: {
        "cd": 0.20,      # 20% customs duty
        "st": 0.18,      # 18% sales tax
        "wht": 0.06,     # 6% WHT (Section 148)
        "acd": 0.0,      # 0% ACD
        "rd": 0.0,       # 0% RD (some items have)
    },
    HSCategory.VEHICLES: {
        "cd": 0.50,      # Up to 50% for cars (varies by engine capacity)
        "st": 0.18,
        "wht": 0.06,
        "acd": 0.0,
        "rd": 0.30,      # Up to 30% regulatory
    },
    HSCategory.TEXTILES: {
        "cd": 0.20,
        "st": 0.18,
        "wht": 0.06,
        "acd": 0.0,
        "rd": 0.0,
    },
    HSCategory.FOOD: {
        "cd": 0.20,
        "st": 0.10,      # Reduced for essential foods
        "wht": 0.06,
        "acd": 0.0,
        "rd": 0.0,
    },
    HSCategory.MACHINERY: {
        "cd": 0.10,
        "st": 0.18,
        "wht": 0.06,
        "acd": 0.0,
        "rd": 0.0,
    },
    HSCategory.CHEMICALS: {
        "cd": 0.20,
        "st": 0.18,
        "wht": 0.06,
        "acd": 0.0,
        "rd": 0.0,
    },
    HSCategory.PHARMA: {
        "cd": 0.10,
        "st": 0.10,      # Reduced
        "wht": 0.06,
        "acd": 0.0,
        "rd": 0.0,
    },
    HSCategory.COSMETICS: {
        "cd": 0.25,
        "st": 0.18,
        "wht": 0.06,
        "acd": 0.0,
        "rd": 0.10,
    },
    HSCategory.JEWELLERY: {
        "cd": 0.05,
        "st": 0.18,
        "wht": 0.06,
        "acd": 0.0,
        "rd": 0.0,
    },
    HSCategory.FURNITURE: {
        "cd": 0.20,
        "st": 0.18,
        "wht": 0.06,
        "acd": 0.0,
        "rd": 0.0,
    },
    HSCategory.DEFAULT: {
        "cd": 0.20,
        "st": 0.18,
        "wht": 0.06,
        "acd": 0.0,
        "rd": 0.0,
    },
}


@dataclass
class CustomDutyInput:
    """Input for custom duty calculation."""
    cif_value: float  # Cost + Insurance + Freight
    hs_category: HSCategory = HSCategory.DEFAULT
    filer_status: str = "filer"  # Affects WHT
    is_commercial: bool = True  # Commercial vs personal import


@dataclass
class CustomDutyResult:
    """Result of custom duty calculation."""
    cif_value: float
    customs_duty: float
    sales_tax: float  # Calculated on (CIF + CD)
    wht_148: float  # Section 148 - calculated on (CIF + CD + ST)
    additional_cd: float
    regulatory_duty: float
    total_duty: float
    landed_cost: float  # CIF + all duties
    effective_rate: float
    notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


class CustomDutyCalculator:
    """Production-grade Custom Duty calculator."""

    @staticmethod
    def validate_input(inp: CustomDutyInput) -> tuple[bool, str]:
        if inp.cif_value < 0:
            return False, "CIF value cannot be negative."
        return True, ""

    @staticmethod
    def is_non_filer(filer_status: str) -> bool:
        """True when the importer is a non-filer.

        Anything that is not exactly "filer" is treated as a non-filer
        (conservative: the higher WHT rate applies).
        """
        return str(filer_status).strip().lower() != "filer"

    @staticmethod
    def calculate(inp: CustomDutyInput) -> CustomDutyResult:
        valid, error = CustomDutyCalculator.validate_input(inp)
        if not valid:
            raise ValueError(error)

        rates = CUSTOMS_RATES[inp.hs_category]
        notes = []
        sources = [
            "Pakistan Customs Act 1969 - Section 18",
            f"HS Category: {inp.hs_category.value}",
            "Sales Tax Act 1990",
            "Income Tax Ordinance - Section 148 (Imports)",
        ]

        # Step 1: Customs Duty on CIF
        cd = inp.cif_value * rates["cd"]
        notes.append(f"Customs Duty @ {rates['cd'] * 100:.0f}% on CIF: PKR {cd:,.2f}")

        # Step 2: Sales Tax on (CIF + CD)
        st_base = inp.cif_value + cd
        st = st_base * rates["st"]
        notes.append(f"Sales Tax @ {rates['st'] * 100:.0f}% on (CIF+CD): PKR {st:,.2f}")

        # Step 3: WHT Section 148 on (CIF + CD + ST)
        wht_base = st_base + st
        wht_rate = rates["wht"]
        # filer_status is documented as affecting WHT: the tariff table
        # publishes only the filer rate, so a non-filer is charged
        # double it — the same doubling convention withholding_tax.py
        # uses for Sections 150/151 (filer 15% -> non-filer 30%).
        # Assumption: personal (non-commercial) imports pay the same
        # Section 148 rate; this simplified model has no separate
        # personal-import rate.
        if CustomDutyCalculator.is_non_filer(inp.filer_status):
            wht_rate = wht_rate * 2
            notes.append(
                f"Non-filer importer: WHT rate {rates['wht'] * 100:.0f}% doubled to "
                f"{wht_rate * 100:.0f}% (Section 148)"
            )
        wht = wht_base * wht_rate
        notes.append(f"WHT (Section 148) @ {wht_rate * 100:.0f}% on (CIF+CD+ST): PKR {wht:,.2f}")

        # Step 4: Additional CD
        acd = st_base * rates["acd"]
        notes.append(f"Additional CD @ {rates['acd'] * 100:.0f}%: PKR {acd:,.2f}")

        # Step 5: Regulatory Duty
        rd = st_base * rates["rd"]
        notes.append(f"Regulatory Duty @ {rates['rd'] * 100:.0f}%: PKR {rd:,.2f}")

        # Total
        total = cd + st + wht + acd + rd
        landed_cost = inp.cif_value + total
        effective_rate = (total / inp.cif_value * 100) if inp.cif_value > 0 else 0

        return CustomDutyResult(
            cif_value=inp.cif_value,
            customs_duty=round(cd, 2),
            sales_tax=round(st, 2),
            wht_148=round(wht, 2),
            additional_cd=round(acd, 2),
            regulatory_duty=round(rd, 2),
            total_duty=round(total, 2),
            landed_cost=round(landed_cost, 2),
            effective_rate=round(effective_rate, 2),
            notes=notes,
            sources=sources,
        )

    @staticmethod
    def format_result(result: CustomDutyResult, currency: str = "PKR") -> str:
        lines = [
            "=== Custom/Import Duty Calculation ===",
            "",
            "--- Base Value ---",
            f"CIF Value:               {currency} {result.cif_value:>15,.2f}",
            "",
            "--- Duties & Taxes ---",
            f"Customs Duty:            {currency} {result.customs_duty:>15,.2f}",
            f"Sales Tax:               {currency} {result.sales_tax:>15,.2f}",
            f"WHT (Section 148):       {currency} {result.wht_148:>15,.2f}",
            f"Additional CD:           {currency} {result.additional_cd:>15,.2f}",
            f"Regulatory Duty:         {currency} {result.regulatory_duty:>15,.2f}",
            "",
            "--- Total ---",
            f"Total Duty:              {currency} {result.total_duty:>15,.2f}",
            f"Landed Cost:             {currency} {result.landed_cost:>15,.2f}",
            f"Effective Duty Rate:     {result.effective_rate:>14.2f}%",
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
