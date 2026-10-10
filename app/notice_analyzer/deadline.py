"""
Notice Deadline Calculator - Production-Grade
==============================================

Calculates response deadlines for FBR notices.

RULE: a deadline is only ever derived from a response date that is LABELED
in the notice itself (e.g. "respond by 15-03-2024", "within 14 days of this
notice"). No response period is invented for a notice type - if the notice
does not state one, the deadline is reported as unknown rather than guessed.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from app.notice_analyzer.classifier import NoticeType


@dataclass
class DeadlineInfo:
    """Calculated deadline information."""
    issue_date: Optional[str]
    deadline_date: Optional[str]
    days_remaining: Optional[int]
    days_given: Optional[int]
    is_overdue: bool
    urgency_level: str  # "critical", "high", "medium", "low", "unknown"
    next_action: str
    notes: list


class DeadlineCalculator:
    """Calculates notice response deadlines."""

    @staticmethod
    def calculate(
        notice_type: NoticeType,
        issue_date_str: Optional[str],
        deadline_date_str: Optional[str] = None,
    ) -> DeadlineInfo:
        """
        Calculate deadline for a notice.

        Args:
            notice_type: Classified notice type
            issue_date_str: Issue date in YYYY-MM-DD format
            deadline_date_str: Response deadline stated in the notice
                (YYYY-MM-DD). When absent, no deadline is invented.
        """
        notes = []

        # Parse issue date
        issue_date = None
        if issue_date_str:
            try:
                issue_date = datetime.strptime(issue_date_str, "%Y-%m-%d")
            except ValueError:
                notes.append(f"Could not parse issue date: {issue_date_str}")

        # Parse the response deadline stated in the notice itself
        deadline_date = None
        if deadline_date_str:
            try:
                deadline_date = datetime.strptime(deadline_date_str, "%Y-%m-%d")
            except ValueError:
                notes.append(f"Could not parse response deadline: {deadline_date_str}")

        # Calculate deadline
        if deadline_date:
            deadline_str = deadline_date.strftime("%Y-%m-%d")
            # Days allowed = gap between the stated deadline and the issue date;
            # reported only when the issue date is actually known.
            days_given = (deadline_date - issue_date).days if issue_date else None
            notes.append(f"Response deadline stated in notice: {deadline_str}")

            # Compare calendar dates so a notice due TODAY is due today, not
            # overdue (the deadline lands at midnight, timestamps would lie).
            today = date.today()
            days_remaining = (deadline_date.date() - today).days
            is_overdue = days_remaining < 0

            if is_overdue:
                urgency = "critical"
                next_action = "URGENT: Deadline passed - file late response or appeal immediately"
            elif days_remaining <= 3:
                urgency = "critical"
                next_action = f"URGENT: Only {days_remaining} days left to respond"
            elif days_remaining <= 7:
                urgency = "high"
                next_action = f"High priority: {days_remaining} days to respond"
            elif days_remaining <= 14:
                urgency = "medium"
                next_action = f"Medium priority: {days_remaining} days to respond"
            else:
                urgency = "low"
                next_action = f"Plan response within {days_remaining} days"
        else:
            deadline_str = None
            days_remaining = None
            days_given = None
            is_overdue = False
            urgency = "unknown"
            next_action = "No response deadline stated in notice - deadline could not be determined"
            notes.append("Deadline could not be determined: no response date labeled in the notice")

        return DeadlineInfo(
            issue_date=issue_date_str,
            deadline_date=deadline_str,
            days_remaining=days_remaining,
            days_given=days_given,
            is_overdue=is_overdue,
            urgency_level=urgency,
            next_action=next_action,
            notes=notes,
        )
