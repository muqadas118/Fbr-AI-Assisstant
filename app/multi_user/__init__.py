"""
Multi-User Foundation - Production-Grade
=========================================

User management, authentication, roles, permissions, and team management.
"""

from app.multi_user.models import (
    User, UserRole, UserProfile, UserSettings,
    Team, TeamMember, AuditLogEntry,
    get_user_manager,
)
from app.multi_user.auth import (
    AuthManager, Session, get_auth_manager,
    hash_password, verify_password,
)
from app.multi_user.team import (
    TeamManager, get_team_manager, has_permission,
    TeamInvitation, InvitationStatus, ROLE_PERMISSIONS,
)
from app.multi_user.api import (
    MultiUserAPI, get_multi_user_api,
)

__all__ = [
    # Models
    "User",
    "UserRole",
    "UserProfile",
    "UserSettings",
    "Team",
    "TeamMember",
    "AuditLogEntry",
    "get_user_manager",
    # Auth
    "AuthManager",
    "Session",
    "get_auth_manager",
    "hash_password",
    "verify_password",
    # Team
    "TeamManager",
    "get_team_manager",
    "has_permission",
    "TeamInvitation",
    "InvitationStatus",
    "ROLE_PERMISSIONS",
    # API
    "MultiUserAPI",
    "get_multi_user_api",
]
