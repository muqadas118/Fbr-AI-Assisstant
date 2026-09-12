"""
Production-Grade Tax Calculation Engine
======================================

11 calculation modules covering all FBR tax types:
1. Income Tax (salaried, business, AOP) ✓
2. Salary Tax (with full year slab breakdown) ✓
3. Business Tax (PTR, turnover-based, normal) ✓
4. Sales Tax (goods, services, imports) ✓
5. Withholding Tax (WHT) - 15+ sections ✓
6. Federal Excise Duty (FED) ✓
7. Capital Gains Tax (CGT) ✓
8. Property/Rental Income Tax ✓
9. Dividend/Profit on Debt Tax ✓
10. Custom/Import Duty ✓
11. Custom Calculation ✓

All 11 calculators complete and production-grade.
All formulas verified against Finance Act 2024-2025 and FBR rules.
Updated: September 2026
"""

from app.calculations.income_tax import IncomeTaxCalculator
from app.calculations.salary_tax import SalaryTaxCalculator
from app.calculations.business_tax import BusinessTaxCalculator, BusinessType, TaxRegime
from app.calculations.sales_tax import SalesTaxCalculator, SalesTaxType, SalesTaxProvince
from app.calculations.withholding_tax import (
    WithholdingTaxCalculator, WHTSection, FilerStatus
)
from app.calculations.federal_excise import FederalExciseCalculator, FEDCategory
from app.calculations.capital_gains import CapitalGainsCalculator, AssetType
from app.calculations.property_tax import PropertyTaxCalculator, PropertyType
from app.calculations.dividend_tax import DividendTaxCalculator, IncomeSource
from app.calculations.custom_duty import CustomDutyCalculator, HSCategory
from app.calculations.custom_calc import CustomCalculator, CustomCalcType
from app.calculations.engine import (
    TaxCalculationEngine, EngineResult, CalculationType,
    get_tax_engine
)

__all__ = [
    # Calculators
    "IncomeTaxCalculator",
    "SalaryTaxCalculator",
    "BusinessTaxCalculator",
    "SalesTaxCalculator",
    "WithholdingTaxCalculator",
    "FederalExciseCalculator",
    "CapitalGainsCalculator",
    "PropertyTaxCalculator",
    "DividendTaxCalculator",
    "CustomDutyCalculator",
    "CustomCalculator",
    # Engine
    "TaxCalculationEngine",
    "EngineResult",
    "CalculationType",
    "get_tax_engine",
    # Enums
    "BusinessType",
    "TaxRegime",
    "SalesTaxType",
    "SalesTaxProvince",
    "WHTSection",
    "FilerStatus",
    "FEDCategory",
    "AssetType",
    "PropertyType",
    "IncomeSource",
    "HSCategory",
    "CustomCalcType",
]
