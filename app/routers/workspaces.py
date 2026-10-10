"""
Workspaces Router
=================

FastAPI router for workspace management.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from app.supabase_auth import require_user
from pydantic import BaseModel, Field

from app.multi_user import get_multi_user_api

logger = logging.getLogger("fbr_api.workspaces")

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])

WORKSPACE_TYPES = ("personal", "business")


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
    silently creating/reading data under another account.
    """
    if claimed and str(claimed).strip() != caller_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to act on behalf of another user",
        )
    return caller_id


# =============================================================================
# Request Models
# =============================================================================

class WorkspaceCreateRequest(BaseModel):
    """Create a workspace."""
    user_id: Optional[str] = Field(
        default=None,
        description="Must match the authenticated caller; falls back to it when omitted.",
    )
    name: str = Field(..., min_length=1, max_length=200, description="Workspace name")
    workspace_type: str = Field(
        default="personal",
        description="Type: personal or business"
    )
    ntn: Optional[str] = Field(default=None, description="NTN for business workspaces")
    description: Optional[str] = None


class WorkspaceUpdateRequest(BaseModel):
    """Update workspace."""
    workspace_id: str
    name: Optional[str] = None
    description: Optional[str] = None


class WorkspaceSwitchRequest(BaseModel):
    """Switch active workspace."""
    user_id: str
    workspace_id: str


# =============================================================================
# Endpoints
# =============================================================================

# PUBLIC - intentionally no auth: healthcheck like /health
@router.get("/health")
async def get_workspaces_health() -> dict:
    """
    Health check for workspaces API.
    """
    return {
        "status": "ok",
        "service": "workspaces",
        "version": "1.0.0",
    }


@router.get("/{user_id}", dependencies=[Depends(require_user)])
async def get_workspaces(user_id: str, caller_id: str = Depends(_caller_id)) -> dict:
    """
    Get all workspaces for a user.

    Returns personal and business workspaces. A user can only list their own.
    """
    target_user_id = _authorized_id(user_id, caller_id)
    try:
        api = get_multi_user_api()
        # Tolerant lookup: works for identities that own teams even when no
        # user row exists (e.g. demo ids provisioned via POST /workspaces/create).
        return {
            "user_id": target_user_id,
            "workspaces": api.get_user_workspaces(target_user_id),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting workspaces")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve workspaces"
        )


@router.post("/create", dependencies=[Depends(require_user)])
async def create_workspace(
    request: WorkspaceCreateRequest,
    caller_id: str = Depends(_caller_id),
) -> dict:
    """
    Create a new workspace.

    Personal workspaces are individual filing workspaces.
    Business workspaces are team/organization workspaces.
    """
    try:
        workspace_type = (request.workspace_type or "personal").strip().lower()
        if workspace_type not in WORKSPACE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"workspace_type must be one of: {', '.join(WORKSPACE_TYPES)}",
            )
        if workspace_type == "business" and not request.ntn:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="ntn is required for business workspaces",
            )

        # The owner comes from the token, never from the body.
        owner_id = _authorized_id(request.user_id, caller_id)
        api = get_multi_user_api()

        # For personal workspaces, use the user's personal team
        # For business, create a team
        if workspace_type == "business":
            team = api.create_team(
                owner_id=owner_id,
                name=request.name,
                ntn=request.ntn,
            )
            return {
                "workspace_id": team.id,
                "name": team.name,
                "type": "business",
                "ntn": team.ntn,
                "created_at": team.created_at,
            }
        else:
            # Personal workspace is per-user, create a minimal team
            team = api.create_team(
                owner_id=owner_id,
                name=f"{request.name} - Personal",
                ntn=None,
            )
            return {
                "workspace_id": team.id,
                "name": team.name,
                "type": "personal",
                "created_at": team.created_at,
            }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error creating workspace")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create workspace"
        )
