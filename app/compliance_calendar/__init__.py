"""
Compliance Calendar - Production-Grade
=======================================

FBR compliance deadlines aur reminders ka centralized system:
- Annual return filing deadlines
- Quarterly advance tax payments
- Withholding tax deposit dates
- Wealth statement / assets declaration
- Sales tax returns (monthly/quarterly)
- Federal excise returns
- Custom duty obligations
- Provincial compliance (Punjab/Sindh/KPK/Balochistan)
- Sector-specific deadlines (banking, telecom, etc.)
- Auto-generated reminders (90/60/30/7/1 days before)
- Holiday/weekend awareness
- Email/SMS notification simulation
- Recurring task management
- Compliance score tracking

Pakistani tax calendar 2025-26 ka complete reference.
"""

from app.compliance_calendar.events import (
    ComplianceEvent, EventType, EventCategory, EventPriority,
    get_all_events, get_events_by_year, get_events_by_type,
)
from app.compliance_calendar.calendar_engine import (
    CalendarEngine, CalendarConfig, ReminderSchedule,
    calculate_compliance_score, generate_calendar_year,
)
from app.compliance_calendar.recurrence import (
    RecurrenceRule, RecurrenceType, expand_recurring_events,
)
from app.compliance_calendar.notifications import (
    NotificationManager, NotificationChannel, NotificationStatus,
    NotificationRecord, get_notification_manager,
)
from app.compliance_calendar.calendar_api import (
    ComplianceCalendarAPI, get_compliance_calendar,
    CalendarQuery, CalendarResponse, UpcomingTask,
)

__all__ = [
    "ComplianceEvent",
    "EventType",
    "EventCategory",
    "EventPriority",
    "get_all_events",
    "get_events_by_year",
    "get_events_by_type",
    "CalendarEngine",
    "CalendarConfig",
    "ReminderSchedule",
    "calculate_compliance_score",
    "generate_calendar_year",
    "RecurrenceRule",
    "RecurrenceType",
    "expand_recurring_events",
    "NotificationManager",
    "NotificationChannel",
    "NotificationStatus",
    "NotificationRecord",
    "get_notification_manager",
    "ComplianceCalendarAPI",
    "get_compliance_calendar",
    "CalendarQuery",
    "CalendarResponse",
    "UpcomingTask",
]
