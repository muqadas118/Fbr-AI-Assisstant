"""
FBR Monitor Router
==================

FastAPI router for FBR portal monitoring operations.
Exposes FBRMonitorAPI as HTTP endpoints.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.fbr_monitor import FBRMonitorAPI, get_fbr_monitor_api

logger = logging.getLogger("fbr_api.monitor")

router = APIRouter(prefix="/monitor", tags=["FBR Monitor"])


# =============================================================================
# Request Models
# =============================================================================

class MonitorSubscribeRequest(BaseModel):
    """Subscribe to FBR monitoring."""
    user_id: str = Field(..., description="User ID")
    ntn: str = Field(..., description="NTN to monitor")
    check_interval_minutes: int = Field(
        default=60,
        ge=15,
        le=1440,
        description="Check interval in minutes"
    )
    notification_email: Optional[str] = Field(
        default=None,
        description="Email for notifications"
    )
    notification_webhook: Optional[str] = Field(
        default=None,
        description="Webhook URL for notifications"
    )


class WebhookRegisterRequest(BaseModel):
    """Register a webhook endpoint."""
    user_id: str
    name: str
    url: str
    secret: Optional[str] = None
    event_types: Optional[list[str]] = None


class SimulateNoticeRequest(BaseModel):
    """Simulate a new FBR notice (for testing)."""
    ntn: str
    notice_number: str
    title: str
    description: str
    action_deadline: Optional[str] = None


# =============================================================================
# Response Models
# =============================================================================

class EventResponse(BaseModel):
    """Monitoring event."""
    id: str
    type: str
    severity: str
    title: str
    description: str
    status: str
    requires_action: bool
    detected_at: str
    reference_number: Optional[str] = None
    action_deadline: Optional[str] = None


class MonitorDashboardResponse(BaseModel):
    """Monitoring dashboard."""
    user_id: str
    total_events: int
    unread_count: int
    critical_count: int
    action_required: int
    recent_events: list[EventResponse]
    critical_events: list[dict]
    statistics: dict


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/subscribe")
async def subscribe_to_monitoring(request: MonitorSubscribeRequest) -> dict:
    """
    Subscribe to FBR portal monitoring.

    Monitors the IRIS portal for new notices, correspondence,
    SROs, and compliance events for the specified NTN.
    """
    try:
        api = get_fbr_monitor_api()
        result = api.subscribe_user(
            user_id=request.user_id,
            ntn=request.ntn,
            check_interval_minutes=request.check_interval_minutes,
            notification_email=request.notification_email,
            notification_webhook=request.notification_webhook,
        )
        return {
            "user_id": result.user_id,
            "ntn": result.ntn,
            "is_active": result.is_active,
            "event_types": result.event_types,
            "check_interval_minutes": result.check_interval_minutes,
            "subscribed_at": result.subscribed_at,
        }
    except Exception as e:
        logger.exception("Error subscribing to monitoring")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to subscribe to monitoring"
        )


@router.delete("/unsubscribe/{user_id}")
async def unsubscribe_from_monitoring(user_id: str) -> dict:
    """
    Unsubscribe from FBR monitoring.
    """
    try:
        api = get_fbr_monitor_api()
        success = api.unsubscribe_user(user_id)
        return {"user_id": user_id, "unsubscribed": success}
    except Exception as e:
        logger.exception("Error unsubscribing")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unsubscribe"
        )


@router.get("/dashboard/{user_id}", response_model=MonitorDashboardResponse)
async def get_monitoring_dashboard(user_id: str) -> MonitorDashboardResponse:
    """
    Get FBR monitoring dashboard for a user.

    Returns recent events, critical alerts, and action-required items.
    """
    try:
        api = get_fbr_monitor_api()
        result = api.get_user_dashboard(user_id)

        return MonitorDashboardResponse(
            user_id=result["user_id"],
            total_events=result["total_events"],
            unread_count=result["unread_count"],
            critical_count=result["critical_count"],
            action_required=result["action_required"],
            recent_events=[EventResponse(**e) for e in result["recent_events"]],
            critical_events=result["critical_events"],
            statistics=result["statistics"],
        )
    except Exception as e:
        logger.exception("Error getting monitoring dashboard")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve monitoring dashboard"
        )


@router.get("/event/{event_id}")
async def get_event_details(event_id: str) -> dict:
    """
    Get details of a specific monitoring event.
    """
    try:
        api = get_fbr_monitor_api()
        result = api.get_event_details(event_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found"
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting event details")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve event details"
        )


@router.post("/event/{event_id}/acknowledge")
async def acknowledge_event(event_id: str) -> dict:
    """
    Acknowledge a monitoring event.
    """
    try:
        api = get_fbr_monitor_api()
        result = api.acknowledge_event(event_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found"
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error acknowledging event")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to acknowledge event"
        )


@router.post("/event/{event_id}/resolve")
async def resolve_event(event_id: str) -> dict:
    """
    Mark a monitoring event as resolved.
    """
    try:
        api = get_fbr_monitor_api()
        result = api.resolve_event(event_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found"
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error resolving event")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resolve event"
        )


@router.post("/webhook")
async def register_webhook(request: WebhookRegisterRequest) -> dict:
    """
    Register a webhook for FBR event notifications.

    Receives POST requests when new FBR events are detected.
    """
    try:
        api = get_fbr_monitor_api()
        return api.register_webhook(
            user_id=request.user_id,
            name=request.name,
            url=request.url,
            secret=request.secret,
            event_types=request.event_types,
        )
    except Exception as e:
        logger.exception("Error registering webhook")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register webhook"
        )


@router.get("/webhook/stats")
async def get_webhook_stats() -> dict:
    """
    Get webhook delivery statistics.
    """
    try:
        api = get_fbr_monitor_api()
        return api.get_webhook_stats()
    except Exception as e:
        logger.exception("Error getting webhook stats")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve webhook stats"
        )


@router.post("/simulate/notice")
async def simulate_notice(request: SimulateNoticeRequest) -> dict:
    """
    Simulate a new FBR notice event (for testing purposes).

    Creates a test notice event to demonstrate monitoring workflow.
    """
    try:
        api = get_fbr_monitor_api()
        result = api.simulate_new_notice(
            ntn=request.ntn,
            notice_number=request.notice_number,
            title=request.title,
            description=request.description,
            action_deadline=request.action_deadline,
        )
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to simulate notice"
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error simulating notice")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to simulate notice"
        )


@router.get("/event-types")
async def get_event_types() -> dict:
    """
    List all FBR monitoring event types.
    """
    try:
        from app.fbr_monitor.monitor_engine import EventType, EventSeverity
        return {
            "event_types": [et.value for et in EventType],
            "severities": [es.value for es in EventSeverity],
        }
    except Exception as e:
        logger.exception("Error listing event types")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve event types"
        )
