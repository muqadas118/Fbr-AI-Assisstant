"""
Test Suite for Tax Health Check
================================
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from app.tax_health import (
    TaxHealthEngine, RiskAnalyzer, RiskLevel,
    PenaltyCalculator, PenaltyType,
    get_tax_health_api,
)


class TestTaxHealthEngine(unittest.TestCase):
    """Test tax health engine."""

    def setUp(self):
        self.engine = TaxHealthEngine()

    def test_perfect_profile(self):
        profile = self.engine.analyze(
            ntn="1234567-8",
            tax_year=2024,
            itr_filed=True,
            itr_filing_date="2025-09-15",
            itr_due_date="2025-09-30",
            declared_income=1000000,
            estimated_income=1000000,
            tax_assessed=100000,
            tax_paid=100000,
            wht_collected=50000,
            wht_deposited=50000,
            st_collected=200000,
            st_deposited=200000,
            notices_outstanding=0,
        )
        self.assertEqual(profile.health_grade, "A+")
        self.assertEqual(profile.risk_level, "low")
        self.assertEqual(len(profile.issues), 0)

    def test_unfiled_itr(self):
        profile = self.engine.analyze(
            ntn="1234567-8",
            tax_year=2024,
            itr_filed=False,
            tax_assessed=100000,
        )
        self.assertGreater(profile.critical_issues_count, 0)
        codes = [i.code for i in profile.issues]
        self.assertIn("ITR001", codes)

    def test_outstanding_tax(self):
        profile = self.engine.analyze(
            ntn="1234567-8",
            tax_year=2024,
            itr_filed=True,
            tax_assessed=100000,
            tax_paid=50000,
        )
        codes = [i.code for i in profile.issues]
        self.assertIn("TAX001", codes)
        self.assertEqual(profile.tax_outstanding, 50000)

    def test_wht_shortfall(self):
        profile = self.engine.analyze(
            ntn="1234567-8",
            tax_year=2024,
            itr_filed=True,
            wht_collected=100000,
            wht_deposited=50000,
        )
        codes = [i.code for i in profile.issues]
        self.assertIn("WHT001", codes)
        self.assertEqual(profile.wht_shortfall, 50000)

    def test_sales_tax_shortfall(self):
        profile = self.engine.analyze(
            ntn="1234567-8",
            tax_year=2024,
            itr_filed=True,
            st_collected=200000,
            st_deposited=100000,
        )
        codes = [i.code for i in profile.issues]
        self.assertIn("ST001", codes)

    def test_notices_outstanding(self):
        profile = self.engine.analyze(
            ntn="1234567-8",
            tax_year=2024,
            itr_filed=True,
            notices_outstanding=2,
        )
        codes = [i.code for i in profile.issues]
        self.assertIn("NOT001", codes)

    def test_grade_calculation(self):
        self.assertEqual(self.engine._get_grade(95), "A+")
        self.assertEqual(self.engine._get_grade(85), "B")
        self.assertEqual(self.engine._get_grade(50), "F")

    def test_recommendations_generated(self):
        profile = self.engine.analyze(
            ntn="1234567-8",
            tax_year=2024,
            itr_filed=False,
        )
        self.assertGreater(len(profile.recommendations), 0)


class TestRiskAnalyzer(unittest.TestCase):
    """Test risk analyzer."""

    def test_no_risk(self):
        factors = RiskAnalyzer.analyze(
            itr_filed=True,
            tax_outstanding=0,
        )
        self.assertEqual(len(factors), 0)

    def test_critical_risk(self):
        factors = RiskAnalyzer.analyze(
            itr_filed=False,
            tax_outstanding=2000000,
            notices_count=5,
        )
        levels = [f.level for f in factors]
        self.assertIn(RiskLevel.CRITICAL, levels)

    def test_overall_risk(self):
        factors = RiskAnalyzer.analyze(
            itr_filed=False,
            tax_outstanding=2000000,
        )
        level, score = RiskAnalyzer.get_overall_risk(factors)
        self.assertEqual(level, RiskLevel.CRITICAL)


class TestPenaltyCalculator(unittest.TestCase):
    """Test penalty calculator."""

    def test_itr_late_filing(self):
        penalties = PenaltyCalculator.calculate_itr_penalty(
            tax_assessed=100000,
            days_late=10,
        )
        self.assertGreater(len(penalties), 0)
        # Should have late filing + surcharge
        types = [p.penalty_type for p in penalties]
        self.assertIn(PenaltyType.LATE_FILING, types)
        self.assertIn(PenaltyType.DEFAULT_SURCHARGE, types)

    def test_wht_penalty(self):
        penalties = PenaltyCalculator.calculate_wht_penalty(shortfall=50000)
        self.assertEqual(len(penalties), 1)
        self.assertEqual(penalties[0].penalty_type, PenaltyType.WHT_PENALTY)
        self.assertEqual(penalties[0].penalty_amount, 5000)  # 10% of 50000

    def test_sales_tax_penalty(self):
        penalties = PenaltyCalculator.calculate_sales_tax_penalty(
            shortfall=100000,
            days_late=5,
        )
        self.assertEqual(len(penalties), 2)
        # First is 25% penalty
        self.assertEqual(penalties[0].penalty_amount, 25000)

    def test_total_penalty_estimate(self):
        result = PenaltyCalculator.estimate_total_penalties(
            tax_assessed=100000,
            tax_paid=50000,
            wht_shortfall=20000,
            st_shortfall=30000,
        )
        self.assertIn("breakdown", result)
        self.assertIn("total_penalty_estimate", result)
        self.assertGreater(result["total_penalty_estimate"], 0)


class TestTaxHealthAPI(unittest.TestCase):
    """Test tax health API."""

    def setUp(self):
        self.api = get_tax_health_api()

    def test_run_health_check(self):
        result = self.api.run_health_check(ntn="1234567-8", tax_year=2024)
        self.assertEqual(result["ntn"], "1234567-8")
        self.assertIn("required_fields", result)

    def test_analyze_with_data(self):
        data = {
            "ntn": "1234567-8",
            "tax_year": 2024,
            "itr_filed": False,
            "tax_assessed": 100000,
            "tax_paid": 50000,
        }
        result = self.api.analyze_with_data(data)
        self.assertIn("health_score", result)
        self.assertIn("issues", result)
        self.assertGreater(len(result["issues"]), 0)

    def test_estimate_penalties(self):
        data = {
            "tax_assessed": 100000,
            "tax_paid": 50000,
            "days_late_itr": 30,
            "wht_shortfall": 10000,
        }
        result = self.api.estimate_penalties(data)
        self.assertGreater(result["total_penalty_estimate"], 0)

    def test_analyze_risk(self):
        data = {
            "itr_filed": False,
            "tax_outstanding": 500000,
            "notices_count": 2,
            # Intended API: an explicit business age (years operating).
            "business_age_years": 1,
        }
        result = self.api.analyze_risk(data)
        self.assertEqual(result["risk_level"], "critical")
        self.assertGreater(len(result["factors"]), 0)
        codes = [f["code"] for f in result["factors"]]
        self.assertIn("RISK008", codes)

    def test_analyze_risk_without_business_age(self):
        # business_age_years defaults to None ("unknown"): the analyzer must
        # skip the new-business check instead of raising TypeError: None < 2.
        data = {
            "itr_filed": False,
            "tax_outstanding": 500000,
            "notices_count": 2,
        }
        result = self.api.analyze_risk(data)
        self.assertEqual(result["risk_level"], "critical")
        self.assertGreater(len(result["factors"]), 0)
        codes = [f["code"] for f in result["factors"]]
        self.assertNotIn("RISK008", codes)

    def test_analyze_risk_mature_business(self):
        data = {
            "itr_filed": True,
            "tax_outstanding": 0,
            "business_age_years": 10,
        }
        result = self.api.analyze_risk(data)
        self.assertEqual(result["risk_level"], "low")
        self.assertEqual(len(result["factors"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
