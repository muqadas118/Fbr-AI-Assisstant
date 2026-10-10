"""
Live FBR Monitoring
==================

In-memory FBR monitoring for taxpayers.

Everything here lives in this process: the subscription store, detected
events, audit log and webhook deliveries are bounded in-memory
collections, so they are lost on restart. Nothing polls the IRIS portal —
events only enter through detect_event(), which the env-gated simulate
route and any future background worker call. Webhook delivery is a real
HTTP POST to the endpoint URL unless FBR_MONITOR_SIMULATE_DELIVERY=1 is
set, which records the delivery as SIMULATED instead. No email and no
Slack/Teams integration exist.

The router endpoints are owner-scoped: a subscription, event or webhook
may only be read or mutated through the identity that owns it, and
simulated notices are gated behind FBR_MONITOR_ALLOW_SIMULATE.
"""

from app.fbr_monitor.monitor_engine import (
    FBRMonitor, FBRMonitorEvent, FBRMonitorConfig,
    EventType, EventSeverity, EventStatus,
    get_fbr_monitor,
)
from app.fbr_monitor.webhook import (
    WebhookManager, WebhookEndpoint, WebhookEvent,
    get_webhook_manager,
)
from app.fbr_monitor.api import (
    FBRMonitorAPI, get_fbr_monitor_api,
    MonitorSubscription, MonitorAlert,
)

__all__ = [
    "FBRMonitor",
    "FBRMonitorEvent",
    "FBRMonitorConfig",
    "EventType",
    "EventSeverity",
    "EventStatus",
    "get_fbr_monitor",
    "WebhookManager",
    "WebhookEndpoint",
    "WebhookEvent",
    "get_webhook_manager",
    "FBRMonitorAPI",
    "get_fbr_monitor_api",
    "MonitorSubscription",
    "MonitorAlert",
]
