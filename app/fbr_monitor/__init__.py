"""
Live FBR Monitoring - Production-Grade
====================================

Real-time monitoring of FBR activities for taxpayers:
- Monitor new notices on IRIS portal
- Track correspondence
- Check return acknowledgment status
- Watch for new SROs/circulars
- Audit alerts
- Tax rate changes
- Policy updates
- Compliance deadline reminders
- Webhook notifications
- Email alerts
- Slack/Teams integration
- Historical monitoring data
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
