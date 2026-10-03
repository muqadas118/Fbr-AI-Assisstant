"""
Vault Router
============

Persistent per-user document storage for the Tax Vault page.
All endpoints require auth (Supabase JWT or internal PBKDF2 session) and
scope every operation to the authenticated user — one user can never read
or mutate another user's documents.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.supabase_auth import require_user
from app.vault_store import get_vault_store

logger = logging.getLogger("fbr_api.vault")

router = APIRouter(prefix="/vault", tags=["Vault"])

ALLOWED_TYPES = {
    "Tax Return",
    "WHT Certificate",
    "Sales Tax Return",
    "Form 16A",
    "Salary Certificate",
    "Bank Statement",
    "Contract",
    "Invoice",
    "Other",
}

MAX_CONTENT_CHARS = 100_000
MAX_FILENAME_CHARS = 200


# =============================================================================
# Request Models
# =============================================================================

class VaultDocumentCreate(BaseModel):
    """Create a vault document."""
    filename: str = Field(..., min_length=1, max_length=MAX_FILENAME_CHARS)
    doc_type: str = Field(default="Other", max_length=50)
    content: str = Field(default="", max_length=MAX_CONTENT_CHARS)
    secure: bool = True


class VaultDocumentUpdate(BaseModel):
    """Update a vault document."""
    filename: Optional[str] = Field(default=None, min_length=1, max_length=MAX_FILENAME_CHARS)
    doc_type: Optional[str] = Field(default=None, max_length=50)
    content: Optional[str] = Field(default=None, max_length=MAX_CONTENT_CHARS)


# =============================================================================
# Helpers
# =============================================================================

def _user_id(user=Depends(require_user)) -> str:
    """Resolve the authenticated user id.

    With Supabase auth the JWT 'sub' claim scopes the vault. When auth is
    disabled for local development (FBR_AUTH_REQUIRED=false, require_user
    returns None) everything lands in one shared 'dev-user' scope so the
    page still works end-to-end before Supabase keys are configured.
    """
    if isinstance(user, dict):
        for key in ("id", "user_id", "sub"):
            if user.get(key):
                return str(user[key])
    return "dev-user"


def _validate_doc_type(doc_type: str) -> str:
    if doc_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid doc_type '{doc_type}'. Allowed: {sorted(ALLOWED_TYPES)}",
        )
    return doc_type


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/health")
async def vault_health() -> dict:
    """Health check (public, like the other routers' /health)."""
    return {"status": "ok", "service": "vault", "version": "1.0.0"}


@router.get("/documents", dependencies=[Depends(require_user)])
async def list_documents(user_id: str = Depends(_user_id)) -> dict:
    """List all vault documents for the authenticated user."""
    store = get_vault_store()
    docs = store.list_documents(user_id)
    return {"user_id": user_id, "documents": docs, "count": len(docs)}


@router.post("/documents", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_user)])
async def create_document(payload: VaultDocumentCreate, user_id: str = Depends(_user_id)) -> dict:
    """Add a document to the vault."""
    _validate_doc_type(payload.doc_type)
    store = get_vault_store()
    doc = store.add_document(
        user_id=user_id,
        filename=payload.filename.strip(),
        doc_type=payload.doc_type,
        content=payload.content,
        secure=payload.secure,
    )
    return doc


@router.get("/documents/{doc_id}", dependencies=[Depends(require_user)])
async def get_document(doc_id: str, user_id: str = Depends(_user_id)) -> dict:
    """Fetch one vault document (with content)."""
    doc = get_vault_store().get_document(doc_id, user_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc


@router.patch("/documents/{doc_id}", dependencies=[Depends(require_user)])
async def update_document(doc_id: str, payload: VaultDocumentUpdate, user_id: str = Depends(_user_id)) -> dict:
    """Rename / retype / edit content of a vault document."""
    if payload.doc_type is not None:
        _validate_doc_type(payload.doc_type)
    doc = get_vault_store().update_document(
        doc_id,
        user_id,
        filename=payload.filename.strip() if payload.filename else None,
        doc_type=payload.doc_type,
        content=payload.content,
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc


@router.delete("/documents/{doc_id}", dependencies=[Depends(require_user)])
async def delete_document(doc_id: str, user_id: str = Depends(_user_id)) -> dict:
    """Delete a vault document."""
    deleted = get_vault_store().delete_document(doc_id, user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return {"deleted": True, "id": doc_id}
