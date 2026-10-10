"""
FBR Monitor Router
==================

FastAPI router for FBR portal monitoring operations.
Exposes FBRMonitorAPI as HTTP endpoints.
"""

import logging
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from app.supabase_auth import require_user
from pydantic import BaseModel, Field

from app.fbr_monitor import FBRMonitorAPI, get_fbr_monitor_api
from app.fbr_monitor.webhook import env_flag_enabled, is_safe_webhook_target

logger = logging.getLogger("fbr_api.monitor")

router = APIRouter(prefix="/monitor", tags=["FBR Monitor"])


# =============================================================================
# Helpers
# =============================================================================

def _authenticated_user_id(user: Optional[dict] = Depends(require_user)) -> str:
    """Resolve the authenticated user id that scopes monitor data.

    With Supabase auth the JWT 'sub' claim scopes subscriptions, events and
    webhooks. When auth is disabled for local development
    (FBR_AUTH_REQUIRED=false, require_user returns None) everything lands in
    one shared 'dev-user' scope so the pages still render end-to-end before
    Supabase keys are configured.
    """
    if isinstance(user, dict):
        for key in ("id", "user_id", "sub"):
            if user.get(key):
                return str(user[key])
    return "dev-user"


def _authorized_user_id(requested: Optional[str], current_user_id: str) -> str:
    """Return the authenticated user id, rejecting a foreign one.

    Monitor resources are per-user, so a path or body naming another account
    is a cross-user access attempt rather than a value to silently override.
    """
    if requested and requested != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot act on another user's monitor data",
        )
    return current_user_id


def _validate_webhook_url(url: str) -> str:
    """Validate a webhook target before it is stored and called.

    Event payloads are POSTed to this URL, so an arbitrary scheme or host is
    an SSRF vector (cloud metadata, internal services, file://). Only https
    is accepted; plain http is limited to a loopback host and only when
    FBR_MONITOR_ALLOW_INSECURE_WEBHOOK=1 is set for local testing.
    """
    try:
        scheme = urlparse(url).scheme.lower()
    except ValueError:
        scheme = ""

    if scheme not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook URL must use https://",
        )

    if not is_safe_webhook_target(url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Insecure webhook URL: https is required, and loopback http "
                "needs FBR_MONITOR_ALLOW_INSECURE_WEBHOOK=1"
            ),
        )

    return url


def _require_event_owner(api: FBRMonitorAPI, event_id: str, current_user_id: str) -> dict:
    """Fetch an event that must belong to the authenticated user.

    Ownership is checked before any status change, so one user cannot
    acknowledge or resolve another user's events by guessing an id.
    """
    event = api.get_event_details(event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    if event["user_id"] != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify another user's monitoring event"
        )
    return event


def _require_simulate_enabled() -> None:
    """Gate the simulated-notice route behind FBR_MONITOR_ALLOW_SIMULATE=1.

    Simulated events share the store with real ones, so the endpoint stays
    off unless a developer opts in per environment.
    """
    if not env_flag_enabled("FBR_MONITOR_ALLOW_SIMULATE"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Event simulation is disabled. "
                "Set FBR_MONITOR_ALLOW_SIMULATE=1 to enable it."
            ),
        )


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

@router.post("/subscribe", dependencies=[Depends(require_user)])
async def subscribe_to_monitoring(
    request: MonitorSubscribeRequest,
    current_user_id: str = Depends(_authenticated_user_id),
) -> dict:
    """
    Subscribe to FBR portal monitoring.

    Monitors the IRIS portal for new notices, correspondence,
    SROs, and compliance events for the specified NTN.

    The subscription is always owned by the authenticated caller; a body
    naming a different user is rejected.
    """
    user_id = _authorized_user_id(request.user_id, current_user_id)

    try:
        api = get_fbr_monitor_api()
        result = api.subscribe_user(
            user_id=user_id,
            ntn=request.ntn,
            check_interval_minutes=request.check_interval_minutes,
            notification_email=request.notification_email,
            notification_webhook=request.notification_webhook,
        )
        return {
            "sub_id": result.sub_id,
            "user_id": result.user_id,
            "ntn": result.ntn,
            "is_active": result.is_active,
            "event_types": result.event_types,
            "check_interval_minutes": result.check_interval_minutes,
            "subscribed_at": result.subscribed_at,
        }
    except Exception:
        logger.exception("Error subscribing to monitoring")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to subscribe to monitoring"
        )


@router.delete("/unsubscribe/{user_id}", dependencies=[Depends(require_user)])
async def unsubscribe_from_monitoring(
    user_id: str,
    current_user_id: str = Depends(_authenticated_user_id),
) -> dict:
    """
    Unsubscribe from FBR monitoring.
    """
    user_id = _authorized_user_id(user_id, current_user_id)

    try:
        api = get_fbr_monitor_api()
        success = api.unsubscribe_user(user_id)
        return {"user_id": user_id, "unsubscribed": success}
    except Exception:
        logger.exception("Error unsubscribing")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unsubscribe"
        )


@router.get("/dashboard/{user_id}", response_model=MonitorDashboardResponse, dependencies=[Depends(require_user)])
async def get_monitoring_dashboard(
    user_id: str,
    current_user_id: str = Depends(_authenticated_user_id),
) -> MonitorDashboardResponse:
    """
    Get FBR monitoring dashboard for a user.

    Returns recent events, critical alerts, and action-required items.
    """
    user_id = _authorized_user_id(user_id, current_user_id)

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
    except Exception:
        logger.exception("Error getting monitoring dashboard")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve monitoring dashboard"
        )


@router.get("/event/{event_id}", dependencies=[Depends(require_user)])
async def get_event_details(
    event_id: str,
    current_user_id: str = Depends(_authenticated_user_id),
) -> dict:
    """
    Get details of a specific monitoring event owned by the caller.
    """
    try:
        api = get_fbr_monitor_api()
        result = api.get_event_details(event_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found"
            )
        if result["user_id"] != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot read another user's monitoring event"
            )
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting event details")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve event details"
        )


@router.post("/event/{event_id}/acknowledge", dependencies=[Depends(require_user)])
async def acknowledge_event(
    event_id: str,
    current_user_id: str = Depends(_authenticated_user_id),
) -> dict:
    """
    Acknowledge a monitoring event.
    """
    try:
        api = get_fbr_monitor_api()
        _require_event_owner(api, event_id, current_user_id)
        result = api.acknowledge_event(event_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found"
            )
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error acknowledging event")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to acknowledge event"
        )


@router.post("/event/{event_id}/resolve", dependencies=[Depends(require_user)])
async def resolve_event(
    event_id: str,
    current_user_id: str = Depends(_authenticated_user_id),
) -> dict:
    """
    Mark a monitoring event as resolved.
    """
    try:
        api = get_fbr_monitor_api()
        _require_event_owner(api, event_id, current_user_id)
        result = api.resolve_event(event_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found"
            )
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error resolving event")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resolve event"
        )


@router.post("/webhook", dependencies=[Depends(require_user)])
async def register_webhook(
    request: WebhookRegisterRequest,
    current_user_id: str = Depends(_authenticated_user_id),
) -> dict:
    """
    Register a webhook for FBR event notifications.

    Receives POST requests when new FBR events are detected, signed with
    X-FBR-Signature when a secret is set.

    Owning caller only: the endpoint belongs to the authenticated user, and
    the URL must be https so payloads are not POSTed to arbitrary hosts.
    """
    # Validated before anything is stored or called; a bad target is a client
    # error, not a server failure.
    _validate_webhook_url(request.url)
    user_id = _authorized_user_id(request.user_id, current_user_id)

    try:
        api = get_fbr_monitor_api()
        return api.register_webhook(
            user_id=user_id,
            name=request.name,
            url=request.url,
            secret=request.secret,
            event_types=request.event_types,
        )
    except Exception:
        logger.exception("Error registering webhook")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register webhook"
        )


@router.get("/webhooks", dependencies=[Depends(require_user)])
async def list_webhooks(
    current_user_id: str = Depends(_authenticated_user_id),
) -> list[dict]:
    """
    List the webhook endpoints registered by the authenticated user.
    """
    try:
        api = get_fbr_monitor_api()
        return api.list_webhooks(current_user_id)
    except Exception:
        logger.exception("Error listing webhooks")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve webhooks"
        )


@router.delete("/webhooks/{endpoint_id}", dependencies=[Depends(require_user)])
async def delete_webhook(
    endpoint_id: str,
    current_user_id: str = Depends(_authenticated_user_id),
) -> dict:
    """
    Delete one of the authenticated user's webhook endpoints.
    """
    try:
        api = get_fbr_monitor_api()
        deleted = api.unregister_webhook(endpoint_id, current_user_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Webhook endpoint not found"
            )
        return {"endpoint_id": endpoint_id, "deleted": True}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error deleting webhook")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete webhook"
        )


@router.get("/webhook/stats", dependencies=[Depends(require_user)])
async def get_webhook_stats() -> dict:
    """
    Get webhook delivery statistics.
    """
    try:
        api = get_fbr_monitor_api()
        return api.get_webhook_stats()
    except Exception:
        logger.exception("Error getting webhook stats")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve webhook stats"
        )


@router.post("/simulate/notice", dependencies=[Depends(require_user)])
async def simulate_notice(request: SimulateNoticeRequest) -> dict:
    """
    Simulate a new FBR notice event (for testing purposes).

    Creates a test notice event to demonstrate monitoring workflow. Disabled
    unless FBR_MONITOR_ALLOW_SIMULATE=1, and the event is tagged
    {'source': 'simulated'} so it is never mistaken for an IRIS notice.
    """
    _require_simulate_enabled()

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
    except Exception:
        logger.exception("Error simulating notice")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to simulate notice"
        )


# PUBLIC - intentionally no auth: static metadata for UI
@router.get("/event-types")
async def get_event_types() -> dict:
    """
    List all FBR monitoring event types.
    """
    from app.fbr_monitor.monitor_engine import EventType, EventSeverity
    return {
        "event_types": [et.value for et in EventType],
        "severities": [es.value for es in EventSeverity],
    }
