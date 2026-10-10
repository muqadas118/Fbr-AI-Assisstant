"""
User Models - Production-Grade
==============================

User, profile, settings, team, and audit log models.
"""

import json
import logging
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger("multi_user")


def _utcnow() -> datetime:
    """Timezone-aware UTC now (datetime.utcnow is deprecated in 3.12+)."""
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 timestamp; naive values are treated as UTC."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


class UserRole(str, Enum):
    """User roles."""
    ADMIN = "admin"  # Full access
    MANAGER = "manager"  # Can manage team members
    ACCOUNTANT = "accountant"  # Can file returns, manage invoices
    VIEWER = "viewer"  # Read-only access
    GUEST = "guest"  # Limited access


@dataclass
class User:
    """A user account."""
    id: str
    email: str
    name: str
    role: UserRole
    password_hash: str
    is_active: bool = True
    is_verified: bool = False
    ntn: Optional[str] = None
    cnic: Optional[str] = None
    organization: Optional[str] = None
    phone: Optional[str] = None
    # Workspace allocated at signup onboarding ("personal" | "business").
    # None until the questionnaire completes; get_effective_workspace falls
    # back to "personal" so pre-onboarding rows need no data migration.
    # Verify the onboarding contract in tests/test_workspace_allocation.py.
    preferred_workspace: Optional[str] = None
    created_at: str = ""
    last_login_at: Optional[str] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = _utcnow().isoformat()
        if isinstance(self.role, str):
            self.role = UserRole(self.role)


@dataclass
class UserProfile:
    """Extended user profile information."""
    user_id: str
    bio: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None
    tax_consultant: bool = False
    languages: list[str] = field(default_factory=lambda: ["en", "ur"])
    avatar_url: Optional[str] = None


@dataclass
class UserSettings:
    """User preferences and settings."""
    user_id: str
    language: str = "en"
    timezone: str = "Asia/Karachi"
    currency: str = "PKR"
    date_format: str = "DD/MM/YYYY"
    theme: str = "light"
    email_notifications: bool = True
    sms_notifications: bool = False
    push_notifications: bool = True
    dashboard_layout: dict = field(default_factory=dict)


@dataclass
class Team:
    """A team of users (e.g., accounting firm, company)."""
    id: str
    name: str
    owner_id: str
    organization_type: Optional[str] = None
    ntn: Optional[str] = None
    plan: str = "free"  # free, pro, enterprise
    is_active: bool = True
    member_count: int = 1
    created_at: str = ""


@dataclass
class TeamMember:
    """A user's membership in a team."""
    id: str
    team_id: str
    user_id: str
    role: UserRole
    invited_by: Optional[str] = None
    joined_at: str = ""
    is_active: bool = True


@dataclass
class AuditLogEntry:
    """An audit log entry."""
    id: str
    user_id: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: dict = field(default_factory=dict)
    ip_address: Optional[str] = None
    timestamp: str = ""


def _default_store_path() -> Path:
    """On-disk home for the auth store (survives backend restarts).

    Overridable via FBR_AUTH_STORE. Defaults to <repo>/data/auth_users.json
    which is git-ignored, so accounts persist across uvicorn restarts instead
    of vanishing (the old in-memory store made 'account created but login
    fails' after every restart).
    """
    override = os.environ.get("FBR_AUTH_STORE", "").strip()
    if override:
        return Path(override)
    # app/multi_user/models.py -> repo root is parents[2]
    return Path(__file__).resolve().parents[2] / "data" / "auth_users.json"


class UserManager:
    """Manages users, profiles, and settings (JSON-persisted)."""

    def __init__(self, store_path: Optional[Path] = None):
        self.users: dict[str, User] = {}
        self.profiles: dict[str, UserProfile] = {}
        self.settings: dict[str, UserSettings] = {}
        self.email_index: dict[str, str] = {}  # email -> user_id
        self.audit_log: list[AuditLogEntry] = []
        self.store_path: Path = store_path or _default_store_path()
        self._lock = threading.Lock()
        self._load()

    # -------- Persistence --------

    def _load(self) -> None:
        """Hydrate the store from disk; tolerate missing/corrupt files."""
        with self._lock:
            self._load_locked()

    def _load_locked(self) -> None:
        try:
            if not self.store_path.exists():
                return
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Auth store load failed (%s): %s", self.store_path, exc)
            return

        for u in raw.get("users", []):
            try:
                user = User(
                    id=u["id"],
                    email=u["email"],
                    name=u.get("name", ""),
                    role=UserRole(u.get("role", UserRole.ACCOUNTANT.value)),
                    password_hash=u.get("password_hash", ""),
                    is_active=u.get("is_active", True),
                    is_verified=u.get("is_verified", False),
                    ntn=u.get("ntn"),
                    cnic=u.get("cnic"),
                    organization=u.get("organization"),
                    phone=u.get("phone"),
                    preferred_workspace=u.get("preferred_workspace"),
                    created_at=u.get("created_at", ""),
                    last_login_at=u.get("last_login_at"),
                )
            except (KeyError, TypeError, ValueError):
                continue
            self.users[user.id] = user
            self.email_index[user.email.lower()] = user.id

        for p in raw.get("profiles", []):
            profile = UserProfile(user_id=p["user_id"])
            for k, v in p.items():
                if k != "user_id" and hasattr(profile, k):
                    setattr(profile, k, v)
            self.profiles[profile.user_id] = profile

        for s in raw.get("settings", []):
            setting = UserSettings(user_id=s["user_id"])
            for k, v in s.items():
                if k != "user_id" and hasattr(setting, k):
                    setattr(setting, k, v)
            self.settings[setting.user_id] = setting

        logger.info("Auth store loaded %d users from %s", len(self.users), self.store_path)

    def _save(self) -> None:
        """Flush the whole store to disk (atomic-ish via tmp + replace)."""
        with self._lock:
            self._save_locked()

    def _save_locked(self) -> None:
        payload = {
            "users": [
                {**asdict(u), "role": u.role.value}
                for u in self.users.values()
            ],
            "profiles": [asdict(p) for p in self.profiles.values()],
            "settings": [asdict(s) for s in self.settings.values()],
        }
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.store_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            os.replace(tmp, self.store_path)
        except OSError as exc:
            logger.error("Auth store save failed (%s): %s", self.store_path, exc)

    def create_user(
        self,
        email: str,
        name: str,
        password_hash: str,
        role: UserRole = UserRole.ACCOUNTANT,
        ntn: Optional[str] = None,
        cnic: Optional[str] = None,
        organization: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> User:
        """Create a new user."""
        with self._lock:
            if email.lower() in self.email_index:
                raise ValueError(f"User with email {email} already exists")

            user = User(
                id=str(uuid.uuid4()),
                email=email.lower(),
                name=name,
                role=role,
                password_hash=password_hash,
                ntn=ntn,
                cnic=cnic,
                organization=organization,
                phone=phone,
            )
            self.users[user.id] = user
            self.email_index[user.email] = user.id

            # Create default profile and settings
            self.profiles[user.id] = UserProfile(user_id=user.id)
            self.settings[user.id] = UserSettings(user_id=user.id)

            self._log_action(user.id, "user.created", "user", user.id)
            self._save_locked()
            logger.info(f"User created: {email} ({role.value})")
            return user

    def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        return self.users.get(user_id)

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        user_id = self.email_index.get(email.lower())
        if user_id:
            return self.users.get(user_id)
        return None

    def update_user(self, user_id: str, **updates) -> Optional[User]:
        """Update user fields."""
        with self._lock:
            user = self.users.get(user_id)
            if not user:
                return None

            for key, value in updates.items():
                if hasattr(user, key) and key not in ("id", "email"):
                    setattr(user, key, value)

            self._log_action(user_id, "user.updated", "user", user_id)
            self._save_locked()
            return user

    def delete_user(self, user_id: str) -> bool:
        """Delete (deactivate) a user."""
        with self._lock:
            user = self.users.get(user_id)
            if not user:
                return False

            user.is_active = False
            self._log_action(user_id, "user.deleted", "user", user_id)
            self._save_locked()
            return True

    def record_login(self, user_id: str) -> None:
        """Record a successful login."""
        with self._lock:
            user = self.users.get(user_id)
            if user:
                user.last_login_at = _utcnow().isoformat()
                self._log_action(user_id, "user.login", "session", None)
                self._save_locked()

    def get_profile(self, user_id: str) -> Optional[UserProfile]:
        """Get user profile."""
        return self.profiles.get(user_id)

    def update_profile(self, user_id: str, **updates) -> Optional[UserProfile]:
        """Update user profile."""
        with self._lock:
            profile = self.profiles.get(user_id)
            if not profile:
                profile = UserProfile(user_id=user_id)
                self.profiles[user_id] = profile

            for key, value in updates.items():
                if hasattr(profile, key):
                    setattr(profile, key, value)

            self._log_action(user_id, "profile.updated", "user_profile", user_id)
            self._save_locked()
            return profile

    def get_settings(self, user_id: str) -> Optional[UserSettings]:
        """Get user settings."""
        return self.settings.get(user_id)

    def update_settings(self, user_id: str, **updates) -> Optional[UserSettings]:
        """Update user settings."""
        with self._lock:
            settings = self.settings.get(user_id)
            if not settings:
                settings = UserSettings(user_id=user_id)
                self.settings[user_id] = settings

            for key, value in updates.items():
                if hasattr(settings, key):
                    setattr(settings, key, value)

            self._log_action(user_id, "settings.updated", "user_settings", user_id)
            self._save_locked()
            return settings

    def list_users(
        self,
        role: Optional[UserRole] = None,
        active_only: bool = True,
    ) -> list[User]:
        """List users with optional filters."""
        users = list(self.users.values())
        if role:
            users = [u for u in users if u.role == role]
        if active_only:
            users = [u for u in users if u.is_active]
        return users

    def get_statistics(self) -> dict:
        """Get user statistics."""
        users = list(self.users.values())
        active = [u for u in users if u.is_active]
        verified = [u for u in users if u.is_verified]
        by_role = {}
        for u in users:
            by_role[u.role.value] = by_role.get(u.role.value, 0) + 1

        return {
            "total_users": len(users),
            "active_users": len(active),
            "verified_users": len(verified),
            "by_role": by_role,
        }

    def _log_action(
        self,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        """Add an audit log entry."""
        entry = AuditLogEntry(
            id=str(uuid.uuid4()),
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            timestamp=_utcnow().isoformat(),
        )
        self.audit_log.append(entry)


# Singleton
_user_manager: Optional[UserManager] = None


def get_user_manager() -> UserManager:
    """Get singleton user manager."""
    global _user_manager
    if _user_manager is None:
        _user_manager = UserManager()
    return _user_manager
