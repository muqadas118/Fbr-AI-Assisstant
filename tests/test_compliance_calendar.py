"""
Test Suite for Compliance Calendar
===================================

Tests all compliance calendar components.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
from datetime import date, datetime, timedelta

from app.compliance_calendar import (
    ComplianceEvent, EventType, EventCategory, EventPriority,
    get_all_events, get_events_by_year, get_events_by_type,
    CalendarEngine, CalendarConfig, calculate_compliance_score,
    generate_calendar_year,
    RecurrenceRule, RecurrenceType, expand_recurring_events,
    NotificationManager, NotificationChannel, NotificationStatus,
    NotificationRecord, get_notification_manager,
    ComplianceCalendarAPI, get_compliance_calendar,
    CalendarQuery, CalendarResponse, UpcomingTask,
)


class TestComplianceEvents(unittest.TestCase):
    """Test compliance events database."""

    def test_all_events_loaded(self):
        events = get_all_events()
        self.assertGreater(len(events), 10)

    def test_events_have_required_fields(self):
        events = get_all_events()
        for event in events:
            self.assertIsNotNone(event.id)
            self.assertIsNotNone(event.title)
            self.assertIsNotNone(event.due_date)
            self.assertIsNotNone(event.event_type)
            self.assertIsNotNone(event.priority)

    def test_filter_by_year(self):
        events_2025 = get_events_by_year(2025)
        self.assertGreater(len(events_2025), 5)
        for event in events_2025:
            self.assertEqual(event.fiscal_year, 2025)

    def test_filter_by_type(self):
        itr_events = get_events_by_type(EventType.ANNUAL_RETURN)
        self.assertGreater(len(itr_events), 0)
        for event in itr_events:
            self.assertEqual(event.event_type, EventType.ANNUAL_RETURN)

    def test_critical_itr_deadline_exists(self):
        events = get_all_events()
        itr_critical = [
            e for e in events
            if e.event_type == EventType.ANNUAL_RETURN
            and e.priority == EventPriority.CRITICAL
            and e.due_date.year in (2025, 2026)
        ]
        self.assertGreater(len(itr_critical), 0)

    def test_advance_tax_quarterly(self):
        events = get_events_by_type(EventType.QUARTERLY_ADVANCE_TAX)
        # Should have at least 4 quarters (for FY25)
        self.assertGreaterEqual(len(events), 4)

    def test_sales_tax_monthly(self):
        events = get_events_by_type(EventType.SALES_TAX_RETURN_MONTHLY)
        # Should have 12 monthly returns
        self.assertGreaterEqual(len(events), 12)


class TestCalendarEngine(unittest.TestCase):
    """Test calendar engine."""

    def setUp(self):
        self.config = CalendarConfig(taxpayer_type="company")
        self.engine = CalendarEngine(self.config)

    def test_get_personalized_events(self):
        events = self.engine.get_personalized_events()
        self.assertGreater(len(events), 0)

    def test_individual_excludes_company_only(self):
        config = CalendarConfig(taxpayer_type="individual")
        engine = CalendarEngine(config)
        events = engine.get_personalized_events()
        for event in events:
            # Individuals shouldn't have company-only events
            if "company" in event.applicable_to and "aop" not in event.applicable_to:
                self.assertNotIn("individual", event.applicable_to)
                # This is expected behavior

    def test_get_year_calendar(self):
        calendar = self.engine.get_year_calendar(2025)
        self.assertGreater(len(calendar), 0)

    def test_compliance_score(self):
        score = self.engine.calculate_compliance_score()
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_compliance_grade(self):
        grade = self.engine.get_compliance_grade()
        self.assertIn(grade, ["A+", "A", "B", "C", "D", "F"])

    def test_get_upcoming(self):
        upcoming = self.engine.get_upcoming(days=30)
        # Could be 0 or more depending on current date
        self.assertIsInstance(upcoming, list)

    def test_get_critical_events(self):
        critical = self.engine.get_critical_events(days=365)
        # Date-dependent: late in a fiscal cycle every critical deadline can
        # already be in the past (e.g. TY2025 ITR due 30 Sep, suite running
        # in October), and get_critical_events looks forward only. Assert
        # the contract (list of CRITICAL events) plus that the dataset does
        # contain critical events at all, instead of a hardcoded count.
        self.assertIsInstance(critical, list)
        for event in critical:
            self.assertEqual(event.priority, EventPriority.CRITICAL)
        all_events = self.engine.get_personalized_events()
        self.assertTrue(
            any(e.priority == EventPriority.CRITICAL for e in all_events),
            "calendar dataset must contain critical events",
        )

    def test_generate_year_calendar(self):
        cal = self.engine.generate_year_calendar(2025)
        self.assertIn("fiscal_year", cal)
        self.assertIn("total_events", cal)
        self.assertIn("by_month", cal)
        self.assertIn("by_category", cal)
        self.assertIn("by_priority", cal)


class TestRecurrenceRules(unittest.TestCase):
    """Test recurrence rules."""

    def test_annual_recurrence(self):
        rule = RecurrenceRule(
            event_id="test",
            recurrence_type=RecurrenceType.ANNUAL,
            start_date=date(2025, 9, 30),
        )
        dates = rule.get_next_dates(3)
        self.assertEqual(len(dates), 3)
        self.assertEqual(dates[0].year, 2025)
        self.assertEqual(dates[1].year, 2026)
        self.assertEqual(dates[2].year, 2027)

    def test_monthly_recurrence(self):
        rule = RecurrenceRule(
            event_id="test",
            recurrence_type=RecurrenceType.MONTHLY,
            start_date=date(2025, 1, 15),
        )
        dates = rule.get_next_dates(6)
        self.assertEqual(len(dates), 6)
        # Check months
        self.assertEqual(dates[0].month, 1)
        self.assertEqual(dates[5].month, 6)

    def test_expand_recurring_events(self):
        events = get_events_by_type(EventType.SALES_TAX_RETURN_MONTHLY)
        if events:
            event = events[0]
            end_date = date(2026, 12, 31)
            expanded = expand_recurring_events(event, end_date)
            self.assertGreater(len(expanded), 1)


class TestNotificationManager(unittest.TestCase):
    """Test notification manager."""

    def setUp(self):
        self.manager = NotificationManager()

    def test_schedule_notification(self):
        records = self.manager.schedule_notification(
            event_id="test-event",
            event_title="Test Event",
            due_date="2025-12-31",
            days_remaining=30,
            recipient="test@example.com",
        )
        self.assertEqual(len(records), 3)  # EMAIL, PUSH, IN_APP default

    def test_send_notification(self):
        records = self.manager.schedule_notification(
            event_id="test-event",
            event_title="Test Event",
            due_date="2025-12-31",
            days_remaining=7,
            recipient="test@example.com",
            channels=[NotificationChannel.EMAIL],
        )
        success = self.manager.send_notification(records[0])
        self.assertTrue(success)
        self.assertEqual(records[0].status, NotificationStatus.SENT)

    def test_send_batch(self):
        records = self.manager.schedule_notification(
            event_id="test-event",
            event_title="Test Event",
            due_date="2025-12-31",
            days_remaining=3,
            recipient="test@example.com",
            channels=[NotificationChannel.EMAIL, NotificationChannel.SMS],
        )
        result = self.manager.send_batch(records)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["sent"], 2)

    def test_cancel_notification(self):
        records = self.manager.schedule_notification(
            event_id="test-event",
            event_title="Test Event",
            due_date="2025-12-31",
            days_remaining=10,
            recipient="test@example.com",
            channels=[NotificationChannel.EMAIL],
        )
        success = self.manager.cancel_notification(records[0].id)
        self.assertTrue(success)


class TestComplianceCalendarAPI(unittest.TestCase):
    """Test compliance calendar API."""

    def setUp(self):
        self.api = get_compliance_calendar()

    def test_get_calendar(self):
        query = CalendarQuery(
            taxpayer_type="company",
            fiscal_year=2025,
        )
        response = self.api.get_calendar(query)
        self.assertIsInstance(response, CalendarResponse)
        self.assertGreater(response.total_events, 0)

    def test_get_upcoming_tasks(self):
        tasks = self.api.get_upcoming_tasks("individual", days=90)
        self.assertIsInstance(tasks, list)

    def test_mark_event_completed(self):
        success = self.api.mark_event_completed("test-event-id")
        self.assertTrue(success)

    def test_schedule_reminders(self):
        # Use a real future event ID
        events = get_all_events()
        if events:
            # Find a non-overdue event
            from datetime import date
            future_event = None
            for e in events:
                if not e.is_overdue(date.today()):
                    future_event = e
                    break
            if future_event:
                result = self.api.schedule_reminders(
                    event_id=future_event.id,
                    recipient="test@example.com",
                )
                self.assertIn("reminders_scheduled", result)

    def test_export_json(self):
        query = CalendarQuery(taxpayer_type="individual", fiscal_year=2025, limit=5)
        exported = self.api.export_calendar(query, format="json")
        self.assertIn("total_events", exported)

    def test_export_csv(self):
        query = CalendarQuery(taxpayer_type="individual", fiscal_year=2025, limit=5)
        exported = self.api.export_calendar(query, format="csv")
        self.assertIsInstance(exported, str)

    def test_dashboard_summary(self):
        summary = self.api.get_dashboard_summary("company")
        self.assertIn("compliance_score", summary)
        self.assertIn("compliance_grade", summary)
        self.assertIn("total_events", summary)


if __name__ == "__main__":
    unittest.main(verbosity=2)
