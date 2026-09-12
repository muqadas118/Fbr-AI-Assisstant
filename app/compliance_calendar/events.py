"""
Compliance Calendar Events - Production-Grade
============================================

FBR compliance events ka complete database:
- Tax return filing deadlines
- Advance tax payment dates
- Withholding tax statements
- Sales tax returns
- Federal excise returns
- Wealth statement declarations
- Audit requirements
- Tax audit calendar
- Sector-specific compliance
- Provincial tax compliance

Pakistan fiscal year: July 1 - June 30
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Optional


class EventType(str, Enum):
    """Type of compliance event."""
    # Income Tax
    ANNUAL_RETURN = "annual_return"
    QUARTERLY_ADVANCE_TAX = "quarterly_advance_tax"
    WEALTH_STATEMENT = "wealth_statement"
    TAX_AUDIT = "tax_audit"
    APPEAL_FILING = "appeal_filing"

    # Withholding Tax
    WHT_STATEMENT = "wht_statement"
    WHT_CERTIFICATE = "wht_certificate"
    WHT_DEPOSIT = "wht_deposit"

    # Sales Tax
    SALES_TAX_RETURN_MONTHLY = "sales_tax_return_monthly"
    SALES_TAX_RETURN_QUARTERLY = "sales_tax_return_quarterly"
    SALES_TAX_AUDIT = "sales_tax_audit"

    # Federal Excise
    FEDERAL_EXCISE_RETURN = "federal_excise_return"

    # Customs
    CUSTOMS_RETURN = "customs_return"
    CUSTOMS_AUDIT = "customs_audit"

    # Provincial
    PROVINCIAL_SALES_TAX = "provincial_sales_tax"
    PROVINCIAL_AUDIT = "provincial_audit"

    # Other
    REGISTRATION_RENEWAL = "registration_renewal"
    CERTIFICATE_RENEWAL = "certificate_renewal"
    ANNUAL_GENERAL_MEETING = "agm"
    FILING_EXTENSION = "filing_extension"
    AMNESTY_SCHEME = "amnesty_scheme"
    VOLUNTARY_DISCLOSURE = "voluntary_disclosure"


class EventCategory(str, Enum):
    """Category of compliance event."""
    INCOME_TAX = "income_tax"
    WITHHOLDING_TAX = "withholding_tax"
    SALES_TAX = "sales_tax"
    FEDERAL_EXCISE = "federal_excise"
    CUSTOMS = "customs"
    PROVINCIAL_TAX = "provincial_tax"
    REGULATORY = "regulatory"
    SPECIAL_SCHEME = "special_scheme"


class EventPriority(str, Enum):
    """Priority level."""
    CRITICAL = "critical"  # Heavy penalty for non-compliance
    HIGH = "high"          # Significant penalty
    MEDIUM = "medium"      # Moderate penalty
    LOW = "low"            # Minor penalty/notice


@dataclass
class ComplianceEvent:
    """
    Single compliance event/deadline.

    Example:
        ComplianceEvent(
            id="itr-filing-2025",
            title="Income Tax Return Filing - TY2025",
            description="Last date to file income tax return for Tax Year 2025",
            event_type=EventType.ANNUAL_RETURN,
            category=EventCategory.INCOME_TAX,
            due_date=date(2025, 9, 30),
            fiscal_year=2025,
            tax_year=2025,
            priority=EventPriority.CRITICAL,
            penalty_for_non_compliance="PKR 500 to 5,000 per day + 50% default surcharge",
            legal_reference="Section 114, ITO 2001",
            is_filing_extension_available=True,
            extension_date=date(2025, 12, 31),
            extension_fee=5000,
            applicable_to=["individual", "business", "company"],
            is_recurring=True,
            recurrence_type="annual",
        )
    """
    id: str
    title: str
    description: str
    event_type: EventType
    category: EventCategory
    due_date: date

    # Year context
    fiscal_year: int
    tax_year: Optional[int] = None
    quarter: Optional[int] = None  # 1, 2, 3, or 4

    # Urgency & priority
    priority: EventPriority = EventPriority.HIGH
    penalty_for_non_compliance: str = ""

    # Legal reference
    legal_reference: str = ""

    # Extension options
    is_filing_extension_available: bool = False
    extension_date: Optional[date] = None
    extension_fee: float = 0.0

    # Applicability
    applicable_to: list[str] = field(default_factory=list)
    sector_filter: Optional[str] = None  # e.g., "banking", "telecom"

    # Recurrence
    is_recurring: bool = True
    recurrence_type: str = "annual"  # annual, quarterly, monthly

    # Notes
    notes: list[str] = field(default_factory=list)
    is_active: bool = True

    # Metadata
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()
        if isinstance(self.event_type, str):
            self.event_type = EventType(self.event_type)
        if isinstance(self.category, str):
            self.category = EventCategory(self.category)
        if isinstance(self.priority, str):
            self.priority = EventPriority(self.priority)

    def days_until_due(self, from_date: Optional[date] = None) -> int:
        """Calculate days until due date."""
        if from_date is None:
            from_date = date.today()
        delta = self.due_date - from_date
        return delta.days

    def is_overdue(self, from_date: Optional[date] = None) -> bool:
        """Check if event is overdue."""
        return self.days_until_due(from_date) < 0

    def is_within_days(self, days: int, from_date: Optional[date] = None) -> bool:
        """Check if due date is within N days."""
        d = self.days_until_due(from_date)
        return 0 <= d <= days


# =============================================================================
# COMPLIANCE EVENTS DATABASE - FY 2025-26 (July 2025 - June 2026)
# =============================================================================

def _build_events_2025_26() -> list[ComplianceEvent]:
    """Build all compliance events for fiscal year 2025-26."""
    events = []

    # =========================================================================
    # JULY 2025 - Q1 STARTS
    # =========================================================================

    # July 1 - Start of fiscal year
    events.append(ComplianceEvent(
        id="fy-start-2025",
        title="Fiscal Year 2025-26 Begins",
        description="Start of new fiscal year for tax purposes",
        event_type=EventType.ANNUAL_RETURN,
        category=EventCategory.INCOME_TAX,
        due_date=date(2025, 7, 1),
        fiscal_year=2025,
        priority=EventPriority.LOW,
        applicable_to=["all"],
        is_recurring=False,
        notes=["New tax year begins", "Advance tax planning recommended"],
    ))

    # July 15 - Q1 Advance Tax Installment 1 (for Companies/AOPs)
    events.append(ComplianceEvent(
        id="q1-adv-tax-2025",
        title="Q1 Advance Tax Installment - Due Date",
        description="First quarterly advance tax payment for Companies and AOPs",
        event_type=EventType.QUARTERLY_ADVANCE_TAX,
        category=EventCategory.INCOME_TAX,
        due_date=date(2025, 7, 15),
        fiscal_year=2025,
        quarter=1,
        priority=EventPriority.CRITICAL,
        penalty_for_non_compliance="10% surcharge on unpaid amount",
        legal_reference="Section 147, ITO 2001",
        applicable_to=["company", "aop"],
        notes=["15% of total advance tax estimated"],
    ))

    # July 31 - July Sales Tax Return (Monthly filers)
    events.append(ComplianceEvent(
        id="st-jul-2025",
        title="Sales Tax Return - July 2025",
        description="Monthly sales tax return for July 2025",
        event_type=EventType.SALES_TAX_RETURN_MONTHLY,
        category=EventCategory.SALES_TAX,
        due_date=date(2025, 7, 31),
        fiscal_year=2025,
        priority=EventPriority.HIGH,
        penalty_for_non_compliance="PKR 500/day + 5% default surcharge",
        legal_reference="Sales Tax Act 1990, Section 26",
        applicable_to=["registered_persons"],
        recurrence_type="monthly",
    ))

    # =========================================================================
    # AUGUST 2025
    # =========================================================================

    # August 14 - Pakistan Independence Day (Holiday)
    events.append(ComplianceEvent(
        id="independence-day-2025",
        title="Independence Day of Pakistan",
        description="National holiday - FBR offices closed",
        event_type=EventType.REGISTRATION_RENEWAL,
        category=EventCategory.REGULATORY,
        due_date=date(2025, 8, 14),
        fiscal_year=2025,
        priority=EventPriority.LOW,
        applicable_to=["all"],
        is_recurring=False,
        notes=["Holiday - no compliance deadlines"],
    ))

    # August 31 - August Sales Tax Return
    events.append(ComplianceEvent(
        id="st-aug-2025",
        title="Sales Tax Return - August 2025",
        description="Monthly sales tax return for August 2025",
        event_type=EventType.SALES_TAX_RETURN_MONTHLY,
        category=EventCategory.SALES_TAX,
        due_date=date(2025, 8, 31),
        fiscal_year=2025,
        priority=EventPriority.HIGH,
        penalty_for_non_compliance="PKR 500/day + 5% default surcharge",
        legal_reference="Sales Tax Act 1990, Section 26",
        applicable_to=["registered_persons"],
        recurrence_type="monthly",
    ))

    # =========================================================================
    # SEPTEMBER 2025 - TAX YEAR 2024 FILING DEADLINE
    # =========================================================================

    # September 30 - INCOME TAX RETURN FILING - CRITICAL DEADLINE
    events.append(ComplianceEvent(
        id="itr-ty2024-2025",
        title="Income Tax Return Filing - Tax Year 2024",
        description="Last date to file income tax return for Tax Year 2024",
        event_type=EventType.ANNUAL_RETURN,
        category=EventCategory.INCOME_TAX,
        due_date=date(2025, 9, 30),
        fiscal_year=2025,
        tax_year=2024,
        priority=EventPriority.CRITICAL,
        penalty_for_non_compliance="PKR 500/day + 50% default surcharge",
        legal_reference="Section 114, ITO 2001",
        is_filing_extension_available=True,
        extension_date=date(2025, 12, 31),
        extension_fee=5000,
        applicable_to=["individual", "business", "company", "aop"],
        is_recurring=False,
        notes=["Most important deadline of the year", "Late filing attracts heavy penalties"],
    ))

    # September 30 - Q2 Advance Tax Installment
    events.append(ComplianceEvent(
        id="q2-adv-tax-2025",
        title="Q2 Advance Tax Installment - Due Date",
        description="Second quarterly advance tax payment",
        event_type=EventType.QUARTERLY_ADVANCE_TAX,
        category=EventCategory.INCOME_TAX,
        due_date=date(2025, 9, 30),
        fiscal_year=2025,
        quarter=2,
        priority=EventPriority.CRITICAL,
        penalty_for_non_compliance="10% surcharge on unpaid amount",
        legal_reference="Section 147, ITO 2001",
        applicable_to=["company", "aop"],
    ))

    # September 30 - WEALTH STATEMENT FILING
    events.append(ComplianceEvent(
        id="wealth-stmt-ty2024-2025",
        title="Wealth Statement Filing - Tax Year 2024",
        description="Annual wealth statement with tax return",
        event_type=EventType.WEALTH_STATEMENT,
        category=EventCategory.INCOME_TAX,
        due_date=date(2025, 9, 30),
        fiscal_year=2025,
        tax_year=2024,
        priority=EventPriority.HIGH,
        penalty_for_non_compliance="PKR 1000/day + 10% wealth surcharge",
        legal_reference="Section 116, ITO 2001",
        applicable_to=["individual", "aop"],
        notes=["Attached with annual tax return"],
    ))

    # September 30 - August Sales Tax Return
    events.append(ComplianceEvent(
        id="st-sep-2025",
        title="Sales Tax Return - September 2025",
        description="Monthly sales tax return for September 2025",
        event_type=EventType.SALES_TAX_RETURN_MONTHLY,
        category=EventCategory.SALES_TAX,
        due_date=date(2025, 9, 30),
        fiscal_year=2025,
        priority=EventPriority.HIGH,
        recurrence_type="monthly",
    ))

    # =========================================================================
    # OCTOBER 2025
    # =========================================================================

    # October 15 - Q2 WHT Statement (July-Sept)
    events.append(ComplianceEvent(
        id="wht-q2-2025",
        title="Quarterly WHT Statement - Q2 FY25",
        description="Quarterly withholding tax statement for July-September 2025",
        event_type=EventType.WHT_STATEMENT,
        category=EventCategory.WITHHOLDING_TAX,
        due_date=date(2025, 10, 15),
        fiscal_year=2025,
        quarter=2,
        priority=EventPriority.HIGH,
        penalty_for_non_compliance="PKR 500/day",
        legal_reference="Section 165, ITO 2001",
        applicable_to=["all_withholders"],
        notes=["Also deposit any outstanding WHT amounts"],
    ))

    # October 31 - October Sales Tax Return
    events.append(ComplianceEvent(
        id="st-oct-2025",
        title="Sales Tax Return - October 2025",
        description="Monthly sales tax return for October 2025",
        event_type=EventType.SALES_TAX_RETURN_MONTHLY,
        category=EventCategory.SALES_TAX,
        due_date=date(2025, 10, 31),
        fiscal_year=2025,
        priority=EventPriority.HIGH,
        recurrence_type="monthly",
    ))

    # =========================================================================
    # NOVEMBER 2025
    # =========================================================================

    # November 15 - Q3 Advance Tax Installment
    events.append(ComplianceEvent(
        id="q3-adv-tax-2025",
        title="Q3 Advance Tax Installment - Due Date",
        description="Third quarterly advance tax payment",
        event_type=EventType.QUARTERLY_ADVANCE_TAX,
        category=EventCategory.INCOME_TAX,
        due_date=date(2025, 11, 15),
        fiscal_year=2025,
        quarter=3,
        priority=EventPriority.CRITICAL,
        applicable_to=["company", "aop"],
    ))

    # November 30 - November Sales Tax Return
    events.append(ComplianceEvent(
        id="st-nov-2025",
        title="Sales Tax Return - November 2025",
        description="Monthly sales tax return for November 2025",
        event_type=EventType.SALES_TAX_RETURN_MONTHLY,
        category=EventCategory.SALES_TAX,
        due_date=date(2025, 11, 30),
        fiscal_year=2025,
        priority=EventPriority.HIGH,
        recurrence_type="monthly",
    ))

    # =========================================================================
    # DECEMBER 2025 - Q3 ends
    # =========================================================================

    # December 15 - Q3 WHT Statement
    events.append(ComplianceEvent(
        id="wht-q3-2025",
        title="Quarterly WHT Statement - Q3 FY25",
        description="Quarterly withholding tax statement for October-December 2025",
        event_type=EventType.WHT_STATEMENT,
        category=EventCategory.WITHHOLDING_TAX,
        due_date=date(2025, 12, 15),
        fiscal_year=2025,
        quarter=3,
        priority=EventPriority.HIGH,
        applicable_to=["all_withholders"],
    ))

    # December 31 - LAST DATE FOR FILING EXTENSION
    events.append(ComplianceEvent(
        id="itr-ext-ty2024-2025",
        title="Income Tax Return Extension - Last Date",
        description="Last date to file tax return with extension for TY2024",
        event_type=EventType.FILING_EXTENSION,
        category=EventCategory.INCOME_TAX,
        due_date=date(2025, 12, 31),
        fiscal_year=2025,
        tax_year=2024,
        priority=EventPriority.CRITICAL,
        penalty_for_non_compliance="Full late filing penalties apply",
        applicable_to=["individual", "business", "company", "aop"],
        is_recurring=False,
        notes=["No further extension after this date"],
    ))

    # December 31 - December Sales Tax Return
    events.append(ComplianceEvent(
        id="st-dec-2025",
        title="Sales Tax Return - December 2025",
        description="Monthly sales tax return for December 2025",
        event_type=EventType.SALES_TAX_RETURN_MONTHLY,
        category=EventCategory.SALES_TAX,
        due_date=date(2025, 12, 31),
        fiscal_year=2025,
        priority=EventPriority.HIGH,
        recurrence_type="monthly",
    ))

    # =========================================================================
    # JANUARY 2026 - Q4 STARTS
    # =========================================================================

    # January 1 - New Year
    events.append(ComplianceEvent(
        id="new-year-2026",
        title="New Year 2026",
        description="Start of calendar year",
        event_type=EventType.REGISTRATION_RENEWAL,
        category=EventCategory.REGULATORY,
        due_date=date(2026, 1, 1),
        fiscal_year=2025,
        priority=EventPriority.LOW,
        applicable_to=["all"],
        is_recurring=False,
        notes=["Ensure all prior year filings are complete"],
    ))

    # January 15 - Q4 Advance Tax Installment (LAST QUARTER)
    events.append(ComplianceEvent(
        id="q4-adv-tax-2025",
        title="Q4 Advance Tax Installment - Due Date",
        description="Fourth and final quarterly advance tax payment for FY25",
        event_type=EventType.QUARTERLY_ADVANCE_TAX,
        category=EventCategory.INCOME_TAX,
        due_date=date(2026, 1, 15),
        fiscal_year=2025,
        quarter=4,
        priority=EventPriority.CRITICAL,
        applicable_to=["company", "aop"],
        notes=["Complete your annual advance tax estimate"],
    ))

    # January 31 - January Sales Tax Return
    events.append(ComplianceEvent(
        id="st-jan-2026",
        title="Sales Tax Return - January 2026",
        description="Monthly sales tax return for January 2026",
        event_type=EventType.SALES_TAX_RETURN_MONTHLY,
        category=EventCategory.SALES_TAX,
        due_date=date(2026, 1, 31),
        fiscal_year=2025,
        priority=EventPriority.HIGH,
        recurrence_type="monthly",
    ))

    # =========================================================================
    # FEBRUARY 2026
    # =========================================================================

    # February 28 - Q4 WHT Statement (Oct-Dec 2025)
    events.append(ComplianceEvent(
        id="wht-q4-2025",
        title="Quarterly WHT Statement - Q4 FY25",
        description="Quarterly withholding tax statement for October-December 2025",
        event_type=EventType.WHT_STATEMENT,
        category=EventCategory.WITHHOLDING_TAX,
        due_date=date(2026, 2, 28),
        fiscal_year=2025,
        quarter=4,
        priority=EventPriority.HIGH,
        applicable_to=["all_withholders"],
    ))

    # February 28 - February Sales Tax Return
    events.append(ComplianceEvent(
        id="st-feb-2026",
        title="Sales Tax Return - February 2026",
        description="Monthly sales tax return for February 2026",
        event_type=EventType.SALES_TAX_RETURN_MONTHLY,
        category=EventCategory.SALES_TAX,
        due_date=date(2026, 2, 28),
        fiscal_year=2025,
        priority=EventPriority.HIGH,
        recurrence_type="monthly",
    ))

    # =========================================================================
    # MARCH 2026
    # =========================================================================

    # March 23 - Pakistan Day (Holiday)
    events.append(ComplianceEvent(
        id="pakistan-day-2026",
        title="Pakistan Day",
        description="National holiday - FBR offices closed",
        event_type=EventType.REGISTRATION_RENEWAL,
        category=EventCategory.REGULATORY,
        due_date=date(2026, 3, 23),
        fiscal_year=2025,
        priority=EventPriority.LOW,
        applicable_to=["all"],
        is_recurring=False,
    ))

    # March 31 - March Sales Tax Return
    events.append(ComplianceEvent(
        id="st-mar-2026",
        title="Sales Tax Return - March 2026",
        description="Monthly sales tax return for March 2026",
        event_type=EventType.SALES_TAX_RETURN_MONTHLY,
        category=EventCategory.SALES_TAX,
        due_date=date(2026, 3, 31),
        fiscal_year=2025,
        priority=EventPriority.HIGH,
        recurrence_type="monthly",
    ))

    # =========================================================================
    # APRIL 2026 - FY END APPROACHES
    # =========================================================================

    # April 15 - Q1 Advance Tax (New FY starts April)
    events.append(ComplianceEvent(
        id="q1-adv-tax-2026",
        title="Q1 Advance Tax Installment FY26 - Due Date",
        description="First quarterly advance tax payment for FY 2025-26",
        event_type=EventType.QUARTERLY_ADVANCE_TAX,
        category=EventCategory.INCOME_TAX,
        due_date=date(2026, 4, 15),
        fiscal_year=2026,
        quarter=1,
        priority=EventPriority.CRITICAL,
        applicable_to=["company", "aop"],
    ))

    # April 30 - April Sales Tax Return
    events.append(ComplianceEvent(
        id="st-apr-2026",
        title="Sales Tax Return - April 2026",
        description="Monthly sales tax return for April 2026",
        event_type=EventType.SALES_TAX_RETURN_MONTHLY,
        category=EventCategory.SALES_TAX,
        due_date=date(2026, 4, 30),
        fiscal_year=2026,
        priority=EventPriority.HIGH,
        recurrence_type="monthly",
    ))

    # =========================================================================
    # MAY 2026
    # =========================================================================

    # May 15 - Q1 WHT Statement (Apr-Jun for FY26)
    events.append(ComplianceEvent(
        id="wht-q1-2026",
        title="Quarterly WHT Statement - Q1 FY26",
        description="Quarterly withholding tax statement for April-June 2026",
        event_type=EventType.WHT_STATEMENT,
        category=EventCategory.WITHHOLDING_TAX,
        due_date=date(2026, 5, 15),
        fiscal_year=2026,
        quarter=1,
        priority=EventPriority.HIGH,
        applicable_to=["all_withholders"],
    ))

    # May 31 - May Sales Tax Return
    events.append(ComplianceEvent(
        id="st-may-2026",
        title="Sales Tax Return - May 2026",
        description="Monthly sales tax return for May 2026",
        event_type=EventType.SALES_TAX_RETURN_MONTHLY,
        category=EventCategory.SALES_TAX,
        due_date=date(2026, 5, 31),
        fiscal_year=2026,
        priority=EventPriority.HIGH,
        recurrence_type="monthly",
    ))

    # =========================================================================
    # JUNE 2026 - FY ENDS
    # =========================================================================

    # June 15 - Q2 Advance Tax Installment
    events.append(ComplianceEvent(
        id="q2-adv-tax-2026",
        title="Q2 Advance Tax Installment FY26 - Due Date",
        description="Second quarterly advance tax payment for FY 2025-26",
        event_type=EventType.QUARTERLY_ADVANCE_TAX,
        category=EventCategory.INCOME_TAX,
        due_date=date(2026, 6, 15),
        fiscal_year=2026,
        quarter=2,
        priority=EventPriority.CRITICAL,
        applicable_to=["company", "aop"],
    ))

    # June 30 - FISCAL YEAR END
    events.append(ComplianceEvent(
        id="fy-end-2026",
        title="Fiscal Year 2025-26 Ends",
        description="End of fiscal year - finalize all accounts",
        event_type=EventType.ANNUAL_RETURN,
        category=EventCategory.INCOME_TAX,
        due_date=date(2026, 6, 30),
        fiscal_year=2025,
        priority=EventPriority.CRITICAL,
        applicable_to=["all"],
        is_recurring=False,
        notes=["Prepare financial statements", "Tax computation for the year"],
    ))

    # June 30 - June Sales Tax Return
    events.append(ComplianceEvent(
        id="st-jun-2026",
        title="Sales Tax Return - June 2026",
        description="Monthly sales tax return for June 2026",
        event_type=EventType.SALES_TAX_RETURN_MONTHLY,
        category=EventCategory.SALES_TAX,
        due_date=date(2026, 6, 30),
        fiscal_year=2026,
        priority=EventPriority.HIGH,
        recurrence_type="monthly",
    ))

    # June 30 - ANNUAL SALES TAX RETURN (FY 2025-26)
    events.append(ComplianceEvent(
        id="annual-st-2026",
        title="Annual Sales Tax Return - FY 2025-26",
        description="Annual consolidated sales tax return for the fiscal year",
        event_type=EventType.SALES_TAX_RETURN_MONTHLY,
        category=EventCategory.SALES_TAX,
        due_date=date(2026, 6, 30),
        fiscal_year=2025,
        priority=EventPriority.HIGH,
        legal_reference="Sales Tax Act 1990",
        applicable_to=["registered_persons"],
        is_recurring=False,
    ))

    return events


# =============================================================================
# ANNUAL EVENTS - Previous Years (for reference/filing)
# =============================================================================

def _build_events_2024_25() -> list[ComplianceEvent]:
    """Build compliance events for fiscal year 2024-25."""
    events = []

    # September 30, 2024 - TY2023 Income Tax Return
    events.append(ComplianceEvent(
        id="itr-ty2023-2024",
        title="Income Tax Return Filing - Tax Year 2023",
        description="Last date to file income tax return for Tax Year 2023",
        event_type=EventType.ANNUAL_RETURN,
        category=EventCategory.INCOME_TAX,
        due_date=date(2024, 9, 30),
        fiscal_year=2024,
        tax_year=2023,
        priority=EventPriority.CRITICAL,
        applicable_to=["individual", "business", "company", "aop"],
        is_recurring=False,
        notes=["Past deadline - for reference only"],
    ))

    return events


def _build_events_2026_27() -> list[ComplianceEvent]:
    """Build compliance events for fiscal year 2026-27 (upcoming)."""
    events = []

    # September 30, 2026 - TY2025 Income Tax Return
    events.append(ComplianceEvent(
        id="itr-ty2025-2026",
        title="Income Tax Return Filing - Tax Year 2025",
        description="Last date to file income tax return for Tax Year 2025",
        event_type=EventType.ANNUAL_RETURN,
        category=EventCategory.INCOME_TAX,
        due_date=date(2026, 9, 30),
        fiscal_year=2026,
        tax_year=2025,
        priority=EventPriority.CRITICAL,
        applicable_to=["individual", "business", "company", "aop"],
        is_recurring=False,
        notes=["Upcoming deadline - prepare in advance"],
    ))

    return events


# =============================================================================
# DATABASE
# =============================================================================

# All events combined
ALL_EVENTS: list[ComplianceEvent] = (
    _build_events_2024_25() +
    _build_events_2025_26() +
    _build_events_2026_27()
)


def get_all_events() -> list[ComplianceEvent]:
    """Get all compliance events."""
    return ALL_EVENTS


def get_events_by_year(fiscal_year: int) -> list[ComplianceEvent]:
    """Get events for a specific fiscal year."""
    return [e for e in ALL_EVENTS if e.fiscal_year == fiscal_year]


def get_events_by_type(event_type: EventType) -> list[ComplianceEvent]:
    """Get events of a specific type."""
    return [e for e in ALL_EVENTS if e.event_type == event_type]


def get_events_by_category(category: EventCategory) -> list[ComplianceEvent]:
    """Get events of a specific category."""
    return [e for e in ALL_EVENTS if e.category == category]


def get_upcoming_events(days: int = 30) -> list[ComplianceEvent]:
    """Get events due within N days."""
    today = date.today()
    upcoming = []
    for e in ALL_EVENTS:
        if e.is_active and not e.is_overdue(today):
            if e.days_until_due(today) <= days:
                upcoming.append(e)
    return sorted(upcoming, key=lambda x: x.due_date)


def get_overdue_events() -> list[ComplianceEvent]:
    """Get overdue events."""
    today = date.today()
    return [e for e in ALL_EVENTS if e.is_active and e.is_overdue(today)]
