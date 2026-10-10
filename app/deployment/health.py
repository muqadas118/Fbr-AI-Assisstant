"""
Health Checks - Production-Grade
================================

Liveness, readiness, and component health monitoring.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable

logger = logging.getLogger("deployment")


class HealthStatus(str, Enum):
    """Health status of a component."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health information for a single component."""
    name: str
    status: HealthStatus
    message: str = ""
    latency_ms: float = 0.0
    metadata: dict = field(default_factory=dict)
    last_checked: str = ""


@dataclass
class HealthCheckResult:
    """Overall health check result."""
    status: HealthStatus
    version: str
    environment: str
    uptime_seconds: float
    timestamp: str
    components: list[ComponentHealth] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "version": self.version,
            "environment": self.environment,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "timestamp": self.timestamp,
            "components": {
                c.name: {
                    "status": c.status.value,
                    "message": c.message,
                    "latency_ms": round(c.latency_ms, 2),
                    "metadata": c.metadata,
                    "last_checked": c.last_checked,
                }
                for c in self.components
            },
            "details": self.details,
        }


class HealthChecker:
    """
    Coordinates health checks for all application components.
    """

    def __init__(self, version: str = "1.0.0", environment: str = "development"):
        self.version = version
        self.environment = environment
        self.start_time = time.time()
        self.checks: dict[str, Callable] = {}
        self.last_results: dict[str, ComponentHealth] = {}

    def register_check(self, name: str, check_fn: Callable[[], ComponentHealth]) -> None:
        """Register a custom health check function."""
        self.checks[name] = check_fn
        logger.info(f"Health check registered: {name}")

    def run_check(self, name: str) -> ComponentHealth:
        """Run a single health check by name."""
        check_fn = self.checks.get(name)
        if not check_fn:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNKNOWN,
                message=f"No health check registered for '{name}'",
            )

        start = time.time()
        try:
            result = check_fn()
            result.latency_ms = (time.time() - start) * 1000
            if not result.last_checked:
                result.last_checked = datetime.utcnow().isoformat()
            self.last_results[name] = result
            return result
        except Exception as e:
            logger.exception(f"Health check {name} failed")
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Check raised exception: {str(e)}",
                latency_ms=(time.time() - start) * 1000,
                last_checked=datetime.utcnow().isoformat(),
            )

    def run_all_checks(self) -> HealthCheckResult:
        """Run all registered health checks."""
        # Built-in checks
        self._register_builtin_checks()

        components = []
        for name in self.checks:
            components.append(self.run_check(name))

        # Aggregate overall status
        statuses = [c.status for c in components]
        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            overall = HealthStatus.UNHEALTHY
        elif any(s == HealthStatus.DEGRADED for s in statuses):
            overall = HealthStatus.DEGRADED
        elif all(s == HealthStatus.HEALTHY for s in statuses):
            overall = HealthStatus.HEALTHY
        else:
            overall = HealthStatus.UNKNOWN

        return HealthCheckResult(
            status=overall,
            version=self.version,
            environment=self.environment,
            uptime_seconds=time.time() - self.start_time,
            timestamp=datetime.utcnow().isoformat(),
            components=components,
        )

    def _register_builtin_checks(self) -> None:
        """Register built-in health checks."""
        if "system" not in self.checks:
            self.checks["system"] = self._check_system

    @staticmethod
    def _check_system() -> ComponentHealth:
        """Check system resource usage."""
        try:
            import psutil  # type: ignore
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            status = HealthStatus.HEALTHY
            if cpu > 90 or mem.percent > 90:
                status = HealthStatus.DEGRADED
            return ComponentHealth(
                name="system",
                status=status,
                message="System resources OK",
                metadata={
                    "cpu_percent": cpu,
                    "memory_percent": mem.percent,
                },
                last_checked=datetime.utcnow().isoformat(),
            )
        except ImportError:
            return ComponentHealth(
                name="system",
                status=HealthStatus.HEALTHY,
                message="psutil not available, basic check only",
                last_checked=datetime.utcnow().isoformat(),
            )

    def liveness(self) -> dict:
        """Liveness probe - is the process alive?"""
        return {
            "status": "alive",
            "uptime_seconds": round(time.time() - self.start_time, 2),
            "timestamp": datetime.utcnow().isoformat(),
        }

    def readiness(self) -> dict:
        """Readiness probe - is the app ready to serve traffic?"""
        result = self.run_all_checks()
        ready = result.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)
        return {
            "ready": ready,
            "status": result.status.value,
            "timestamp": result.timestamp,
        }


# Singleton
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get singleton health checker."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker
