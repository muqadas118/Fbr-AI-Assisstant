"""
Application Configuration - Production-Grade
=============================================

Environment-aware settings, logging configuration, and secrets management.
"""

import logging
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("deployment")


class Environment(str, Enum):
    """Application environment."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class LogLevel(str, Enum):
    """Logging level."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class Settings:
    """
    Application settings loaded from environment variables.

    Supports .env files via python-dotenv (optional).
    """
    # App
    app_name: str = "FBR AI Tax Assistant"
    app_version: str = "1.0.0"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    log_level: LogLevel = LogLevel.INFO

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    cors_origins: list[str] = field(default_factory=lambda: ["*"])

    # Security
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    bcrypt_rounds: int = 12

    # Database
    database_url: str = "sqlite:///./fbr_assistant.db"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Cache / Redis
    redis_url: Optional[str] = None
    cache_ttl_seconds: int = 300

    # Storage
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 25

    # Rate limiting
    rate_limit_per_minute: int = 60
    rate_limit_burst: int = 100

    # External APIs
    fbr_api_base_url: str = "https://gw.fbr.gov.pk"
    fbr_api_timeout: int = 30
    fbr_api_key: Optional[str] = None

    # Email
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: str = "noreply@fbr-assistant.pk"

    # SMS
    sms_provider: Optional[str] = None
    sms_api_key: Optional[str] = None

    # Monitoring
    enable_metrics: bool = True
    enable_tracing: bool = False
    sentry_dsn: Optional[str] = None

    # Feature flags
    enable_ai_features: bool = True
    enable_pdf_processing: bool = True
    enable_ocr: bool = True
    enable_notifications: bool = True

    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    def validate(self) -> list[str]:
        """Validate configuration, return list of issues."""
        issues = []
        if self.is_production():
            if self.secret_key == "change-me-in-production":
                issues.append("SECRET_KEY must be changed in production")
            if not self.database_url.startswith(("postgresql://", "mysql://")):
                issues.append("Production should use PostgreSQL or MySQL")
        return issues


# Singleton settings
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get application settings (singleton)."""
    global _settings
    if _settings is None:
        _settings = _load_settings()
    return _settings


def _load_settings() -> Settings:
    """Load settings from environment variables."""
    env_str = os.getenv("APP_ENV", "development").lower()
    try:
        env = Environment(env_str)
    except ValueError:
        env = Environment.DEVELOPMENT

    log_str = os.getenv("LOG_LEVEL", "INFO").upper()
    try:
        log_level = LogLevel(log_str)
    except ValueError:
        log_level = LogLevel.INFO

    return Settings(
        app_name=os.getenv("APP_NAME", "FBR AI Tax Assistant"),
        app_version=os.getenv("APP_VERSION", "1.0.0"),
        environment=env,
        debug=os.getenv("DEBUG", "false").lower() == "true",
        log_level=log_level,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        workers=int(os.getenv("WORKERS", "1")),
        cors_origins=os.getenv("CORS_ORIGINS", "*").split(","),
        secret_key=os.getenv("SECRET_KEY", "change-me-in-production"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./fbr_assistant.db"),
        redis_url=os.getenv("REDIS_URL"),
        enable_metrics=os.getenv("ENABLE_METRICS", "true").lower() == "true",
        sentry_dsn=os.getenv("SENTRY_DSN"),
        fbr_api_key=os.getenv("FBR_API_KEY"),
    )


def configure_logging(
    level: LogLevel = LogLevel.INFO,
    json_format: bool = False,
) -> None:
    """Configure application logging."""
    log_format = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    logging.basicConfig(
        level=level.value,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logger.info(f"Logging configured: level={level.value}")
