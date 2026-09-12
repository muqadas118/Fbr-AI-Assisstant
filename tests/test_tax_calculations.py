"""
Test Suite for Tax Calculation Engine
=====================================

Tests accuracy of all tax calculators against:
- FBR Finance Act 2024-25 rules
- Edge cases (zero income, very high income)
- Validation (negative inputs, invalid values)
- Known FBR calculator outputs (regression)

Run: python -m tests.test_tax_calculations
"""

import sys
import unittest
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.calculations.income_tax import (
    IncomeTaxCalculator, IncomeTaxInput, IncomeTaxResult,
    FilingStatus, TaxYear
)
from app.calculations.salary_tax import (
    SalaryTaxCalculator, SalaryTaxInput
)


class TestIncomeTaxCalculator(unittest.TestCase):
    """Test Income Tax Calculator accuracy."""

    def test_salaried_zero_income(self):
        """Zero income should give zero tax."""
        inp = IncomeTaxInput(
            gross_income=0,
            filing_status=FilingStatus.SALARIED,
        )
        result = IncomeTaxCalculator.calculate(inp)
        self.assertEqual(result.tax_after_credits, 0)
        self.assertEqual(result.taxable_income, 0)

    def test_salaried_below_threshold(self):
        """Income below 600k should be tax-free."""
        inp = IncomeTaxInput(
            gross_income=500_000,
            filing_status=FilingStatus.SALARIED,
        )
        result = IncomeTaxCalculator.calculate(inp)
        self.assertEqual(result.tax_after_credits, 0)

    def test_salaried_1_2_million(self):
        """1.2M should be in 5% bracket only."""
        inp = IncomeTaxInput(
            gross_income=1_200_000,
            filing_status=FilingStatus.SALARIED,
        )
        result = IncomeTaxCalculator.calculate(inp)
        # 600k-1.2M @ 5% = 30,000
        self.assertAlmostEqual(result.tax_after_credits, 30_000, places=2)

    def test_salaried_2_4_million(self):
        """2.4M should hit 10% bracket fully."""
        inp = IncomeTaxInput(
            gross_income=2_400_000,
            filing_status=FilingStatus.SALARIED,
        )
        result = IncomeTaxCalculator.calculate(inp)
        # 600k-1.2M @ 5% = 30,000
        # 1.2M-2.4M @ 10% = 120,000
        # Total = 150,000
        self.assertAlmostEqual(result.tax_after_credits, 150_000, places=2)

    def test_salaried_5_million(self):
        """5M should hit 20% bracket."""
        inp = IncomeTaxInput(
            gross_income=5_000_000,
            filing_status=FilingStatus.SALARIED,
        )
        result = IncomeTaxCalculator.calculate(inp)
        # 600k-1.2M @ 5% = 30,000
        # 1.2M-2.4M @ 10% = 120,000
        # 2.4M-3.6M @ 15% = 180,000
        # 3.6M-5.0M @ 20% = 280,000
        # Total = 610,000
        self.assertAlmostEqual(result.tax_after_credits, 610_000, places=2)

    def test_business_versus_salaried_same_income(self):
        """Same income, different rates between salaried and business."""
        business_inp = IncomeTaxInput(
            gross_income=3_000_000,
            filing_status=FilingStatus.BUSINESS,
        )
        salaried_inp = IncomeTaxInput(
            gross_income=3_000_000,
            filing_status=FilingStatus.SALARIED,
        )
        b_result = IncomeTaxCalculator.calculate(business_inp)
        s_result = IncomeTaxCalculator.calculate(salaried_inp)
        # Business has higher rates for same brackets
        self.assertGreater(b_result.tax_after_credits, s_result.tax_after_credits)

    def test_corporate_company(self):
        """Corporate flat rate (29% for regular, 20% for small)."""
        # Regular company
        corp_inp = IncomeTaxInput(
            gross_income=10_000_000,
            filing_status=FilingStatus.COMPANY_PRIVATE,
        )
        result = IncomeTaxCalculator.calculate(corp_inp)
        self.assertAlmostEqual(result.tax_after_credits, 2_900_000, places=2)

        # Small company
        small_inp = IncomeTaxInput(
            gross_income=10_000_000,
            filing_status=FilingStatus.COMPANY_PRIVATE,
            is_small_company=True,
        )
        s_result = IncomeTaxCalculator.calculate(small_inp)
        self.assertAlmostEqual(s_result.tax_after_credits, 2_000_000, places=2)

    def test_zakat_deduction(self):
        """Zakat should reduce taxable income."""
        no_zakat = IncomeTaxInput(
            gross_income=2_000_000,
            filing_status=FilingStatus.SALARIED,
        )
        with_zakat = IncomeTaxInput(
            gross_income=2_000_000,
            filing_status=FilingStatus.SALARIED,
            zakat_paid=100_000,
        )
        r1 = IncomeTaxCalculator.calculate(no_zakat)
        r2 = IncomeTaxCalculator.calculate(with_zakat)
        self.assertLess(r2.tax_after_credits, r1.tax_after_credits)

    def test_investment_credit(self):
        """Investment in equity should give tax credit."""
        no_inv = IncomeTaxInput(
            gross_income=5_000_000,
            filing_status=FilingStatus.BUSINESS,
        )
        with_inv = IncomeTaxInput(
            gross_income=5_000_000,
            filing_status=FilingStatus.BUSINESS,
            investment_in_equity=500_000,
        )
        r1 = IncomeTaxCalculator.calculate(no_inv)
        r2 = IncomeTaxCalculator.calculate(with_inv)
        # With investment should be less
        self.assertLess(r2.tax_after_credits, r1.tax_after_credits)
        # And credit should be applied
        self.assertGreater(r2.tax_credits_applied, 0)

    def test_negative_income_rejected(self):
        """Negative income should be rejected."""
        inp = IncomeTaxInput(
            gross_income=-100_000,
            filing_status=FilingStatus.SALARIED,
        )
        with self.assertRaises(ValueError):
            IncomeTaxCalculator.calculate(inp)

    def test_very_high_income_35pct_bracket(self):
        """Income > 12M should hit 35% bracket."""
        inp = IncomeTaxInput(
            gross_income=20_000_000,
            filing_status=FilingStatus.SALARIED,
        )
        result = IncomeTaxCalculator.calculate(inp)
        # 0-600k: 0
        # 600k-1.2M: 30k
        # 1.2M-2.4M: 120k
        # 2.4M-3.6M: 180k
        # 3.6M-6M: 480k
        # 6M-12M: 1.5M
        # 12M-20M @ 35%: 2.8M
        # Total = 5,110,000
        self.assertAlmostEqual(result.tax_after_credits, 5_110_000, places=2)

    def test_format_result(self):
        """Test result formatting produces readable string."""
        inp = IncomeTaxInput(
            gross_income=1_500_000,
            filing_status=FilingStatus.SALARIED,
        )
        result = IncomeTaxCalculator.calculate(inp)
        formatted = IncomeTaxCalculator.format_result(result)
        self.assertIn("Income Tax Calculation", formatted)
        self.assertIn("Tax Slab Breakdown", formatted)
        self.assertIn("PKR", formatted)


class TestSalaryTaxCalculator(unittest.TestCase):
    """Test Salary Tax Calculator accuracy."""

    def test_basic_salary_no_rent(self):
        """Basic salary with no rent = no HRA exemption."""
        inp = SalaryTaxInput(
            basic_salary=100_000,  # 1.2M annual
            house_rent_received=50_000,
            rent_paid_annual=0,  # No rent
        )
        result = SalaryTaxCalculator.calculate(inp)
        self.assertEqual(result.hra_exemption, 0)

    def test_hra_full_exemption_metro(self):
        """Full HRA exemption when conditions met."""
        # Basic = 100k/month = 1.2M annual
        # HRA = 50k/month = 600k annual
        # Rent paid = 900k annual (exceeds 600k and 25% of basic = 300k)
        # Exemption = min(600k, 900k - 120k, 300k) = min(600k, 780k, 300k) = 300k
        inp = SalaryTaxInput(
            basic_salary=100_000,
            house_rent_received=50_000,
            rent_paid_annual=900_000,
            city_type="metro",
        )
        result = SalaryTaxCalculator.calculate(inp)
        self.assertEqual(result.hra_exemption, 300_000)

    def test_hra_full_exemption_non_metro(self):
        """15% rule for non-metro."""
        # Basic = 100k/month = 1.2M annual
        # HRA = 50k/month = 600k annual
        # Rent paid = 1M
        # Exemption = min(600k, 1M - 120k, 180k) = 180k
        inp = SalaryTaxInput(
            basic_salary=100_000,
            house_rent_received=50_000,
            rent_paid_annual=1_000_000,
            city_type="non_metro",
        )
        result = SalaryTaxCalculator.calculate(inp)
        self.assertEqual(result.hra_exemption, 180_000)

    def test_medical_allowance_capped(self):
        """Medical allowance capped at 120k."""
        inp = SalaryTaxInput(
            basic_salary=100_000,
            medical_allowance=20_000,  # 240k annual
        )
        result = SalaryTaxCalculator.calculate(inp)
        self.assertEqual(result.medical_exemption, 120_000)

    def test_medical_under_limit(self):
        """Medical allowance under limit = full exemption."""
        inp = SalaryTaxInput(
            basic_salary=100_000,
            medical_allowance=5_000,  # 60k annual
        )
        result = SalaryTaxCalculator.calculate(inp)
        self.assertEqual(result.medical_exemption, 60_000)

    def test_transport_no_exemption(self):
        """Transport allowance has no exemption."""
        inp = SalaryTaxInput(
            basic_salary=100_000,
            transport_allowance=10_000,  # 120k annual
        )
        result = SalaryTaxCalculator.calculate(inp)
        self.assertEqual(result.transport_exemption, 0)

    def test_pf_deduction_capped(self):
        """PF deduction capped at 1/3 of basic."""
        # Basic = 100k/month = 1.2M
        # Max PF = 1.2M/3 = 400k
        inp = SalaryTaxInput(
            basic_salary=100_000,
            provident_fund_employee=500_000,  # Above limit
        )
        result = SalaryTaxCalculator.calculate(inp)
        self.assertEqual(result.pf_deduction, 400_000)

    def test_eobi_deduction(self):
        """EOBI contribution deduction."""
        inp = SalaryTaxInput(
            basic_salary=100_000,
            eobi_contribution=50_000,  # Above max
        )
        result = SalaryTaxCalculator.calculate(inp)
        self.assertEqual(result.eobi_deduction, 36_000)

    def test_monthly_tax_calculation(self):
        """Monthly tax = annual / 12."""
        inp = SalaryTaxInput(
            basic_salary=300_000,  # 3.6M annual
        )
        result = SalaryTaxCalculator.calculate(inp)
        # 3.6M should hit top of 15% bracket
        # 600k @ 0% = 0
        # 600k @ 5% = 30k
        # 1.2M @ 10% = 120k
        # 1.2M @ 15% = 180k
        # Total = 330k
        self.assertAlmostEqual(result.annual_tax, 330_000, places=2)
        self.assertAlmostEqual(result.monthly_tax, 27_500, places=2)

    def test_format_result(self):
        """Format result readable."""
        inp = SalaryTaxInput(
            basic_salary=100_000,
            house_rent_received=50_000,
            rent_paid_annual=600_000,
            medical_allowance=10_000,
        )
        result = SalaryTaxCalculator.calculate(inp)
        formatted = SalaryTaxCalculator.format_result(result)
        self.assertIn("Salary Tax Calculation", formatted)
        self.assertIn("Exemptions", formatted)
        self.assertIn("PKR", formatted)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases across calculators."""

    def test_zero_basic_salary(self):
        """Zero salary should give zero tax."""
        inp = SalaryTaxInput(basic_salary=0)
        result = SalaryTaxCalculator.calculate(inp)
        self.assertEqual(result.annual_tax, 0)

    def test_extreme_high_income(self):
        """Test with 1 billion income."""
        inp = IncomeTaxInput(
            gross_income=1_000_000_000,
            filing_status=FilingStatus.BUSINESS,
        )
        result = IncomeTaxCalculator.calculate(inp)
        # Should not crash, should return valid result
        self.assertGreater(result.tax_after_credits, 0)
        self.assertLess(result.tax_after_credits, 1_000_000_000)

    def test_all_deductions_applied(self):
        """All deductions together should work."""
        inp = SalaryTaxInput(
            basic_salary=200_000,
            house_rent_received=80_000,
            rent_paid_annual=1_500_000,
            medical_allowance=15_000,
            provident_fund_employee=100_000,
            eobi_contribution=30_000,
            zakat_paid=50_000,
        )
        result = SalaryTaxCalculator.calculate(inp)
        # Should not crash
        self.assertGreater(result.annual_gross, 0)
        self.assertGreater(result.taxable_income, 0)


def run_tests():
    """Run all tests and return success status."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestIncomeTaxCalculator))
    suite.addTests(loader.loadTestsFromTestCase(TestSalaryTaxCalculator))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
