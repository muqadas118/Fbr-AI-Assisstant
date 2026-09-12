"""
Test Suite for Notice Analyzer
===============================

Tests all notice analysis components.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from datetime import datetime, timedelta

from app.notice_analyzer import (
    NoticeClassifier, NoticeType,
    NoticeExtractor, ExtractedInfo,
    DeadlineCalculator,
    ActionPlanGenerator,
    AppealGuideGenerator,
    NoticeAnalyzer, get_notice_analyzer,
)


class TestNoticeClassifier(unittest.TestCase):
    """Test notice classification."""

    def test_show_cause_114(self):
        text = """
        SHOW CAUSE NOTICE
        Under Section 114(3) of the Income Tax Ordinance, 2001

        You are hereby required to show cause why proceedings should not be
        initiated against you for the tax year 2024.
        """
        result = NoticeClassifier.classify(text)
        self.assertEqual(result.notice_type, NoticeType.SHOW_CAUSE_114)
        self.assertGreater(result.confidence, 0.5)
        self.assertTrue(result.is_appealable)
        self.assertTrue(result.is_critical)

    def test_show_cause_122(self):
        text = """
        SHOW CAUSE NOTICE
        Under Section 122(1) of the Income Tax Ordinance, 2001

        It is alleged that you have concealed income of PKR 5,000,000
        through misrepresentation of facts.
        """
        result = NoticeClassifier.classify(text)
        self.assertEqual(result.notice_type, NoticeType.SHOW_CAUSE_122)
        self.assertGreater(result.confidence, 0.5)

    def test_assessment_122(self):
        text = """
        ORDER UNDER SECTION 122(4)
        Final Assessment Order for Tax Year 2024

        After considering your response, the total income is determined
        to be PKR 8,000,000 with tax of PKR 1,200,000.
        """
        result = NoticeClassifier.classify(text)
        self.assertEqual(result.notice_type, NoticeType.ASSESSMENT_122)

    def test_demand_137(self):
        text = """
        DEMAND NOTICE
        Under Section 137(1) of the Income Tax Ordinance, 2001

        You are hereby directed to pay the amount of PKR 500,000
        which is now payable.
        """
        result = NoticeClassifier.classify(text)
        self.assertEqual(result.notice_type, NoticeType.DEMAND_137)

    def test_penalty_182(self):
        text = """
        PENALTY NOTICE
        Under Section 182 of the Income Tax Ordinance, 2001

        You are hereby penalized PKR 100,000 for non-compliance.
        """
        result = NoticeClassifier.classify(text)
        self.assertEqual(result.notice_type, NoticeType.PENALTY_182)

    def test_audit_214C(self):
        text = """
        AUDIT NOTICE
        Under Section 214C of the Income Tax Ordinance, 2001

        Your tax affairs for the year 2024 have been selected for audit.
        """
        result = NoticeClassifier.classify(text)
        self.assertEqual(result.notice_type, NoticeType.AUDIT_214C)

    def test_empty_text(self):
        result = NoticeClassifier.classify("")
        self.assertEqual(result.notice_type, NoticeType.UNKNOWN)
        self.assertEqual(result.confidence, 0.0)

    def test_short_text(self):
        result = NoticeClassifier.classify("hello")
        self.assertEqual(result.notice_type, NoticeType.UNKNOWN)


class TestNoticeExtractor(unittest.TestCase):
    """Test notice information extraction."""

    def test_extract_ntn(self):
        text = "Taxpayer NTN: 1234567-8"
        info = NoticeExtractor.extract(text)
        self.assertEqual(info.taxpayer_ntn, "1234567-8")

    def test_extract_cnic(self):
        text = "CNIC: 12345-1234567-1"
        info = NoticeExtractor.extract(text)
        self.assertEqual(info.taxpayer_cnic, "12345-1234567-1")

    def test_extract_notice_id(self):
        text = "Notice No: FBR/2024/12345"
        info = NoticeExtractor.extract(text)
        self.assertIsNotNone(info.notice_id)

    def test_extract_date(self):
        text = "Dated: 15-03-2024"
        info = NoticeExtractor.extract(text)
        self.assertEqual(info.issue_date, "2024-03-15")

    def test_extract_amounts(self):
        text = """
        Total demand: PKR 1,500,000
        Tax: PKR 1,200,000
        Penalty: PKR 300,000
        """
        info = NoticeExtractor.extract(text)
        self.assertEqual(info.total_demanded, 1_500_000)
        self.assertEqual(info.tax_amount, 1_200_000)
        self.assertEqual(info.penalty_amount, 300_000)

    def test_extract_sections(self):
        text = """
        Under Section 114(3), Section 122(1), and Section 137(1)
        """
        info = NoticeExtractor.extract(text)
        self.assertGreater(len(info.sections_cited), 0)

    def test_extract_tax_years(self):
        text = "For Tax Year 2024 and Tax Year 2023"
        info = NoticeExtractor.extract(text)
        self.assertIn("2024", info.tax_years)
        self.assertIn("2023", info.tax_years)

    def test_extract_quality(self):
        text = """
        SHOW CAUSE NOTICE Under Section 114
        NTN: 1234567-8
        Notice No: FBR/123
        Dated: 15-03-2024
        Tax Year: 2024
        Section 114
        Amount: PKR 500,000
        """
        info = NoticeExtractor.extract(text)
        self.assertGreaterEqual(info.extraction_quality, 0.5)


class TestDeadlineCalculator(unittest.TestCase):
    """Test deadline calculation."""

    def test_future_deadline(self):
        future_date = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        info = DeadlineCalculator.calculate(NoticeType.SHOW_CAUSE_114, future_date)
        self.assertIsNotNone(info.deadline_date)
        self.assertGreater(info.days_remaining, 0)
        self.assertFalse(info.is_overdue)

    def test_overdue(self):
        past_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        info = DeadlineCalculator.calculate(NoticeType.SHOW_CAUSE_114, past_date)
        self.assertTrue(info.is_overdue)
        self.assertEqual(info.urgency_level, "critical")

    def test_urgent(self):
        # Issue date 13 days ago, SCN has 14 days response
        # So 1 day remaining
        date_13_days_ago = (datetime.now() - timedelta(days=13)).strftime("%Y-%m-%d")
        info = DeadlineCalculator.calculate(NoticeType.SHOW_CAUSE_114, date_13_days_ago)
        self.assertLessEqual(info.days_remaining, 1)
        self.assertIn(info.urgency_level, ["critical", "high"])

    def test_no_issue_date(self):
        info = DeadlineCalculator.calculate(NoticeType.SHOW_CAUSE_114, None)
        self.assertIsNone(info.deadline_date)
        self.assertEqual(info.urgency_level, "unknown")


class TestActionPlanGenerator(unittest.TestCase):
    """Test action plan generation."""

    def test_show_cause_plan(self):
        plan = ActionPlanGenerator.generate(NoticeType.SHOW_CAUSE_114)
        self.assertGreater(plan.total_steps, 0)
        self.assertGreater(plan.estimated_total_hours, 0)
        self.assertTrue(plan.requires_professional_help)
        self.assertGreater(len(plan.common_mistakes), 0)
        self.assertGreater(len(plan.helpful_tips), 0)

    def test_demand_plan(self):
        plan = ActionPlanGenerator.generate(NoticeType.DEMAND_137)
        self.assertGreater(plan.total_steps, 0)
        self.assertTrue(plan.requires_payment)
        self.assertFalse(plan.requires_professional_help)

    def test_generic_plan(self):
        plan = ActionPlanGenerator.generate(NoticeType.UNKNOWN)
        self.assertGreater(plan.total_steps, 0)
        # Should not crash

    def test_plan_format(self):
        plan = ActionPlanGenerator.generate(NoticeType.SHOW_CAUSE_114)
        formatted = ActionPlanGenerator.format_plan(plan)
        self.assertIn("Action Plan", formatted)
        self.assertIn("Step", formatted)


class TestAppealGuideGenerator(unittest.TestCase):
    """Test appeal guide generation."""

    def test_appealable_notice(self):
        guide = AppealGuideGenerator.generate(NoticeType.SHOW_CAUSE_114)
        self.assertTrue(guide.is_appealable)
        self.assertEqual(guide.time_limit_days, 30)
        self.assertEqual(guide.forum, "commissioner_appeals")
        self.assertGreater(len(guide.common_grounds), 0)
        self.assertGreater(len(guide.documents_needed), 0)

    def test_non_appealable_notice(self):
        guide = AppealGuideGenerator.generate(NoticeType.INFORMATION_REQUEST)
        self.assertFalse(guide.is_appealable)

    def test_prosecution(self):
        guide = AppealGuideGenerator.generate(NoticeType.PROSECUTION)
        self.assertTrue(guide.is_appealable)
        # Prosecution has shorter response time
        self.assertLessEqual(guide.time_limit_days, 14)

    def test_format_guide(self):
        guide = AppealGuideGenerator.generate(NoticeType.ASSESSMENT_122)
        formatted = AppealGuideGenerator.format_guide(guide)
        self.assertIn("Appeal Guide", formatted)
        self.assertIn("Forum", formatted)


class TestNoticeAnalyzer(unittest.TestCase):
    """Test the unified analyzer."""

    def setUp(self):
        self.analyzer = get_notice_analyzer()
        self.sample_text = """
        FEDERAL BOARD OF REVENANCE
        SHOW CAUSE NOTICE

        Notice No: FBR/IT/2024/12345
        Dated: 01-03-2024

        To: Mr. Ahmed Khan
        NTN: 1234567-8
        CNIC: 12345-1234567-1

        Under Section 114(3) of the Income Tax Ordinance, 2001

        You are hereby required to show cause why proceedings should not be
        initiated against you for Tax Year 2024.

        Alleged amount: PKR 5,000,000
        Penalty under Section 182: PKR 500,000

        You must respond within 14 days.

        Reference Section 114(3), Section 182
        """

    def test_complete_analysis(self):
        result = self.analyzer.analyze(self.sample_text)
        self.assertIsNotNone(result.analysis_id)
        self.assertEqual(result.notice_type, "show_cause_section_114")
        self.assertGreater(result.confidence, 0.3)
        self.assertTrue(result.is_critical)
        self.assertTrue(result.is_appealable)
        self.assertEqual(result.taxpayer_ntn, "1234567-8")
        self.assertEqual(result.issue_date, "2024-03-01")
        self.assertIn("2024", result.tax_years)
        self.assertIsNotNone(result.action_plan)
        self.assertIsNotNone(result.appeal_guide)
        self.assertGreater(len(result.formatted_text), 0)
        self.assertGreater(len(result.summary), 0)

    def test_audit_trail(self):
        self.analyzer.analyze(self.sample_text)
        self.analyzer.analyze(self.sample_text)
        self.assertGreaterEqual(len(self.analyzer.audit_log), 2)

    def test_format_output(self):
        result = self.analyzer.analyze(self.sample_text)
        # Check key sections present
        self.assertIn("FBR NOTICE ANALYSIS", result.formatted_text)
        self.assertIn("Action Plan", result.formatted_text)
        self.assertIn("Deadline", result.formatted_text)

    def test_short_text(self):
        result = self.analyzer.analyze("show cause notice")
        # Should not crash
        self.assertIsNotNone(result.analysis_id)

    def test_empty_text(self):
        result = self.analyzer.analyze("")
        self.assertEqual(result.notice_type, "unknown")
        self.assertEqual(result.confidence, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
