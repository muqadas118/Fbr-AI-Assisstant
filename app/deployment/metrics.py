"""
Metrics Collection - Production-Grade
=====================================

Prometheus-compatible metrics for monitoring application performance.
"""

import logging
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger("deployment")


class MetricType(str, Enum):
    """Type of metric."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricPoint:
    """A single metric data point."""
    name: str
    value: float
    labels: dict = field(default_factory=dict)
    timestamp: str = ""


class MetricsCollector:
    """
    Thread-safe in-memory metrics collector.

    Provides counter, gauge, and histogram metrics.
    Prometheus-compatible output format.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._histogram_buckets: dict[str, list[float]] = {}
        self._timings: dict[str, list[float]] = defaultdict(list)
        self._start_time = time.time()
        # Default histogram buckets (latency in seconds)
        self._default_buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]

    # -------- Counter --------
    def inc_counter(self, name: str, value: float = 1.0, labels: Optional[dict] = None) -> None:
        """Increment a counter metric."""
        key = self._make_key(name, labels or {})
        with self._lock:
            self._counters[key] += value

    def get_counter(self, name: str, labels: Optional[dict] = None) -> float:
        key = self._make_key(name, labels or {})
        with self._lock:
            return self._counters.get(key, 0.0)

    # -------- Gauge --------
    def set_gauge(self, name: str, value: float, labels: Optional[dict] = None) -> None:
        """Set a gauge metric value."""
        key = self._make_key(name, labels or {})
        with self._lock:
            self._gauges[key] = value

    def get_gauge(self, name: str, labels: Optional[dict] = None) -> Optional[float]:
        key = self._make_key(name, labels or {})
        with self._lock:
            return self._gauges.get(key)

    # -------- Histogram --------
    def observe_histogram(self, name: str, value: float, labels: Optional[dict] = None) -> None:
        """Record an observation in a histogram."""
        key = self._make_key(name, labels or {})
        with self._lock:
            self._histograms[key].append(value)

    def get_histogram_stats(self, name: str, labels: Optional[dict] = None) -> dict:
        """Get histogram statistics."""
        key = self._make_key(name, labels or {})
        with self._lock:
            values = self._histograms.get(key, [])
            if not values:
                return {"count": 0, "sum": 0, "min": 0, "max": 0, "avg": 0}
            return {
                "count": len(values),
                "sum": sum(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
                "p50": self._percentile(values, 50),
                "p95": self._percentile(values, 95),
                "p99": self._percentile(values, 99),
            }

    # -------- Timing helper --------
    def time_operation(self, name: str, labels: Optional[dict] = None):
        """Context manager to time an operation."""
        return _TimedOperation(self, name, labels)

    # -------- Aggregation --------
    def aggregate_by_label(self, metric_name: str, label_key: str) -> dict:
        """Aggregate counter values by a specific label."""
        with self._lock:
            results = {}
            prefix = f"{metric_name}#{{"
            for key, value in self._counters.items():
                if key.startswith(prefix):
                    # Extract labels
                    label_part = key[len(prefix):-1]
                    label_value = ""
                    search = f'"{label_key}":"'
                    idx = label_part.find(search)
                    if idx >= 0:
                        start = idx + len(search)
                        end = label_part.find('"', start)
                        label_value = label_part[start:end]
                    results[label_value] = results.get(label_value, 0) + value
            return results

    # -------- Prometheus output --------
    def to_prometheus(self) -> str:
        """Export all metrics in Prometheus text format."""
        lines = []
        ts = datetime.utcnow().isoformat() + "Z"

        with self._lock:
            # Counters
            for key, value in self._counters.items():
                name, labels_str = self._parse_key(key)
                lines.append(f"# TYPE {name} counter")
                lines.append(f"# HELP {name} counter metric")
                lines.append(f"{name}{labels_str} {value} {ts}")

            # Gauges
            for key, value in self._gauges.items():
                name, labels_str = self._parse_key(key)
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"# HELP {name} gauge metric")
                lines.append(f"{name}{labels_str} {value} {ts}")

            # Histograms
            for key, values in self._histograms.items():
                if not values:
                    continue
                name, labels_str = self._parse_key(key)
                lines.append(f"# TYPE {name} histogram")
                lines.append(f"# HELP {name} histogram metric")
                total = sum(values)
                count = len(values)
                lines.append(f"{name}_sum{labels_str} {total} {ts}")
                lines.append(f"{name}_count{labels_str} {count} {ts}")
                buckets = self._histogram_buckets.get(key, self._default_buckets)
                for bucket in buckets:
                    bucket_count = sum(1 for v in values if v <= bucket)
                    b_labels = labels_str[:-1] + f',le="{bucket}"]'
                    lines.append(f"{name}_bucket{b_labels} {bucket_count} {ts}")
                lines.append(f"{name}_bucket{labels_str[:-1]},le=\"+Inf\"] {count} {ts}")

        return "\n".join(lines) + "\n"

    def get_all_metrics(self) -> dict:
        """Get all metrics as a dictionary."""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {
                    k: {"count": len(v), "sum": sum(v)}
                    for k, v in self._histograms.items()
                    if v
                },
                "uptime_seconds": time.time() - self._start_time,
            }

    def get_summary(self) -> dict:
        """Get a summary of all metrics."""
        with self._lock:
            return {
                "total_counters": len(self._counters),
                "total_gauges": len(self._gauges),
                "total_histograms": len(self._histograms),
                "uptime_seconds": round(time.time() - self._start_time, 2),
            }

    # -------- Helpers --------
    @staticmethod
    def _make_key(name: str, labels: dict) -> str:
        if not labels:
            return name
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}#{{{label_str}}}"

    @staticmethod
    def _parse_key(key: str) -> tuple[str, str]:
        if "#{" not in key:
            return key, "{}"
        name, labels_part = key.split("#{", 1)
        labels_str = "{" + labels_part
        return name, labels_str

    @staticmethod
    def _percentile(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        idx = int(len(sorted_vals) * p / 100)
        idx = min(idx, len(sorted_vals) - 1)
        return sorted_vals[idx]


class _TimedOperation:
    """Context manager for timing operations."""

    def __init__(self, collector: MetricsCollector, name: str, labels: Optional[dict]):
        self.collector = collector
        self.name = name
        self.labels = labels or {}
        self.start_time: float = 0

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, *args):
        duration = time.time() - self.start_time
        self.collector.observe_histogram(self.name, duration, self.labels)


# Singleton
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get singleton metrics collector."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
