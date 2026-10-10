"""
Team Management - Production-Grade
==================================

Team creation, membership management, invitations, and permissions.
"""

import json
import logging
import os
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from app.multi_user.models import (
    Team, TeamMember, UserRole, get_user_manager,
)

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


def _default_team_store_path() -> Path:
    """On-disk home for the team store (survives backend restarts).

    Overridable via FBR_TEAM_STORE. Defaults to <repo>/data/auth_teams.json
    which is git-ignored, exactly like UserManager's data/auth_users.json, so
    teams/memberships/invitations no longer vanish on uvicorn restarts.
    """
    override = os.environ.get("FBR_TEAM_STORE", "").strip()
    if override:
        return Path(override)
    # app/multi_user/team.py -> repo root is parents[2]
    return Path(__file__).resolve().parents[2] / "data" / "auth_teams.json"


class TeamManager:
    """Manages teams, memberships, and invitations (JSON-persisted)."""

    def __init__(self, store_path: Optional[Path] = None):
        self.teams: dict[str, Team] = {}
        self.memberships: dict[str, TeamMember] = {}  # member_id
        self.invitations: dict[str, TeamInvitation] = {}
        # Indexes
        self.team_members_index: dict[str, list[str]] = {}  # team_id -> [member_id]
        self.user_teams_index: dict[str, list[str]] = {}  # user_id -> [team_id]
        self.store_path: Path = store_path or _default_team_store_path()
        # Reentrant: public mutators nest (create_team -> add_member,
        # accept_invitation -> add_member), so a plain Lock would deadlock.
        self._lock = threading.RLock()
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
            logger.warning("Team store load failed (%s): %s", self.store_path, exc)
            return

        for t in raw.get("teams", []):
            try:
                team = Team(
                    id=t["id"],
                    name=t.get("name", ""),
                    owner_id=t.get("owner_id", ""),
                    organization_type=t.get("organization_type"),
                    ntn=t.get("ntn"),
                    plan=t.get("plan", "free"),
                    is_active=t.get("is_active", True),
                    member_count=t.get("member_count", 1),
                    created_at=t.get("created_at", ""),
                )
            except (KeyError, TypeError, ValueError):
                continue
            self.teams[team.id] = team

        for m in raw.get("memberships", []):
            try:
                member = TeamMember(
                    id=m["id"],
                    team_id=m.get("team_id", ""),
                    user_id=m.get("user_id", ""),
                    role=UserRole(m.get("role", UserRole.ACCOUNTANT.value)),
                    invited_by=m.get("invited_by"),
                    joined_at=m.get("joined_at", ""),
                    is_active=m.get("is_active", True),
                )
            except (KeyError, TypeError, ValueError):
                continue
            self.memberships[member.id] = member
            self.team_members_index.setdefault(member.team_id, []).append(member.id)
            self.user_teams_index.setdefault(member.user_id, []).append(member.team_id)

        for i in raw.get("invitations", []):
            try:
                invitation = TeamInvitation(
                    id=i["id"],
                    team_id=i.get("team_id", ""),
                    email=i.get("email", ""),
                    role=UserRole(i.get("role", UserRole.ACCOUNTANT.value)),
                    invited_by=i.get("invited_by", ""),
                    invited_at=i.get("invited_at", ""),
                    expires_at=i["expires_at"],
                    status=InvitationStatus(
                        i.get("status", InvitationStatus.PENDING.value)
                    ),
                    accepted_at=i.get("accepted_at"),
                )
            except (KeyError, TypeError, ValueError):
                continue
            self.invitations[invitation.id] = invitation

        logger.info(
            "Team store loaded %d teams from %s", len(self.teams), self.store_path
        )

    def _save(self) -> None:
        """Flush the store to disk (atomic-ish via tmp + replace)."""
        with self._lock:
            self._save_locked()

    def _save_locked(self) -> None:
        payload = {
            "teams": [asdict(t) for t in self.teams.values()],
            "memberships": [
                {**asdict(m), "role": m.role.value}
                for m in self.memberships.values()
            ],
            "invitations": [
                {**asdict(i), "role": i.role.value, "status": i.status.value}
                for i in self.invitations.values()
            ],
        }
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.store_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            os.replace(tmp, self.store_path)
        except OSError as exc:
            logger.error("Team store save failed (%s): %s", self.store_path, exc)

    def create_team(
        self,
        owner_id: str,
        name: str,
        organization_type: Optional[str] = None,
        ntn: Optional[str] = None,
    ) -> Team:
        """Create a new team and add owner as ADMIN."""
        with self._lock:
            team = Team(
                id=str(uuid.uuid4()),
                name=name,
                owner_id=owner_id,
                organization_type=organization_type,
                ntn=ntn,
                created_at=_utcnow().isoformat(),
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
        with self._lock:
            team = self.teams.get(team_id)
            if not team:
                return None
            for key, value in updates.items():
                if hasattr(team, key) and key not in ("id", "owner_id"):
                    setattr(team, key, value)
            self._save_locked()
            return team

    def delete_team(self, team_id: str) -> bool:
        """Delete a team and all its memberships."""
        with self._lock:
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
            # Drop this team's invitations
            for inv_id in [
                i for i, inv in self.invitations.items() if inv.team_id == team_id
            ]:
                self.invitations.pop(inv_id, None)
            self._save_locked()
            return True

    def add_member(
        self,
        team_id: str,
        user_id: str,
        role: UserRole,
        invited_by: Optional[str],
    ) -> TeamMember:
        """Add a member to a team."""
        with self._lock:
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
                joined_at=_utcnow().isoformat(),
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
            self._save_locked()
            return member

    def remove_member(self, team_id: str, user_id: str) -> bool:
        """Remove a member from a team."""
        with self._lock:
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

            self._save_locked()
            return True

    def update_member_role(
        self,
        team_id: str,
        user_id: str,
        new_role: UserRole,
    ) -> Optional[TeamMember]:
        """Update a member's role in a team."""
        with self._lock:
            membership = self._find_membership(team_id, user_id)
            if not membership:
                return None

            # Cannot change owner's role
            team = self.teams.get(team_id)
            if team and team.owner_id == user_id:
                raise ValueError("Cannot change team owner's role")

            membership.role = new_role
            self._save_locked()
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
        """Create an invitation to join a team.

        The team must exist and the inviter must hold `manage_team` on it.
        """
        with self._lock:
            if team_id not in self.teams:
                raise ValueError(f"Team {team_id} not found")
            if not self.check_permission(invited_by, team_id, "manage_team"):
                raise PermissionError(
                    f"User {invited_by} is not allowed to invite members to team {team_id}"
                )

            now = _utcnow()
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
            self._save_locked()
            logger.info(f"Invitation sent to {email} for team {team_id}")
            return invitation

    def accept_invitation(
        self,
        invitation_id: str,
        user_id: str,
        email: Optional[str] = None,
    ) -> bool:
        """Accept an invitation and add user to team.

        The accepting identity must be the invited address: `email` is
        compared case-insensitively against the invitation, and when it is
        omitted it is resolved from the accepting user's account.
        """
        with self._lock:
            invitation = self.invitations.get(invitation_id)
            if not invitation:
                return False

            if invitation.status != InvitationStatus.PENDING:
                return False

            if email is None:
                user = get_user_manager().get_user(user_id)
                email = user.email if user else None
            if email is None:
                raise ValueError(
                    "Cannot accept an invitation: no email on file to verify "
                    "the invited address"
                )
            if email.strip().lower() != invitation.email:
                raise ValueError(
                    "Invitation email does not match the invited address"
                )

            now = _utcnow()
            if _parse_iso(invitation.expires_at) < now:
                invitation.status = InvitationStatus.EXPIRED
                self._save_locked()
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
            self._save_locked()
            return True

    def decline_invitation(self, invitation_id: str) -> bool:
        """Decline an invitation."""
        with self._lock:
            invitation = self.invitations.get(invitation_id)
            if not invitation or invitation.status != InvitationStatus.PENDING:
                return False
            invitation.status = InvitationStatus.DECLINED
            self._save_locked()
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
        """Find membership record for a user in a team (indexed lookup)."""
        for member_id in self.team_members_index.get(team_id, []):
            member = self.memberships.get(member_id)
            if member and member.user_id == user_id:
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
