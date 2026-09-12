"""
Compliance Calendar API - Production-Grade
==========================================

Unified high-level API for compliance calendar operations:
- Get upcoming tasks
- Get calendar for period
- Get compliance score
- Mark events as completed
- Schedule reminders
- Generate year calendar
- Export calendar (JSON/CSV)
"""

import csv
import io
import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Optional

from app.compliance_calendar.events import (
    ComplianceEvent, EventType, EventCategory, EventPriority,
    get_all_events, get_events_by_year, get_upcoming_events,
)
from app.compliance_calendar.calendar_engine import (
    CalendarEngine, CalendarConfig, calculate_compliance_score,
)
from app.compliance_calendar.notifications import (
    NotificationManager, NotificationChannel, NotificationPriority,
    get_notification_manager,
)

logger = logging.getLogger("compliance_calendar")


@dataclass
class CalendarQuery:
    """Query parameters for calendar."""
    taxpayer_type: str = "individual"
    fiscal_year: Optional[int] = None
    tax_year: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    event_types: list[EventType] = field(default_factory=list)
    categories: list[EventCategory] = field(default_factory=list)
    min_priority: EventPriority = EventPriority.LOW
    include_holidays: bool = True
    limit: Optional[int] = None


@dataclass
class UpcomingTask:
    """Upcoming task summary."""
    event_id: str
    title: str
    due_date: str
    days_remaining: int
    priority: str
    category: str
    event_type: str
    is_overdue: bool
    urgency: str
    action_required: str


@dataclass
class CalendarResponse:
    """Full calendar response."""
    query: dict
    total_events: int
    events: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    upcoming_tasks: list[UpcomingTask] = field(default_factory=list)
    overdue_events: list[dict] = field(default_factory=list)
    compliance_score: float = 0.0
    compliance_grade: str = "F"
    recommendations: list[str] = field(default_factory=list)
    generated_at: str = ""


class ComplianceCalendarAPI:
    """Main API for compliance calendar."""

    def __init__(self):
        self.notification_manager = get_notification_manager()
        self.completed_events: set[str] = set()  # Track manually completed events

    def get_calendar(self, query: CalendarQuery) -> CalendarResponse:
        """Get compliance calendar based on query."""
        config = CalendarConfig(
            taxpayer_type=query.taxpayer_type,
            tax_year=query.tax_year or date.today().year - 1,
            fiscal_year=query.fiscal_year or 2025,
        )
        engine = CalendarEngine(config)

        # Get applicable events
        all_events = get_all_events()
        filtered_events = []

        for event in all_events:
            if not self._matches_query(event, query):
                continue
            if not self._is_applicable(event, query.taxpayer_type):
                continue
            if not query.include_holidays and self._is_holiday(event):
                continue
            filtered_events.append(event)

        # Apply limit
        if query.limit:
            filtered_events = filtered_events[:query.limit]

        # Build response
        events_data = [self._event_to_dict(e) for e in filtered_events]
        upcoming = self._build_upcoming_tasks(filtered_events)
        overdue = [
            self._event_to_dict(e) for e in filtered_events
            if e.is_overdue()
        ]
        score = engine.calculate_compliance_score()
        grade = engine.get_compliance_grade()
        summary = self._build_summary(filtered_events, query)
        recommendations = self._build_recommendations(filtered_events, score)

        return CalendarResponse(
            query=asdict(query) if hasattr(query, '__dataclass_fields__') else {},
            total_events=len(filtered_events),
            events=events_data,
            summary=summary,
            upcoming_tasks=upcoming,
            overdue_events=overdue,
            compliance_score=score,
            compliance_grade=grade,
            recommendations=recommendations,
            generated_at=datetime.utcnow().isoformat(),
        )

    def get_upcoming_tasks(
        self,
        taxpayer_type: str = "individual",
        days: int = 30,
    ) -> list[UpcomingTask]:
        """Get upcoming tasks for a taxpayer type."""
        query = CalendarQuery(
            taxpayer_type=taxpayer_type,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=days),
        )
        response = self.get_calendar(query)
        return response.upcoming_tasks

    def mark_event_completed(self, event_id: str) -> bool:
        """Mark an event as completed (user has filed)."""
        self.completed_events.add(event_id)
        logger.info(f"Event marked as completed: {event_id}")
        return True

    def schedule_reminders(
        self,
        event_id: str,
        recipient: str = "user@example.com",
        channels: Optional[list[NotificationChannel]] = None,
    ) -> dict:
        """Schedule reminder notifications for an event."""
        events = [e for e in get_all_events() if e.id == event_id]
        if not events:
            return {"error": "Event not found"}

        event = events[0]
        days_remaining = event.days_until_due()

        if days_remaining < 0:
            return {"error": "Event is already overdue"}

        records = self.notification_manager.schedule_notification(
            event_id=event.id,
            event_title=event.title,
            due_date=event.due_date.isoformat(),
            days_remaining=days_remaining,
            recipient=recipient,
            channels=channels or [NotificationChannel.EMAIL, NotificationChannel.PUSH],
            priority=self._get_notification_priority(event.priority),
        )

        return {
            "event_id": event_id,
            "reminders_scheduled": len(records),
            "reminder_ids": [r.id for r in records],
        }

    def export_calendar(
        self,
        query: CalendarQuery,
        format: str = "json",
    ) -> str:
        """Export calendar to JSON or CSV."""
        response = self.get_calendar(query)

        if format == "json":
            return json.dumps(
                {
                    "total_events": response.total_events,
                    "events": response.events,
                    "compliance_score": response.compliance_score,
                    "compliance_grade": response.compliance_grade,
                    "generated_at": response.generated_at,
                },
                indent=2,
            )

        elif format == "csv":
            output = io.StringIO()
            if response.events:
                writer = csv.DictWriter(output, fieldnames=response.events[0].keys())
                writer.writeheader()
                writer.writerows(response.events)
            return output.getvalue()

        else:
            raise ValueError(f"Unsupported format: {format}")

    def get_dashboard_summary(self, taxpayer_type: str = "individual") -> dict:
        """Get dashboard summary for compliance status."""
        today = date.today()
        query = CalendarQuery(taxpayer_type=taxpayer_type)
        response = self.get_calendar(query)

        # Critical events in next 30 days
        critical_upcoming = [
            t for t in response.upcoming_tasks
            if t.priority == "critical" and t.days_remaining <= 30
        ]

        # Critical events in next 7 days
        critical_7_days = [
            t for t in response.upcoming_tasks
            if t.priority == "critical" and t.days_remaining <= 7
        ]

        return {
            "taxpayer_type": taxpayer_type,
            "compliance_score": response.compliance_score,
            "compliance_grade": response.compliance_grade,
            "total_events": response.total_events,
            "overdue_count": len(response.overdue_events),
            "critical_upcoming_30d": len(critical_upcoming),
            "critical_upcoming_7d": len(critical_7_days),
            "next_7_days_tasks": [
                {
                    "title": t.title,
                    "due_date": t.due_date,
                    "days_remaining": t.days_remaining,
                }
                for t in response.upcoming_tasks
                if t.days_remaining <= 7
            ],
            "compliance_grade_color": self._get_grade_color(response.compliance_grade),
            "summary_message": self._get_grade_message(
                response.compliance_grade,
                len(response.overdue_events)
            ),
        }

    def _matches_query(self, event: ComplianceEvent, query: CalendarQuery) -> bool:
        """Check if event matches query filters."""
        if query.start_date and event.due_date < query.start_date:
            return False
        if query.end_date and event.due_date > query.end_date:
            return False
        if query.fiscal_year and event.fiscal_year != query.fiscal_year:
            return False
        if query.tax_year and event.tax_year != query.tax_year:
            return False
        if query.event_types and event.event_type not in query.event_types:
            return False
        if query.categories and event.category not in query.categories:
            return False

        # Priority check
        priority_order = {
            EventPriority.LOW: 0,
            EventPriority.MEDIUM: 1,
            EventPriority.HIGH: 2,
            EventPriority.CRITICAL: 3,
        }
        if priority_order.get(event.priority, 0) < priority_order.get(query.min_priority, 0):
            return False

        return True

    def _is_applicable(self, event: ComplianceEvent, taxpayer_type: str) -> bool:
        """Check if event applies to taxpayer."""
        if "all" in event.applicable_to:
            return True
        return taxpayer_type in event.applicable_to

    def _is_holiday(self, event: ComplianceEvent) -> bool:
        """Check if event is a holiday."""
        return event.category == EventCategory.REGULATORY and "Holiday" in event.title

    def _event_to_dict(self, event: ComplianceEvent) -> dict:
        """Convert event to dictionary."""
        return {
            "id": event.id,
            "title": event.title,
            "description": event.description,
            "due_date": event.due_date.isoformat(),
            "fiscal_year": event.fiscal_year,
            "tax_year": event.tax_year,
            "quarter": event.quarter,
            "priority": event.priority.value,
            "category": event.category.value,
            "event_type": event.event_type.value,
            "legal_reference": event.legal_reference,
            "penalty": event.penalty_for_non_compliance,
            "days_remaining": event.days_until_due(),
            "is_overdue": event.is_overdue(),
            "is_completed": event.id in self.completed_events,
            "extension_available": event.is_filing_extension_available,
            "extension_date": event.extension_date.isoformat() if event.extension_date else None,
        }

    def _build_upcoming_tasks(self, events: list[ComplianceEvent]) -> list[UpcomingTask]:
        """Build upcoming tasks list."""
        tasks = []
        for event in events:
            days = event.days_until_due()
            if days < 0:
                continue  # Skip overdue (handled separately)
            tasks.append(UpcomingTask(
                event_id=event.id,
                title=event.title,
                due_date=event.due_date.isoformat(),
                days_remaining=days,
                priority=event.priority.value,
                category=event.category.value,
                event_type=event.event_type.value,
                is_overdue=False,
                urgency=self._get_urgency(days),
                action_required=self._get_action_required(event),
            ))
        # Sort by days remaining
        tasks.sort(key=lambda x: x.days_remaining)
        return tasks

    def _build_summary(self, events: list[ComplianceEvent], query: CalendarQuery) -> dict:
        """Build summary statistics."""
        summary = {
            "by_category": {},
            "by_priority": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            "by_month": {},
            "by_type": {},
        }

        for event in events:
            cat = event.category.value
            summary["by_category"][cat] = summary["by_category"].get(cat, 0) + 1
            summary["by_priority"][event.priority.value] += 1

            month_key = event.due_date.strftime("%Y-%m")
            summary["by_month"][month_key] = summary["by_month"].get(month_key, 0) + 1

            type_key = event.event_type.value
            summary["by_type"][type_key] = summary["by_type"].get(type_key, 0) + 1

        return summary

    def _build_recommendations(self, events: list[ComplianceEvent], score: float) -> list[str]:
        """Build recommendations based on events."""
        recommendations = []

        if score < 70:
            recommendations.append(
                "⚠️ Your compliance score is low. File all pending returns immediately."
            )

        # Check for overdue
        overdue_count = sum(1 for e in events if e.is_overdue())
        if overdue_count > 0:
            recommendations.append(
                f"🔴 You have {overdue_count} overdue compliance items. "
                f"Take action immediately to minimize penalties."
            )

        # Check for upcoming critical
        critical_upcoming = [
            e for e in events
            if e.priority == EventPriority.CRITICAL
            and 0 <= e.days_until_due() <= 7
        ]
        if critical_upcoming:
            recommendations.append(
                f"📅 {len(critical_upcoming)} critical events due in next 7 days. "
                f"Plan your schedule accordingly."
            )

        # General recommendations
        recommendations.append(
            "💡 Set up automatic reminders 30, 14, and 7 days before deadlines."
        )
        recommendations.append(
            "💡 Keep digital copies of all filings and acknowledgments."
        )
        recommendations.append(
            "💡 Engage a tax professional for complex compliance matters."
        )

        return recommendations

    def _get_urgency(self, days: int) -> str:
        """Get urgency level for a task."""
        if days <= 0:
            return "overdue"
        elif days <= 1:
            return "critical"
        elif days <= 3:
            return "very_high"
        elif days <= 7:
            return "high"
        elif days <= 14:
            return "medium"
        elif days <= 30:
            return "low"
        else:
            return "very_low"

    def _get_action_required(self, event: ComplianceEvent) -> str:
        """Get action required for event."""
        if event.priority == EventPriority.CRITICAL:
            return "URGENT: Take immediate action"
        elif event.priority == EventPriority.HIGH:
            return "Important: Schedule this task"
        else:
            return "Plan ahead"

    def _get_notification_priority(self, event_priority: EventPriority) -> NotificationPriority:
        """Map event priority to notification priority."""
        mapping = {
            EventPriority.CRITICAL: NotificationPriority.URGENT,
            EventPriority.HIGH: NotificationPriority.HIGH,
            EventPriority.MEDIUM: NotificationPriority.NORMAL,
            EventPriority.LOW: NotificationPriority.LOW,
        }
        return mapping.get(event_priority, NotificationPriority.NORMAL)

    def _get_grade_color(self, grade: str) -> str:
        """Get color code for grade."""
        color_map = {
            "A+": "green",
            "A": "green",
            "B": "blue",
            "C": "orange",
            "D": "red",
            "F": "red",
        }
        return color_map.get(grade, "gray")

    def _get_grade_message(self, grade: str, overdue_count: int) -> str:
        """Get user-friendly grade message."""
        if grade in ("A+", "A"):
            return "Excellent! You're highly compliant. Keep up the great work! 🎉"
        elif grade == "B":
            return "Good compliance! Minor improvements possible."
        elif grade == "C":
            return "Average compliance. Please focus on filing on time."
        elif grade == "D":
            return "Below average. You need to catch up on filings."
        else:
            return f"Critical: {overdue_count} overdue items. Take action now!"


# Singleton
_calendar_api: Optional[ComplianceCalendarAPI] = None


def get_compliance_calendar() -> ComplianceCalendarAPI:
    """Get singleton compliance calendar API."""
    global _calendar_api
    if _calendar_api is None:
        _calendar_api = ComplianceCalendarAPI()
    return _calendar_api
