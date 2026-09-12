"""
Recurrence Rules for Compliance Events
======================================

Handle recurring events:
- Annual (yearly)
- Quarterly
- Monthly
- Custom intervals
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Optional

from app.compliance_calendar.events import ComplianceEvent, EventType


class RecurrenceType(str, Enum):
    """Type of recurrence."""
    NONE = "none"
    ANNUAL = "annual"
    QUARTERLY = "quarterly"
    MONTHLY = "monthly"
    BIANNUAL = "biannual"
    CUSTOM = "custom"


@dataclass
class RecurrenceRule:
    """Rule for recurring events."""
    event_id: str
    recurrence_type: RecurrenceType
    start_date: date
    end_date: Optional[date] = None
    interval: int = 1  # Every N periods

    def get_next_dates(self, count: int = 5) -> list[date]:
        """Get next N occurrence dates."""
        dates = []
        current = self.start_date

        for _ in range(count):
            if self.end_date and current > self.end_date:
                break

            dates.append(current)

            if self.recurrence_type == RecurrenceType.ANNUAL:
                current = current.replace(year=current.year + self.interval)
            elif self.recurrence_type == RecurrenceType.QUARTERLY:
                # Add 3 months
                current = self._add_months(current, 3)
            elif self.recurrence_type == RecurrenceType.MONTHLY:
                current = self._add_months(current, 1)
            elif self.recurrence_type == RecurrenceType.BIANNUAL:
                current = current.replace(year=current.year + 2)
            else:
                break

        return dates

    @staticmethod
    def _add_months(d: date, months: int) -> date:
        """Add N months to a date, handling month-end edge cases."""
        new_month = d.month + months
        new_year = d.year + (new_month - 1) // 12
        new_month = ((new_month - 1) % 12) + 1
        # Clamp day to valid range for new month
        max_day = calendar.monthrange(new_year, new_month)[1]
        new_day = min(d.day, max_day)
        return date(new_year, new_month, new_day)


def expand_recurring_events(
    base_event: ComplianceEvent,
    end_date: date,
) -> list[ComplianceEvent]:
    """Expand a recurring event into multiple instances."""
    if not base_event.is_recurring:
        return [base_event]

    # Map event type to recurrence
    recurrence_map = {
        "annual": RecurrenceType.ANNUAL,
        "quarterly": RecurrenceType.QUARTERLY,
        "monthly": RecurrenceType.MONTHLY,
    }

    rec_type = recurrence_map.get(base_event.recurrence_type, RecurrenceType.ANNUAL)
    rule = RecurrenceRule(
        event_id=base_event.id,
        recurrence_type=rec_type,
        start_date=base_event.due_date,
        end_date=end_date,
    )

    dates = rule.get_next_dates(count=10)
    expanded = []

    for i, d in enumerate(dates):
        new_event = ComplianceEvent(
            id=f"{base_event.id}-{d.year}" if rec_type == RecurrenceType.ANNUAL else f"{base_event.id}-{i}",
            title=base_event.title,
            description=base_event.description,
            event_type=base_event.event_type,
            category=base_event.category,
            due_date=d,
            fiscal_year=base_event.fiscal_year + (d.year - base_event.due_date.year),
            tax_year=base_event.tax_year,
            quarter=base_event.quarter,
            priority=base_event.priority,
            penalty_for_non_compliance=base_event.penalty_for_non_compliance,
            legal_reference=base_event.legal_reference,
            is_filing_extension_available=base_event.is_filing_extension_available,
            extension_date=base_event.extension_date,
            extension_fee=base_event.extension_fee,
            applicable_to=base_event.applicable_to,
            sector_filter=base_event.sector_filter,
            is_recurring=True,
            recurrence_type=base_event.recurrence_type,
            notes=base_event.notes,
        )
        expanded.append(new_event)

    return expanded
