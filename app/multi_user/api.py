"""
Multi-User API - Production-Grade
=================================

High-level API for user, auth, and team operations.
"""

import logging
from typing import Optional

from app.multi_user.models import (
    User, UserRole, UserProfile, UserSettings, Team, TeamMember,
    get_user_manager,
)
from app.multi_user.auth import (
    AuthManager, Session, hash_password, verify_password, get_auth_manager,
)
from app.multi_user.team import (
    TeamManager, TeamInvitation, get_team_manager,
)

logger = logging.getLogger("multi_user")


class MultiUserAPI:
    """Unified API for multi-user operations."""

    def __init__(self):
        self.users = get_user_manager()
        self.auth = get_auth_manager()
        self.teams = get_team_manager()

    # -------- User Registration / Login --------

    def register_user(
        self,
        email: str,
        password: str,
        name: str,
        role: UserRole = UserRole.ACCOUNTANT,
        ntn: Optional[str] = None,
        cnic: Optional[str] = None,
        organization: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> User:
        """Register a new user account."""
        pwd_hash = hash_password(password)
        return self.users.create_user(
            email=email,
            name=name,
            password_hash=pwd_hash,
            role=role,
            ntn=ntn,
            cnic=cnic,
            organization=organization,
            phone=phone,
        )

    def login(
        self,
        email: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Optional[dict]:
        """Authenticate a user and create a session."""
        user = self.users.get_user_by_email(email)
        if not user or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None

        session = self.auth.create_session(
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.users.record_login(user.id)

        return {
            "user": self._user_to_dict(user),
            "session": self._session_to_dict(session),
        }

    def logout(self, token: str) -> bool:
        """Logout a session."""
        session = self.auth.validate_token(token)
        if not session:
            return False
        return self.auth.revoke_session(session.id)

    def change_password(
        self,
        user_id: str,
        old_password: str,
        new_password: str,
    ) -> bool:
        """Change a user's password."""
        user = self.users.get_user(user_id)
        if not user:
            return False
        if not verify_password(old_password, user.password_hash):
            return False
        user.password_hash = hash_password(new_password)
        # Revoke all existing sessions on password change
        self.auth.revoke_all_sessions(user_id)
        return True

    # -------- User Profile / Settings --------

    def get_user_profile(self, user_id: str) -> Optional[dict]:
        """Get user with profile and settings."""
        user = self.users.get_user(user_id)
        if not user:
            return None
        profile = self.users.get_profile(user_id)
        settings = self.users.get_settings(user_id)
        return {
            "user": self._user_to_dict(user),
            "profile": self._profile_to_dict(profile) if profile else None,
            "settings": self._settings_to_dict(settings) if settings else None,
        }

    def update_profile(self, user_id: str, **updates) -> Optional[dict]:
        """Update user profile."""
        profile = self.users.update_profile(user_id, **updates)
        if not profile:
            return None
        return self._profile_to_dict(profile)

    def update_settings(self, user_id: str, **updates) -> Optional[dict]:
        """Update user settings."""
        settings = self.users.update_settings(user_id, **updates)
        if not settings:
            return None
        return self._settings_to_dict(settings)

    # -------- Team Management --------

    def create_team(
        self,
        owner_id: str,
        name: str,
        organization_type: Optional[str] = None,
        ntn: Optional[str] = None,
    ) -> Team:
        """Create a new team."""
        return self.teams.create_team(
            owner_id=owner_id,
            name=name,
            organization_type=organization_type,
            ntn=ntn,
        )

    def invite_user_to_team(
        self,
        team_id: str,
        email: str,
        role: UserRole,
        invited_by: str,
    ) -> TeamInvitation:
        """Invite a user to a team."""
        return self.teams.invite_to_team(
            team_id=team_id,
            email=email,
            role=role,
            invited_by=invited_by,
        )

    def accept_team_invitation(
        self,
        invitation_id: str,
        user_id: str,
    ) -> bool:
        """Accept a team invitation."""
        return self.teams.accept_invitation(invitation_id, user_id)

    def get_team_dashboard(self, team_id: str) -> dict:
        """Get team dashboard data."""
        team = self.teams.get_team(team_id)
        if not team:
            return {}
        members = self.teams.get_team_members(team_id)
        invitations = self.teams.get_pending_invitations(team_id)

        return {
            "team": self._team_to_dict(team),
            "member_count": len(members),
            "members": [self._member_to_dict(m) for m in members],
            "pending_invitations": len(invitations),
            "invitations": [self._invitation_to_dict(i) for i in invitations],
        }

    def get_user_workspaces(self, user_id: str) -> list[dict]:
        """Workspaces (teams) for a user, tolerant of unregistered identities.

        Unlike get_user_dashboard (which gates on a user row), this works for
        any identity that owns/holds teams — e.g. demo ids created through
        POST /workspaces/create without a prior /team/register.
        """
        return [self._team_to_dict(t) for t in self.teams.get_user_teams(user_id)]

    def get_user_dashboard(self, user_id: str) -> dict:
        """Get user dashboard across teams."""
        user = self.users.get_user(user_id)
        if not user:
            return {}

        teams = self.teams.get_user_teams(user_id)
        sessions = self.auth.list_sessions(user_id)
        invitations = self.teams.get_user_invitations(user.email)

        return {
            "user": self._user_to_dict(user),
            "team_count": len(teams),
            "teams": [self._team_to_dict(t) for t in teams],
            "active_sessions": len(sessions),
            "pending_invitations": [
                self._invitation_to_dict(i) for i in invitations
            ],
        }

    def get_statistics(self) -> dict:
        """Get overall system statistics."""
        return {
            "users": self.users.get_statistics(),
            "auth": self.auth.get_statistics(),
            "teams": self.teams.get_statistics(),
        }

    # -------- Helpers --------

    def _user_to_dict(self, user: User) -> dict:
        return {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "ntn": user.ntn,
            "organization": user.organization,
            "created_at": user.created_at,
            "last_login_at": user.last_login_at,
        }

    def _profile_to_dict(self, profile: UserProfile) -> dict:
        return {
            "user_id": profile.user_id,
            "bio": profile.bio,
            "address": profile.address,
            "city": profile.city,
            "province": profile.province,
            "languages": profile.languages,
        }

    def _settings_to_dict(self, settings: UserSettings) -> dict:
        return {
            "user_id": settings.user_id,
            "language": settings.language,
            "timezone": settings.timezone,
            "currency": settings.currency,
            "date_format": settings.date_format,
            "theme": settings.theme,
            "email_notifications": settings.email_notifications,
            "sms_notifications": settings.sms_notifications,
            "push_notifications": settings.push_notifications,
        }

    def _team_to_dict(self, team: Team) -> dict:
        return {
            "id": team.id,
            "name": team.name,
            "owner_id": team.owner_id,
            "organization_type": team.organization_type,
            "ntn": team.ntn,
            "plan": team.plan,
            "is_active": team.is_active,
            "member_count": team.member_count,
            "created_at": team.created_at,
        }

    def _member_to_dict(self, member: TeamMember) -> dict:
        return {
            "id": member.id,
            "team_id": member.team_id,
            "user_id": member.user_id,
            "role": member.role.value,
            "joined_at": member.joined_at,
            "is_active": member.is_active,
        }

    def _session_to_dict(self, session: Session) -> dict:
        return {
            "id": session.id,
            "user_id": session.user_id,
            "created_at": session.created_at,
            "expires_at": session.expires_at,
            "ip_address": session.ip_address,
        }

    def _invitation_to_dict(self, invitation: TeamInvitation) -> dict:
        return {
            "id": invitation.id,
            "team_id": invitation.team_id,
            "email": invitation.email,
            "role": invitation.role.value,
            "status": invitation.status.value,
            "invited_at": invitation.invited_at,
            "expires_at": invitation.expires_at,
        }


# Singleton
_api: Optional[MultiUserAPI] = None


def get_multi_user_api() -> MultiUserAPI:
    """Get singleton multi-user API."""
    global _api
    if _api is None:
        _api = MultiUserAPI()
    return _api
