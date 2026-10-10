"""
Quota Router
============

HTTP surface for the per-user daily quota (ChatGPT-style: a fixed budget of
assistant messages and chat file uploads that resets at local midnight).

Every route requires authentication (`Depends(require_user)`) and is
owner-scoped: the acting `user_id` comes from the token (the same
dev-user fallback pattern as `app/routers/vault.py`), so one user can never
read another user's quota. Reads are rate-limited via the shared
`RateLimiter`. The store itself never raises — a store failure degrades to
a full-limit snapshot per `FBR_QUOTA_FAIL_OPEN`.
"""

import logging

from fastapi import APIRouter, Depends, Request

from app.common.rate_limit import RateLimiter
from app.quotas import get_quota_store
from app.supabase_auth import require_user

logger = logging.getLogger("fbr_api.quota")

router = APIRouter(prefix="/quota", tags=["Quota"])

# Read-only dashboard endpoint: generous 120 req/60s per token/IP, tunable
# via QUOTA_RATE_LIMIT="<count>/<seconds>".
_limiter = RateLimiter.from_env(
    "QUOTA_RATE_LIMIT", default_limit=120, default_window=60.0
)


def _user_id(user=Depends(require_user)) -> str:
    """Resolve the authenticated, owner-scoping user id.

    Mirrors `app/routers/vault.py`: with a real token the JWT 'sub' (or
    id/user_id) scopes the quota; under the FBR_AUTH_REQUIRED=false dev
    bypass everything falls back to one shared 'dev-user' scope.
    """
    if isinstance(user, dict):
        for key in ("id", "user_id", "sub"):
            if user.get(key):
                return str(user[key])
    return "dev-user"


@router.get("", dependencies=[Depends(require_user)])
async def get_quota(request: Request, user_id: str = Depends(_user_id)) -> dict:
    """Read-only snapshot of the caller's daily message/upload quota.

    Returns the canonical quota JSON shape (`enabled`, `user_id`, `date`,
    `timezone`, `reset_at`, `messages{used,limit,remaining}`,
    `uploads{used,limit,remaining}`). Does not consume anything.
    """
    _limiter.check(request)
    return get_quota_store().snapshot(user_id).dict()
