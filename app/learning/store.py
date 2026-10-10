"""
Personalization Learning Store
==============================

SQLite-backed store for behavioural personalization signals.

This is **behavioural personalization, NOT model training**. No model
weights are read, written, or changed anywhere in this module. It records
per-user derived signals, feedback, and generated recommendations, and
turns the interactions into a per-user profile and recommendation set.

Design guarantees:
    * Per-user isolation: every read/write is scoped by `user_id`; the
      recommender never aggregates across users.
    * Privacy by design: raw query text is stored ONLY when env
      `FBR_LEARNING_STORE_RAW_QUERIES=1` (default OFF) — otherwise the
      stored `query` column is empty and only derived signals persist.
      Retention cap via `FBR_LEARNING_RETENTION_DAYS` (default 90) and a
      hard per-user interaction cap of 500 rows.
    * Degrades safely: if the store is unavailable or personalization is
      disabled globally, every public method returns empty/None/False/0
      and never raises into the caller's request path.

Connection discipline mirrors `app.vault_store` (one connection per call,
WAL mode, a process lock for writes).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.learning.profile import UserProfile, build_profile
from app.learning.recommender import Recommendation, build_recommendations

logger = logging.getLogger("fbr_learning")

# `__file__` is `<project>/app/learning/store.py`; three dirnames land on the
# project root, so the store defaults to `<project>/data/learning.db`.
_DEFAULT_DB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data"
)

# Hard per-user interaction row cap (non-negotiable privacy budget).
_MAX_INTERACTIONS_PER_USER = 500

_SCHEMA = """
CREATE TABLE IF NOT EXISTS interactions (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    query       TEXT NOT NULL DEFAULT '',
    domain      TEXT NOT NULL DEFAULT '',
    tools       TEXT NOT NULL DEFAULT '[]',
    signals     TEXT NOT NULL DEFAULT '{}',
    rating      INTEGER,
    channel     TEXT NOT NULL DEFAULT 'assistant',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lrn_int_user ON interactions (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS feedback (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    message_id  TEXT NOT NULL,
    rating      INTEGER NOT NULL,
    comment     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lrn_fb_user ON feedback (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS recommendations (
    user_id       TEXT NOT NULL,
    id            TEXT NOT NULL,
    kind          TEXT NOT NULL DEFAULT '',
    title         TEXT NOT NULL DEFAULT '',
    body          TEXT NOT NULL DEFAULT '',
    action_label  TEXT NOT NULL DEFAULT '',
    action_path   TEXT NOT NULL DEFAULT '',
    priority      INTEGER NOT NULL DEFAULT 0,
    source        TEXT NOT NULL DEFAULT '',
    dismissed     INTEGER NOT NULL DEFAULT 0,
    impressions   INTEGER NOT NULL DEFAULT 0,
    last_shown_at TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (user_id, id)
);
CREATE INDEX IF NOT EXISTS idx_lrn_rec_user ON recommendations (user_id);

CREATE TABLE IF NOT EXISTS settings (
    user_id     TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, key)
);
"""


def _now() -> datetime:
    """Timezone-aware UTC now (datetime.utcnow is deprecated in 3.12+)."""
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _env_flag(name: str, default: bool) -> bool:
    """Read a boolean env at call time (so tests can flip it)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


class LearningStore:
    """Process-wide, thread-safe, per-user SQLite store for personalization.

    Thread-safe via a process lock plus one connection per call (cheap at
    this scale, mirrors VaultStore). Every public method is defensive and
    never raises into the caller's request path.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._lock = threading.Lock()
        self._db_path = db_path or os.environ.get(
            "FBR_LEARNING_DB", os.path.join(_DEFAULT_DB_DIR, "learning.db")
        )
        self._available = True
        try:
            with self._connect() as conn:
                conn.executescript(_SCHEMA)
        except Exception as exc:  # noqa: BLE001 - degrade to no-op store
            self._available = False
            logger.error("Learning store init failed at %s: %s", self._db_path, exc)
        else:
            logger.info("Learning store ready at %s", self._db_path)

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(self._db_path)), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @contextmanager
    def _with_conn(self):
        """Acquire the process lock and yield one fresh connection.

        Commits on clean exit, rolls back on error, always releases the
        lock and closes the connection. Mirrors VaultStore's per-call
        connection discipline (SQLite via WAL).
        """
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
    # Config / state
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        return self._available

    @property
    def store_raw_queries(self) -> bool:
        return _env_flag("FBR_LEARNING_STORE_RAW_QUERIES", False)

    @property
    def retention_days(self) -> int:
        return _env_int("FBR_LEARNING_RETENTION_DAYS", 90)

    @property
    def learning_enabled(self) -> bool:
        """Global on/off switch for the whole learning module."""
        return _env_flag("FBR_LEARNING_ENABLED", True)

    # ------------------------------------------------------------------
    # Personalized on/off
    # ------------------------------------------------------------------

    def is_personalized(self, user_id: str) -> bool:
        """Whether personalization is active for this user.

        Returns False when the module is globally disabled, when the user
        opted out, or when the store is unavailable. Defaults to True
        (opt-out model) when no setting exists and the store is healthy.
        Never raises.
        """
        try:
            if not self.learning_enabled or not self._available:
                return False
            with self._with_conn() as conn:
                row = conn.execute(
                    "SELECT value FROM settings WHERE user_id = ? AND key = 'personalized'",
                    (user_id,),
                ).fetchone()
            if row is None:
                return True
            return str(row["value"]) == "1"
        except Exception as exc:  # noqa: BLE001 - safe degrade
            logger.warning("is_personalized failed for %s: %s", user_id, exc)
            return False

    def set_personalized(self, user_id: str, enabled: bool) -> None:
        """Persist this user's personalization preference. Never raises.

        `is_personalized` still honors the global `FBR_LEARNING_ENABLED`
        switch, so a stored preference takes effect when the module is on.
        """
        try:
            if not self._available:
                return
            with self._with_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO settings (user_id, key, value, updated_at)
                    VALUES (?, 'personalized', ?, ?)
                    ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value,
                                                          updated_at = excluded.updated_at
                    """,
                    (user_id, "1" if enabled else "0", _now_iso()),
                )
        except Exception as exc:  # noqa: BLE001 - safe degrade
            logger.warning("set_personalized failed for %s: %s", user_id, exc)

    # ------------------------------------------------------------------
    # Record interactions
    # ------------------------------------------------------------------

    def record_interaction(
        self,
        user_id: str,
        *,
        query: str = "",
        domain: str = "",
        tools: Optional[list[str]] = None,
        signals: Optional[dict[str, Any]] = None,
        rating: Optional[int] = None,
        channel: str = "assistant",
    ) -> None:
        """Record one interaction for `user_id`.

        No-op when personalization is disabled/opted-out for the user, or
        when the store is unavailable. Raw query text is stored only when
        `FBR_LEARNING_STORE_RAW_QUERIES=1`. Enforces the retention cap and
        the hard 500-row cap. Never raises.
        """
        try:
            if not self.learning_enabled or not self._available:
                return
            if not self.is_personalized(user_id):
                return

            now = _now_iso()
            stored_query = (query or "") if self.store_raw_queries else ""
            tools_json = json.dumps(list(tools) if tools else [])
            signals_json = json.dumps(dict(signals) if signals else {})
            rec_id = "int-" + uuid.uuid4().hex[:16]
            cutoff = (_now() - timedelta(days=self.retention_days)).isoformat()

            with self._with_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO interactions
                        (id, user_id, query, domain, tools, signals, rating, channel, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rec_id, user_id, stored_query, domain or "",
                        tools_json, signals_json, rating, channel, now,
                    ),
                )
                # Retention: drop this user's interactions older than the cap.
                conn.execute(
                    "DELETE FROM interactions WHERE user_id = ? AND created_at < ?",
                    (user_id, cutoff),
                )
                # Hard per-user row cap: keep only the newest N rows.
                conn.execute(
                    """
                    DELETE FROM interactions
                    WHERE user_id = ?
                      AND id NOT IN (
                          SELECT id FROM interactions WHERE user_id = ?
                          ORDER BY created_at DESC
                          LIMIT ?
                      )
                    """,
                    (user_id, user_id, _MAX_INTERACTIONS_PER_USER),
                )
        except Exception as exc:  # noqa: BLE001 - safe degrade
            logger.warning("record_interaction failed for %s: %s", user_id, exc)

    def record_feedback(
        self, user_id: str, *, message_id: str, rating: int, comment: str = ""
    ) -> None:
        """Record one feedback event for `user_id`. Never raises.

        Feedback is stored regardless of the personalization opt-out (it is
        the user's explicit input and drives their own future signals), but
        is still confined to this user. Raw `comment` text is stored (the
        user wrote it for support); set `FBR_LEARNING_STORE_RAW_QUERIES=1`
        to also retain them.
        """
        try:
            if not self.learning_enabled or not self._available:
                return
            fb_id = "fb-" + uuid.uuid4().hex[:16]
            now = _now_iso()
            cutoff = (_now() - timedelta(days=self.retention_days)).isoformat()
            with self._with_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO feedback (id, user_id, message_id, rating, comment, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (fb_id, user_id, message_id, int(rating), comment or "", now),
                )
                conn.execute(
                    "DELETE FROM feedback WHERE user_id = ? AND created_at < ?",
                    (user_id, cutoff),
                )
        except Exception as exc:  # noqa: BLE001 - safe degrade
            logger.warning("record_feedback failed for %s: %s", user_id, exc)

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------

    def _interaction_rows(self, user_id: str) -> list[dict]:
        cutoff = (_now() - timedelta(days=self.retention_days)).isoformat()
        with self._with_conn() as conn:
            rows = conn.execute(
                """
                SELECT domain, tools, signals, rating, created_at
                FROM interactions
                WHERE user_id = ? AND created_at >= ?
                ORDER BY created_at DESC
                """,
                (user_id, cutoff),
            ).fetchall()
        out: list[dict] = []
        for r in rows:
            signals = _safe_json(r["signals"], {})
            tools = _safe_json(r["tools"], [])
            out.append(
                {
                    "domain": r["domain"],
                    "tools": tools if isinstance(tools, list) else [],
                    "signals": signals if isinstance(signals, dict) else {},
                    "rating": r["rating"],
                    "created_at": r["created_at"],
                }
            )
        return out

    def get_profile(self, user_id: str) -> Optional[UserProfile]:
        """Aggregate this user's interactions into a UserProfile.

        Returns None when personalization is disabled/opted-out, when the
        store is unavailable, or when the user has no retained
        interactions. Never raises.
        """
        try:
            if not self.learning_enabled or not self._available:
                return None
            if not self.is_personalized(user_id):
                return None
            rows = self._interaction_rows(user_id)
            if not rows:
                return None
            return build_profile(rows, decay_days=30)
        except Exception as exc:  # noqa: BLE001 - safe degrade
            logger.warning("get_profile failed for %s: %s", user_id, exc)
            return None

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def _dismissed_ids(self, conn: sqlite3.Connection, user_id: str) -> set:
        rows = conn.execute(
            "SELECT id FROM recommendations WHERE user_id = ? AND dismissed = 1",
            (user_id,),
        ).fetchall()
        return {r["id"] for r in rows}

    def _persist_rec(self, conn: sqlite3.Connection, user_id: str, rec: Recommendation) -> None:
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO recommendations
                (user_id, id, kind, title, body, action_label, action_path,
                 priority, source, dismissed, impressions, last_shown_at,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, NULL, ?, ?)
            ON CONFLICT(user_id, id) DO UPDATE SET
                kind = excluded.kind,
                title = excluded.title,
                body = excluded.body,
                action_label = excluded.action_label,
                action_path = excluded.action_path,
                priority = excluded.priority,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (
                user_id, rec.id, rec.kind, rec.title, rec.body,
                rec.action_label, rec.action_path, rec.priority, rec.source,
                now, now,
            ),
        )

    def get_recommendations(self, user_id: str, limit: int = 5) -> list[Recommendation]:
        """Build and return this user's recommendation list.

        Returns [] when personalization is disabled/opted-out or the store
        is unavailable. Calendar `deadline` recommendations are skipped if
        the calendar import fails. Persists freshly generated recs (keeping
        their dismissed/impressions state), filters dismissed ids, sorts by
        priority and caps at `limit`. Never raises.
        """
        try:
            if not self.learning_enabled or not self._available:
                return []
            if not self.is_personalized(user_id):
                return []

            rows = self._interaction_rows(user_id)
            profile = build_profile(rows, decay_days=30)

            with self._with_conn() as conn:
                dismissed = self._dismissed_ids(conn, user_id)

            calendar_events = self._calendar_events()
            recs = build_recommendations(profile, calendar_events, dismissed, max(0, int(limit)))
            if recs:
                try:
                    with self._with_conn() as conn:
                        for rec in recs:
                            self._persist_rec(conn, user_id, rec)
                except Exception as exc:  # noqa: BLE001 - persistence is best-effort
                    logger.warning("recommendation persist failed for %s: %s", user_id, exc)
            return recs
        except Exception as exc:  # noqa: BLE001 - safe degrade
            logger.warning("get_recommendations failed for %s: %s", user_id, exc)
            return []

    @staticmethod
    def _calendar_events() -> list:
        """Fetch upcoming compliance events, guarded.

        Import failure (or any error) returns [] so deadline
        recommendations are skipped rather than breaking the request.
        """
        try:
            from app.compliance_calendar.events import get_upcoming_events

            events = get_upcoming_events(days=30)
            return list(events or [])
        except Exception as exc:  # noqa: BLE001 - skip deadline recs
            logger.warning("compliance calendar unavailable for deadlines: %s", exc)
            return []

    def dismiss_recommendation(self, user_id: str, rec_id: str) -> bool:
        """Persist a dismissal for `(user_id, rec_id)`.

        Works even if the rec was never materialized in the table (the id
        is stored so future refreshes filter it). Returns True on success,
        False on failure. Never raises.
        """
        try:
            if not self.learning_enabled or not self._available:
                return False
            now = _now_iso()
            with self._with_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO recommendations
                        (user_id, id, kind, dismissed, created_at, updated_at)
                    VALUES (?, ?, 'manual', 1, ?, ?)
                    ON CONFLICT(user_id, id) DO UPDATE SET
                        dismissed = 1,
                        updated_at = excluded.updated_at
                    """,
                    (user_id, rec_id, now, now),
                )
            return True
        except Exception as exc:  # noqa: BLE001 - safe degrade
            logger.warning("dismiss_recommendation failed for %s/%s: %s", user_id, rec_id, exc)
            return False

    def record_recommendation_impressions(self, user_id: str, rec_ids: list[str]) -> int:
        """Tally impressions for the given rec ids for this user.

        Best-effort; returns the number of rec ids impressioned. Never
        raises.
        """
        try:
            if not self.learning_enabled or not self._available:
                return 0
            now = _now_iso()
            count = 0
            with self._with_conn() as conn:
                for rec_id in rec_ids or []:
                    if not rec_id:
                        continue
                    conn.execute(
                        """
                        INSERT INTO recommendations
                            (user_id, id, kind, dismissed, impressions, last_shown_at,
                             created_at, updated_at)
                        VALUES (?, ?, 'impression', 0, 1, ?, ?, ?)
                        ON CONFLICT(user_id, id) DO UPDATE SET
                            impressions = recommendations.impressions + 1,
                            last_shown_at = excluded.last_shown_at,
                            updated_at = excluded.updated_at
                        """,
                        (user_id, rec_id, now, now, now),
                    )
                    count += 1
            return count
        except Exception as exc:  # noqa: BLE001 - safe degrade
            logger.warning("record_recommendation_impressions failed for %s: %s", user_id, exc)
            return 0

    # ------------------------------------------------------------------
    # Privacy: export / delete
    # ------------------------------------------------------------------

    def export_user_data(self, user_id: str) -> dict:
        """Return everything stored for this user (privacy export).

        Always returns a dict (empty structure on failure). Raw query text
        is only present if `FBR_LEARNING_STORE_RAW_QUERIES=1` was on when
        it was recorded.
        """
        empty = {
            "user_id": user_id,
            "exported_at": _now_iso(),
            "interactions": [],
            "feedback": [],
            "recommendations": [],
            "settings": {},
        }
        try:
            if not self._available:
                return empty
            with self._with_conn() as conn:
                interactions = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT * FROM interactions WHERE user_id = ? ORDER BY created_at DESC",
                        (user_id,),
                    ).fetchall()
                ]
                feedback = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT * FROM feedback WHERE user_id = ? ORDER BY created_at DESC",
                        (user_id,),
                    ).fetchall()
                ]
                recommendations = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT * FROM recommendations WHERE user_id = ? ORDER BY updated_at DESC",
                        (user_id,),
                    ).fetchall()
                ]
                settings = {
                    r["key"]: r["value"]
                    for r in conn.execute(
                        "SELECT key, value FROM settings WHERE user_id = ?",
                        (user_id,),
                    ).fetchall()
                }
            return {
                "user_id": user_id,
                "exported_at": _now_iso(),
                "interactions": interactions,
                "feedback": feedback,
                "recommendations": recommendations,
                "settings": settings,
            }
        except Exception as exc:  # noqa: BLE001 - safe degrade
            logger.warning("export_user_data failed for %s: %s", user_id, exc)
            return empty

    def delete_user_data(self, user_id: str) -> int:
        """Delete all learning data for this user. Returns rows deleted.

        Never raises; returns 0 on failure.
        """
        try:
            if not self._available:
                return 0
            deleted = 0
            with self._with_conn() as conn:
                for table in ("interactions", "feedback", "recommendations", "settings"):
                    cur = conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
                    deleted += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
            return deleted
        except Exception as exc:  # noqa: BLE001 - safe degrade
            logger.warning("delete_user_data failed for %s: %s", user_id, exc)
            return 0

    def prune_expired(self) -> int:
        """Delete interactions and feedback older than the retention cap.

        Cross-cutting maintenance (not per-user). Returns total rows
        deleted. Never raises.
        """
        try:
            if not self._available:
                return 0
            cutoff = (_now() - timedelta(days=self.retention_days)).isoformat()
            deleted = 0
            with self._with_conn() as conn:
                for table in ("interactions", "feedback"):
                    cur = conn.execute(f"DELETE FROM {table} WHERE created_at < ?", (cutoff,))
                    deleted += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
            return deleted
        except Exception as exc:  # noqa: BLE001 - safe degrade
            logger.warning("prune_expired failed: %s", exc)
            return 0


def _safe_json(raw: Any, default: Any) -> Any:
    """Best-effort JSON decode with a fallback default."""
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return default


_store: Optional[LearningStore] = None
_store_lock = threading.Lock()


def get_learning_store() -> LearningStore:
    """Process-wide singleton, lazily created. Never raises."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = LearningStore()
    return _store
