"""
Sales Tax Calculator - Production-Grade
========================================

Handles:
- Output tax (sales)
- Input tax (purchases)
- Net payable / refundable
- Sales tax on services (provincial/federal)
- Sales tax on goods (varies by category)
- Sales tax on imports
- Reduced rate items (3rd schedule)
- Exempt items (5th/6th schedule)
- Punjab/Sindh/KPK/Balochistan service tax
- Retail-stage taxation
"""

from dataclasses import dataclass, field
from enum import Enum


class SalesTaxType(str, Enum):
    GOODS = "goods"
    SERVICES = "services"
    IMPORTS = "imports"
    RETAIL = "retail"


class SalesTaxProvince(str, Enum):
    PUNJAB = "punjab"
    SINDH = "sindh"
    KPK = "kpk"
    BALOCHISTAN = "balochistan"
    ISLAMABAD = "islamabad"
    FEDERAL = "federal"  # Federal services


# Sales tax rates (as of Finance Act 2024-25)
# Federal GST rate: 18% standard
STANDARD_GST_RATE = 0.18

# Reduced rate items (commonly used)
REDUCED_RATES = {
    "agriculture_inputs": 0.05,      # Fertilizer, seeds
    "medicines_local": 0.10,         # Locally manufactured medicines
    "edible_oil": 0.10,
    "sugar": 0.17,
    "textiles_local": 0.17,         # Most textiles
    "electric_vehicles_low": 0.01,  # Up to 50kWh
    "electric_vehicles_mid": 0.06,  # 50-100kWh
    "three_wheeler_ev": 0.01,
    "cng": 0.05,
    "computer_laptops": 0.05,       # ICT items
    "smartphones_local": 0.10,
    "smartphones_imported": 0.18,
    "solar_panels": 0.05,
    "baby_food": 0.10,
}

# Service tax rates by province (PST/SST)
PROVINCIAL_SERVICE_RATES = {
    "punjab": 0.16,      # 16% Punjab
    "sindh": 0.15,        # 15% Sindh
    "kpk": 0.15,          # 15% KPK
    "balochistan": 0.15,  # 15% Balochistan
    "islamabad": 0.16,    # 16% ICT
}

# Federal services taxed at 18%
FEDERAL_SERVICES_RATE = 0.18

# Zero-rated exports
EXPORT_RATE = 0.0


@dataclass
class SalesTaxInput:
    """Input for sales tax calculation."""
    sales_tax_type: SalesTaxType = SalesTaxType.GOODS
    province: SalesTaxProvince = SalesTaxProvince.PUNJAB

    # For output tax (sales)
    sales_value: float = 0.0
    sales_category: str = "standard"  # or specific category like "textiles_local"

    # For input tax (purchases)
    purchases_value: float = 0.0
    purchases_category: str = "standard"

    # Imports
    import_value: float = 0.0
    import_category: str = "standard"
    # NOTE: `is_retail_supplier` and `customs_duty` were removed — both were
    # declared but never read by any calculation path (retail-stage tax is
    # selected by sales_tax_type=RETAIL; imports are taxed on import_value
    # only), so accepting them silently ignored the caller's input.

    # Exemptions
    is_export: bool = False  # Zero-rated if export
    is_exempt: bool = False  # Fully exempt

    # Services-specific
    service_category: str = "general"
    is_federal_service: bool = False  # Federal vs provincial


@dataclass
class SalesTaxResult:
    """Result of sales tax calculation."""
    output_tax: float
    input_tax: float
    net_payable: float  # Positive = payable, Negative = refundable
    sales_value: float
    purchases_value: float
    applicable_rate: float
    exempt_amount: float = 0.0
    zero_rated_amount: float = 0.0
    notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    breakdown: list[dict] = field(default_factory=list)


class SalesTaxCalculator:
    """
    Production-grade sales tax calculator.

    Handles goods, services, imports, and retail-stage taxation
    per FBR rules and provincial tax laws.
    """

    @staticmethod
    def validate_input(inp: SalesTaxInput) -> tuple[bool, str]:
        """Validate sales tax input."""
        if inp.sales_value < 0:
            return False, "Sales value cannot be negative."
        if inp.purchases_value < 0:
            return False, "Purchases value cannot be negative."
        if inp.import_value < 0:
            return False, "Import value cannot be negative."
        return True, ""

    @staticmethod
    def get_applicable_rate(inp: SalesTaxInput) -> tuple[float, str]:
        """
        Determine applicable sales tax rate based on input.

        Returns (rate, reason).
        """
        # Check export (zero-rated)
        if inp.is_export:
            return EXPORT_RATE, "Zero-rated export"

        # Check exempt
        if inp.is_exempt:
            return 0.0, "Exempt item"

        # Services
        if inp.sales_tax_type == SalesTaxType.SERVICES:
            if inp.is_federal_service:
                return FEDERAL_SERVICES_RATE, f"Federal service ({inp.service_category})"
            else:
                # `federal` (and any unmapped province) is not a
                # provincial rate — fall back to the federal services
                # rate, not to a provincial 16%.
                rate = PROVINCIAL_SERVICE_RATES.get(
                    inp.province.value, FEDERAL_SERVICES_RATE
                )
                return rate, f"{inp.province.value.title()} provincial service tax"

        # Goods
        if inp.sales_tax_type == SalesTaxType.GOODS:
            if inp.sales_category == "standard":
                return STANDARD_GST_RATE, "Standard GST rate (18%)"
            if inp.sales_category in REDUCED_RATES:
                return REDUCED_RATES[inp.sales_category], f"Reduced rate ({inp.sales_category})"
            return STANDARD_GST_RATE, f"Default standard rate for {inp.sales_category}"

        # Imports
        if inp.sales_tax_type == SalesTaxType.IMPORTS:
            if inp.import_category in REDUCED_RATES:
                return REDUCED_RATES[inp.import_category], f"Reduced import rate ({inp.import_category})"
            return STANDARD_GST_RATE, "Standard import rate (18%)"

        # Retail
        if inp.sales_tax_type == SalesTaxType.RETAIL:
            return STANDARD_GST_RATE, "Retail-stage sales tax"

        return STANDARD_GST_RATE, "Default rate"

    @staticmethod
    def calculate(inp: SalesTaxInput) -> SalesTaxResult:
        """Calculate sales tax with full breakdown."""
        valid, error = SalesTaxCalculator.validate_input(inp)
        if not valid:
            raise ValueError(error)

        notes = []
        sources = [
            "FBR Sales Tax Act 1990",
            f"Provincial Sales Tax ({inp.province.value.title()})",
        ]

        rate, rate_reason = SalesTaxCalculator.get_applicable_rate(inp)
        notes.append(f"Applicable rate: {rate * 100:.1f}% ({rate_reason})")

        # ============================================================
        # Determine applicable value based on tax type
        # ============================================================
        if inp.sales_tax_type == SalesTaxType.IMPORTS:
            sales_value = inp.import_value
            purchases_value = inp.purchases_value
            # Imports: GST on (CIF value + customs duty + other charges)
            # Simplified: GST on import value (CIF)
        else:
            sales_value = inp.sales_value
            purchases_value = inp.purchases_value

        # ============================================================
        # Output Tax (on sales)
        # ============================================================
        # Defaults so every branch leaves both flags bound
        # (is_export previously crashed with UnboundLocalError on exempt).
        zero_rated = 0.0
        exempt = 0.0

        if inp.is_export:
            output_tax = 0.0
            zero_rated = sales_value
            notes.append("Zero-rated export - no output tax but input tax refundable")
        elif inp.is_exempt:
            output_tax = 0.0
            zero_rated = 0.0
            exempt = sales_value
            notes.append("Exempt - no output tax, input tax not refundable")
            # FIX: exempt sales full ITC - Section 8(1)(b) STA 1990 disallows input
            # tax on exempt supplies, so exempt input tax is zero; the input-tax
            # block below now credits only taxable-supply ITC (value - exempt share).
        else:
            zero_rated = 0.0
            exempt = 0.0
            output_tax = sales_value * rate

        # ============================================================
        # Input Tax (on purchases)
        # ============================================================
        if inp.purchases_value > 0:
            input_rate, input_reason = SalesTaxCalculator.get_applicable_rate(
                SalesTaxInput(
                    sales_tax_type=inp.sales_tax_type,
                    province=inp.province,
                    sales_value=inp.purchases_value,
                    sales_category=inp.purchases_category,
                )
            )
            input_tax = inp.purchases_value * input_rate
            if inp.is_exempt:
                # FIX: exempt sales full ITC - Section 8(1)(b) STA 1990 disallows
                # input tax on exempt supplies. Credit only the taxable-supply
                # share (attribution); with single-flag exempt semantics this is
                # the whole ITC restricted to zero when all supplies are exempt.
                taxable_share = (sales_value - exempt) / sales_value if sales_value > 0 else 0.0
                full_input_tax = input_tax
                input_tax = input_tax * taxable_share
                notes.append(
                    f"Input tax restricted to taxable supplies: PKR {input_tax:,.2f} "
                    f"of PKR {full_input_tax:,.2f} (taxable share {taxable_share * 100:.1f}%); "
                    "ITC on exempt supplies not allowed - Section 8(1)(b), STA 1990"
                )
            else:
                notes.append(f"Input tax @ {input_rate * 100:.1f}% on purchases: PKR {input_tax:,.2f}")
        else:
            input_tax = 0.0

        # Net payable
        net_payable = output_tax - input_tax
        if net_payable < 0:
            notes.append(f"Net position: REFUNDABLE (PKR {abs(net_payable):,.2f})")
        else:
            notes.append(f"Net position: PAYABLE (PKR {net_payable:,.2f})")

        sources.extend([
            "Sales Tax Act 1990 - Section 3 (Charge of Sales Tax)",
            "Sales Tax Act 1990 - Section 8 (Input Tax Credit)",
        ])

        return SalesTaxResult(
            output_tax=round(output_tax, 2),
            input_tax=round(input_tax, 2),
            net_payable=round(net_payable, 2),
            sales_value=sales_value,
            purchases_value=purchases_value,
            applicable_rate=rate,
            exempt_amount=exempt,
            zero_rated_amount=zero_rated,
            notes=notes,
            sources=sources,
            breakdown=[{
                "component": "Output Tax",
                "base": sales_value,
                "rate": f"{rate * 100:.1f}%",
                "amount": output_tax,
            }, {
                "component": "Input Tax",
                "base": inp.purchases_value,
                "rate": f"{rate * 100:.1f}%",
                "amount": input_tax,
            }, {
                "component": "Net Payable/Refundable",
                "amount": net_payable,
            }],
        )

    @staticmethod
    def format_result(result: SalesTaxResult, currency: str = "PKR") -> str:
        """Format result as human-readable string."""
        lines = [
            "=== Sales Tax Calculation ===",
            "",
            "--- Output Tax (Sales) ---",
            f"Sales Value:             {currency} {result.sales_value:>15,.2f}",
            f"Applicable Rate:         {result.applicable_rate * 100:>14.1f}%",
            f"Output Tax:              {currency} {result.output_tax:>15,.2f}",
            "",
            "--- Input Tax (Purchases) ---",
            f"Purchases Value:         {currency} {result.purchases_value:>15,.2f}",
            f"Input Tax:               {currency} {result.input_tax:>15,.2f}",
            "",
            "--- Net Position ---",
            f"Net {'Payable' if result.net_payable >= 0 else 'Refundable'}:    "
            f"{currency} {abs(result.net_payable):>15,.2f}",
            "",
            "--- Additional Info ---",
        ]
        if result.zero_rated_amount > 0:
            lines.append(f"Zero-Rated Amount:       {currency} {result.zero_rated_amount:>15,.2f}")
        if result.exempt_amount > 0:
            lines.append(f"Exempt Amount:           {currency} {result.exempt_amount:>15,.2f}")
        lines.append("")
        lines.append("--- Notes ---")
        for note in result.notes:
            lines.append(f"  • {note}")
        lines.append("")
        lines.append("--- Sources ---")
        for src in result.sources:
            lines.append(f"  📄 {src}")
        return "\n".join(lines)
