"""
Team Management - Production-Grade
==================================

Team creation, membership management, invitations, and permissions.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from app.multi_user.models import (
    Team, TeamMember, UserRole, get_user_manager,
)

logger = logging.getLogger("multi_user")


class InvitationStatus(str, Enum):
    """Status of a team invitation."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


@dataclass
class TeamInvitation:
    """An invitation to join a team."""
    id: str
    team_id: str
    email: str
    role: UserRole
    invited_by: str
    invited_at: str
    expires_at: str
    status: InvitationStatus = InvitationStatus.PENDING
    accepted_at: Optional[str] = None


# Permission matrix: what each role can do
ROLE_PERMISSIONS = {
    UserRole.ADMIN: {
        "manage_team", "manage_billing", "view_audit",
        "file_returns", "manage_invoices", "view_reports",
        "manage_settings", "delete_team",
    },
    UserRole.MANAGER: {
        "manage_team", "view_audit", "file_returns",
        "manage_invoices", "view_reports", "manage_settings",
    },
    UserRole.ACCOUNTANT: {
        "file_returns", "manage_invoices", "view_reports",
    },
    UserRole.VIEWER: {
        "view_reports",
    },
    UserRole.GUEST: {
        # Limited to what's explicitly shared with them
    },
}


def has_permission(role: UserRole, permission: str) -> bool:
    """Check if a role has a specific permission."""
    return permission in ROLE_PERMISSIONS.get(role, set())


class TeamManager:
    """Manages teams, memberships, and invitations."""

    def __init__(self):
        self.teams: dict[str, Team] = {}
        self.memberships: dict[str, TeamMember] = {}  # member_id
        self.invitations: dict[str, TeamInvitation] = {}
        # Indexes
        self.team_members_index: dict[str, list[str]] = {}  # team_id -> [member_id]
        self.user_teams_index: dict[str, list[str]] = {}  # user_id -> [team_id]

    def create_team(
        self,
        owner_id: str,
        name: str,
        organization_type: Optional[str] = None,
        ntn: Optional[str] = None,
    ) -> Team:
        """Create a new team and add owner as ADMIN."""
        team = Team(
            id=str(uuid.uuid4()),
            name=name,
            owner_id=owner_id,
            organization_type=organization_type,
            ntn=ntn,
            created_at=datetime.utcnow().isoformat(),
        )
        self.teams[team.id] = team

        # Add owner as first member
        self.add_member(team.id, owner_id, UserRole.ADMIN, invited_by=None)

        logger.info(f"Team created: {name} (owner: {owner_id})")
        return team

    def get_team(self, team_id: str) -> Optional[Team]:
        """Get a team by ID."""
        return self.teams.get(team_id)

    def update_team(self, team_id: str, **updates) -> Optional[Team]:
        """Update team fields."""
        team = self.teams.get(team_id)
        if not team:
            return None
        for key, value in updates.items():
            if hasattr(team, key) and key not in ("id", "owner_id"):
                setattr(team, key, value)
        return team

    def delete_team(self, team_id: str) -> bool:
        """Delete a team and all its memberships."""
        if team_id not in self.teams:
            return False
        del self.teams[team_id]
        # Remove all memberships
        member_ids = self.team_members_index.pop(team_id, [])
        for mid in member_ids:
            self.memberships.pop(mid, None)
        # Remove from user index
        for uid, tids in list(self.user_teams_index.items()):
            self.user_teams_index[uid] = [t for t in tids if t != team_id]
        return True

    def add_member(
        self,
        team_id: str,
        user_id: str,
        role: UserRole,
        invited_by: Optional[str],
    ) -> TeamMember:
        """Add a member to a team."""
        # Check if already a member
        existing = self._find_membership(team_id, user_id)
        if existing:
            existing.role = role
            existing.is_active = True
            return existing

        member = TeamMember(
            id=str(uuid.uuid4()),
            team_id=team_id,
            user_id=user_id,
            role=role,
            invited_by=invited_by,
            joined_at=datetime.utcnow().isoformat(),
        )
        self.memberships[member.id] = member

        # Update indexes
        if team_id not in self.team_members_index:
            self.team_members_index[team_id] = []
        self.team_members_index[team_id].append(member.id)

        if user_id not in self.user_teams_index:
            self.user_teams_index[user_id] = []
        self.user_teams_index[user_id].append(team_id)

        # Update team member count
        team = self.teams.get(team_id)
        if team:
            team.member_count = len(self.team_members_index[team_id])

        logger.info(f"User {user_id} added to team {team_id} as {role.value}")
        return member

    def remove_member(self, team_id: str, user_id: str) -> bool:
        """Remove a member from a team."""
        membership = self._find_membership(team_id, user_id)
        if not membership:
            return False

        # Cannot remove the owner
        team = self.teams.get(team_id)
        if team and team.owner_id == user_id:
            raise ValueError("Cannot remove team owner")

        membership.is_active = False

        # Update indexes
        if team_id in self.team_members_index:
            self.team_members_index[team_id] = [
                m for m in self.team_members_index[team_id]
                if m != membership.id
            ]
        if user_id in self.user_teams_index:
            self.user_teams_index[user_id] = [
                t for t in self.user_teams_index[user_id]
                if t != team_id
            ]

        # Update team member count
        if team:
            team.member_count = len(self.team_members_index.get(team_id, []))

        return True

    def update_member_role(
        self,
        team_id: str,
        user_id: str,
        new_role: UserRole,
    ) -> Optional[TeamMember]:
        """Update a member's role in a team."""
        membership = self._find_membership(team_id, user_id)
        if not membership:
            return None

        # Cannot change owner's role
        team = self.teams.get(team_id)
        if team and team.owner_id == user_id:
            raise ValueError("Cannot change team owner's role")

        membership.role = new_role
        return membership

    def get_member(self, team_id: str, user_id: str) -> Optional[TeamMember]:
        """Get a member's membership record."""
        return self._find_membership(team_id, user_id)

    def get_team_members(self, team_id: str) -> list[TeamMember]:
        """Get all active members of a team."""
        member_ids = self.team_members_index.get(team_id, [])
        return [
            m for m in (self.memberships.get(mid) for mid in member_ids)
            if m and m.is_active
        ]

    def get_user_teams(self, user_id: str) -> list[Team]:
        """Get all teams a user belongs to."""
        team_ids = self.user_teams_index.get(user_id, [])
        return [t for t in (self.teams.get(tid) for tid in team_ids) if t]

    def get_user_role(self, user_id: str, team_id: str) -> Optional[UserRole]:
        """Get a user's role in a team."""
        membership = self._find_membership(team_id, user_id)
        if membership and membership.is_active:
            return membership.role
        return None

    def invite_to_team(
        self,
        team_id: str,
        email: str,
        role: UserRole,
        invited_by: str,
        expires_in_days: int = 7,
    ) -> TeamInvitation:
        """Create an invitation to join a team."""
        now = datetime.utcnow()
        from datetime import timedelta
        expires = now + timedelta(days=expires_in_days)

        invitation = TeamInvitation(
            id=str(uuid.uuid4()),
            team_id=team_id,
            email=email.lower(),
            role=role,
            invited_by=invited_by,
            invited_at=now.isoformat(),
            expires_at=expires.isoformat(),
        )
        self.invitations[invitation.id] = invitation
        logger.info(f"Invitation sent to {email} for team {team_id}")
        return invitation

    def accept_invitation(self, invitation_id: str, user_id: str) -> bool:
        """Accept an invitation and add user to team."""
        invitation = self.invitations.get(invitation_id)
        if not invitation:
            return False

        if invitation.status != InvitationStatus.PENDING:
            return False

        now = datetime.utcnow()
        if datetime.fromisoformat(invitation.expires_at) < now:
            invitation.status = InvitationStatus.EXPIRED
            return False

        invitation.status = InvitationStatus.ACCEPTED
        invitation.accepted_at = now.isoformat()

        # Add user to team
        self.add_member(
            invitation.team_id,
            user_id,
            invitation.role,
            invited_by=invitation.invited_by,
        )
        return True

    def decline_invitation(self, invitation_id: str) -> bool:
        """Decline an invitation."""
        invitation = self.invitations.get(invitation_id)
        if not invitation or invitation.status != InvitationStatus.PENDING:
            return False
        invitation.status = InvitationStatus.DECLINED
        return True

    def get_pending_invitations(self, team_id: str) -> list[TeamInvitation]:
        """Get all pending invitations for a team."""
        return [
            i for i in self.invitations.values()
            if i.team_id == team_id and i.status == InvitationStatus.PENDING
        ]

    def get_user_invitations(self, email: str) -> list[TeamInvitation]:
        """Get all pending invitations for an email."""
        return [
            i for i in self.invitations.values()
            if i.email == email.lower() and i.status == InvitationStatus.PENDING
        ]

    def _find_membership(self, team_id: str, user_id: str) -> Optional[TeamMember]:
        """Find membership record for a user in a team."""
        for member in self.memberships.values():
            if member.team_id == team_id and member.user_id == user_id:
                return member
        return None

    def check_permission(
        self,
        user_id: str,
        team_id: str,
        permission: str,
    ) -> bool:
        """Check if a user has a specific permission in a team."""
        role = self.get_user_role(user_id, team_id)
        if not role:
            return False
        return has_permission(role, permission)

    def get_statistics(self) -> dict:
        """Get team statistics."""
        return {
            "total_teams": len(self.teams),
            "total_memberships": len(self.memberships),
            "active_memberships": sum(1 for m in self.memberships.values() if m.is_active),
            "pending_invitations": sum(
                1 for i in self.invitations.values()
                if i.status == InvitationStatus.PENDING
            ),
        }


# Singleton
_team_manager: Optional[TeamManager] = None


def get_team_manager() -> TeamManager:
    """Get singleton team manager."""
    global _team_manager
    if _team_manager is None:
        _team_manager = TeamManager()
    return _team_manager
