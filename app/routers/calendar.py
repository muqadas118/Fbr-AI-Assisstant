"""
Compliance Calendar Router
=========================

FastAPI router for compliance calendar operations.
Exposes ComplianceCalendarAPI as HTTP endpoints.
"""

import logging
from datetime import date, datetime
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.supabase_auth import require_user
from pydantic import BaseModel, Field

from app.compliance_calendar import (
    ComplianceCalendarAPI, get_compliance_calendar,
    EventType, EventCategory, EventPriority,
)

logger = logging.getLogger("fbr_api.calendar")

router = APIRouter(prefix="/calendar", tags=["Compliance Calendar"])


# =============================================================================
# Enums
# =============================================================================

class TaxpayerType(str, Enum):
    INDIVIDUAL = "individual"
    BUSINESS = "business"
    COMPANY = "company"
    AOP = "aop"


class CalendarFormat(str, Enum):
    JSON = "json"
    CSV = "csv"


# =============================================================================
# Request Models
# =============================================================================

class CalendarQueryRequest(BaseModel):
    """Query parameters for calendar."""
    taxpayer_type: TaxpayerType = Field(
        default=TaxpayerType.INDIVIDUAL,
        description="Type of taxpayer"
    )
    fiscal_year: Optional[int] = Field(
        default=None,
        description="Fiscal year (e.g. 2025, 2026)"
    )
    tax_year: Optional[int] = Field(
        default=None,
        description="Tax year (e.g. 2024, 2025)"
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Start date (YYYY-MM-DD)"
    )
    end_date: Optional[str] = Field(
        default=None,
        description="End date (YYYY-MM-DD)"
    )
    event_types: Optional[list[str]] = Field(
        default=None,
        description="Filter by event types"
    )
    categories: Optional[list[str]] = Field(
        default=None,
        description="Filter by event categories"
    )
    min_priority: Optional[str] = Field(
        default=None,
        description="Minimum priority (low, medium, high, critical)"
    )
    include_holidays: bool = Field(
        default=True,
        description="Include holidays in results"
    )
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=500,
        description="Maximum number of events to return"
    )


class ReminderRequest(BaseModel):
    """Request to schedule a reminder."""
    event_id: str = Field(..., description="Event ID to schedule reminder for")
    recipient: str = Field(
        default="user@example.com",
        description="Email address for reminder"
    )
    channels: Optional[list[str]] = Field(
        default=None,
        description="Notification channels (email, sms, push, whatsapp)"
    )


# =============================================================================
# Response Models
# =============================================================================

class EventResponse(BaseModel):
    """Single compliance event."""
    id: str
    title: str
    description: Optional[str] = None
    due_date: str
    fiscal_year: int
    tax_year: Optional[int] = None
    quarter: Optional[str] = None
    priority: str
    category: str
    event_type: str
    legal_reference: Optional[str] = None
    penalty: Optional[str] = None
    days_remaining: int
    is_overdue: bool
    is_completed: bool
    extension_available: bool
    extension_date: Optional[str] = None


class UpcomingTaskResponse(BaseModel):
    """Upcoming task."""
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


class CalendarResponse(BaseModel):
    """Full calendar response."""
    query: dict
    total_events: int
    events: list[EventResponse]
    summary: dict
    upcoming_tasks: list[UpcomingTaskResponse]
    overdue_events: list[EventResponse]
    compliance_score: float
    compliance_grade: str
    recommendations: list[str]
    generated_at: str


class DashboardSummaryResponse(BaseModel):
    """Dashboard summary."""
    taxpayer_type: str
    compliance_score: float
    compliance_grade: str
    total_events: int
    overdue_count: int
    critical_upcoming_30d: int
    critical_upcoming_7d: int
    next_7_days_tasks: list[dict]
    compliance_grade_color: str
    summary_message: str


class ReminderResponse(BaseModel):
    """Reminder scheduling response."""
    event_id: str
    reminders_scheduled: int
    reminder_ids: list[str]


# =============================================================================
# Internal helpers
# =============================================================================

def _build_query(request: CalendarQueryRequest) -> dict:
    """Build calendar query dict from request."""
    from app.compliance_calendar.events import ComplianceEvent, get_all_events
    from app.compliance_calendar.calendar_engine import CalendarConfig

    q = CalendarQueryRequest(
        taxpayer_type=request.taxpayer_type,
        fiscal_year=request.fiscal_year or date.today().year,
        tax_year=request.tax_year,
        start_date=request.start_date,
        end_date=request.end_date,
        event_types=request.event_types,
        categories=request.categories,
        min_priority=request.min_priority,
        include_holidays=request.include_holidays,
        limit=request.limit,
    )

    from app.compliance_calendar.calendar_api import CalendarQuery
    from datetime import datetime

    return CalendarQuery(
        taxpayer_type=q.taxpayer_type.value,
        fiscal_year=q.fiscal_year or 2025,
        tax_year=q.tax_year,
        start_date=datetime.fromisoformat(q.start_date).date() if q.start_date else None,
        end_date=datetime.fromisoformat(q.end_date).date() if q.end_date else None,
        event_types=[EventType(et) for et in q.event_types] if q.event_types else [],
        categories=[EventCategory(cat) for cat in q.categories] if q.categories else [],
        min_priority=EventPriority(q.min_priority) if q.min_priority else EventPriority.LOW,
        include_holidays=q.include_holidays,
        limit=q.limit,
    )


# =============================================================================
# Endpoints
# =============================================================================

@router.get("", response_model=CalendarResponse, dependencies=[Depends(require_user)])
async def get_calendar(
    taxpayer_type: TaxpayerType = Query(default=TaxpayerType.INDIVIDUAL),
    fiscal_year: Optional[int] = Query(default=None, ge=2020, le=2030),
    tax_year: Optional[int] = Query(default=None, ge=2020, le=2030),
    start_date: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    event_type: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    include_holidays: bool = Query(default=True),
    limit: Optional[int] = Query(default=None, ge=1, le=500),
) -> CalendarResponse:
    """
    Get compliance calendar with events, compliance score, and recommendations.

    Returns all applicable FBR compliance deadlines for the taxpayer type,
    organized by priority, category, and urgency.
    """
    try:
        api = get_compliance_calendar()

        # Build query
        from datetime import datetime
        query_kwargs = {
            "taxpayer_type": taxpayer_type.value,
            "fiscal_year": fiscal_year or date.today().year,
            "include_holidays": include_holidays,
        }
        if tax_year:
            query_kwargs["tax_year"] = tax_year
        if start_date:
            query_kwargs["start_date"] = datetime.fromisoformat(start_date).date()
        if end_date:
            query_kwargs["end_date"] = datetime.fromisoformat(end_date).date()
        if event_type:
            query_kwargs["event_types"] = [EventType(event_type)]
        if category:
            query_kwargs["categories"] = [EventCategory(category)]
        if priority:
            query_kwargs["min_priority"] = EventPriority(priority)
        if limit:
            query_kwargs["limit"] = limit

        from app.compliance_calendar.calendar_api import CalendarQuery
        query = CalendarQuery(**{k: v for k, v in query_kwargs.items() if v is not None})

        response = api.get_calendar(query)

        return CalendarResponse(
            query=response.query,
            total_events=response.total_events,
            events=[EventResponse(**e) for e in response.events],
            summary=response.summary,
            upcoming_tasks=[UpcomingTaskResponse(**asdict(t)) for t in response.upcoming_tasks],
            overdue_events=[EventResponse(**e) for e in response.overdue_events],
            compliance_score=response.compliance_score,
            compliance_grade=response.compliance_grade,
            recommendations=response.recommendations,
            generated_at=response.generated_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Error getting calendar")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve compliance calendar"
        )


@router.get("/upcoming", response_model=list[UpcomingTaskResponse], dependencies=[Depends(require_user)])
async def get_upcoming_tasks(
    taxpayer_type: TaxpayerType = Query(default=TaxpayerType.INDIVIDUAL),
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look ahead"),
) -> list[UpcomingTaskResponse]:
    """
    Get upcoming compliance tasks sorted by urgency.

    Returns tasks due within the specified number of days, sorted by
    days remaining (most urgent first).
    """
    try:
        api = get_compliance_calendar()
        tasks = api.get_upcoming_tasks(taxpayer_type.value, days)
        return [UpcomingTaskResponse(**asdict(t)) for t in tasks]
    except Exception as e:
        logger.exception("Error getting upcoming tasks")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve upcoming tasks"
        )


@router.post("/events/{event_id}/complete", response_model=dict, dependencies=[Depends(require_user)])
async def mark_event_complete(event_id: str) -> dict:
    """
    Mark a compliance event as completed.

    Indicates that the user has filed/submitted the required document.
    """
    try:
        api = get_compliance_calendar()
        success = api.mark_event_completed(event_id)
        return {"event_id": event_id, "completed": success}
    except Exception as e:
        logger.exception("Error marking event complete")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark event as complete"
        )


@router.post("/reminders", response_model=ReminderResponse, dependencies=[Depends(require_user)])
async def schedule_reminder(request: ReminderRequest) -> ReminderResponse:
    """
    Schedule reminder notifications for a compliance event.

    Supports email, SMS, push, and WhatsApp notification channels.
    """
    try:
        api = get_compliance_calendar()

        from app.compliance_calendar.notifications import NotificationChannel
        channels = [
            NotificationChannel(ch)
            for ch in (request.channels or ["email", "push"])
        ]

        result = api.schedule_reminders(
            event_id=request.event_id,
            recipient=request.recipient,
            channels=channels,
        )

        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result["error"]
            )

        return ReminderResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error scheduling reminder")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to schedule reminder"
        )


@router.get("/export", dependencies=[Depends(require_user)])
async def export_calendar(
    taxpayer_type: TaxpayerType = Query(default=TaxpayerType.INDIVIDUAL),
    fiscal_year: Optional[int] = Query(default=None),
    format: CalendarFormat = Query(default=CalendarFormat.JSON),
) -> dict | str:
    """
    Export compliance calendar as JSON or CSV.

    Returns calendar events formatted as requested.
    """
    try:
        api = get_compliance_calendar()

        from app.compliance_calendar.calendar_api import CalendarQuery
        query = CalendarQuery(
            taxpayer_type=taxpayer_type.value,
            fiscal_year=fiscal_year or date.today().year,
        )

        return api.export_calendar(query, format.value)
    except Exception as e:
        logger.exception("Error exporting calendar")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export calendar"
        )


@router.get("/dashboard", response_model=DashboardSummaryResponse, dependencies=[Depends(require_user)])
async def get_dashboard(
    taxpayer_type: TaxpayerType = Query(default=TaxpayerType.INDIVIDUAL),
) -> DashboardSummaryResponse:
    """
    Get compliance dashboard summary.

    Returns high-level compliance status including score, grade,
    overdue count, and critical upcoming items.
    """
    try:
        api = get_compliance_calendar()
        summary = api.get_dashboard_summary(taxpayer_type.value)
        return DashboardSummaryResponse(**summary)
    except Exception as e:
        logger.exception("Error getting dashboard")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve dashboard"
        )


# PUBLIC - intentionally no auth: static metadata for UI
@router.get("/types")
async def get_event_types() -> dict:
    """List all event types and categories."""
    return {
        "event_types": [et.value for et in EventType],
        "categories": [cat.value for cat in EventCategory],
        "priorities": [pri.value for pri in EventPriority],
    }


# Helper for dataclass serialization
def asdict(obj):
    """Recursively convert dataclass to dict."""
    import dataclasses
    if dataclasses.is_dataclass(obj):
        result = {}
        for k, v in vars(obj).items():
            result[k] = asdict(v)
        return result
    elif isinstance(obj, list):
        return [asdict(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: asdict(v) for k, v in obj.items()}
    else:
        return obj
