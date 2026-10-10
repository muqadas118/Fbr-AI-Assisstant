"""
Webhook Manager
===============

Manage webhook endpoints for FBR event notifications.

Endpoints and deliveries live in this process only, so they are lost on
restart and the delivery log is capped. Deliveries are real HTTP POSTs to the
endpoint URL. Set FBR_MONITOR_SIMULATE_DELIVERY=1 to skip the HTTP call - such
deliveries are recorded as SIMULATED with response_code 0, never as delivered.
"""

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger("fbr_monitor")

# The delivery log is process-local, so it is capped to keep a busy monitor
# from growing it without bound.
DELIVERY_LOG_MAXLEN = 1000

# Backoff between delivery retries: short and capped, so an unreachable or
# slow endpoint cannot pin a caller for the full timeout budget repeatedly.
RETRY_BACKOFF_SECONDS = 0.5
RETRY_BACKOFF_MAX_SECONDS = 2.0

# Hosts that may receive plain http, and only when insecure delivery is
# explicitly enabled for local testing.
_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")


def env_flag_enabled(name: str) -> bool:
    """Read a boolean env flag; anything but 1/true/on means disabled."""
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def sign_payload(body: bytes, secret: str) -> str:
    """Return the HMAC-SHA256 signature for a request body.

    Sent as `X-FBR-Signature: sha256=<hexdigest>` so the receiver can verify
    the payload was signed with the shared secret.
    """
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def is_safe_webhook_target(url: str) -> bool:
    """Whether POSTing an event payload to `url` is allowed.

    Payloads carry taxpayer data, so anything but a loopback http target is
    refused: https is the only scheme accepted in production, and plain http
    is limited to localhost with FBR_MONITOR_ALLOW_INSECURE_WEBHOOK=1.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    if parsed.scheme == "https":
        return True

    if parsed.scheme == "http":
        return (
            env_flag_enabled("FBR_MONITOR_ALLOW_INSECURE_WEBHOOK")
            and (parsed.hostname or "").lower() in _LOOPBACK_HOSTS
        )

    return False


class WebhookStatus(str, Enum):
    """Status of webhook delivery."""
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    SIMULATED = "simulated"


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
        self.delivery_log: deque[WebhookEvent] = deque(maxlen=DELIVERY_LOG_MAXLEN)

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
            created_at=datetime.now(timezone.utc).isoformat(),
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

            # Real HTTP delivery, or an explicitly simulated one
            self._deliver(delivery, endpoint)
            self.delivery_log.append(delivery)
            triggered.append(delivery)

        return triggered

    def _deliver(self, delivery: WebhookEvent, endpoint: WebhookEndpoint) -> None:
        """POST the payload to the endpoint, retrying transient failures.

        Retries the initial call up to `endpoint.retry_count` times with a
        short backoff. The recorded status always reflects what actually
        happened: the HTTP status code for real calls, and SIMULATED /
        response_code 0 when delivery is stubbed out by
        FBR_MONITOR_SIMULATE_DELIVERY=1.
        """
        body = json.dumps(delivery.payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if endpoint.secret:
            # Receivers verify the body against this header's HMAC.
            headers["X-FBR-Signature"] = sign_payload(body, endpoint.secret)

        # The initial attempt plus the configured retries.
        attempts = max(endpoint.retry_count, 0) + 1
        simulated = env_flag_enabled("FBR_MONITOR_SIMULATE_DELIVERY")

        if simulated:
            # No HTTP call and no fake 200: the delivery stays marked as
            # simulated so success_rate only ever reflects real responses.
            delivery.attempts = 1
            delivery.last_attempt_at = datetime.now(timezone.utc).isoformat()
            delivery.status = WebhookStatus.SIMULATED
            delivery.response_code = 0
            delivery.delivered_at = datetime.now(timezone.utc).isoformat()
            return

        for attempt in range(1, attempts + 1):
            delivery.attempts = attempt
            delivery.last_attempt_at = datetime.now(timezone.utc).isoformat()

            if not is_safe_webhook_target(endpoint.url):
                delivery.status = WebhookStatus.FAILED
                delivery.error = f"Blocked webhook target: {endpoint.url}"
                return

            try:
                response = requests.post(
                    endpoint.url,
                    data=body,
                    headers=headers,
                    timeout=endpoint.timeout_seconds,
                )
                delivery.response_code = response.status_code
                delivery.response_body = response.text[:500]

                if 200 <= response.status_code < 300:
                    delivery.status = WebhookStatus.DELIVERED
                    delivery.delivered_at = datetime.now(timezone.utc).isoformat()
                    delivery.error = None
                    return

                delivery.error = f"HTTP {response.status_code}"
            except requests.RequestException as exc:
                delivery.error = f"{type(exc).__name__}: {exc}"
                delivery.response_code = None

            delivery.status = WebhookStatus.RETRYING
            if attempt < attempts:
                backoff = min(
                    RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)),
                    RETRY_BACKOFF_MAX_SECONDS,
                )
                time.sleep(backoff)

        delivery.status = WebhookStatus.FAILED

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
        simulated = sum(1 for d in self.delivery_log if d.status == WebhookStatus.SIMULATED)

        return {
            "total_endpoints": len(self.endpoints),
            "total_deliveries": total,
            "successful_deliveries": delivered,
            "failed_deliveries": failed,
            "simulated_deliveries": simulated,
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
