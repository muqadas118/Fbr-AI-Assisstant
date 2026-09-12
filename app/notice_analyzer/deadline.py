"""
Notice Deadline Calculator - Production-Grade
==============================================

Calculates response deadlines for different notice types per FBR rules.

Standard response periods:
- Show Cause Notice: 14-30 days
- Assessment Order: 30 days (appeal period)
- Demand Notice: 30 days
- Recovery Notice: 15-30 days
- Penalty Notice: 30 days
- Audit Notice: 14 days
- Enquiry Notice: 7-14 days
- Intimation: 15 days
- Wealth Statement: 30 days
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from app.notice_analyzer.classifier import NoticeType


@dataclass
class DeadlineInfo:
    """Calculated deadline information."""
    issue_date: Optional[str]
    deadline_date: Optional[str]
    days_remaining: Optional[int]
    days_given: int
    is_overdue: bool
    urgency_level: str  # "critical", "high", "medium", "low"
    next_action: str
    notes: list


# Standard response periods (in days)
RESPONSE_PERIODS = {
    NoticeType.SHOW_CAUSE_114: 14,
    NoticeType.SHOW_CAUSE_122: 14,
    NoticeType.SHOW_CAUSE_161: 14,
    NoticeType.SHOW_CAUSE_GENERAL: 14,

    NoticeType.ASSESSMENT_120: 30,
    NoticeType.ASSESSMENT_121: 30,
    NoticeType.ASSESSMENT_122: 30,
    NoticeType.PROVISIONAL_ASSESSMENT: 30,
    NoticeType.BEST_JUDGMENT: 30,
    NoticeType.AMENDED_ASSESSMENT: 30,

    NoticeType.DEMAND_137: 30,
    NoticeType.RECOVERY_138: 15,
    NoticeType.ARREARS_NOTICE: 30,

    NoticeType.PENALTY_182: 30,
    NoticeType.PENALTY_184: 30,
    NoticeType.PENALTY_GENERAL: 30,

    NoticeType.AUDIT_214C: 14,
    NoticeType.AUDIT_SELECTION: 14,
    NoticeType.ENQUIRY_176: 7,

    NoticeType.INTIMATION_143: 15,
    NoticeType.RECTIFICATION: 30,
    NoticeType.REVISION: 30,
    NoticeType.AMENDMENT: 30,

    NoticeType.REFUND_NOTICE: 60,
    NoticeType.WEALTH_STATEMENT: 30,
    NoticeType.COMPLIANCE_NOTICE: 14,

    NoticeType.APPEAL_ORDER: 0,  # Already decided
    NoticeType.STAY_ORDER: 0,

    NoticeType.PROSECUTION: 14,
    NoticeType.SURVEY: 7,
    NoticeType.ATTACHMENT: 7,
    NoticeType.SEIZURE: 7,
    NoticeType.AUCTION: 7,
    NoticeType.SEALING: 7,

    NoticeType.INFORMATION_REQUEST: 14,
    NoticeType.RECONCILIATION: 14,
    NoticeType.ADJUSTMENT: 14,
}


class DeadlineCalculator:
    """Calculates notice response deadlines."""

    @staticmethod
    def calculate(notice_type: NoticeType, issue_date_str: Optional[str]) -> DeadlineInfo:
        """
        Calculate deadline for a notice.

        Args:
            notice_type: Classified notice type
            issue_date_str: Issue date in YYYY-MM-DD format
        """
        notes = []

        # Get response period
        days_given = RESPONSE_PERIODS.get(notice_type, 30)
        notes.append(f"Standard response period: {days_given} days")

        # Parse issue date
        issue_date = None
        if issue_date_str:
            try:
                issue_date = datetime.strptime(issue_date_str, "%Y-%m-%d")
            except ValueError:
                notes.append(f"Could not parse issue date: {issue_date_str}")

        # Calculate deadline
        if issue_date:
            deadline_date = issue_date + timedelta(days=days_given)
            deadline_str = deadline_date.strftime("%Y-%m-%d")

            # Calculate days remaining
            today = datetime.now()
            days_remaining = (deadline_date - today).days
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
            is_overdue = False
            urgency = "unknown"
            next_action = "Issue date not found - cannot calculate deadline"
            notes.append("Provide issue date to calculate deadline")

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
