"""
Supabase Auth — JWT Validation for FastAPI
==========================================

Validates Supabase JWT tokens from the Authorization: Bearer header.
Uses the JWT secret to verify tokens locally (no network call to Supabase).

Usage:
    from app.supabase_auth import get_current_user

    @app.get("/api/auth/me")
    async def me(user: dict = Depends(get_current_user)):
        return user
"""

import os
import logging
from typing import Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger("supabase_auth")

# ─── Config ───────────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "").strip()
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "").strip()
SUPABASE_JWT_ALGORITHM = "HS256"

# Supabase issues access tokens with a fixed audience claim. It is NOT the anon
# key — validating against the anon key rejects every genuine login.
SUPABASE_JWT_AUDIENCE = "authenticated"


def _is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY and SUPABASE_JWT_SECRET)


def auth_required() -> bool:
    """Whether protected endpoints must carry a valid bearer token.

    Defaults to True. Set FBR_AUTH_REQUIRED=false only for local development,
    before the frontend login flow exists. Read at call time (not import time)
    so tests and dev servers can flip it without reimporting the module.
    """
    return os.environ.get("FBR_AUTH_REQUIRED", "true").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _jwt_claims(token: str) -> dict:
    """Decode and verify a Supabase JWT. Raises HTTPException on failure."""
    if not _is_configured():
        raise HTTPException(
            status_code=503,
            detail="Supabase is not configured. Set SUPABASE_URL, SUPABASE_ANON_KEY, and SUPABASE_JWT_SECRET.",
        )
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=[SUPABASE_JWT_ALGORITHM],
            audience=SUPABASE_JWT_AUDIENCE,
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


def _user_from_payload(payload: dict) -> dict:
    """Map Supabase JWT claims onto the user dict the app uses."""
    # Supabase puts user metadata under "user_metadata"
    meta = payload.get("user_metadata") or {}
    return {
        "id": payload.get("sub", ""),
        "email": payload.get("email", ""),
        "full_name": meta.get("full_name") or meta.get("name", ""),
        "avatar_url": meta.get("avatar_url", ""),
        "role": payload.get("role", "authenticated"),
        # Include raw token info for logging/debugging
        "iss": payload.get("iss", ""),
        "exp": payload.get("exp", 0),
    }


# ─── FastAPI Dependencies ─────────────────────────────────────────────────────

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """
    Extract and validate the Supabase JWT from the Authorization header.

    Returns a user dict:
        {
            "id": "<uuid>",
            "email": "user@example.com",
            "full_name": "Hamza Ahmed",
            "role": "authenticated"
        }

    Raises HTTPException 401 if missing or invalid.
    Raises HTTPException 503 if Supabase is not configured.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header. Expected: Bearer <token>",
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header. Expected: Bearer <token>",
        )

    return _user_from_payload(_jwt_claims(credentials.credentials))


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    """
    Like get_current_user but returns None instead of raising when unauthenticated.
    Use for endpoints that work both with and without auth.
    """
    if credentials is None or not credentials.credentials:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


async def require_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    """Guard for cost-bearing endpoints.

    Enforces a valid bearer token when FBR_AUTH_REQUIRED is on (the default).
    When explicitly disabled for local development it returns None and logs a
    warning, so the fail-open state is visible in the logs and on /health rather
    than being silent.
    """
    if not auth_required():
        logger.warning(
            "FBR_AUTH_REQUIRED=false — request served WITHOUT authentication. "
            "Do not run this way on a reachable network."
        )
        return None
    return await get_current_user(credentials)


# ─── Helpers for frontend use ─────────────────────────────────────────────────

def get_supabase_config() -> dict:
    """Return sanitized config for the frontend (safe to expose)."""
    return {
        "url": SUPABASE_URL,
        "anon_key": SUPABASE_ANON_KEY,
        "configured": _is_configured(),
    }
