"""
Notification Manager - Production-Grade
=======================================

FBR compliance reminders ka notification system:
- Email notifications (simulated)
- SMS notifications (simulated)
- Push notifications (simulated)
- In-app notifications
- Reminder scheduling (90/60/30/14/7/1 days before)
- Notification history
- Do Not Disturb settings
- Batch notifications
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
    scheduled_for: datetime = field(default_factory=datetime.utcnow)
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    metadata: dict = field(default_factory=dict)


class NotificationManager:
    """
    Manages all compliance notifications.

    In production, this would integrate with:
    - SMTP server for email
    - SMS gateway (e.g., Twilio, MSG91)
    - Firebase/APNs for push
    - WhatsApp Business API
    """

    def __init__(self):
        self.queue: list[NotificationRecord] = []
        self.sent_history: list[NotificationRecord] = []
        self._notification_id_counter = 0

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
                scheduled_for=datetime.utcnow(),
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
        """Send a single notification (simulated)."""
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
                record.sent_at = datetime.utcnow()
                self.sent_history.append(record)
                logger.info(f"Sent {record.channel.value} notification: {record.id}")
            else:
                record.status = NotificationStatus.FAILED
                record.retry_count += 1
                logger.error(f"Failed to send notification: {record.id}")

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
        }

        for record in records:
            if self.send_notification(record):
                results["sent"] += 1
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
        """Simulate email sending."""
        # In production: integrate with SMTP/SendGrid/etc.
        logger.info(
            f"[EMAIL SIMULATED] To: {record.recipient}, "
            f"Subject: {record.subject[:50]}..."
        )
        return True

    def _send_sms(self, record: NotificationRecord) -> bool:
        """Simulate SMS sending."""
        # In production: integrate with Twilio/MSG91/etc.
        logger.info(
            f"[SMS SIMULATED] To: {record.recipient}, "
            f"Message: {record.message[:50]}..."
        )
        return True

    def _send_push(self, record: NotificationRecord) -> bool:
        """Simulate push notification."""
        # In production: integrate with Firebase/APNs
        logger.info(f"[PUSH SIMULATED] Title: {record.subject[:30]}...")
        return True

    def _send_whatsapp(self, record: NotificationRecord) -> bool:
        """Simulate WhatsApp message."""
        logger.info(
            f"[WHATSAPP SIMULATED] To: {record.recipient}, "
            f"Message: {record.message[:50]}..."
        )
        return True

    def _send_in_app(self, record: NotificationRecord) -> bool:
        """Simulate in-app notification."""
        logger.info(f"[IN-APP SIMULATED] {record.subject}")
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
