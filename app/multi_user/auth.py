"""
Authentication Manager - Production-Grade
=========================================

Password hashing, session management, and API key handling.
"""

import hashlib
import hmac
import logging
import os
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

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


def _session_ttl_hours() -> int:
    """Session lifetime in hours, configurable via FBR_SESSION_TTL_HOURS."""
    raw = (os.environ.get("FBR_SESSION_TTL_HOURS") or "").strip()
    if not raw:
        return AuthManager.DEFAULT_SESSION_HOURS
    try:
        hours = int(raw)
    except ValueError:
        logger.warning(
            "Invalid FBR_SESSION_TTL_HOURS=%r; using %d",
            raw, AuthManager.DEFAULT_SESSION_HOURS,
        )
        return AuthManager.DEFAULT_SESSION_HOURS
    if hours <= 0:
        logger.warning(
            "FBR_SESSION_TTL_HOURS must be positive (got %r); using %d",
            raw, AuthManager.DEFAULT_SESSION_HOURS,
        )
        return AuthManager.DEFAULT_SESSION_HOURS
    return hours


def hash_password(password: str, salt: Optional[str] = None) -> str:
    """
    Hash a password using PBKDF2 with SHA-256.

    Returns: 'salt$hash' format string
    """
    if salt is None:
        salt = secrets.token_hex(16)

    pwd_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations=100_000,
    )
    return f"{salt}${pwd_hash.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a stored hash."""
    try:
        salt, stored_hash = password_hash.split("$", 1)
        pwd_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations=100_000,
        )
        return hmac.compare_digest(pwd_hash.hex(), stored_hash)
    except (ValueError, AttributeError):
        return False


@dataclass
class Session:
    """An active user session."""
    id: str
    user_id: str
    token: str
    created_at: str
    expires_at: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    is_active: bool = True


@dataclass
class APIKey:
    """An API key for programmatic access."""
    id: str
    user_id: str
    key_hash: str  # Hashed, not the actual key
    name: str
    scopes: list[str] = field(default_factory=list)
    created_at: str = ""
    last_used_at: Optional[str] = None
    expires_at: Optional[str] = None
    is_active: bool = True


class AuthManager:
    """Manages authentication, sessions, and API keys."""

    DEFAULT_SESSION_HOURS = 24

    def __init__(self):
        self.sessions: dict[str, Session] = {}
        self.api_keys: dict[str, APIKey] = {}  # key_hash -> APIKey
        self.token_index: dict[str, str] = {}  # token -> session_id

    def create_session(
        self,
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        duration_hours: Optional[int] = None,
    ) -> Session:
        """Create a new session for a user.

        `duration_hours` defaults to the configured TTL (FBR_SESSION_TTL_HOURS).
        """
        if duration_hours is None:
            duration_hours = _session_ttl_hours()

        token = secrets.token_urlsafe(32)
        now = _utcnow()
        expires = now + timedelta(hours=duration_hours)

        session = Session(
            id=str(uuid.uuid4()),
            user_id=user_id,
            token=token,
            created_at=now.isoformat(),
            expires_at=expires.isoformat(),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.sessions[session.id] = session
        self.token_index[token] = session.id

        logger.info(f"Session created for user {user_id}")
        return session

    def validate_token(self, token: str) -> Optional[Session]:
        """Validate a session token and return the session if valid."""
        self.cleanup_expired_sessions()

        session_id = self.token_index.get(token)
        if not session_id:
            return None

        session = self.sessions.get(session_id)
        if not session or not session.is_active:
            return None

        # Check expiry
        if _utcnow() > _parse_iso(session.expires_at):
            session.is_active = False
            self.token_index.pop(session.token, None)
            return None

        return session

    def revoke_session(self, session_id: str) -> bool:
        """Revoke a session."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        session.is_active = False
        self.token_index.pop(session.token, None)
        return True

    def revoke_all_sessions(self, user_id: str) -> int:
        """Revoke all sessions for a user."""
        count = 0
        for session in self.sessions.values():
            if session.user_id == user_id and session.is_active:
                session.is_active = False
                self.token_index.pop(session.token, None)
                count += 1
        return count

    def list_sessions(self, user_id: str) -> list[Session]:
        """List active sessions for a user."""
        self.cleanup_expired_sessions()
        return [
            s for s in self.sessions.values()
            if s.user_id == user_id and s.is_active
        ]

    def create_api_key(
        self,
        user_id: str,
        name: str,
        scopes: Optional[list[str]] = None,
        expires_in_days: Optional[int] = None,
    ) -> tuple[APIKey, str]:
        """
        Create an API key.

        Returns: (api_key_record, plain_text_key)
        Note: The plain text key is only shown once at creation.
        """
        plain_key = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(plain_key.encode("utf-8")).hexdigest()

        now = _utcnow()
        expires_at = None
        if expires_in_days:
            expires_at = (now + timedelta(days=expires_in_days)).isoformat()

        api_key = APIKey(
            id=str(uuid.uuid4()),
            user_id=user_id,
            key_hash=key_hash,
            name=name,
            scopes=scopes or ["read"],
            created_at=now.isoformat(),
            expires_at=expires_at,
        )
        self.api_keys[key_hash] = api_key

        logger.info(f"API key created for user {user_id}: {name}")
        return api_key, plain_key

    def validate_api_key(self, plain_key: str) -> Optional[APIKey]:
        """Validate an API key and return the record."""
        key_hash = hashlib.sha256(plain_key.encode("utf-8")).hexdigest()
        api_key = self.api_keys.get(key_hash)

        if not api_key or not api_key.is_active:
            return None

        # Check expiry
        if api_key.expires_at:
            if _utcnow() > _parse_iso(api_key.expires_at):
                api_key.is_active = False
                return None

        api_key.last_used_at = _utcnow().isoformat()
        return api_key

    def revoke_api_key(self, key_id: str) -> bool:
        """Revoke an API key."""
        for api_key in self.api_keys.values():
            if api_key.id == key_id:
                api_key.is_active = False
                return True
        return False

    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions. Returns count removed."""
        now = _utcnow()
        expired_ids = []
        for sid, session in self.sessions.items():
            if session.is_active:
                if now > _parse_iso(session.expires_at):
                    session.is_active = False
                    self.token_index.pop(session.token, None)
                    expired_ids.append(sid)
        return len(expired_ids)

    def get_statistics(self) -> dict:
        """Get auth statistics."""
        active_sessions = sum(1 for s in self.sessions.values() if s.is_active)
        active_keys = sum(1 for k in self.api_keys.values() if k.is_active)
        return {
            "total_sessions": len(self.sessions),
            "active_sessions": active_sessions,
            "total_api_keys": len(self.api_keys),
            "active_api_keys": active_keys,
        }


# Singleton
_auth_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    """Get singleton auth manager."""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager
