"""
User Models - Production-Grade
==============================

User, profile, settings, team, and audit log models.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger("multi_user")


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
            self.created_at = datetime.utcnow().isoformat()
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


class UserManager:
    """Manages users, profiles, and settings."""

    def __init__(self):
        self.users: dict[str, User] = {}
        self.profiles: dict[str, UserProfile] = {}
        self.settings: dict[str, UserSettings] = {}
        self.email_index: dict[str, str] = {}  # email -> user_id
        self.audit_log: list[AuditLogEntry] = []

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
        if email in self.email_index:
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
        user = self.users.get(user_id)
        if not user:
            return None

        for key, value in updates.items():
            if hasattr(user, key) and key not in ("id", "email"):
                setattr(user, key, value)

        self._log_action(user_id, "user.updated", "user", user_id)
        return user

    def delete_user(self, user_id: str) -> bool:
        """Delete (deactivate) a user."""
        user = self.users.get(user_id)
        if not user:
            return False

        user.is_active = False
        self._log_action(user_id, "user.deleted", "user", user_id)
        return True

    def record_login(self, user_id: str) -> None:
        """Record a successful login."""
        user = self.users.get(user_id)
        if user:
            user.last_login_at = datetime.utcnow().isoformat()
            self._log_action(user_id, "user.login", "session", None)

    def get_profile(self, user_id: str) -> Optional[UserProfile]:
        """Get user profile."""
        return self.profiles.get(user_id)

    def update_profile(self, user_id: str, **updates) -> Optional[UserProfile]:
        """Update user profile."""
        profile = self.profiles.get(user_id)
        if not profile:
            profile = UserProfile(user_id=user_id)
            self.profiles[user_id] = profile

        for key, value in updates.items():
            if hasattr(profile, key):
                setattr(profile, key, value)

        self._log_action(user_id, "profile.updated", "user_profile", user_id)
        return profile

    def get_settings(self, user_id: str) -> Optional[UserSettings]:
        """Get user settings."""
        return self.settings.get(user_id)

    def update_settings(self, user_id: str, **updates) -> Optional[UserSettings]:
        """Update user settings."""
        settings = self.settings.get(user_id)
        if not settings:
            settings = UserSettings(user_id=user_id)
            self.settings[user_id] = settings

        for key, value in updates.items():
            if hasattr(settings, key):
                setattr(settings, key, value)

        self._log_action(user_id, "settings.updated", "user_settings", user_id)
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
            timestamp=datetime.utcnow().isoformat(),
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
