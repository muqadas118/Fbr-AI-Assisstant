"""
FBR Monitor API
===============

High-level API for FBR monitoring operations.

Backed by the in-memory monitor engine and webhook manager, so state does not
survive a restart. Webhook delivery is real HTTP unless
FBR_MONITOR_SIMULATE_DELIVERY=1 is set.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from app.fbr_monitor.monitor_engine import (
    FBRMonitorConfig,
    EventType, EventSeverity, EventStatus,
    get_fbr_monitor,
)
from app.fbr_monitor.webhook import (
    get_webhook_manager,
)

logger = logging.getLogger("fbr_monitor")


@dataclass
class MonitorSubscription:
    """Subscription info."""
    sub_id: str
    user_id: str
    ntn: str
    is_active: bool
    event_types: list[str]
    check_interval_minutes: int
    subscribed_at: str
    last_check_at: Optional[str] = None
    events_received: int = 0


@dataclass
class MonitorAlert:
    """Alert for a monitoring event."""
    alert_id: str
    user_id: str
    event_type: str
    severity: str
    title: str
    description: str
    requires_action: bool
    action_deadline: Optional[str] = None
    reference_number: Optional[str] = None
    url: Optional[str] = None
    created_at: str = ""


class FBRMonitorAPI:
    """API for FBR monitoring."""

    def __init__(self):
        self.monitor = get_fbr_monitor()
        self.webhook_manager = get_webhook_manager()

    def subscribe_user(
        self,
        user_id: str,
        ntn: str,
        check_interval_minutes: int = 60,
        notification_email: Optional[str] = None,
        notification_webhook: Optional[str] = None,
    ) -> MonitorSubscription:
        """Subscribe a user to FBR monitoring."""
        config = FBRMonitorConfig(
            ntn=ntn,
            user_id=user_id,
            check_interval_minutes=check_interval_minutes,
            notification_email=notification_email,
            notification_webhook=notification_webhook,
        )
        sub_id = self.monitor.subscribe(config)

        return MonitorSubscription(
            sub_id=sub_id,
            user_id=user_id,
            ntn=ntn,
            is_active=True,
            event_types=[e.value for e in EventType],
            check_interval_minutes=check_interval_minutes,
            subscribed_at=config.subscribed_at,
        )

    def get_subscriptions(self, user_id: str) -> list[MonitorSubscription]:
        """List a user's subscriptions (a user can hold several)."""
        return [
            MonitorSubscription(
                sub_id=config.sub_id,
                user_id=config.user_id,
                ntn=config.ntn,
                is_active=True,
                event_types=[e.value for e in EventType],
                check_interval_minutes=config.check_interval_minutes,
                subscribed_at=config.subscribed_at,
            )
            for config in self.monitor.get_subscriptions(user_id)
        ]

    def unsubscribe_user(self, user_id: str) -> bool:
        """Unsubscribe user."""
        return self.monitor.unsubscribe(user_id)

    def get_user_dashboard(self, user_id: str) -> dict:
        """Get user dashboard."""
        events = self.monitor.get_events(user_id=user_id, limit=100)
        critical = self.monitor.get_critical(user_id)
        stats = self.monitor.get_statistics(user_id=user_id)

        return {
            "user_id": user_id,
            "total_events": stats["total_events"],
            "unread_count": stats["unread_count"],
            "critical_count": stats["critical_count"],
            "action_required": stats["action_required_count"],
            "recent_events": [
                {
                    "id": e.id,
                    "type": e.event_type.value,
                    "severity": e.severity.value,
                    "title": e.title,
                    "description": e.description,
                    "status": e.status.value,
                    "requires_action": e.requires_action,
                    "detected_at": e.detected_at,
                }
                for e in events[:10]
            ],
            "critical_events": [
                {
                    "id": e.id,
                    "title": e.title,
                    "description": e.description,
                    "action_deadline": e.action_deadline,
                }
                for e in critical
            ],
            "statistics": stats,
        }

    def get_event_details(self, event_id: str) -> Optional[dict]:
        """Get details of a specific event."""
        for event in self.monitor.events:
            if event.id == event_id:
                return {
                    "id": event.id,
                    "user_id": event.user_id,
                    "ntn": event.ntn,
                    "event_type": event.event_type.value,
                    "severity": event.severity.value,
                    "title": event.title,
                    "description": event.description,
                    "reference_number": event.reference_number,
                    "url": event.url,
                    "detected_at": event.detected_at,
                    "status": event.status.value,
                    "requires_action": event.requires_action,
                    "action_deadline": event.action_deadline,
                    "metadata": event.metadata,
                }
        return None

    def acknowledge_event(self, event_id: str) -> Optional[dict]:
        """Mark event as acknowledged."""
        event = self.monitor.update_event_status(
            event_id,
            EventStatus.ACKNOWLEDGED,
        )
        if event:
            return {"event_id": event.id, "status": event.status.value}
        return None

    def resolve_event(self, event_id: str) -> Optional[dict]:
        """Mark event as resolved."""
        event = self.monitor.update_event_status(event_id, EventStatus.RESOLVED)
        if event:
            return {"event_id": event.id, "status": event.status.value}
        return None

    def simulate_new_notice(
        self,
        ntn: str,
        notice_number: str,
        title: str,
        description: str,
        action_deadline: Optional[str] = None,
    ) -> Optional[dict]:
        """Simulate a new FBR notice event (for testing).

        The event is tagged {'source': 'simulated'} so a test notice is never
        mistaken for one the IRIS portal actually produced.
        """
        event = self.monitor.detect_event(
            ntn=ntn,
            event_type=EventType.NEW_NOTICE,
            title=title,
            description=description,
            severity=EventSeverity.HIGH,
            reference_number=notice_number,
            requires_action=bool(action_deadline),
            action_deadline=action_deadline,
            metadata={"source": "simulated", "notice_number": notice_number},
        )
        if event:
            return self.get_event_details(event.id)
        return None

    def register_webhook(
        self,
        user_id: str,
        name: str,
        url: str,
        secret: Optional[str] = None,
        event_types: Optional[list[str]] = None,
    ) -> dict:
        """Register a webhook endpoint."""
        endpoint = self.webhook_manager.register(
            user_id=user_id,
            name=name,
            url=url,
            secret=secret,
            event_types=event_types,
        )
        return {
            "id": endpoint.id,
            "name": endpoint.name,
            "url": endpoint.url,
            "is_active": endpoint.is_active,
            "event_types": endpoint.event_types,
        }

    def list_webhooks(self, user_id: str) -> list[dict]:
        """List the webhook endpoints a user owns (never their secrets)."""
        return [
            {
                "id": endpoint.id,
                "name": endpoint.name,
                "url": endpoint.url,
                "is_active": endpoint.is_active,
                "event_types": endpoint.event_types,
                "created_at": endpoint.created_at,
                "has_secret": bool(endpoint.secret),
            }
            for endpoint in self.webhook_manager.list_endpoints(user_id)
        ]

    def unregister_webhook(self, endpoint_id: str, user_id: str) -> bool:
        """Unregister a webhook endpoint, but only one the user owns."""
        endpoint = self.webhook_manager.endpoints.get(endpoint_id)
        if endpoint is None or endpoint.user_id != user_id:
            return False
        return self.webhook_manager.unregister(endpoint_id)

    def get_webhook_stats(self) -> dict:
        """Get webhook delivery statistics."""
        return self.webhook_manager.get_statistics()


# Singleton
_api: Optional[FBRMonitorAPI] = None


def get_fbr_monitor_api() -> FBRMonitorAPI:
    """Get singleton FBR monitor API."""
    global _api
    if _api is None:
        _api = FBRMonitorAPI()
    return _api
