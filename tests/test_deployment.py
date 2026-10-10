"""
Test Suite for Production Deployment
=====================================
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest


class TestConfig(unittest.TestCase):
    """Test configuration management."""

    def setUp(self):
        from app.deployment.config import Settings, Environment
        self.Settings = Settings
        self.Environment = Environment

    def test_default_settings(self):
        from app.deployment.config import get_settings
        settings = get_settings()
        self.assertEqual(settings.app_name, "FBR AI Tax Assistant")
        self.assertEqual(settings.environment, self.Environment.DEVELOPMENT)

    def test_is_production(self):
        s = self.Settings(environment=self.Environment.PRODUCTION)
        self.assertTrue(s.is_production())
        s2 = self.Settings(environment=self.Environment.DEVELOPMENT)
        self.assertFalse(s2.is_production())

    def test_validation_in_production(self):
        s = self.Settings(
            environment=self.Environment.PRODUCTION,
            secret_key="change-me-in-production",
        )
        issues = s.validate()
        self.assertGreater(len(issues), 0)
        self.assertTrue(any("SECRET_KEY" in i for i in issues))

    def test_validation_with_good_secret(self):
        s = self.Settings(
            environment=self.Environment.PRODUCTION,
            secret_key="super-secret-key-12345",
            database_url="postgresql://localhost/db",
        )
        issues = s.validate()
        self.assertEqual(len(issues), 0)

    def test_logging_configuration(self):
        from app.deployment.config import configure_logging, LogLevel
        # Should not raise
        configure_logging(LogLevel.INFO)
        configure_logging(LogLevel.DEBUG)


class TestHealthChecker(unittest.TestCase):
    """Test health checks."""

    def setUp(self):
        from app.deployment.health import HealthChecker, HealthStatus
        self.HealthChecker = HealthChecker
        self.HealthStatus = HealthStatus
        self.checker = HealthChecker(version="1.0.0", environment="test")

    def test_initialization(self):
        self.assertEqual(self.checker.version, "1.0.0")
        self.assertEqual(self.checker.environment, "test")

    def test_liveness(self):
        result = self.checker.liveness()
        self.assertEqual(result["status"], "alive")
        self.assertIn("uptime_seconds", result)

    def test_readiness(self):
        result = self.checker.readiness()
        self.assertIn("ready", result)
        self.assertIn("status", result)

    def test_register_and_run_check(self):
        from app.deployment.health import ComponentHealth

        def custom_check():
            return ComponentHealth(
                name="custom",
                status=self.HealthStatus.HEALTHY,
                message="OK",
            )

        self.checker.register_check("custom", custom_check)
        result = self.checker.run_check("custom")
        self.assertEqual(result.status, self.HealthStatus.HEALTHY)
        self.assertEqual(result.message, "OK")

    def test_check_with_exception(self):
        def failing_check():
            raise ValueError("Test error")

        self.checker.register_check("failing", failing_check)
        result = self.checker.run_check("failing")
        self.assertEqual(result.status, self.HealthStatus.UNHEALTHY)

    def test_run_all_checks(self):
        from app.deployment.health import ComponentHealth

        def ok():
            return ComponentHealth(name="ok", status=self.HealthStatus.HEALTHY, message="OK")
        def bad():
            return ComponentHealth(name="bad", status=self.HealthStatus.UNHEALTHY, message="Bad")

        self.checker.register_check("ok", ok)
        self.checker.register_check("bad", bad)
        result = self.checker.run_all_checks()
        # Overall should be UNHEALTHY due to 'bad' component
        self.assertEqual(result.status, self.HealthStatus.UNHEALTHY)
        # ok, bad, and the built-in system check
        self.assertEqual(len(result.components), 3)
        component_names = [c.name for c in result.components]
        self.assertIn("ok", component_names)
        self.assertIn("bad", component_names)

    def test_to_dict(self):
        result = self.checker.run_all_checks()
        d = result.to_dict()
        self.assertIn("status", d)
        self.assertIn("components", d)
        self.assertIn("version", d)


class TestMetricsCollector(unittest.TestCase):
    """Test metrics collection."""

    def setUp(self):
        from app.deployment.metrics import MetricsCollector
        self.collector = MetricsCollector()

    def test_counter_increment(self):
        self.collector.inc_counter("requests_total", value=1)
        self.collector.inc_counter("requests_total", value=3)
        self.assertEqual(self.collector.get_counter("requests_total"), 4)

    def test_counter_with_labels(self):
        self.collector.inc_counter("requests_total", labels={"method": "GET"})
        self.collector.inc_counter("requests_total", value=2, labels={"method": "GET"})
        self.assertEqual(
            self.collector.get_counter("requests_total", labels={"method": "GET"}),
            3,
        )

    def test_gauge_set(self):
        self.collector.set_gauge("cpu_usage", 75.0)
        self.assertEqual(self.collector.get_gauge("cpu_usage"), 75.0)

    def test_gauge_update(self):
        self.collector.set_gauge("memory", 100)
        self.collector.set_gauge("memory", 200)
        self.assertEqual(self.collector.get_gauge("memory"), 200)

    def test_histogram_observation(self):
        for v in [0.1, 0.2, 0.3, 0.4, 0.5]:
            self.collector.observe_histogram("latency", v)
        stats = self.collector.get_histogram_stats("latency")
        self.assertEqual(stats["count"], 5)
        self.assertAlmostEqual(stats["avg"], 0.3, places=2)

    def test_histogram_percentiles(self):
        for v in range(1, 101):
            self.collector.observe_histogram("lat", float(v))
        stats = self.collector.get_histogram_stats("lat")
        # p50 of [1..100] is the value at index int(100*50/100)=50, which is 51
        self.assertEqual(stats["p50"], 51.0)
        self.assertEqual(stats["p99"], 100.0)

    def test_time_operation(self):
        import time
        with self.collector.time_operation("operation_time"):
            time.sleep(0.01)
        stats = self.collector.get_histogram_stats("operation_time")
        self.assertEqual(stats["count"], 1)
        self.assertGreater(stats["max"], 0)

    def test_prometheus_output(self):
        self.collector.inc_counter("test_counter", value=5)
        self.collector.set_gauge("test_gauge", 42.0)
        output = self.collector.to_prometheus()
        self.assertIn("test_counter", output)
        self.assertIn("test_gauge", output)
        self.assertIn("# TYPE", output)

    def test_summary(self):
        self.collector.inc_counter("c1")
        self.collector.set_gauge("g1", 1.0)
        self.collector.observe_histogram("h1", 0.1)
        summary = self.collector.get_summary()
        self.assertEqual(summary["total_counters"], 1)
        self.assertEqual(summary["total_gauges"], 1)
        self.assertEqual(summary["total_histograms"], 1)


class TestMonitoringService(unittest.TestCase):
    """Test monitoring and alerting."""

    def setUp(self):
        from app.deployment.monitoring import (
            MonitoringService, AlertSeverity, AlertChannel,
        )
        self.monitoring = MonitoringService()
        self.AlertSeverity = AlertSeverity
        self.AlertChannel = AlertChannel

    def test_create_alert(self):
        alert = self.monitoring.create_alert(
            title="Test Alert",
            message="Test message",
            severity=self.AlertSeverity.WARNING,
            source="test-component",
        )
        self.assertIsNotNone(alert.id)
        self.assertFalse(alert.is_resolved)

    def test_active_alerts(self):
        self.monitoring.create_alert("A1", "M", self.AlertSeverity.INFO, "s1")
        self.monitoring.create_alert("A2", "M", self.AlertSeverity.ERROR, "s2")
        active = self.monitoring.get_active_alerts()
        self.assertEqual(len(active), 2)

    def test_filtered_active_alerts(self):
        self.monitoring.create_alert("A1", "M", self.AlertSeverity.INFO, "s1")
        self.monitoring.create_alert("A2", "M", self.AlertSeverity.CRITICAL, "s2")
        critical = self.monitoring.get_active_alerts(severity=self.AlertSeverity.CRITICAL)
        self.assertEqual(len(critical), 1)

    def test_acknowledge_alert(self):
        alert = self.monitoring.create_alert("A", "M", self.AlertSeverity.INFO, "s")
        success = self.monitoring.acknowledge_alert(alert.id)
        self.assertTrue(success)
        self.assertIsNotNone(alert.acknowledged_at)

    def test_resolve_alert(self):
        alert = self.monitoring.create_alert("A", "M", self.AlertSeverity.INFO, "s")
        success = self.monitoring.resolve_alert(alert.id)
        self.assertTrue(success)
        self.assertTrue(alert.is_resolved)
        active = self.monitoring.get_active_alerts()
        self.assertEqual(len(active), 0)

    def test_add_rule(self):
        rule = self.monitoring.add_rule(
            name="High CPU",
            metric_name="cpu_usage",
            threshold=80.0,
            comparison="gt",
            severity=self.AlertSeverity.WARNING,
        )
        self.assertIsNotNone(rule.id)

    def test_evaluate_rules_triggers_alert(self):
        self.monitoring.add_rule(
            name="High CPU",
            metric_name="cpu_usage",
            threshold=80.0,
            comparison="gt",
            severity=self.AlertSeverity.CRITICAL,
        )
        triggered = self.monitoring.evaluate_rules({"cpu_usage": 95.0})
        self.assertEqual(len(triggered), 1)
        self.assertEqual(triggered[0].severity, self.AlertSeverity.CRITICAL)

    def test_evaluate_rules_no_trigger(self):
        self.monitoring.add_rule(
            name="High CPU",
            metric_name="cpu_usage",
            threshold=80.0,
            comparison="gt",
            severity=self.AlertSeverity.WARNING,
        )
        triggered = self.monitoring.evaluate_rules({"cpu_usage": 50.0})
        self.assertEqual(len(triggered), 0)

    def test_remove_rule(self):
        rule = self.monitoring.add_rule(
            "R1", "metric1", 10, "gt", self.AlertSeverity.INFO
        )
        success = self.monitoring.remove_rule(rule.id)
        self.assertTrue(success)
        self.assertNotIn(rule.id, self.monitoring.rules)

    def test_alert_history(self):
        for i in range(5):
            self.monitoring.create_alert(f"A{i}", "M", self.AlertSeverity.INFO, "s")
        history = self.monitoring.get_alert_history(limit=3)
        self.assertEqual(len(history), 3)

    def test_statistics(self):
        self.monitoring.create_alert("A", "M", self.AlertSeverity.WARNING, "s")
        self.monitoring.add_rule("R", "m", 1, "gt", self.AlertSeverity.INFO)
        stats = self.monitoring.get_statistics()
        self.assertEqual(stats["total_alerts"], 1)
        self.assertEqual(stats["active_alerts"], 1)
        self.assertEqual(stats["active_rules"], 1)


class TestEvaluateRule(unittest.TestCase):
    """Test rule evaluation helper."""

    def test_gt_comparison(self):
        from app.deployment.monitoring import (
            AlertRule, AlertSeverity, AlertChannel, evaluate_rule,
        )
        rule = AlertRule(
            id="r1", name="R", metric_name="m", threshold=10,
            comparison="gt", severity=AlertSeverity.WARNING,
            channel=AlertChannel.EMAIL,
        )
        self.assertTrue(evaluate_rule(rule, 20))
        self.assertFalse(evaluate_rule(rule, 5))

    def test_lt_comparison(self):
        from app.deployment.monitoring import (
            AlertRule, AlertSeverity, AlertChannel, evaluate_rule,
        )
        rule = AlertRule(
            id="r1", name="R", metric_name="m", threshold=10,
            comparison="lt", severity=AlertSeverity.WARNING,
            channel=AlertChannel.EMAIL,
        )
        self.assertTrue(evaluate_rule(rule, 5))
        self.assertFalse(evaluate_rule(rule, 20))

    def test_inactive_rule(self):
        from app.deployment.monitoring import (
            AlertRule, AlertSeverity, AlertChannel, evaluate_rule,
        )
        rule = AlertRule(
            id="r1", name="R", metric_name="m", threshold=10,
            comparison="gt", severity=AlertSeverity.WARNING,
            channel=AlertChannel.EMAIL, is_active=False,
        )
        self.assertFalse(evaluate_rule(rule, 100))


if __name__ == "__main__":
    unittest.main(verbosity=2)
