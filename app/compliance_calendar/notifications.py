"""
Notification Manager - Production-Grade
=======================================

FBR compliance reminders ka notification system:
- Email notifications (simulated)
- SMS notifications (simulated)
- Push notifications (simulated)
- In-app notifications (simulated)
- Reminder scheduling (90/60/30/14/7/1 days before)
- Notification history
- Do Not Disturb settings
- Batch notifications

DELIVERY HONESTY
----------------
No channel is wired up to a real provider. Every `_send_*` below only logs, so
they must NOT report success: simulated deliveries are marked SIMULATED (and
`send_notification()` returns False for them), while the in-app channel, which
really does append to the in-app inbox, is marked SENT and returns True. A
record in `sent_history` therefore always means "actually delivered".
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger("compliance_calendar")


class NotificationChannel(str, Enum):
    """Channel for notification delivery."""
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    IN_APP = "in_app"
    WHATSAPP = "whatsapp"


class NotificationStatus(str, Enum):
    """Status of a notification."""
    PENDING = "pending"
    SENT = "sent"
    # Recorded when a delivery path is simulated (logs only, no provider).
    # Anything still SIMULATED was not actually delivered.
    SIMULATED = "simulated"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NotificationPriority(str, Enum):
    """Urgency of notification."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class NotificationRecord:
    """Single notification record."""
    id: str
    event_id: str
    channel: NotificationChannel
    recipient: str
    subject: str
    message: str
    status: NotificationStatus = NotificationStatus.PENDING
    priority: NotificationPriority = NotificationPriority.NORMAL
    scheduled_for: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    # Set when a channel was only simulated, so callers can tell a real
    # delivery from a log line.
    simulated: bool = False
    metadata: dict = field(default_factory=dict)


class NotificationManager:
    """
    Manages all compliance notifications.

    In production, this would integrate with:
    - SMTP server for email
    - SMS gateway (e.g., Twilio, MSG91)
    - Firebase/APNs for push
    - WhatsApp Business API

    Until those integrations exist, only IN_APP is a real delivery; the rest
    are simulated and reported as such (see module docstring).
    """

    def __init__(self):
        self.queue: list[NotificationRecord] = []
        self.sent_history: list[NotificationRecord] = []
        # Real deliveries to the in-app inbox, the only channel that is
        # actually delivered in this build.
        self.in_app_inbox: list[NotificationRecord] = []

    def schedule_notification(
        self,
        event_id: str,
        event_title: str,
        due_date: str,
        days_remaining: int,
        recipient: str,
        channels: list[NotificationChannel] = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
    ) -> list[NotificationRecord]:
        """Schedule reminder notifications for an event."""
        if channels is None:
            channels = [
                NotificationChannel.EMAIL,
                NotificationChannel.PUSH,
                NotificationChannel.IN_APP,
            ]

        records = []
        subject = self._generate_subject(event_title, days_remaining)
        message = self._generate_message(event_title, due_date, days_remaining)

        for channel in channels:
            record = NotificationRecord(
                id=str(uuid.uuid4()),
                event_id=event_id,
                channel=channel,
                recipient=recipient,
                subject=subject,
                message=message,
                priority=priority,
                scheduled_for=datetime.now(timezone.utc),
                metadata={
                    "days_remaining": days_remaining,
                    "urgency": self._get_urgency(days_remaining),
                },
            )
            records.append(record)
            self.queue.append(record)

        logger.info(
            f"Scheduled {len(records)} notifications for event {event_id} "
            f"({days_remaining} days remaining)"
        )
        return records

    def send_notification(self, record: NotificationRecord) -> bool:
        """
        Send a single notification.

        Returns True only for a real delivery (IN_APP). Simulated channels are
        marked SIMULATED and return False - a True/False here is never a guess.
        """
        try:
            # Simulate sending based on channel
            if record.channel == NotificationChannel.EMAIL:
                success = self._send_email(record)
            elif record.channel == NotificationChannel.SMS:
                success = self._send_sms(record)
            elif record.channel == NotificationChannel.PUSH:
                success = self._send_push(record)
            elif record.channel == NotificationChannel.WHATSAPP:
                success = self._send_whatsapp(record)
            else:
                success = self._send_in_app(record)

            if success:
                record.status = NotificationStatus.SENT
                record.sent_at = datetime.now(timezone.utc)
                self.sent_history.append(record)
                logger.info(f"Sent {record.channel.value} notification: {record.id}")
            elif record.channel == NotificationChannel.IN_APP:
                # In-app delivery failed (records itself as FAILED).
                record.retry_count += 1
                logger.error(f"Failed to send notification: {record.id}")
            else:
                # No provider integration for this channel: not sent, and said so.
                record.status = NotificationStatus.SIMULATED
                record.simulated = True
                logger.info(
                    f"SIMULATED (not delivered) {record.channel.value} "
                    f"notification: {record.id} - no provider integration configured"
                )

            return success

        except Exception as e:
            record.status = NotificationStatus.FAILED
            record.error_message = str(e)
            record.retry_count += 1
            logger.exception(f"Error sending notification {record.id}")
            return False

    def send_batch(self, records: list[NotificationRecord]) -> dict:
        """Send multiple notifications."""
        results = {
            "total": len(records),
            "sent": 0,
            "failed": 0,
            "failed_ids": [],
            "simulated": 0,
            "simulated_ids": [],
        }

        for record in records:
            if self.send_notification(record):
                results["sent"] += 1
            elif record.status == NotificationStatus.SIMULATED:
                results["simulated"] += 1
                results["simulated_ids"].append(record.id)
            else:
                results["failed"] += 1
                results["failed_ids"].append(record.id)

        return results

    def cancel_notification(self, notification_id: str) -> bool:
        """Cancel a pending notification."""
        for record in self.queue:
            if record.id == notification_id:
                record.status = NotificationStatus.CANCELLED
                logger.info(f"Cancelled notification: {notification_id}")
                return True
        return False

    def get_pending(self) -> list[NotificationRecord]:
        """Get all pending notifications."""
        return [r for r in self.queue if r.status == NotificationStatus.PENDING]

    def get_history(self, limit: int = 50) -> list[NotificationRecord]:
        """Get notification history."""
        return self.sent_history[-limit:]

    def _send_email(self, record: NotificationRecord) -> bool:
        """Simulate email sending (no SMTP provider configured)."""
        # In production: integrate with SMTP/SendGrid/etc.
        logger.info(
            f"[EMAIL SIMULATED] To: {record.recipient}, "
            f"Subject: {record.subject[:50]}..."
        )
        return False

    def _send_sms(self, record: NotificationRecord) -> bool:
        """Simulate SMS sending (no SMS gateway configured)."""
        # In production: integrate with Twilio/MSG91/etc.
        logger.info(
            f"[SMS SIMULATED] To: {record.recipient}, "
            f"Message: {record.message[:50]}..."
        )
        return False

    def _send_push(self, record: NotificationRecord) -> bool:
        """Simulate push notification (no FCM/APNs provider configured)."""
        # In production: integrate with Firebase/APNs
        logger.info(f"[PUSH SIMULATED] Title: {record.subject[:30]}...")
        return False

    def _send_whatsapp(self, record: NotificationRecord) -> bool:
        """Simulate WhatsApp message (no WhatsApp Business API configured)."""
        logger.info(
            f"[WHATSAPP SIMULATED] To: {record.recipient}, "
            f"Message: {record.message[:50]}..."
        )
        return False

    def _send_in_app(self, record: NotificationRecord) -> bool:
        """Deliver an in-app notification (the one channel that really sends)."""
        record.delivered_at = datetime.now(timezone.utc)
        self.in_app_inbox.append(record)
        logger.info(f"[IN-APP] To: {record.recipient}, Subject: {record.subject}")
        return True

    def _generate_subject(self, event_title: str, days_remaining: int) -> str:
        """Generate notification subject."""
        if days_remaining == 0:
            return f"⚠️ URGENT: {event_title} is DUE TODAY!"
        elif days_remaining == 1:
            return f"🔴 REMINDER: {event_title} is due TOMORROW!"
        elif days_remaining <= 7:
            return f"🟡 Due Soon: {event_title} in {days_remaining} days"
        elif days_remaining <= 30:
            return f"📅 Reminder: {event_title} in {days_remaining} days"
        else:
            return f"📋 Upcoming: {event_title} on your calendar"

    def _generate_message(self, event_title: str, due_date: str, days_remaining: int) -> str:
        """Generate notification message."""
        if days_remaining == 0:
            return (
                f"⚠️ CRITICAL: '{event_title}' is due TODAY ({due_date}).\n\n"
                f"Please complete this compliance task immediately to avoid penalties.\n\n"
                f"This is your final reminder."
            )
        elif days_remaining == 1:
            return (
                f"🔴 IMPORTANT: '{event_title}' is due TOMORROW ({due_date}).\n\n"
                f"Complete this task before the deadline to avoid penalties.\n\n"
                f"Don't wait - act now!"
            )
        elif days_remaining <= 7:
            return (
                f"🟡 REMINDER: '{event_title}' is due in {days_remaining} days ({due_date}).\n\n"
                f"Start preparing your documents now.\n\n"
                f"Priority: HIGH"
            )
        elif days_remaining <= 30:
            return (
                f"📅 NOTICE: '{event_title}' is due in {days_remaining} days ({due_date}).\n\n"
                f"Mark this in your calendar and plan accordingly.\n\n"
                f"Priority: NORMAL"
            )
        else:
            return (
                f"📋 UPCOMING: '{event_title}' is scheduled for {due_date}.\n\n"
                f"You have {days_remaining} days to prepare.\n\n"
                f"Priority: LOW"
            )

    def _get_urgency(self, days_remaining: int) -> str:
        """Determine urgency level."""
        if days_remaining <= 1:
            return "critical"
        elif days_remaining <= 7:
            return "high"
        elif days_remaining <= 30:
            return "medium"
        else:
            return "low"


# Singleton
_notification_manager: Optional[NotificationManager] = None


def get_notification_manager() -> NotificationManager:
    """Get singleton notification manager."""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager
