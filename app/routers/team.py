"""
Team Router
===========

FastAPI router for team management operations.
Exposes MultiUserAPI team functions as HTTP endpoints.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.multi_user import MultiUserAPI, get_multi_user_api

logger = logging.getLogger("fbr_api.team")

router = APIRouter(prefix="/team", tags=["Team Management"])


# =============================================================================
# Request Models
# =============================================================================

class CreateTeamRequest(BaseModel):
    """Create a new team."""
    owner_id: str
    name: str = Field(..., min_length=1, max_length=200)
    organization_type: Optional[str] = None
    ntn: Optional[str] = None


class InviteUserRequest(BaseModel):
    """Invite a user to team."""
    team_id: str
    email: str = Field(..., description="Email of user to invite")
    role: str = Field(..., description="Role: admin, manager, accountant, viewer, guest")
    invited_by: str


class AcceptInvitationRequest(BaseModel):
    """Accept a team invitation."""
    invitation_id: str
    user_id: str


class RegisterUserRequest(BaseModel):
    """Register a new user."""
    email: str = Field(..., description="Email address")
    password: str = Field(..., min_length=8, description="Password (min 8 chars)")
    name: str = Field(..., min_length=1, description="Full name")
    role: str = Field(default="accountant", description="Role")
    ntn: Optional[str] = None
    cnic: Optional[str] = None
    organization: Optional[str] = None
    phone: Optional[str] = None


class LoginRequest(BaseModel):
    """User login."""
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    """Change password."""
    user_id: str
    old_password: str
    new_password: str = Field(..., min_length=8)


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/register")
async def register_user(request: RegisterUserRequest) -> dict:
    """
    Register a new user account.

    Creates a new user with email, password, and profile.
    """
    try:
        api = get_multi_user_api()

        from app.multi_user.models import UserRole
        try:
            role = UserRole(request.role)
        except ValueError:
            role = UserRole.ACCOUNTANT

        user = api.register_user(
            email=request.email,
            password=request.password,
            name=request.name,
            role=role,
            ntn=request.ntn,
            cnic=request.cnic,
            organization=request.organization,
            phone=request.phone,
        )

        return {
            "user_id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
            "created_at": user.created_at,
        }
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


@router.post("/login")
async def login(request: LoginRequest) -> dict:
    """
    Authenticate user and create session.

    Returns user profile and session token.
    """
    try:
        api = get_multi_user_api()
        result = api.login(request.email, request.password)

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error during login")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


@router.post("/logout")
async def logout(token: str) -> dict:
    """
    Logout and invalidate session.
    """
    try:
        api = get_multi_user_api()
        success = api.logout(token)
        return {"success": success}
    except Exception as e:
        logger.exception("Error during logout")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )


@router.post("/password/change")
async def change_password(request: ChangePasswordRequest) -> dict:
    """
    Change user password.
    """
    try:
        api = get_multi_user_api()
        success = api.change_password(
            request.user_id,
            request.old_password,
            request.new_password,
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid old password or user not found"
            )
        return {"success": True, "message": "Password changed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error changing password")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password"
        )


@router.post("/create")
async def create_team(request: CreateTeamRequest) -> dict:
    """
    Create a new team/organization.

    Teams allow multiple users to collaborate under one NTN.
    """
    try:
        api = get_multi_user_api()
        team = api.create_team(
            owner_id=request.owner_id,
            name=request.name,
            organization_type=request.organization_type,
            ntn=request.ntn,
        )
        return {
            "team_id": team.id,
            "name": team.name,
            "owner_id": team.owner_id,
            "ntn": team.ntn,
            "created_at": team.created_at,
        }
    except Exception as e:
        logger.exception("Error creating team")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create team"
        )


@router.post("/invite")
async def invite_user(request: InviteUserRequest) -> dict:
    """
    Invite a user to join a team.

    Sends invitation email (simulated) with team role assignment.
    """
    try:
        api = get_multi_user_api()

        from app.multi_user.models import UserRole
        try:
            role = UserRole(request.role)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role: {request.role}"
            )

        invitation = api.invite_user_to_team(
            team_id=request.team_id,
            email=request.email,
            role=role,
            invited_by=request.invited_by,
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
    except Exception as e:
        logger.exception("Error inviting user")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to invite user"
        )


@router.post("/invitation/accept")
async def accept_invitation(request: AcceptInvitationRequest) -> dict:
    """
    Accept a team invitation.
    """
    try:
        api = get_multi_user_api()
        success = api.accept_team_invitation(
            request.invitation_id,
            request.user_id,
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid invitation or already accepted"
            )
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error accepting invitation")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to accept invitation"
        )


@router.get("/dashboard/{team_id}")
async def get_team_dashboard(team_id: str) -> dict:
    """
    Get team dashboard with members and invitations.
    """
    try:
        api = get_multi_user_api()
        return api.get_team_dashboard(team_id)
    except Exception as e:
        logger.exception("Error getting team dashboard")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve team dashboard"
        )


@router.get("/user-dashboard/{user_id}")
async def get_user_dashboard(user_id: str) -> dict:
    """
    Get user dashboard across all teams.
    """
    try:
        api = get_multi_user_api()
        return api.get_user_dashboard(user_id)
    except Exception as e:
        logger.exception("Error getting user dashboard")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user dashboard"
        )


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
    except Exception as e:
        logger.exception("Error listing roles")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve roles"
        )
