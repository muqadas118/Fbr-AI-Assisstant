"""
Monitoring and Alerting - Production-Grade
==========================================

Alert management, notification routing, and incident tracking.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable

logger = logging.getLogger("deployment")


class AlertSeverity(str, Enum):
    """Severity of an alert."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertChannel(str, Enum):
    """Notification channel for alerts."""
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    WEBHOOK = "webhook"
    SLACK = "slack"
    INTERNAL = "internal"


@dataclass
class Alert:
    """An alert/notification."""
    id: str
    title: str
    message: str
    severity: AlertSeverity
    source: str  # Component that triggered the alert
    channel: AlertChannel = AlertChannel.INTERNAL
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
    acknowledged_at: Optional[str] = None
    resolved_at: Optional[str] = None
    is_resolved: bool = False

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()

    def acknowledge(self) -> None:
        if not self.acknowledged_at:
            self.acknowledged_at = datetime.utcnow().isoformat()

    def resolve(self) -> None:
        self.is_resolved = True
        if not self.resolved_at:
            self.resolved_at = datetime.utcnow().isoformat()


@dataclass
class AlertRule:
    """A rule for triggering alerts based on metrics."""
    id: str
    name: str
    metric_name: str
    threshold: float
    comparison: str  # "gt", "lt", "eq", "ne"
    severity: AlertSeverity
    channel: AlertChannel
    is_active: bool = True
    cooldown_seconds: int = 300
    last_triggered_at: Optional[str] = None


# Rule evaluation helpers
def evaluate_rule(rule: AlertRule, current_value: float) -> bool:
    """Evaluate if a rule's threshold is breached."""
    if not rule.is_active:
        return False
    if rule.comparison == "gt":
        return current_value > rule.threshold
    if rule.comparison == "lt":
        return current_value < rule.threshold
    if rule.comparison == "gte":
        return current_value >= rule.threshold
    if rule.comparison == "lte":
        return current_value <= rule.threshold
    if rule.comparison == "eq":
        return current_value == rule.threshold
    if rule.comparison == "ne":
        return current_value != rule.threshold
    return False


class MonitoringService:
    """
    Centralized monitoring and alerting service.

    Tracks active alerts, applies rules, and dispatches notifications.
    """

    def __init__(self):
        self.alerts: list[Alert] = []
        self.rules: dict[str, AlertRule] = {}
        # Index by source for quick lookup
        self.alerts_by_source: dict[str, list[str]] = {}
        # Active alerts (not resolved)
        self.active_alert_ids: set[str] = set()

    def create_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        source: str,
        channel: AlertChannel = AlertChannel.INTERNAL,
        metadata: Optional[dict] = None,
    ) -> Alert:
        """Create and record a new alert."""
        alert = Alert(
            id=str(uuid.uuid4()),
            title=title,
            message=message,
            severity=severity,
            source=source,
            channel=channel,
            metadata=metadata or {},
        )
        self.alerts.append(alert)
        self.active_alert_ids.add(alert.id)

        if source not in self.alerts_by_source:
            self.alerts_by_source[source] = []
        self.alerts_by_source[source].append(alert.id)

        logger.warning(
            f"Alert created: [{severity.value}] {title} ({source})"
        )
        return alert

    def add_rule(
        self,
        name: str,
        metric_name: str,
        threshold: float,
        comparison: str,
        severity: AlertSeverity,
        channel: AlertChannel = AlertChannel.EMAIL,
        cooldown_seconds: int = 300,
    ) -> AlertRule:
        """Add an alert rule."""
        rule = AlertRule(
            id=str(uuid.uuid4()),
            name=name,
            metric_name=metric_name,
            threshold=threshold,
            comparison=comparison,
            severity=severity,
            channel=channel,
            cooldown_seconds=cooldown_seconds,
        )
        self.rules[rule.id] = rule
        logger.info(f"Alert rule added: {name}")
        return rule

    def remove_rule(self, rule_id: str) -> bool:
        """Remove an alert rule."""
        if rule_id in self.rules:
            del self.rules[rule_id]
            return True
        return False

    def evaluate_rules(self, metric_values: dict[str, float]) -> list[Alert]:
        """
        Evaluate all rules against current metric values.

        Args:
            metric_values: Dict of {metric_name: current_value}

        Returns: List of newly triggered alerts.
        """
        triggered = []
        now = datetime.utcnow()

        for rule in self.rules.values():
            if not rule.is_active:
                continue

            current = metric_values.get(rule.metric_name)
            if current is None:
                continue

            # Cooldown check
            if rule.last_triggered_at:
                last_dt = datetime.fromisoformat(rule.last_triggered_at)
                elapsed = (now - last_dt).total_seconds()
                if elapsed < rule.cooldown_seconds:
                    continue

            if evaluate_rule(rule, current):
                alert = self.create_alert(
                    title=f"Rule triggered: {rule.name}",
                    message=f"Metric '{rule.metric_name}' = {current} "
                            f"({rule.comparison} {rule.threshold})",
                    severity=rule.severity,
                    source=rule.metric_name,
                    channel=rule.channel,
                    metadata={
                        "rule_id": rule.id,
                        "metric_value": current,
                        "threshold": rule.threshold,
                    },
                )
                rule.last_triggered_at = now.isoformat()
                triggered.append(alert)

        return triggered

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged."""
        for alert in self.alerts:
            if alert.id == alert_id:
                alert.acknowledge()
                return True
        return False

    def resolve_alert(self, alert_id: str) -> bool:
        """Mark an alert as resolved."""
        for alert in self.alerts:
            if alert.id == alert_id:
                alert.resolve()
                self.active_alert_ids.discard(alert_id)
                logger.info(f"Alert resolved: {alert.title}")
                return True
        return False

    def get_active_alerts(
        self,
        severity: Optional[AlertSeverity] = None,
        source: Optional[str] = None,
    ) -> list[Alert]:
        """Get active (unresolved) alerts, optionally filtered."""
        results = [a for a in self.alerts if a.id in self.active_alert_ids]
        if severity:
            results = [a for a in results if a.severity == severity]
        if source:
            results = [a for a in results if a.source == source]
        return results

    def get_alert_history(
        self,
        limit: int = 100,
        severity: Optional[AlertSeverity] = None,
    ) -> list[Alert]:
        """Get historical alerts."""
        results = list(self.alerts)
        if severity:
            results = [a for a in results if a.severity == severity]
        return results[-limit:]

    def get_statistics(self) -> dict:
        """Get monitoring statistics."""
        active = self.get_active_alerts()
        by_severity = {s.value: 0 for s in AlertSeverity}
        for alert in active:
            by_severity[alert.severity.value] += 1

        return {
            "total_alerts": len(self.alerts),
            "active_alerts": len(active),
            "resolved_alerts": sum(1 for a in self.alerts if a.is_resolved),
            "active_rules": sum(1 for r in self.rules.values() if r.is_active),
            "by_severity": by_severity,
        }


# Singleton
_monitoring_service: Optional[MonitoringService] = None


def get_monitoring_service() -> MonitoringService:
    """Get singleton monitoring service."""
    global _monitoring_service
    if _monitoring_service is None:
        _monitoring_service = MonitoringService()
    return _monitoring_service
