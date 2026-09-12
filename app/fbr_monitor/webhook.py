"""
Webhook Manager - Production-Grade
=================================

Manage webhook endpoints for FBR event notifications.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import json

logger = logging.getLogger("fbr_monitor")


class WebhookStatus(str, Enum):
    """Status of webhook delivery."""
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class WebhookEndpoint:
    """A registered webhook endpoint."""
    id: str
    user_id: str
    name: str
    url: str
    secret: Optional[str] = None  # For HMAC signing
    is_active: bool = True
    event_types: list[str] = field(default_factory=list)  # Empty = all
    retry_count: int = 3
    timeout_seconds: int = 30
    created_at: str = ""


@dataclass
class WebhookEvent:
    """A webhook event delivery attempt."""
    id: str
    endpoint_id: str
    event_id: str
    payload: dict
    status: WebhookStatus = WebhookStatus.PENDING
    attempts: int = 0
    last_attempt_at: Optional[str] = None
    response_code: Optional[int] = None
    response_body: Optional[str] = None
    error: Optional[str] = None
    delivered_at: Optional[str] = None


class WebhookManager:
    """Manages webhook endpoints and event delivery."""

    def __init__(self):
        self.endpoints: dict[str, WebhookEndpoint] = {}
        self.delivery_log: list[WebhookEvent] = []

    def register(
        self,
        user_id: str,
        name: str,
        url: str,
        secret: Optional[str] = None,
        event_types: Optional[list[str]] = None,
    ) -> WebhookEndpoint:
        """Register a new webhook endpoint."""
        endpoint = WebhookEndpoint(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=name,
            url=url,
            secret=secret,
            event_types=event_types or [],
            created_at=datetime.utcnow().isoformat(),
        )
        self.endpoints[endpoint.id] = endpoint
        logger.info(f"Registered webhook endpoint: {name} ({url}) for user {user_id}")
        return endpoint

    def unregister(self, endpoint_id: str) -> bool:
        """Unregister a webhook endpoint."""
        if endpoint_id in self.endpoints:
            del self.endpoints[endpoint_id]
            return True
        return False

    def list_endpoints(self, user_id: Optional[str] = None) -> list[WebhookEndpoint]:
        """List webhook endpoints for a user."""
        if user_id:
            return [e for e in self.endpoints.values() if e.user_id == user_id]
        return list(self.endpoints.values())

    def trigger(
        self,
        event_id: str,
        event_type: str,
        payload: dict,
        user_id: Optional[str] = None,
    ) -> list[WebhookEvent]:
        """Trigger webhooks for an event."""
        triggered = []

        for endpoint in self.endpoints.values():
            if not endpoint.is_active:
                continue

            if user_id and endpoint.user_id != user_id:
                continue

            # Filter by event type
            if endpoint.event_types and event_type not in endpoint.event_types:
                continue

            # Create delivery record
            delivery = WebhookEvent(
                id=str(uuid.uuid4()),
                endpoint_id=endpoint.id,
                event_id=event_id,
                payload=payload,
            )

            # Simulate delivery (in production, would call endpoint.url)
            self._simulate_delivery(delivery, endpoint)
            self.delivery_log.append(delivery)
            triggered.append(delivery)

        return triggered

    def _simulate_delivery(self, delivery: WebhookEvent, endpoint: WebhookEndpoint) -> None:
        """Simulate webhook delivery."""
        delivery.attempts = 1
        delivery.last_attempt_at = datetime.utcnow().isoformat()

        # Simulated success
        delivery.status = WebhookStatus.DELIVERED
        delivery.response_code = 200
        delivery.delivered_at = datetime.utcnow().isoformat()

    def get_delivery_log(
        self,
        endpoint_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[WebhookEvent]:
        """Get webhook delivery log."""
        log = self.delivery_log
        if endpoint_id:
            log = [d for d in log if d.endpoint_id == endpoint_id]
        return log[-limit:]

    def get_statistics(self) -> dict:
        """Get webhook statistics."""
        total = len(self.delivery_log)
        delivered = sum(1 for d in self.delivery_log if d.status == WebhookStatus.DELIVERED)
        failed = sum(1 for d in self.delivery_log if d.status == WebhookStatus.FAILED)

        return {
            "total_endpoints": len(self.endpoints),
            "total_deliveries": total,
            "successful_deliveries": delivered,
            "failed_deliveries": failed,
            "success_rate": round(delivered / total * 100, 2) if total > 0 else 0,
        }


# Singleton
_webhook_manager: Optional[WebhookManager] = None


def get_webhook_manager() -> WebhookManager:
    """Get singleton webhook manager."""
    global _webhook_manager
    if _webhook_manager is None:
        _webhook_manager = WebhookManager()
    return _webhook_manager
