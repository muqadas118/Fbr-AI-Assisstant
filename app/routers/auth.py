"""
Auth Router — first-party signup / login / session endpoints
============================================================

Backs the frontend sign-up and sign-in flows directly against the
backend's own identity system (PBKDF2 password hashing + opaque session
tokens from app.multi_user). No external auth provider required.

Endpoints (all public — the caller has no token yet, except /me):
    POST /auth/signup   {email, password, name?, profile_type?, org_name?}
                                                     -> user + session token
    POST /auth/login    {email, password}            -> user + session token
    POST /auth/logout   (Bearer token)               -> invalidate session
    GET  /auth/me       (Bearer token)               -> current user
    POST /auth/refresh  (Bearer token)               -> new token, same user
    POST /auth/workspace (Bearer token)              -> allocate primary workspace

Tokens are opaque strings stored in the AuthManager's session registry.
Clients send them as `Authorization: Bearer <token>`; require_user
accepts them (see app.supabase_auth._user_from_session_token).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field

from app.common.rate_limit import RateLimiter
from app.multi_user import get_multi_user_api
from app.supabase_auth import get_current_user, require_user

logger = logging.getLogger("fbr_api.auth")

router = APIRouter(prefix="/auth", tags=["Auth"])

security = HTTPBearer(auto_error=False)

# Brute-force protection on the credential endpoints. Scoped per-token
# (hash) or per-client-host — the same primitive the LLM endpoints use.
_signup_limiter = RateLimiter.from_env("AUTH_SIGNUP_RATE_LIMIT", default_limit=10, default_window=300.0)
_login_limiter = RateLimiter.from_env("AUTH_LOGIN_RATE_LIMIT", default_limit=15, default_window=300.0)

# NOTE: signup/login/logout are intentionally PUBLIC — a visitor has no
# token yet. require_user would 401 every signup before it could happen.


# =============================================================================
# Request / response models
# =============================================================================

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    name: str = Field("", max_length=200)
    organization: Optional[str] = None
    # Onboarding: personal | business — whom the account is for. Info-only at
    # signup; the workspace itself is allocated after the questionnaire via
    # POST /auth/workspace. Accepted values enforced in the endpoint.
    profile_type: Optional[str] = None
    org_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


# =============================================================================
# Helpers
# =============================================================================

def _user_brief(user) -> dict:
    """Shape the multi-user User into the public auth payload."""
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role.value,
        "organization": user.organization,
        "preferred_workspace": user.preferred_workspace,
        "created_at": user.created_at,
    }


def _auth_response(user, session) -> dict:
    return {
        "user": _user_brief(user),
        "token": session.token,
        "expires_at": session.expires_at,
        "token_type": "bearer",
    }


def _identity(request: Request) -> str:
    host = getattr(request.client, "host", None) if request.client else None
    return host or "unknown"


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/signup")
async def signup(request: Request, payload: SignupRequest) -> dict:
    """Create an account and immediately return a session token."""
    _signup_limiter.check(request)
    api = get_multi_user_api()

    email = payload.email.strip().lower()
    name = payload.name.strip() or email.split("@", 1)[0]

    profile_type = (payload.profile_type or "").strip().lower()
    if profile_type and profile_type not in ("personal", "business"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="profile_type must be 'personal' or 'business'.",
        )
    if profile_type == "personal":
        profile_type = None

    organization = payload.organization or payload.org_name

    existing = api.users.get_user_by_email(email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Try signing in.",
        )

    try:
        user = api.register_user(
            email=email,
            password=payload.password,
            name=name,
            organization=organization,
        )
    except ValueError as exc:
        # UserManager raises ValueError("User with email ... already exists")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Try signing in.",
        ) from exc

    session = api.auth.create_session(
        user_id=user.id,
        ip_address=_identity(request),
        user_agent=request.headers.get("user-agent"),
    )
    logger.info("Signup created user %s (%s)", email, user.id)
    return _auth_response(user, session)


@router.post("/login")
async def login(request: Request, payload: LoginRequest) -> dict:
    """Verify credentials and return a session token."""
    _login_limiter.check(request)
    api = get_multi_user_api()

    result = api.login(
        email=payload.email.strip().lower(),
        password=payload.password,
        ip_address=_identity(request),
        user_agent=request.headers.get("user-agent"),
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    user_data = result["user"]
    logger.info("Login for %s", user_data["email"])
    # api.login() already created a fresh AuthManager session for this
    # user; fetch it (the most recent active one) for its opaque token.
    sessions = api.auth.list_sessions(user_data["id"])
    token = sessions[-1].token if sessions else ""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed: session could not be created.",
        )
    return {
        "user": user_data,
        "token": token,
        "expires_at": sessions[-1].expires_at,
        "token_type": "bearer",
    }


@router.post("/logout", dependencies=[Depends(require_user)])
async def logout(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Invalidate the presented session token."""
    token = credentials.credentials if credentials else ""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Expected: Bearer <token>",
        )
    api = get_multi_user_api()
    ok = api.logout(token)
    return {"success": bool(ok)}


@router.get("/me", dependencies=[Depends(require_user)])
async def me(user: dict = Depends(get_current_user)) -> dict:
    """Resolve the current user from a bearer token (backend or Supabase)."""
    api = get_multi_user_api()

    # Backend session token: get_current_user resolves user_id for these.
    backend_user = None
    if user.get("id"):
        backend_user = api.users.get_user(user["id"])
    if backend_user is not None:
        return {"user": _user_brief(backend_user), "source": "backend"}

    # Supabase JWT: return the claims we have, no local user row required.
    return {"user": user, "source": "supabase" if user.get("iss") else "unknown"}


@router.post("/refresh", dependencies=[Depends(require_user)])
async def refresh_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Rotate to a fresh session token for the same user."""
    token = credentials.credentials if credentials else ""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Expected: Bearer <token>",
        )
    api = get_multi_user_api()
    session = api.auth.validate_token(token)
    if session is None:
        # Supabase tokens cannot be rotated here — the client refreshes those
        # itself. Only backend sessions rotate.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid. Please sign in again.",
        )
    api.auth.revoke_session(session.id)
    new_session = api.auth.create_session(
        user_id=session.user_id,
        ip_address=_identity(request),
        user_agent=request.headers.get("user-agent"),
    )
    user = api.users.get_user(session.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid. Please sign in again.",
        )
    return _auth_response(user, new_session)


class WorkspaceAllocationRequest(BaseModel):
    """Allocate the primary workspace after the signup questionnaire."""

    workspace_type: str = Field(
        "personal",
        description="Which workspace becomes the user's primary: personal | business",
    )


@router.post("/workspace", dependencies=[Depends(require_user)])
async def allocate_workspace(
    request: Request,
    payload: WorkspaceAllocationRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    """Persist the signup questionnaire's workspace choice on the user row.

    Called once by the frontend onboarding flow right after signup; safe to
    call again (idempotent — the latest choice wins).
    """
    api = get_multi_user_api()

    backend_user = None
    if user.get("id"):
        backend_user = api.users.get_user(user["id"])
    if backend_user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workspace allocation requires a backend account "
            "(supabase-only identities are not supported).",
        )

    try:
        updated = api.set_preferred_workspace(
            backend_user.id, payload.workspace_type
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    logger.info(
        "Workspace allocated for %s: %s", backend_user.email, updated.preferred_workspace
    )
    return {
        "user": _user_brief(updated),
        "preferred_workspace": updated.preferred_workspace,
    }
