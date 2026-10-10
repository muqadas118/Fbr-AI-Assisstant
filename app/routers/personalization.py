"""
Personalization Router
=====================

HTTP surface for the self-learning / personalization backend.

Every route requires authentication (`Depends(require_user)`) and is
owner-scoped: the acting `user_id` comes from the token (the same
dev-user fallback pattern as `app/routers/vault.py`), and every store
call is made with that id, so one user can never read or mutate another
user's learning data. Profile reads and feedback are rate-limited via the
shared `RateLimiter`.

This is behavioural personalization, NOT model training — the endpoints
only expose and control per-user behavioural signals and recommendations.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator

from app.common.rate_limit import RateLimiter
from app.learning import get_learning_store
from app.supabase_auth import require_user

logger = logging.getLogger("fbr_api.personalization")

router = APIRouter(prefix="/personalization", tags=["Personalization"])

# Independent buckets so a cheap read (/profile) cannot be starved by a
# write (/feedback) and vice versa. Per-process, token/IP-keyed (as the
# shared limiter is).
_profile_limiter = RateLimiter.from_env(
    "FBR_LEARNING_PROFILE_RATE_LIMIT", default_limit=60, default_window=60.0
)
_feedback_limiter = RateLimiter.from_env(
    "FBR_LEARNING_FEEDBACK_RATE_LIMIT", default_limit=30, default_window=60.0
)

_MAX_COMMENT_CHARS = 2000
_MAX_REC_LIMIT = 20


# =============================================================================
# Request Models
# =============================================================================

class FeedbackRequest(BaseModel):
    """Thumbs-up/down feedback on a single assistant message."""
    message_id: str = Field(..., min_length=1, max_length=200)
    rating: int = Field(..., description="+1 for helpful, -1 for unhelpful")
    comment: str = Field(default="", max_length=_MAX_COMMENT_CHARS)

    @field_validator("rating")
    @classmethod
    def _rating_must_be_plus_or_minus_one(cls, v: int) -> int:
        if v not in (-1, 1):
            raise ValueError("rating must be -1 or 1")
        return v


class PersonalizationToggle(BaseModel):
    """Opt the caller in/out of behavioural personalization."""
    enabled: bool


# =============================================================================
# Helpers
# =============================================================================

def _user_id(user=Depends(require_user)) -> str:
    """Resolve the authenticated, owner-scoping user id.

    Mirrors `app/routers/vault.py`: with a real token the JWT 'sub' (or
    id/user_id) scopes the store; under the FBR_AUTH_REQUIRED=false dev
    bypass everything falls back to one shared 'dev-user' scope.
    """
    if isinstance(user, dict):
        for key in ("id", "user_id", "sub"):
            if user.get(key):
                return str(user[key])
    return "dev-user"


def _ensure_owner(user, claimed_user_id: Optional[str], uid: str) -> None:
    """403 if a request payload claims a user id that is not the caller.

    The personalization bodies do not carry a user id today, so this is a
    defensive guard reused by any future owner-scoped payload.
    """
    if claimed_user_id and str(claimed_user_id) != uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only act on your own personalization data.",
        )
    _ = user


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), _MAX_REC_LIMIT))


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/profile", dependencies=[Depends(require_user)])
async def get_profile(request: Request, user_id: str = Depends(_user_id)) -> dict:
    """Return the caller's aggregated behavioural profile signals + stats.

    Always 200 with a fixed shape (empty signals when the user is new,
    opted out, or the store is unavailable).
    """
    _profile_limiter.check(request)
    store = get_learning_store()
    enabled = store.is_personalized(user_id)
    profile = store.get_profile(user_id)
    if profile is None:
        body = {"signals": {}, "top_domains": [], "total_interactions": 0, "last_active": None}
    else:
        body = profile.dict()
    # Fixed shape consumed by the frontend PersonalizationPanel: `user_id`
    # for identity, `enabled` for the effective on/off state.
    return {
        "user_id": user_id,
        "enabled": enabled,
        "signals": body.get("signals", {}),
        "top_domains": body.get("top_domains", []),
        "total_interactions": body.get("total_interactions", 0),
        "last_active": body.get("last_active"),
    }


@router.get("/recommendations", dependencies=[Depends(require_user)])
async def get_recommendations(
    limit: int = Query(default=5, ge=1, le=_MAX_REC_LIMIT),
    user_id: str = Depends(_user_id),
) -> list:
    """Return the caller's ordered recommendation list as a bare array.

    The frontend `RecommendationStrip` consumes the array directly, so the
    route returns `[{id, kind, title, body, action_label, action_path,
    priority, source}, ...]` with no wrapper object.
    """
    store = get_learning_store()
    recs = store.get_recommendations(user_id, limit=_clamp_limit(limit))
    return [r.dict() for r in recs]


@router.post("/recommendations/{rec_id}/dismiss", dependencies=[Depends(require_user)])
async def dismiss_recommendation(rec_id: str, user_id: str = Depends(_user_id)) -> dict:
    """Dismiss a recommendation for the caller (owner-scoped by user_id)."""
    ok = get_learning_store().dismiss_recommendation(user_id, rec_id)
    # Unknown id / store unavailable -> dismissed:false (200), never an error:
    # a dismiss is best-effort UI state, not a request the user must retry.
    return {"dismissed": bool(ok)}


@router.post("/feedback", dependencies=[Depends(require_user)])
async def post_feedback(
    payload: FeedbackRequest,
    request: Request,
    user_id: str = Depends(_user_id),
) -> dict:
    """Record thumbs-up/down feedback for the caller. Rate-limited."""
    _feedback_limiter.check(request)
    # Defensive owner guard: the feedback body carries no user id today;
    # if one is ever added, reject a mismatch rather than silently scoping.
    _ensure_owner(None, getattr(payload, "user_id", None), user_id)
    get_learning_store().record_feedback(
        user_id,
        message_id=payload.message_id,
        rating=payload.rating,
        comment=payload.comment,
    )
    return {"recorded": True}


@router.delete("/me/data", dependencies=[Depends(require_user)])
async def delete_my_data(user_id: str = Depends(_user_id)) -> dict:
    """Delete ALL personalization data for the caller (privacy right)."""
    deleted = get_learning_store().delete_user_data(user_id)
    return {"deleted": int(deleted or 0)}


@router.put("/me/personalization", dependencies=[Depends(require_user)])
async def set_my_personalization(
    payload: PersonalizationToggle,
    user_id: str = Depends(_user_id),
) -> dict:
    """Opt the caller in/out of behavioural personalization."""
    _ensure_owner(None, getattr(payload, "user_id", None), user_id)
    store = get_learning_store()
    store.set_personalized(user_id, payload.enabled)
    # Report the EFFECTIVE state (global switch AND opt-out), not the request.
    return {"enabled": store.is_personalized(user_id)}
