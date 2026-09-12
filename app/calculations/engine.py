"""
Tax Calculation Engine - Unified Orchestrator
==============================================

Single entry point for all 11 tax calculation modules.
Routes user queries to the correct calculator and returns
production-grade results with full audit trail.

Usage:
    engine = TaxCalculationEngine()
    result = engine.calculate("salary", {...input...})
"""

import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from app.calculations.income_tax import (
    IncomeTaxCalculator, IncomeTaxInput, IncomeTaxResult, FilingStatus, TaxYear
)
from app.calculations.salary_tax import (
    SalaryTaxCalculator, SalaryTaxInput, SalaryTaxResult
)
from app.calculations.business_tax import (
    BusinessTaxCalculator, BusinessTaxInput, BusinessTaxResult, BusinessType, TaxRegime
)
from app.calculations.sales_tax import (
    SalesTaxCalculator, SalesTaxInput, SalesTaxResult, SalesTaxType, SalesTaxProvince
)
from app.calculations.withholding_tax import (
    WithholdingTaxCalculator, WHTInput, WHTResult, WHTSection, FilerStatus
)
from app.calculations.federal_excise import (
    FederalExciseCalculator, FEDInput, FEDResult, FEDCategory
)
from app.calculations.capital_gains import (
    CapitalGainsCalculator, CGTInput, CGTResult, AssetType
)
from app.calculations.property_tax import (
    PropertyTaxCalculator, PropertyTaxInput, PropertyTaxResult, PropertyType
)
from app.calculations.dividend_tax import (
    DividendTaxCalculator, DividendTaxInput, DividendTaxResult, IncomeSource
)
from app.calculations.custom_duty import (
    CustomDutyCalculator, CustomDutyInput, CustomDutyResult, HSCategory
)
from app.calculations.custom_calc import (
    CustomCalculator, CustomCalcInput, CustomCalcResult, CustomCalcType
)

logger = logging.getLogger("tax_engine")


class CalculationType(str, Enum):
    """All supported calculation types."""
    INCOME_TAX = "income_tax"
    SALARY_TAX = "salary_tax"
    BUSINESS_TAX = "business_tax"
    SALES_TAX = "sales_tax"
    WITHHOLDING_TAX = "withholding_tax"
    FEDERAL_EXCISE = "federal_excise"
    CAPITAL_GAINS = "capital_gains"
    PROPERTY_TAX = "property_tax"
    DIVIDEND_TAX = "dividend_tax"
    CUSTOM_DUTY = "custom_duty"
    CUSTOM_CALC = "custom_calc"


@dataclass
class CalculationAudit:
    """Audit trail for every calculation."""
    calculation_id: str
    calculation_type: str
    timestamp: str
    duration_ms: float
    inputs: dict
    result: dict
    success: bool
    error: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class EngineResult:
    """Unified result from the calculation engine."""
    success: bool
    calculation_type: str
    data: Any  # Calculator-specific result
    formatted: str
    audit: CalculationAudit
    error: Optional[str] = None


class TaxCalculationEngine:
    """
    Production-Grade Unified Tax Calculation Engine.

    Routes requests to the appropriate calculator module and
    provides full audit trail, validation, and error handling.
    """

    def __init__(self):
        self.audit_log: list[CalculationAudit] = []
        self._supported = {
            CalculationType.INCOME_TAX: self._calc_income_tax,
            CalculationType.SALARY_TAX: self._calc_salary_tax,
            CalculationType.BUSINESS_TAX: self._calc_business_tax,
            CalculationType.SALES_TAX: self._calc_sales_tax,
            CalculationType.WITHHOLDING_TAX: self._calc_wht,
            CalculationType.FEDERAL_EXCISE: self._calc_fed,
            CalculationType.CAPITAL_GAINS: self._calc_cgt,
            CalculationType.PROPERTY_TAX: self._calc_property,
            CalculationType.DIVIDEND_TAX: self._calc_dividend,
            CalculationType.CUSTOM_DUTY: self._calc_custom_duty,
            CalculationType.CUSTOM_CALC: self._calc_custom,
        }

    @property
    def supported_types(self) -> list[str]:
        return [t.value for t in self._supported.keys()]

    def calculate(
        self,
        calc_type: str | CalculationType,
        inputs: dict,
    ) -> EngineResult:
        """
        Perform a tax calculation.

        Args:
            calc_type: One of CalculationType values
            inputs: Dictionary of input parameters for the calculator

        Returns:
            EngineResult with calculator result, formatted output, and audit
        """
        calc_id = str(uuid.uuid4())
        start_time = time.time()
        timestamp = datetime.utcnow().isoformat()

        # Normalize calc_type
        if isinstance(calc_type, str):
            try:
                calc_type = CalculationType(calc_type)
            except ValueError:
                return EngineResult(
                    success=False,
                    calculation_type=calc_type,
                    data=None,
                    formatted="",
                    audit=CalculationAudit(
                        calculation_id=calc_id,
                        calculation_type=calc_type,
                        timestamp=timestamp,
                        duration_ms=0,
                        inputs=inputs,
                        result={},
                        success=False,
                        error=f"Unsupported calculation type: {calc_type}. "
                              f"Supported: {self.supported_types}",
                    ),
                    error=f"Unsupported calculation type: {calc_type}",
                )

        # Route to calculator
        handler = self._supported.get(calc_type)
        if not handler:
            return EngineResult(
                success=False,
                calculation_type=calc_type.value,
                data=None,
                formatted="",
                audit=CalculationAudit(
                    calculation_id=calc_id,
                    calculation_type=calc_type.value,
                    timestamp=timestamp,
                    duration_ms=0,
                    inputs=inputs,
                    result={},
                    success=False,
                    error=f"Calculator not yet implemented: {calc_type.value}",
                ),
                error=f"Calculator not yet implemented: {calc_type.value}",
            )

        try:
            result_data, formatted = handler(inputs)
            duration_ms = (time.time() - start_time) * 1000

            audit = CalculationAudit(
                calculation_id=calc_id,
                calculation_type=calc_type.value,
                timestamp=timestamp,
                duration_ms=round(duration_ms, 3),
                inputs=inputs,
                result=asdict(result_data) if hasattr(result_data, '__dataclass_fields__') else {"raw": str(result_data)},
                success=True,
            )
            self.audit_log.append(audit)
            logger.info(
                f"Calc {calc_id[:8]} {calc_type.value} "
                f"= {getattr(result_data, 'tax_after_credits', 'N/A')} "
                f"in {duration_ms:.2f}ms"
            )

            return EngineResult(
                success=True,
                calculation_type=calc_type.value,
                data=result_data,
                formatted=formatted,
                audit=audit,
            )

        except ValueError as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = f"Validation error: {e}"
            audit = CalculationAudit(
                calculation_id=calc_id,
                calculation_type=calc_type.value,
                timestamp=timestamp,
                duration_ms=round(duration_ms, 3),
                inputs=inputs,
                result={},
                success=False,
                error=error_msg,
            )
            self.audit_log.append(audit)
            logger.warning(f"Calc {calc_id[:8]} validation failed: {e}")
            return EngineResult(
                success=False,
                calculation_type=calc_type.value,
                data=None,
                formatted="",
                audit=audit,
                error=error_msg,
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = f"Internal calculation error: {type(e).__name__}: {e}"
            audit = CalculationAudit(
                calculation_id=calc_id,
                calculation_type=calc_type.value,
                timestamp=timestamp,
                duration_ms=round(duration_ms, 3),
                inputs=inputs,
                result={},
                success=False,
                error=error_msg,
            )
            self.audit_log.append(audit)
            logger.error(f"Calc {calc_id[:8]} error: {e}", exc_info=True)
            return EngineResult(
                success=False,
                calculation_type=calc_type.value,
                data=None,
                formatted="",
                audit=audit,
                error=error_msg,
            )

    def _calc_income_tax(self, inputs: dict) -> tuple[IncomeTaxResult, str]:
        """Route to Income Tax Calculator."""
        # Parse filing_status
        filing_status_str = inputs.get("filing_status", "salaried")
        filing_status = FilingStatus(filing_status_str)

        # Parse tax_year
        tax_year_str = inputs.get("tax_year", "2025")
        tax_year = TaxYear(tax_year_str)

        # Build input
        income_input = IncomeTaxInput(
            gross_income=float(inputs.get("gross_income", 0)),
            filing_status=filing_status,
            tax_year=tax_year,
            zakat_paid=float(inputs.get("zakat_paid", 0)),
            donations=float(inputs.get("donations", 0)),
            investment_in_equity=float(inputs.get("investment_in_equity", 0)),
            tuition_fees=float(inputs.get("tuition_fees", 0)),
            medical_allowance=float(inputs.get("medical_allowance", 0)),
            is_small_company=bool(inputs.get("is_small_company", False)),
            is_aviation_banking=bool(inputs.get("is_aviation_banking", False)),
            include_other_sources=float(inputs.get("include_other_sources", 0)),
        )

        result = IncomeTaxCalculator.calculate(income_input)
        formatted = IncomeTaxCalculator.format_result(result)
        return result, formatted

    def _calc_salary_tax(self, inputs: dict) -> tuple[SalaryTaxResult, str]:
        """Route to Salary Tax Calculator."""
        tax_year_str = inputs.get("tax_year", "2025")
        tax_year = TaxYear(tax_year_str)

        salary_input = SalaryTaxInput(
            basic_salary=float(inputs.get("basic_salary", 0)),
            house_rent_received=float(inputs.get("house_rent_received", 0)),
            medical_allowance=float(inputs.get("medical_allowance", 0)),
            transport_allowance=float(inputs.get("transport_allowance", 0)),
            conveyance_allowance=float(inputs.get("conveyance_allowance", 0)),
            special_allowances=float(inputs.get("special_allowances", 0)),
            bonuses_annual=float(inputs.get("bonuses_annual", 0)),
            overtime_annual=float(inputs.get("overtime_annual", 0)),
            other_allowances=float(inputs.get("other_allowances", 0)),
            rent_paid_annual=float(inputs.get("rent_paid_annual", 0)),
            city_type=inputs.get("city_type", "metro"),
            provident_fund_employee=float(inputs.get("provident_fund_employee", 0)),
            gratuity_provided=bool(inputs.get("gratuity_provided", False)),
            eobi_contribution=float(inputs.get("eobi_contribution", 0)),
            tax_year=tax_year,
            zakat_paid=float(inputs.get("zakat_paid", 0)),
            donations=float(inputs.get("donations", 0)),
            investment_in_equity=float(inputs.get("investment_in_equity", 0)),
            tuition_fees=float(inputs.get("tuition_fees", 0)),
        )

        result = SalaryTaxCalculator.calculate(salary_input)
        formatted = SalaryTaxCalculator.format_result(result)
        return result, formatted

    def _calc_business_tax(self, inputs: dict) -> tuple[BusinessTaxResult, str]:
        """Route to Business Tax Calculator."""
        tax_year_str = inputs.get("tax_year", "2025")
        tax_year = TaxYear(tax_year_str)
        business_type = BusinessType(inputs.get("business_type", "individual_business"))
        tax_regime = TaxRegime(inputs.get("tax_regime", "normal"))

        business_input = BusinessTaxInput(
            business_income=float(inputs.get("business_income", 0)),
            business_type=business_type,
            tax_year=tax_year,
            tax_regime=tax_regime,
            annual_turnover=float(inputs.get("annual_turnover", 0)),
            business_category=inputs.get("business_category", "goods"),
            is_retailer=bool(inputs.get("is_retailer", False)),
            zakat_paid=float(inputs.get("zakat_paid", 0)),
            donations=float(inputs.get("donations", 0)),
            investment_in_equity=float(inputs.get("investment_in_equity", 0)),
            brought_forward_losses=float(inputs.get("brought_forward_losses", 0)),
        )

        result = BusinessTaxCalculator.calculate(business_input)
        formatted = BusinessTaxCalculator.format_result(result)
        return result, formatted

    def _calc_sales_tax(self, inputs: dict) -> tuple[SalesTaxResult, str]:
        """Route to Sales Tax Calculator."""
        stype = SalesTaxType(inputs.get("sales_tax_type", "goods"))
        province = SalesTaxProvince(inputs.get("province", "punjab"))

        sales_input = SalesTaxInput(
            sales_tax_type=stype,
            province=province,
            sales_value=float(inputs.get("sales_value", 0)),
            sales_category=inputs.get("sales_category", "standard"),
            purchases_value=float(inputs.get("purchases_value", 0)),
            purchases_category=inputs.get("purchases_category", "standard"),
            import_value=float(inputs.get("import_value", 0)),
            import_category=inputs.get("import_category", "standard"),
            customs_duty=float(inputs.get("customs_duty", 0)),
            is_export=bool(inputs.get("is_export", False)),
            is_exempt=bool(inputs.get("is_exempt", False)),
            is_retail_supplier=bool(inputs.get("is_retail_supplier", False)),
            service_category=inputs.get("service_category", "general"),
            is_federal_service=bool(inputs.get("is_federal_service", False)),
        )

        result = SalesTaxCalculator.calculate(sales_input)
        formatted = SalesTaxCalculator.format_result(result)
        return result, formatted

    def _calc_wht(self, inputs: dict) -> tuple[WHTResult, str]:
        """Route to WHT Calculator."""
        section = WHTSection(inputs.get("section", "150_dividend"))
        filer_status = FilerStatus(inputs.get("filer_status", "filer"))

        wht_input = WHTInput(
            section=section,
            filer_status=filer_status,
            transaction_amount=float(inputs.get("transaction_amount", 0)),
            description=inputs.get("description", ""),
        )

        result = WithholdingTaxCalculator.calculate(wht_input)
        formatted = WithholdingTaxCalculator.format_result(result)
        return result, formatted

    def _calc_fed(self, inputs: dict) -> tuple[FEDResult, str]:
        """Route to Federal Excise Duty Calculator."""
        category = FEDCategory(inputs.get("category", "cigarettes"))

        fed_input = FEDInput(
            category=category,
            value=float(inputs.get("value", 0)),
            quantity=float(inputs.get("quantity", 0)),
        )

        result = FederalExciseCalculator.calculate(fed_input)
        formatted = FederalExciseCalculator.format_result(result)
        return result, formatted

    def _calc_cgt(self, inputs: dict) -> tuple[CGTResult, str]:
        """Route to Capital Gains Calculator."""
        asset_type = AssetType(inputs.get("asset_type", "immovable_property"))

        cgt_input = CGTInput(
            asset_type=asset_type,
            acquisition_cost=float(inputs.get("acquisition_cost", 0)),
            sale_value=float(inputs.get("sale_value", 0)),
            holding_period_years=float(inputs.get("holding_period_years", 1)),
            filer_status=inputs.get("filer_status", "filer"),
            improvement_cost=float(inputs.get("improvement_cost", 0)),
            selling_expenses=float(inputs.get("selling_expenses", 0)),
        )

        result = CapitalGainsCalculator.calculate(cgt_input)
        formatted = CapitalGainsCalculator.format_result(result)
        return result, formatted

    def _calc_property(self, inputs: dict) -> tuple[PropertyTaxResult, str]:
        """Route to Property Tax Calculator."""
        from app.calculations.property_tax import PropertyType as PT
        prop_type = PT(inputs.get("property_type", "residential"))
        tax_year = TaxYear(inputs.get("tax_year", "2025"))
        filing_status = FilingStatus(inputs.get("filing_status", "individual"))

        prop_input = PropertyTaxInput(
            annual_rent_received=float(inputs.get("annual_rent_received", 0)),
            property_type=prop_type,
            tax_year=tax_year,
            filing_status=filing_status,
            property_tax_paid=float(inputs.get("property_tax_paid", 0)),
            insurance_premium=float(inputs.get("insurance_premium", 0)),
            mortgage_interest=float(inputs.get("mortgage_interest", 0)),
            repair_expenses=float(inputs.get("repair_expenses", 0)),
            zakat_paid=float(inputs.get("zakat_paid", 0)),
            other_income=float(inputs.get("other_income", 0)),
        )

        result = PropertyTaxCalculator.calculate(prop_input)
        formatted = PropertyTaxCalculator.format_result(result)
        return result, formatted

    def _calc_dividend(self, inputs: dict) -> tuple[DividendTaxResult, str]:
        """Route to Dividend Tax Calculator."""
        income_source = IncomeSource(inputs.get("income_source", "dividend"))

        div_input = DividendTaxInput(
            income_source=income_source,
            gross_income=float(inputs.get("gross_income", 0)),
            filer_status=inputs.get("filer_status", "filer"),
        )

        result = DividendTaxCalculator.calculate(div_input)
        formatted = DividendTaxCalculator.format_result(result)
        return result, formatted

    def _calc_custom_duty(self, inputs: dict) -> tuple[CustomDutyResult, str]:
        """Route to Custom Duty Calculator."""
        hs_category = HSCategory(inputs.get("hs_category", "default"))

        duty_input = CustomDutyInput(
            cif_value=float(inputs.get("cif_value", 0)),
            hs_category=hs_category,
            filer_status=inputs.get("filer_status", "filer"),
            is_commercial=bool(inputs.get("is_commercial", True)),
        )

        result = CustomDutyCalculator.calculate(duty_input)
        formatted = CustomDutyCalculator.format_result(result)
        return result, formatted

    def _calc_custom(self, inputs: dict) -> tuple[CustomCalcResult, str]:
        """Route to Custom Calculator."""
        calc_type = CustomCalcType(inputs.get("calc_type", "percentage"))

        custom_input = CustomCalcInput(
            calc_type=calc_type,
            base_value=float(inputs.get("base_value", 0)),
            rate=float(inputs.get("rate", 0)),
            principal=float(inputs.get("principal", 0)),
            days_late=int(inputs.get("days_late", 0)),
            monthly_rate=float(inputs.get("monthly_rate", 0)),
            periods=int(inputs.get("periods", 1)),
            description=inputs.get("description", ""),
            variables=inputs.get("variables", {}),
        )

        result = CustomCalculator.calculate(custom_input)
        formatted = CustomCalculator.format_result(result)
        return result, formatted

    def get_audit_trail(self, limit: int = 100) -> list[dict]:
        """Get recent audit records."""
        return [asdict(a) for a in self.audit_log[-limit:]]

    def clear_audit_log(self):
        """Clear audit log (for testing or privacy)."""
        self.audit_log.clear()


# Singleton instance for app-wide use
_engine_instance: Optional[TaxCalculationEngine] = None


def get_tax_engine() -> TaxCalculationEngine:
    """Get or create the singleton tax calculation engine."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = TaxCalculationEngine()
    return _engine_instance
