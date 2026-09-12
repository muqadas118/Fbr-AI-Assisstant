"""
Test Suite for FBR Monitor
============================
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from app.fbr_monitor import (
    FBRMonitor, FBRMonitorEvent, FBRMonitorConfig,
    EventType, EventSeverity, EventStatus,
    WebhookManager, WebhookEndpoint, WebhookEvent,
    FBRMonitorAPI, get_fbr_monitor_api,
    MonitorSubscription, MonitorAlert,
)


class TestFBRMonitor(unittest.TestCase):
    """Test FBR monitor."""

    def setUp(self):
        # Fresh monitor for each test
        from app.fbr_monitor.monitor_engine import FBRMonitor
        self.monitor = FBRMonitor()

    def test_subscribe(self):
        config = FBRMonitorConfig(
            ntn="1234567-8",
            user_id="user1",
        )
        sub_id = self.monitor.subscribe(config)
        self.assertIsNotNone(sub_id)
        self.assertIn("user1", self.monitor.configs)

    def test_unsubscribe(self):
        config = FBRMonitorConfig(
            ntn="1234567-8",
            user_id="user1",
        )
        self.monitor.subscribe(config)
        success = self.monitor.unsubscribe("user1")
        self.assertTrue(success)
        self.assertNotIn("user1", self.monitor.configs)

    def test_detect_event(self):
        config = FBRMonitorConfig(
            ntn="1234567-8",
            user_id="user1",
        )
        self.monitor.subscribe(config)

        event = self.monitor.detect_event(
            ntn="1234567-8",
            event_type=EventType.NEW_NOTICE,
            title="Test Notice",
            description="Test description",
            severity=EventSeverity.HIGH,
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.user_id, "user1")

    def test_get_events_filtered(self):
        config = FBRMonitorConfig(
            ntn="1234567-8",
            user_id="user1",
        )
        self.monitor.subscribe(config)
        self.monitor.detect_event(
            ntn="1234567-8",
            event_type=EventType.NEW_NOTICE,
            title="N1",
            description="D1",
        )
        self.monitor.detect_event(
            ntn="1234567-8",
            event_type=EventType.AUDIT_NOTICE,
            title="N2",
            description="D2",
            severity=EventSeverity.CRITICAL,
        )
        events = self.monitor.get_events(
            user_id="user1",
            severity=EventSeverity.CRITICAL,
        )
        self.assertEqual(len(events), 1)

    def test_update_status(self):
        config = FBRMonitorConfig(
            ntn="1234567-8",
            user_id="user1",
        )
        self.monitor.subscribe(config)
        event = self.monitor.detect_event(
            ntn="1234567-8",
            event_type=EventType.NEW_NOTICE,
            title="N1",
            description="D1",
        )
        result = self.monitor.update_event_status(event.id, EventStatus.ACKNOWLEDGED)
        self.assertEqual(result.status, EventStatus.ACKNOWLEDGED)

    def test_get_unread(self):
        config = FBRMonitorConfig(
            ntn="1234567-8",
            user_id="user1",
        )
        self.monitor.subscribe(config)
        self.monitor.detect_event(
            ntn="1234567-8",
            event_type=EventType.NEW_NOTICE,
            title="N1",
            description="D1",
        )
        unread = self.monitor.get_unread("user1")
        self.assertEqual(len(unread), 1)

    def test_statistics(self):
        config = FBRMonitorConfig(
            ntn="1234567-8",
            user_id="user1",
        )
        self.monitor.subscribe(config)
        self.monitor.detect_event(
            ntn="1234567-8",
            event_type=EventType.NEW_NOTICE,
            title="N1",
            description="D1",
            severity=EventSeverity.CRITICAL,
        )
        stats = self.monitor.get_statistics("user1")
        self.assertEqual(stats["total_events"], 1)
        self.assertEqual(stats["critical_count"], 1)


class TestWebhookManager(unittest.TestCase):
    """Test webhook manager."""

    def setUp(self):
        from app.fbr_monitor.webhook import WebhookManager
        self.manager = WebhookManager()

    def test_register_webhook(self):
        endpoint = self.manager.register(
            user_id="user1",
            name="Test Webhook",
            url="https://example.com/webhook",
        )
        self.assertIsNotNone(endpoint.id)
        self.assertTrue(endpoint.is_active)

    def test_unregister_webhook(self):
        endpoint = self.manager.register(
            user_id="user1",
            name="Test",
            url="https://example.com",
        )
        success = self.manager.unregister(endpoint.id)
        self.assertTrue(success)

    def test_trigger_webhook(self):
        self.manager.register(
            user_id="user1",
            name="Test",
            url="https://example.com",
        )
        deliveries = self.manager.trigger(
            event_id="event1",
            event_type=EventType.NEW_NOTICE.value,
            payload={"test": "data"},
        )
        self.assertEqual(len(deliveries), 1)

    def test_filtered_webhook(self):
        self.manager.register(
            user_id="user1",
            name="Filtered",
            url="https://example.com",
            event_types=["new_notice"],
        )
        # Should NOT trigger for audit_notice
        deliveries = self.manager.trigger(
            event_id="event1",
            event_type="audit_notice",
            payload={"test": "data"},
        )
        self.assertEqual(len(deliveries), 0)

    def test_statistics(self):
        self.manager.register(
            user_id="user1",
            name="Test",
            url="https://example.com",
        )
        self.manager.trigger(
            event_id="e1",
            event_type="new_notice",
            payload={},
        )
        stats = self.manager.get_statistics()
        self.assertEqual(stats["total_endpoints"], 1)
        self.assertEqual(stats["total_deliveries"], 1)


class TestFBRMonitorAPI(unittest.TestCase):
    """Test FBR monitor API."""

    def setUp(self):
        # Use fresh singletons for testing
        from app.fbr_monitor.monitor_engine import FBRMonitor
        from app.fbr_monitor.webhook import WebhookManager
        from app.fbr_monitor.api import FBRMonitorAPI
        self.api = FBRMonitorAPI()
        # Reset
        self.api.monitor = FBRMonitor()
        self.api.webhook_manager = WebhookManager()

    def test_subscribe_user(self):
        sub = self.api.subscribe_user(
            user_id="user1",
            ntn="1234567-8",
        )
        self.assertEqual(sub.ntn, "1234567-8")
        self.assertTrue(sub.is_active)

    def test_unsubscribe_user(self):
        self.api.subscribe_user(user_id="user1", ntn="1234567-8")
        success = self.api.unsubscribe_user("user1")
        self.assertTrue(success)

    def test_simulate_new_notice(self):
        self.api.subscribe_user(user_id="user1", ntn="1234567-8")
        event = self.api.simulate_new_notice(
            ntn="1234567-8",
            notice_number="FBR/2024/001",
            title="Show Cause Notice",
            description="Test",
            action_deadline="2024-12-31",
        )
        self.assertIsNotNone(event)
        self.assertEqual(event["reference_number"], "FBR/2024/001")

    def test_dashboard(self):
        self.api.subscribe_user(user_id="user1", ntn="1234567-8")
        self.api.simulate_new_notice(
            ntn="1234567-8",
            notice_number="N1",
            title="T1",
            description="D1",
        )
        dashboard = self.api.get_user_dashboard("user1")
        self.assertEqual(dashboard["total_events"], 1)

    def test_acknowledge_event(self):
        self.api.subscribe_user(user_id="user1", ntn="1234567-8")
        event = self.api.simulate_new_notice(
            ntn="1234567-8",
            notice_number="N1",
            title="T1",
            description="D1",
        )
        result = self.api.acknowledge_event(event["id"])
        self.assertEqual(result["status"], "acknowledged")

    def test_register_webhook(self):
        result = self.api.register_webhook(
            user_id="user1",
            name="My Webhook",
            url="https://example.com",
        )
        self.assertIsNotNone(result["id"])

    def test_webhook_stats(self):
        result = self.api.get_webhook_stats()
        self.assertIn("total_endpoints", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
