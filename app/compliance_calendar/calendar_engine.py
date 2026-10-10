"""
Compliance Calendar Engine - Production-Grade
==============================================

Smart engine jo:
- Reminders schedule karta hai (90/60/30/14/7/1 days before)
- Weekend/holiday awareness
- Compliance score calculate karta hai
- Year-wise calendar generate karta hai
- Personalized calendar based on user profile

COMPLIANCE SCORING CONTRACT
---------------------------
A score is only computed from real completion data: the events the caller says
the user actually filed (`completed_event_ids` / `CalendarConfig.completed_event_ids`).
When nothing has passed its due date, or when no completion data was supplied
at all, the score is None ("insufficient data") instead of a fabricated 0 or
100. Callers must render that case explicitly - a fake 0 reads as total
non-compliance and a fake 100 reads as perfect compliance.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Optional

from app.compliance_calendar.events import (
    ComplianceEvent, EventPriority,
    get_all_events, get_events_by_year, get_upcoming_events,
)

# Sentinel returned by the scoring helpers when there is not enough real data
# to say anything meaningful. Kept as a module constant so callers can compare
# against it (and so it never looks like a real score).
INSUFFICIENT_DATA = None


@dataclass
class ReminderSchedule:
    """Reminder configuration for an event."""
    event_id: str
    reminder_intervals: list[int] = field(default_factory=lambda: [90, 60, 30, 14, 7, 1])
    send_email: bool = True
    send_sms: bool = True
    send_push: bool = True

    def calculate_reminder_dates(self, due_date: date) -> list[date]:
        """Calculate actual reminder dates from due date."""
        today = date.today()
        reminder_dates = []
        for days in self.reminder_intervals:
            reminder_date = due_date - timedelta(days=days)
            if reminder_date >= today:
                reminder_dates.append(reminder_date)
        return reminder_dates


@dataclass
class CalendarConfig:
    """User-specific calendar configuration."""
    taxpayer_type: str = "individual"  # individual, business, company, aop
    # Tax year = the most recent completed tax year, so a default-config engine
    # does not anchor itself to a stale year.
    tax_year: int = field(default_factory=lambda: date.today().year - 1)
    # Fiscal year defaults to the year in progress so the calendar never
    # silently anchors to a stale year (2025) once time moves on.
    fiscal_year: int = field(default_factory=lambda: date.today().year)
    sectors: list[str] = field(default_factory=list)
    registered_for_sales_tax: bool = True
    registered_for_wht: bool = True
    is_filer: bool = True
    include_holidays: bool = True
    reminder_intervals: list[int] = field(default_factory=lambda: [90, 60, 30, 14, 7, 1])
    # IDs of events the user has actually filed. Empty means "unknown", not
    # "nothing filed" - the compliance score distinguishes the two.
    completed_event_ids: Optional[set[str]] = None


class CalendarEngine:
    """Main calendar engine."""

    def __init__(self, config: Optional[CalendarConfig] = None):
        self.config = config or CalendarConfig()
        self.events = get_all_events()

    def get_personalized_events(self) -> list[ComplianceEvent]:
        """Get events applicable to user's profile."""
        applicable = []
        for event in self.events:
            if not event.is_active:
                continue
            if "all" in event.applicable_to:
                applicable.append(event)
                continue
            if self.config.taxpayer_type in event.applicable_to:
                applicable.append(event)
        return applicable

    def get_year_calendar(self, fiscal_year: int) -> list[ComplianceEvent]:
        """Get full calendar for a fiscal year."""
        events = get_events_by_year(fiscal_year)
        # Filter by taxpayer profile
        return [e for e in events if self._is_applicable(e)]

    def _is_applicable(self, event: ComplianceEvent) -> bool:
        """Check if event applies to current user."""
        if "all" in event.applicable_to:
            return True
        if self.config.taxpayer_type in event.applicable_to:
            return True
        return False

    def get_upcoming(self, days: int = 30) -> list[ComplianceEvent]:
        """Get events due within N days for current user."""
        all_upcoming = get_upcoming_events(days)
        return [e for e in all_upcoming if self._is_applicable(e)]

    def get_overdue(self) -> list[ComplianceEvent]:
        """Get overdue events for current user."""
        today = date.today()
        overdue = []
        for event in self.get_personalized_events():
            if event.is_overdue(today):
                overdue.append(event)
        return sorted(overdue, key=lambda x: x.due_date)

    def get_critical_events(self, days: int = 30) -> list[ComplianceEvent]:
        """Get critical events due within N days."""
        upcoming = self.get_upcoming(days)
        return [e for e in upcoming if e.priority == EventPriority.CRITICAL]

    def calculate_compliance_score(
        self,
        completed_event_ids: Optional[Iterable[str]] = None,
        today: Optional[date] = None,
    ) -> Optional[float]:
        """
        Calculate compliance score (0-100) from real completion data.

        The score is `completed past-due events / total past-due events`, where
        "completed" means the event id appears in `completed_event_ids`
        (defaults to `CalendarConfig.completed_event_ids`). Nothing is assumed
        here: the previous implementation counted every past event as completed
        unless it showed up in an overdue list the same loop had already
        excluded it from, so the score was always 0.

        Returns None ("insufficient data") when either no event has fallen due
        yet or no completion data was supplied. Returning 0 in that case would
        claim the user filed nothing; returning 100 would claim a perfect
        record. Callers must render the None case explicitly.
        """
        today = today or date.today()

        if completed_event_ids is None:
            completed_event_ids = self.config.completed_event_ids
        completed = set(completed_event_ids) if completed_event_ids is not None else set()

        past_due = [
            e for e in self.get_personalized_events()
            if e.due_date < today
        ]

        if not past_due or completed_event_ids is None:
            return INSUFFICIENT_DATA

        completed_count = sum(1 for e in past_due if e.id in completed)
        return round((completed_count / len(past_due)) * 100, 2)

    def get_compliance_grade(
        self,
        completed_event_ids: Optional[Iterable[str]] = None,
        today: Optional[date] = None,
    ) -> str:
        """
        Get letter grade based on compliance score.

        Returns "insufficient_data" (not "F") when the score cannot be
        computed, so a missing-filing-data state is never rendered as the worst
        possible grade.
        """
        score = self.calculate_compliance_score(completed_event_ids, today)
        if score is None:
            return "insufficient_data"
        if score >= 95:
            return "A+"
        elif score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"

    def get_reminder_schedule(self, event: ComplianceEvent) -> ReminderSchedule:
        """Get reminder schedule for a specific event."""
        return ReminderSchedule(
            event_id=event.id,
            reminder_intervals=self.config.reminder_intervals,
        )

    def generate_year_calendar(self, fiscal_year: int) -> dict:
        """Generate full year calendar as a structured dict."""
        events = self.get_year_calendar(fiscal_year)

        calendar = {
            "fiscal_year": fiscal_year,
            "taxpayer_type": self.config.taxpayer_type,
            "total_events": len(events),
            "by_month": {},
            "by_category": {},
            "by_priority": {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
            },
        }

        for event in events:
            # By month
            month_key = event.due_date.strftime("%Y-%m")
            if month_key not in calendar["by_month"]:
                calendar["by_month"][month_key] = []
            calendar["by_month"][month_key].append({
                "id": event.id,
                "title": event.title,
                "date": event.due_date.isoformat(),
                "priority": event.priority.value,
                "category": event.category.value,
            })

            # By category
            cat = event.category.value
            calendar["by_category"][cat] = calendar["by_category"].get(cat, 0) + 1

            # By priority
            calendar["by_priority"][event.priority.value] += 1

        return calendar


def calculate_compliance_score(
    events: list[ComplianceEvent],
    completed_event_ids: Optional[Iterable[str]] = None,
    today: Optional[date] = None,
) -> Optional[float]:
    """
    Calculate compliance score from a list of events plus completion data.

    `completed_event_ids` must be supplied explicitly; an empty set means
    "nothing was filed" (score 0) while None means "unknown" (score None -
    insufficient data). Returns None when no event has fallen due yet.
    """
    today = today or date.today()
    past_events = [e for e in events if e.due_date < today]
    if not past_events or completed_event_ids is None:
        return INSUFFICIENT_DATA
    completed = set(completed_event_ids)
    completed_count = sum(1 for e in past_events if e.id in completed)
    return round((completed_count / len(past_events)) * 100, 2)


def generate_calendar_year(fiscal_year: int, taxpayer_type: str = "individual") -> dict:
    """Generate calendar for a year."""
    config = CalendarConfig(
        fiscal_year=fiscal_year,
        taxpayer_type=taxpayer_type,
    )
    engine = CalendarEngine(config)
    return engine.generate_year_calendar(fiscal_year)
