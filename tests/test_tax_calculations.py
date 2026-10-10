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
    IncomeTaxCalculator, IncomeTaxInput, FilingStatus, TaxYear
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

    def test_donation_credit_average_rate(self):
        """Section 61: credit = (A/B) x C (average-rate method).

        Taxable 5,000,000 business individual (TY 2026):
        tax before credits = 1,610,000 + 45% of (5M - 5.6M is negative,
        so fully in the 5.6M bracket? No: 5M < 5.6M, so use 3.2M-5.6M
        bracket: 650,000 + 40% x (5,000,000 - 3,200,000) = 1,370,000.
        Donation 100,000, within the 30% cap (1.5M).
        Expected credit = (100,000 / 5,000,000) x 1,370,000 = 27,400.
        """
        inp = IncomeTaxInput(
            gross_income=5_000_000,
            filing_status=FilingStatus.BUSINESS,
            tax_year=TaxYear.TY_2026,
            donations=100_000,
        )
        result = IncomeTaxCalculator.calculate(inp)
        self.assertAlmostEqual(result.tax_credits_applied, 27_400, places=2)
        self.assertAlmostEqual(result.tax_after_credits, 1_370_000 - 27_400, places=2)
        self.assertTrue(
            any("Section 61" in n for n in result.notes),
            "Notes should reference Section 61",
        )

    def test_donation_credit_capped_at_30pct(self):
        """Donations above 30% of taxable income are capped.

        Taxable 1,000,000: 30% cap = 300,000. Donating 500,000 should
        use only 300,000. TY 2025 business slabs: only the amount above
        600k is taxed -> 400,000 x 10% = 40,000. Credit =
        (300,000 / 1,000,000) x 40,000 = 12,000.
        """
        inp = IncomeTaxInput(
            gross_income=1_000_000,
            filing_status=FilingStatus.BUSINESS,
            tax_year=TaxYear.TY_2025,
            donations=500_000,
        )
        result = IncomeTaxCalculator.calculate(inp)
        self.assertAlmostEqual(result.tax_credits_applied, 12_000, places=2)
        self.assertTrue(
            any("limited to 30%" in n for n in result.notes),
            "Notes should mention the 30% cap",
        )

    def test_donation_credit_zero_taxable_income(self):
        """No taxable income -> no Section 61 credit, no crash."""
        inp = IncomeTaxInput(
            gross_income=0,
            filing_status=FilingStatus.BUSINESS,
            donations=100_000,
        )
        result = IncomeTaxCalculator.calculate(inp)
        self.assertEqual(result.tax_credits_applied, 0)
        self.assertEqual(result.tax_after_credits, 0)

    def test_donation_credit_company(self):
        """Company path: Section 61 credit with 20% cap.

        Taxable 5,000,000 @ 29% = 1,450,000. Donation 500,000 is within
        the 20% cap (1,000,000). Credit = (500,000 / 5,000,000) x
        1,450,000 = 145,000.
        """
        inp = IncomeTaxInput(
            gross_income=5_000_000,
            filing_status=FilingStatus.COMPANY_PRIVATE,
            donations=500_000,
        )
        result = IncomeTaxCalculator.calculate(inp)
        self.assertAlmostEqual(result.tax_credits_applied, 145_000, places=2)

    def test_negative_income_rejected(self):
        """Negative income should be rejected."""
        inp = IncomeTaxInput(
            gross_income=-100_000,
            filing_status=FilingStatus.SALARIED,
        )
        with self.assertRaises(ValueError):
            IncomeTaxCalculator.calculate(inp)

    def test_income_cap_boundary_exactly_1t(self):
        """Income exactly at the 1 trillion cap is accepted."""
        inp = IncomeTaxInput(
            gross_income=1_000_000_000_000,
            filing_status=FilingStatus.SALARIED,
            tax_year=TaxYear.TY_2026,
        )
        result = IncomeTaxCalculator.calculate(inp)
        # TY 2026 salaried: cumulative at 7M = 1,424,000, then 35% above 7M.
        expected = 1_424_000 + 0.35 * (1_000_000_000_000 - 7_000_000)
        self.assertAlmostEqual(result.tax_after_credits, expected, places=2)

    def test_income_cap_boundary_just_above_1t(self):
        """Income 1 rupee above the 1T cap is rejected with a clear message."""
        inp = IncomeTaxInput(
            gross_income=1_000_000_000_001,
            filing_status=FilingStatus.SALARIED,
            tax_year=TaxYear.TY_2026,
        )
        with self.assertRaises(ValueError) as ctx:
            IncomeTaxCalculator.calculate(inp)
        self.assertIn("1,000,000,000,000", str(ctx.exception))

    def test_decimal_amounts(self):
        """Decimal (paisa-level) amounts compute without rounding drift.

        Salaried TY 2026 income 1,234,567.89:
        600k @1% = 6,000; (1,234,567.89 - 1,200,000) @ 11% = 3,802.47.
        Tax = 9,802.47. Donation 999.99 -> credit = (999.99 / 1,234,567.89)
        x 9,802.47 = 7.94 (rounded). Final = 9,794.53.
        """
        inp = IncomeTaxInput(
            gross_income=1_234_567.89,
            filing_status=FilingStatus.SALARIED,
            tax_year=TaxYear.TY_2026,
            donations=999.99,
        )
        result = IncomeTaxCalculator.calculate(inp)
        self.assertAlmostEqual(result.tax_before_credits, 9_802.47, places=2)
        self.assertAlmostEqual(result.tax_credits_applied, 7.94, places=2)
        self.assertAlmostEqual(result.tax_after_credits, 9_794.53, places=2)

    def test_donation_cap_huge_donation(self):
        """A donation far above taxable income is capped at 30%, no crash.

        Salaried TY 2026 income 1,000,000: tax = 4,000 (400k @ 1%).
        Donation 999,999,999 caps to 300,000 -> credit =
        (300,000 / 1,000,000) x 4,000 = 1,200. Final = 2,800.
        """
        inp = IncomeTaxInput(
            gross_income=1_000_000,
            filing_status=FilingStatus.SALARIED,
            tax_year=TaxYear.TY_2026,
            donations=999_999_999,
        )
        result = IncomeTaxCalculator.calculate(inp)
        self.assertAlmostEqual(result.tax_credits_applied, 1_200, places=2)
        self.assertAlmostEqual(result.tax_after_credits, 2_800, places=2)
        self.assertTrue(
            any("limited to 30%" in n for n in result.notes),
            "Notes should mention the 30% cap",
        )

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
