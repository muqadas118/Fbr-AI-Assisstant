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

from app.multi_user import MultiUserAPI, get_multi_user_api

logger = logging.getLogger("fbr_api.workspaces")

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


# =============================================================================
# Request Models
# =============================================================================

class WorkspaceCreateRequest(BaseModel):
    """Create a workspace."""
    user_id: str
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
async def get_workspaces(user_id: str) -> dict:
    """
    Get all workspaces for a user.

    Returns personal and business workspaces.
    """
    try:
        api = get_multi_user_api()
        # Tolerant lookup: works for identities that own teams even when no
        # user row exists (e.g. demo ids provisioned via POST /workspaces/create).
        return {
            "user_id": user_id,
            "workspaces": api.get_user_workspaces(user_id),
        }
    except Exception as e:
        logger.exception("Error getting workspaces")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve workspaces"
        )


@router.post("/create", dependencies=[Depends(require_user)])
async def create_workspace(request: WorkspaceCreateRequest) -> dict:
    """
    Create a new workspace.

    Personal workspaces are individual filing workspaces.
    Business workspaces are team/organization workspaces.
    """
    try:
        api = get_multi_user_api()

        # For personal workspaces, use the user's personal team
        # For business, create a team
        if request.workspace_type == "business":
            team = api.create_team(
                owner_id=request.user_id,
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
                owner_id=request.user_id,
                name=f"{request.name} - Personal",
                ntn=None,
            )
            return {
                "workspace_id": team.id,
                "name": team.name,
                "type": "personal",
                "created_at": team.created_at,
            }
    except Exception as e:
        logger.exception("Error creating workspace")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create workspace"
        )
