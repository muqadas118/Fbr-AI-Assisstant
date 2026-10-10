"""
Team Router
===========

FastAPI router for team management operations.
Exposes MultiUserAPI team functions as HTTP endpoints.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from app.supabase_auth import require_user
from pydantic import BaseModel, EmailStr, Field

from app.common.rate_limit import RateLimiter
from app.multi_user import get_multi_user_api

logger = logging.getLogger("fbr_api.team")

router = APIRouter(prefix="/team", tags=["Team Management"])


# Brute-force protection on the credential endpoints — the same sliding-window
# primitive /auth/signup and /assistant/ask use. These routes are PUBLIC (a
# visitor has no token yet), so the limiter keys on the client host.
_register_limiter = RateLimiter.from_env(
    "TEAM_AUTH_RATE_LIMIT", default_limit=10, default_window=60.0
)
_login_limiter = RateLimiter.from_env(
    "TEAM_AUTH_RATE_LIMIT", default_limit=10, default_window=60.0
)


# =============================================================================
# Request Models
# =============================================================================

class CreateTeamRequest(BaseModel):
    """Create a new team."""
    owner_id: Optional[str] = Field(
        default=None,
        description="Must match the authenticated caller; falls back to it when omitted.",
    )
    name: str = Field(..., min_length=1, max_length=200)
    organization_type: Optional[str] = None
    ntn: Optional[str] = None


class InviteUserRequest(BaseModel):
    """Invite a user to team."""
    team_id: str = Field(..., min_length=1)
    email: EmailStr = Field(..., description="Email of user to invite")
    role: str = Field(..., description="Role: admin, manager, accountant, viewer, guest")
    invited_by: Optional[str] = Field(
        default=None,
        description="Must match the authenticated caller; falls back to it when omitted.",
    )


class AcceptInvitationRequest(BaseModel):
    """Accept a team invitation."""
    invitation_id: str = Field(..., min_length=1)
    user_id: Optional[str] = Field(
        default=None,
        description="Must match the authenticated caller; falls back to it when omitted.",
    )


class RegisterUserRequest(BaseModel):
    """Register a new user."""
    email: EmailStr = Field(..., description="Email address")
    password: str = Field(
        ..., min_length=8, max_length=128, description="Password (min 8 chars)"
    )
    name: str = Field(..., min_length=1, max_length=200, description="Full name")
    role: str = Field(default="accountant", description="Role")
    ntn: Optional[str] = None
    cnic: Optional[str] = None
    organization: Optional[str] = None
    phone: Optional[str] = None


class LoginRequest(BaseModel):
    """User login."""
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    """Change password."""
    user_id: Optional[str] = Field(
        default=None,
        description="Must match the authenticated caller; falls back to it when omitted.",
    )
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class LogoutRequest(BaseModel):
    """Logout and invalidate a session.

    A JSON body ({"token": ...}) is the contract the frontend uses; a lone
    scalar parameter would be bound as a query parameter by FastAPI and
    every call would fail with 422.
    """
    token: str = Field(..., min_length=1, max_length=4096)


# =============================================================================
# Authorization helpers
# =============================================================================

def _caller_id(user: Optional[dict] = Depends(require_user)) -> str:
    """Resolve the authenticated caller's user id.

    Mirrors app/routers/vault.py._user_id: a valid bearer token (Supabase JWT
    or first-party backend session) names the caller. When auth is disabled
    for local development (FBR_AUTH_REQUIRED=false, require_user returns
    None) the shared 'dev-user' scope keeps the endpoints usable.
    """
    if isinstance(user, dict):
        for key in ("id", "user_id", "sub"):
            if user.get(key):
                return str(user[key])
    return "dev-user"


def _authorized_id(claimed: Optional[str], caller_id: str) -> str:
    """Resolve a client-supplied owner id against the authenticated caller.

    The authenticated caller is the authority: an omitted id defaults to it,
    and a body naming a different user is rejected with 403 instead of
    silently acting on another account.
    """
    if claimed and str(claimed).strip() != caller_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to act on behalf of another user",
        )
    return caller_id


def _require_team_member(api, caller_id: str, team_id: str) -> None:
    """403 unless the caller is a member of the team it is reaching into.

    Membership lookups go through TeamManager (get_team / get_user_role) — the
    owner is always an ADMIN member, so both reads and writes are gated here.
    A 404 for an unknown team avoids leaking which team ids exist.
    """
    team = api.teams.get_team(team_id)
    if team is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )
    is_member = (
        team.owner_id == caller_id
        or api.teams.get_user_role(caller_id, team_id) is not None
    )
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this team",
        )


# =============================================================================
# Endpoints
# =============================================================================

# PUBLIC - intentionally no auth: user has no token yet
@router.post("/register")
async def register_user(request: Request, payload: RegisterUserRequest) -> dict:
    """
    Register a new user account.

    Creates a new user with email, password, and profile.
    """
    _register_limiter.check(request)
    try:
        api = get_multi_user_api()

        from app.multi_user.models import UserRole
        try:
            role = UserRole(payload.role)
        except ValueError:
            role = UserRole.ACCOUNTANT

        user = api.register_user(
            email=payload.email,
            password=payload.password,
            name=payload.name,
            role=role,
            ntn=payload.ntn,
            cnic=payload.cnic,
            organization=payload.organization,
            phone=payload.phone,
        )

        return {
            "user_id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
            "created_at": user.created_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error registering user")
        # Don't expose internal errors
        if "already exists" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register user"
        )


# PUBLIC - intentionally no auth: user has no token yet
@router.post("/login")
async def login(request: Request, payload: LoginRequest) -> dict:
    """
    Authenticate user and create session.

    Returns user profile and session token.
    """
    _login_limiter.check(request)
    try:
        api = get_multi_user_api()
        result = api.login(payload.email, payload.password)

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        # api.login() creates the session itself and returns it (with the
        # opaque token), so no session-registry lookup is needed here.
        session = result.get("session") or {}
        token = session.get("token") or ""
        if not token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Login failed: session could not be created.",
            )
        return {
            "user": result["user"],
            "token": token,
            "expires_at": session.get("expires_at"),
            "token_type": "bearer",
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error during login")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


@router.post("/logout", dependencies=[Depends(require_user)])
async def logout(payload: LogoutRequest) -> dict:
    """
    Logout and invalidate session.

    The token arrives as a JSON body ({"token": ...}) — a lone scalar would be
    bound as a query parameter by FastAPI, which the frontend never sends.
    """
    try:
        api = get_multi_user_api()
        success = api.logout(payload.token)
        return {"success": success}
    except Exception:
        logger.exception("Error during logout")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )


@router.post("/password/change", dependencies=[Depends(require_user)])
async def change_password(
    payload: ChangePasswordRequest,
    caller_id: str = Depends(_caller_id),
) -> dict:
    """
    Change user password.

    Only the authenticated caller may change their own password; the target
    user id comes from the token, not the body.
    """
    target_user_id = _authorized_id(payload.user_id, caller_id)
    try:
        api = get_multi_user_api()
        success = api.change_password(
            target_user_id,
            payload.old_password,
            payload.new_password,
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid old password or user not found"
            )
        return {"success": True, "message": "Password changed successfully"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error changing password")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password"
        )


@router.post("/create", dependencies=[Depends(require_user)])
async def create_team(
    payload: CreateTeamRequest,
    caller_id: str = Depends(_caller_id),
) -> dict:
    """
    Create a new team/organization.

    Teams allow multiple users to collaborate under one NTN.
    """
    try:
        api = get_multi_user_api()
        team = api.create_team(
            owner_id=_authorized_id(payload.owner_id, caller_id),
            name=payload.name,
            organization_type=payload.organization_type,
            ntn=payload.ntn,
        )
        return {
            "team_id": team.id,
            "name": team.name,
            "owner_id": team.owner_id,
            "ntn": team.ntn,
            "created_at": team.created_at,
        }
    except Exception:
        logger.exception("Error creating team")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create team"
        )


@router.post("/invite", dependencies=[Depends(require_user)])
async def invite_user(
    payload: InviteUserRequest,
    caller_id: str = Depends(_caller_id),
) -> dict:
    """
    Invite a user to join a team.

    Sends invitation email (simulated) with team role assignment. Requires
    the caller to own the team or be an existing member, and the invitation
    is always attributed to the authenticated caller.
    """
    try:
        api = get_multi_user_api()

        _require_team_member(api, caller_id, payload.team_id)
        invited_by = _authorized_id(payload.invited_by, caller_id)

        from app.multi_user.models import UserRole
        try:
            role = UserRole(payload.role)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role: {payload.role}"
            )

        invitation = api.invite_user_to_team(
            team_id=payload.team_id,
            email=payload.email,
            role=role,
            invited_by=invited_by,
        )

        return {
            "invitation_id": invitation.id,
            "email": invitation.email,
            "role": invitation.role.value,
            "status": invitation.status.value,
            "expires_at": invitation.expires_at,
        }
    except HTTPException:
        raise
    except PermissionError as e:
        # TeamManager.invite_to_team rejects a caller without manage_team.
        logger.warning("Invite to team %s rejected: %s", payload.team_id, e)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        # TeamManager.invite_to_team rejects a nonexistent team.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception:
        logger.exception("Error inviting user")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to invite user"
        )


@router.post("/invitation/accept", dependencies=[Depends(require_user)])
async def accept_invitation(
    payload: AcceptInvitationRequest,
    caller_id: str = Depends(_caller_id),
) -> dict:
    """
    Accept a team invitation.

    Only the authenticated caller may accept on their own behalf.
    """
    target_user_id = _authorized_id(payload.user_id, caller_id)
    try:
        api = get_multi_user_api()
        success = api.accept_team_invitation(
            payload.invitation_id,
            target_user_id,
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid invitation or already accepted"
            )
        return {"success": True}
    except HTTPException:
        raise
    except ValueError as e:
        # TeamManager.accept_invitation rejects an identity whose email does
        # not match the invited address (or that has no email on file).
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception:
        logger.exception("Error accepting invitation")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to accept invitation"
        )


@router.get("/dashboard/{team_id}", dependencies=[Depends(require_user)])
async def get_team_dashboard(
    team_id: str,
    caller_id: str = Depends(_caller_id),
) -> dict:
    """
    Get team dashboard with members and invitations.

    Restricted to the team's owner and its active members.
    """
    try:
        api = get_multi_user_api()
        _require_team_member(api, caller_id, team_id)
        return api.get_team_dashboard(team_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting team dashboard")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve team dashboard"
        )


@router.get("/user-dashboard/{user_id}", dependencies=[Depends(require_user)])
async def get_user_dashboard(user_id: str, caller_id: str = Depends(_caller_id)) -> dict:
    """
    Get user dashboard across all teams.

    A user can only read their own dashboard.
    """
    try:
        api = get_multi_user_api()
        target_user_id = _authorized_id(user_id, caller_id)
        return api.get_user_dashboard(target_user_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting user dashboard")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user dashboard"
        )


# PUBLIC - intentionally no auth: needed for signup UI
@router.get("/roles")
async def get_roles() -> dict:
    """
    List available team roles and their permissions.
    """
    try:
        from app.multi_user.team import ROLE_PERMISSIONS
        from app.multi_user.models import UserRole

        roles = {}
        for role in UserRole:
            perms = ROLE_PERMISSIONS.get(role, [])
            roles[role.value] = {
                "label": role.value.replace("_", " ").title(),
                "permissions": perms,
            }

        return {"roles": roles}
    except Exception:
        logger.exception("Error listing roles")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve roles"
        )
