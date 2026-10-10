"""
Daily Per-User Quota Store
==========================

ChatGPT-style daily quotas for the FBR assistant: a per-user budget of
assistant messages and chat file uploads that resets at local midnight.

Public contract (kept stable for downstream consumers):
    get_quota_store() -> QuotaStore          # process-wide singleton
    QuotaStore.snapshot / consume_message / consume_upload / is_enabled
    QuotaSnapshot (+ .dict() -> the exact JSON shape served by GET /quota)

Configuration (env, read at call time so tests can flip them):
    FBR_QUOTA_ENABLED         global on/off switch (default on)
    FBR_DAILY_MESSAGE_LIMIT   default 10
    FBR_DAILY_UPLOAD_LIMIT    default 5
    FBR_QUOTA_DB              SQLite path (default data/usage.db)
    FBR_QUOTA_TIMEZONE        IANA zone for the day boundary (default Asia/Karachi)
    FBR_QUOTA_FAIL_OPEN       default on — see the tradeoff note below

Limit semantics: a limit of ``0`` means "blocked immediately" (a real zero
budget); a NEGATIVE limit means unlimited. Unparseable env values fall back
to the default and are logged once.

Fail-open vs fail-closed tradeoff: the quota system is a metering feature,
not a security boundary, so when the SQLite store errors the default
(``FBR_QUOTA_FAIL_OPEN=1``) returns a full-limit snapshot with
``allowed=True`` — users keep chatting and the outage only costs unbilled
usage. Set ``FBR_QUOTA_FAIL_OPEN=0`` to fail-closed (``allowed=False``)
instead when hard budget enforcement matters more than availability. Either
way the error is logged and ``snapshot``/``consume_*`` NEVER raise into the
request path.

Connection discipline mirrors ``app/learning/store.py``: one connection per
call, WAL mode, a process lock around every read/write. The consume path is
additionally guarded by a single ``INSERT ... ON CONFLICT DO UPDATE ...
WHERE used < limit`` statement, so the last slot cannot be handed to two
concurrent callers (even across processes, the loser's upsert updates 0 rows).
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("fbr_quotas")

# `__file__` is `<project>/app/quotas.py`; two dirnames land on the project
# root, so the store defaults to `<project>/data/usage.db`. (Three dirnames
# would resolve one level ABOVE the project and write outside the repo.)
_DEFAULT_DB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS quota_usage (
    user_id       TEXT NOT NULL,
    day           TEXT NOT NULL,
    messages_used INTEGER NOT NULL DEFAULT 0,
    uploads_used  INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (user_id, day)
);
"""

# Env names whose unparseable values have already been logged (log once).
_BAD_ENV_LOGGED: set[str] = set()
_TZ_FALLBACK_LOGGED = False


def _env_flag(name: str, default: bool) -> bool:
    """Read a boolean env at call time (so tests can flip it)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_limit(name: str, default: int) -> int:
    """Parse a quota limit env. 0 = blocked, negative = unlimited.

    Bad values (non-integer) fall back to the default and are logged once.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        if name not in _BAD_ENV_LOGGED:
            _BAD_ENV_LOGGED.add(name)
            logger.warning(
                "Invalid %s=%r (expected an integer); using default %d. "
                "0 blocks immediately, a negative value means unlimited.",
                name, raw, default,
            )
        return default


def _resolve_timezone() -> tuple[tzinfo, str]:
    """Resolve FBR_QUOTA_TIMEZONE; never raises.

    zoneinfo may lack IANA data on Windows, so a lookup failure falls back
    to a fixed UTC+5 offset (Pakistan, the default zone's offset) and is
    logged once.
    """
    global _TZ_FALLBACK_LOGGED
    name = os.environ.get("FBR_QUOTA_TIMEZONE", "").strip() or "Asia/Karachi"
    try:
        return ZoneInfo(name), name
    except Exception as exc:  # noqa: BLE001 - missing tzdata on Windows
        if not _TZ_FALLBACK_LOGGED:
            _TZ_FALLBACK_LOGGED = True
            logger.warning(
                "Timezone %r unavailable (%s); falling back to fixed UTC+5.",
                name, exc,
            )
        return timezone(timedelta(hours=5)), name


def _now_in_tz(tz: tzinfo) -> datetime:
    """Current time in ``tz``. Monkeypatched by tests to freeze/advance the day."""
    return datetime.now(tz)


@dataclass(frozen=True)
class QuotaSnapshot:
    """Read-only view of one user's quota for the current local day."""

    enabled: bool
    user_id: str
    date: str
    timezone: str
    reset_at: str
    messages_used: int
    messages_limit: int
    messages_remaining: int
    allowed_message: bool
    uploads_used: int
    uploads_limit: int
    uploads_remaining: int
    allowed_upload: bool

    def dict(self) -> dict:
        """Exact JSON shape served by GET /quota and echoed in responses."""
        return {
            "enabled": self.enabled,
            "user_id": self.user_id,
            "date": self.date,
            "timezone": self.timezone,
            "reset_at": self.reset_at,
            "messages": {
                "used": self.messages_used,
                "limit": self.messages_limit,
                "remaining": self.messages_remaining,
            },
            "uploads": {
                "used": self.uploads_used,
                "limit": self.uploads_limit,
                "remaining": self.uploads_remaining,
            },
        }


class QuotaStore:
    """Thread-safe per-user daily quota store (SQLite, WAL, per-call connections)."""

    def __init__(self, db_path: Optional[str] = None):
        self._lock = threading.Lock()
        self._db_path = db_path or os.environ.get(
            "FBR_QUOTA_DB", os.path.join(_DEFAULT_DB_DIR, "usage.db")
        )
        self._available = True
        try:
            with self._with_conn() as conn:
                conn.executescript(_SCHEMA)
        except Exception as exc:  # noqa: BLE001 - degrade to fail-open/fail-closed
            self._available = False
            logger.error("Quota store init failed at %s: %s", self._db_path, exc)

    # ------------------------------------------------------------------
    # Connection (mirrors app/learning/store.py)
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(self._db_path)), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @contextmanager
    def _with_conn(self):
        """Process lock + one fresh connection; commit/rollback/lock-release."""
        with self._lock:
            conn = self._connect()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Config (env read at call time)
    # ------------------------------------------------------------------

    def is_enabled(self) -> bool:
        return _env_flag("FBR_QUOTA_ENABLED", True)

    @property
    def message_limit(self) -> int:
        return _env_limit("FBR_DAILY_MESSAGE_LIMIT", 10)

    @property
    def upload_limit(self) -> int:
        return _env_limit("FBR_DAILY_UPLOAD_LIMIT", 5)

    @property
    def fail_open(self) -> bool:
        return _env_flag("FBR_QUOTA_FAIL_OPEN", True)

    # ------------------------------------------------------------------
    # Day boundary
    # ------------------------------------------------------------------

    def _day_info(self) -> tuple[str, str, str, str]:
        """(local day, tz name, next-midnight reset, now ISO) — never raises."""
        tz, name = _resolve_timezone()
        now = _now_in_tz(tz)
        day = now.date()
        reset = datetime(day.year, day.month, day.day, tzinfo=tz) + timedelta(days=1)
        return day.isoformat(), name, reset.isoformat(), now.isoformat()

    # ------------------------------------------------------------------
    # Snapshot helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _remaining(used: int, limit: int) -> int:
        # Never negative; a negative (unlimited) limit reports remaining 0.
        return max(0, limit - used) if limit >= 0 else 0

    def _build(
        self,
        user_id: str,
        day: str,
        tz_name: str,
        reset_at: str,
        messages_used: int,
        uploads_used: int,
        allowed_message: bool,
        allowed_upload: bool,
    ) -> QuotaSnapshot:
        msg_limit = self.message_limit
        up_limit = self.upload_limit
        return QuotaSnapshot(
            enabled=self.is_enabled(),
            user_id=user_id,
            date=day,
            timezone=tz_name,
            reset_at=reset_at,
            messages_used=messages_used,
            messages_limit=msg_limit,
            messages_remaining=self._remaining(messages_used, msg_limit),
            allowed_message=allowed_message,
            uploads_used=uploads_used,
            uploads_limit=up_limit,
            uploads_remaining=self._remaining(uploads_used, up_limit),
            allowed_upload=allowed_upload,
        )

    def _fail_snapshot(self, user_id: str) -> QuotaSnapshot:
        """Full-limit snapshot used when the store errors (never raises)."""
        allowed = self.fail_open
        try:
            day, tz_name, reset_at, _now_iso = self._day_info()
        except Exception:  # noqa: BLE001 - last-resort degrade
            day, tz_name, reset_at, _now_iso = "", "UTC", "", ""
        return self._build(
            user_id, day, tz_name, reset_at,
            messages_used=0, uploads_used=0,
            allowed_message=allowed, allowed_upload=allowed,
        )

    def _read_counts(self, conn: sqlite3.Connection, user_id: str, day: str) -> tuple[int, int]:
        row = conn.execute(
            "SELECT messages_used, uploads_used FROM quota_usage WHERE user_id = ? AND day = ?",
            (user_id, day),
        ).fetchone()
        if row is None:
            return 0, 0
        return int(row["messages_used"]), int(row["uploads_used"])

    # ------------------------------------------------------------------
    # Public API (never raises)
    # ------------------------------------------------------------------

    def snapshot(self, user_id: str) -> QuotaSnapshot:
        """Read-only quota view for today. Never increments anything."""
        try:
            if not self.is_enabled():
                day, tz_name, reset_at, _now_iso = self._day_info()
                return self._build(
                    user_id, day, tz_name, reset_at, 0, 0,
                    allowed_message=True, allowed_upload=True,
                )
            day, tz_name, reset_at, _now_iso = self._day_info()
            with self._with_conn() as conn:
                messages_used, uploads_used = self._read_counts(conn, user_id, day)
            msg_limit = self.message_limit
            up_limit = self.upload_limit
            return self._build(
                user_id, day, tz_name, reset_at, messages_used, uploads_used,
                allowed_message=msg_limit < 0 or messages_used < msg_limit,
                allowed_upload=up_limit < 0 or uploads_used < up_limit,
            )
        except Exception as exc:  # noqa: BLE001 - safe degrade
            logger.warning("quota snapshot failed for %s: %s", user_id, exc)
            return self._fail_snapshot(user_id)

    def _consume(self, user_id: str, kind: str) -> QuotaSnapshot:
        try:
            if not self.is_enabled():
                return self.snapshot(user_id)
            day, tz_name, reset_at, now_iso = self._day_info()
            limit = self.message_limit if kind == "messages" else self.upload_limit

            if limit == 0:
                # A real zero budget blocks immediately; no DB write needed.
                with self._with_conn() as conn:
                    messages_used, uploads_used = self._read_counts(conn, user_id, day)
                msg_limit = self.message_limit
                up_limit = self.upload_limit
                return self._build(
                    user_id, day, tz_name, reset_at, messages_used, uploads_used,
                    allowed_message=(kind != "messages") and (msg_limit < 0 or messages_used < msg_limit),
                    allowed_upload=(kind != "uploads") and (up_limit < 0 or uploads_used < up_limit),
                )

            # Guard for the single-statement upsert. A negative (unlimited)
            # limit uses a guard no counter can reach.
            guard = limit if limit >= 0 else 2**63 - 1
            with self._with_conn() as conn:
                messages_used, uploads_used = self._read_counts(conn, user_id, day)
                current = messages_used if kind == "messages" else uploads_used
                # A negative limit means unlimited: never blocked.
                if limit >= 0 and current >= limit:
                    allowed = False
                else:
                    # Atomic: the WHERE guard means the last slot can never
                    # be handed to two concurrent callers (rowcount 0 = lost).
                    if kind == "messages":
                        cur = conn.execute(
                            """
                            INSERT INTO quota_usage
                                (user_id, day, messages_used, uploads_used, updated_at)
                            VALUES (?, ?, 1, 0, ?)
                            ON CONFLICT(user_id, day) DO UPDATE SET
                                messages_used = quota_usage.messages_used + 1,
                                updated_at = excluded.updated_at
                            WHERE quota_usage.messages_used < ?
                            """,
                            (user_id, day, now_iso, guard),
                        )
                    else:
                        cur = conn.execute(
                            """
                            INSERT INTO quota_usage
                                (user_id, day, messages_used, uploads_used, updated_at)
                            VALUES (?, ?, 0, 1, ?)
                            ON CONFLICT(user_id, day) DO UPDATE SET
                                uploads_used = quota_usage.uploads_used + 1,
                                updated_at = excluded.updated_at
                            WHERE quota_usage.uploads_used < ?
                            """,
                            (user_id, day, now_iso, guard),
                        )
                    allowed = cur.rowcount > 0
                # Re-read inside the same locked transaction for the snapshot.
                messages_used, uploads_used = self._read_counts(conn, user_id, day)

            msg_limit = self.message_limit
            up_limit = self.upload_limit
            msg_allowed = (
                allowed if kind == "messages"
                else (msg_limit < 0 or messages_used < msg_limit)
            )
            up_allowed = (
                allowed if kind == "uploads"
                else (up_limit < 0 or uploads_used < up_limit)
            )
            return self._build(
                user_id, day, tz_name, reset_at, messages_used, uploads_used,
                allowed_message=msg_allowed, allowed_upload=up_allowed,
            )
        except Exception as exc:  # noqa: BLE001 - safe degrade
            logger.warning("quota consume_%s failed for %s: %s", kind, user_id, exc)
            return self._fail_snapshot(user_id)

    def consume_message(self, user_id: str) -> QuotaSnapshot:
        """Atomically count one assistant message. Increments only if under limit."""
        return self._consume(user_id, "messages")

    def consume_upload(self, user_id: str) -> QuotaSnapshot:
        """Atomically count one chat file upload. Increments only if under limit."""
        return self._consume(user_id, "uploads")


_store: Optional[QuotaStore] = None
_store_lock = threading.Lock()


def get_quota_store() -> QuotaStore:
    """Process-wide singleton, lazily created. Never raises."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = QuotaStore()
    return _store
