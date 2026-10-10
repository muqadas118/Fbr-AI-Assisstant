"""
FBR Monitor Engine
==================

In-memory FBR monitoring state.

Everything here lives in this process: subscriptions, events and the audit
log are bounded in-memory collections, so they are lost on restart. Nothing
polls the IRIS portal - events only enter through detect_event(), which the
env-gated simulate route and any future background worker call.
"""

import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger("fbr_monitor")

# In-memory collections are process-local, so they are capped to keep a busy
# monitor from growing them without bound.
STATE_MAXLEN = 1000


class EventType(str, Enum):
    """Types of FBR events to monitor."""
    NEW_NOTICE = "new_notice"
    NEW_ORDER = "new_order"
    NEW_INTIMATION = "new_intimation"
    RETURN_ACKNOWLEDGED = "return_acknowledged"
    PAYMENT_RECEIVED = "payment_received"
    REFUND_ISSUED = "refund_issued"
    AUDIT_NOTICE = "audit_notice"
    TAX_RATE_CHANGE = "tax_rate_change"
    NEW_SRO = "new_sro"
    NEW_CIRCULAR = "new_circular"
    DEADLINE_REMINDER = "deadline_reminder"
    COMPLIANCE_ALERT = "compliance_alert"


class EventSeverity(str, Enum):
    """Severity of FBR event."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class EventStatus(str, Enum):
    """Event status."""
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


@dataclass
class FBRMonitorConfig:
    """Configuration for FBR monitoring."""
    ntn: str
    user_id: str
    sub_id: str = ""
    subscribed_at: str = ""
    monitor_notices: bool = True
    monitor_payments: bool = True
    monitor_returns: bool = True
    monitor_policy_changes: bool = True
    check_interval_minutes: int = 60
    notification_email: Optional[str] = None
    notification_webhook: Optional[str] = None
    notify_on: list[EventSeverity] = field(default_factory=lambda: [
        EventSeverity.CRITICAL, EventSeverity.HIGH, EventSeverity.MEDIUM
    ])


@dataclass
class FBRMonitorEvent:
    """An FBR event detected by the monitor."""
    id: str
    user_id: str
    ntn: str
    event_type: EventType
    severity: EventSeverity
    title: str
    description: str
    reference_number: Optional[str] = None
    url: Optional[str] = None
    detected_at: str = ""
    status: EventStatus = EventStatus.NEW
    requires_action: bool = False
    action_deadline: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.detected_at:
            self.detected_at = datetime.now(timezone.utc).isoformat()
        if isinstance(self.event_type, str):
            self.event_type = EventType(self.event_type)
        if isinstance(self.severity, str):
            self.severity = EventSeverity(self.severity)
        if isinstance(self.status, str):
            self.status = EventStatus(self.status)


def _same_subscription(a: FBRMonitorConfig, b: FBRMonitorConfig) -> bool:
    """Whether two configs monitor the same events for the same NTN."""
    return (
        a.ntn == b.ntn
        and a.user_id == b.user_id
        and a.check_interval_minutes == b.check_interval_minutes
        and a.monitor_notices == b.monitor_notices
        and a.monitor_payments == b.monitor_payments
        and a.monitor_returns == b.monitor_returns
        and a.monitor_policy_changes == b.monitor_policy_changes
    )


class FBRMonitor:
    """Main FBR monitor."""

    def __init__(self):
        # A user can hold several subscriptions (different NTNs, intervals or
        # event selections), so configs map a user id to a list.
        self.configs: dict[str, list[FBRMonitorConfig]] = {}
        self.events: deque[FBRMonitorEvent] = deque(maxlen=STATE_MAXLEN)
        self.audit_log: deque[dict] = deque(maxlen=STATE_MAXLEN)

    def subscribe(self, config: FBRMonitorConfig) -> str:
        """Subscribe a user to FBR monitoring.

        Returns the stored sub_id. Subscriptions are appended to the user's
        list; one that selects the same events for the same NTN and interval
        updates the existing entry instead of piling up a duplicate.
        """
        subscriptions = self.configs.setdefault(config.user_id, [])
        existing = next((c for c in subscriptions if _same_subscription(c, config)), None)

        if existing is not None:
            existing.notification_email = config.notification_email
            existing.notification_webhook = config.notification_webhook
            logger.info(
                f"User {config.user_id} updated FBR monitor subscription "
                f"{existing.sub_id} for NTN {config.ntn}"
            )
            return existing.sub_id

        config.sub_id = str(uuid.uuid4())
        config.subscribed_at = datetime.now(timezone.utc).isoformat()
        subscriptions.append(config)
        logger.info(
            f"User {config.user_id} subscribed to FBR monitor for NTN {config.ntn}"
        )
        return config.sub_id

    def get_subscriptions(self, user_id: str) -> list[FBRMonitorConfig]:
        """List the subscriptions stored for a user."""
        return list(self.configs.get(user_id, []))

    def unsubscribe(self, user_id: str) -> bool:
        """Unsubscribe a user (drops every subscription they hold)."""
        if user_id in self.configs:
            del self.configs[user_id]
            return True
        return False

    def detect_event(
        self,
        ntn: str,
        event_type: EventType,
        title: str,
        description: str,
        severity: EventSeverity = EventSeverity.MEDIUM,
        reference_number: Optional[str] = None,
        url: Optional[str] = None,
        requires_action: bool = False,
        action_deadline: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[FBRMonitorEvent]:
        """
        Detect and record a new FBR event.

        Every user subscribed to this NTN is notified, so an NTN shared by
        several taxpayers is not attributed only to whoever subscribed first.
        The first event created is returned for callers acting on one event.

        No portal polling happens here: this is called by the env-gated
        simulate route and by any future background worker.
        """
        # Every user subscribed to this NTN gets an event; a shared NTN must
        # not be attributed only to the first matching subscription.
        subscriber_ids: list[str] = []
        for subscriptions in self.configs.values():
            for cfg in subscriptions:
                if cfg.ntn == ntn and cfg.user_id not in subscriber_ids:
                    subscriber_ids.append(cfg.user_id)

        if not subscriber_ids:
            return None

        events = []
        for user_id in subscriber_ids:
            event = FBRMonitorEvent(
                id=str(uuid.uuid4()),
                user_id=user_id,
                ntn=ntn,
                event_type=event_type,
                severity=severity,
                title=title,
                description=description,
                reference_number=reference_number,
                url=url,
                requires_action=requires_action,
                action_deadline=action_deadline,
                metadata=metadata or {},
            )

            self.events.append(event)
            self.audit_log.append({
                "event_id": event.id,
                "user_id": user_id,
                "ntn": ntn,
                "type": event_type.value,
                "timestamp": event.detected_at,
            })
            events.append(event)

        logger.info(
            f"Detected FBR event: {event_type.value} for NTN {ntn} "
            f"(severity: {severity.value}, subscribers: {len(subscriber_ids)})"
        )

        return events[0]

    def get_events(
        self,
        user_id: Optional[str] = None,
        severity: Optional[EventSeverity] = None,
        status: Optional[EventStatus] = None,
        event_type: Optional[EventType] = None,
        limit: int = 50,
    ) -> list[FBRMonitorEvent]:
        """Get events with filters."""
        filtered = self.events

        if user_id:
            filtered = [e for e in filtered if e.user_id == user_id]
        if severity:
            filtered = [e for e in filtered if e.severity == severity]
        if status:
            filtered = [e for e in filtered if e.status == status]
        if event_type:
            filtered = [e for e in filtered if e.event_type == event_type]

        return filtered[-limit:]

    def update_event_status(
        self,
        event_id: str,
        status: EventStatus,
    ) -> Optional[FBRMonitorEvent]:
        """Update event status."""
        for event in self.events:
            if event.id == event_id:
                event.status = status
                logger.info(f"Event {event_id} status updated to {status.value}")
                return event
        return None

    def get_unread(self, user_id: str) -> list[FBRMonitorEvent]:
        """Get unread events for user."""
        return [e for e in self.events if e.user_id == user_id and e.status == EventStatus.NEW]

    def get_critical(self, user_id: Optional[str] = None) -> list[FBRMonitorEvent]:
        """Get critical events."""
        return self.get_events(
            user_id=user_id,
            severity=EventSeverity.CRITICAL,
            status=EventStatus.NEW,
        )

    def get_statistics(self, user_id: Optional[str] = None) -> dict:
        """Get monitoring statistics."""
        events = self.get_events(user_id=user_id, limit=10000)

        by_type = {}
        by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        by_status = {"new": 0, "acknowledged": 0, "in_progress": 0, "resolved": 0, "closed": 0}

        for e in events:
            by_type[e.event_type.value] = by_type.get(e.event_type.value, 0) + 1
            by_severity[e.severity.value] = by_severity.get(e.severity.value, 0) + 1
            by_status[e.status.value] = by_status.get(e.status.value, 0) + 1

        return {
            "total_events": len(events),
            "by_type": by_type,
            "by_severity": by_severity,
            "by_status": by_status,
            "unread_count": sum(1 for e in events if e.status == EventStatus.NEW),
            "critical_count": sum(1 for e in events if e.severity == EventSeverity.CRITICAL),
            "action_required_count": sum(1 for e in events if e.requires_action and e.status == EventStatus.NEW),
        }


# Singleton
_monitor: Optional[FBRMonitor] = None


def get_fbr_monitor() -> FBRMonitor:
    """Get singleton FBR monitor."""
    global _monitor
    if _monitor is None:
        _monitor = FBRMonitor()
    return _monitor
