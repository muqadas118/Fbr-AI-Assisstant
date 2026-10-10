"""
Vault Store
===========

SQLite-backed persistent storage for user tax documents (Tax Vault).
One small table, one connection-per-call (cheap at this scale), WAL mode.

The dev/prod database split documented in CLAUDE.md is SQLite -> PostgreSQL;
this module isolates all SQL so a PostgreSQL adapter can replace it later.
"""

import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("fbr_vault")

_DEFAULT_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_DB_PATH = os.environ.get("FBR_VAULT_DB", os.path.join(_DEFAULT_DB_DIR, "vault.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vault_documents (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    filename    TEXT NOT NULL,
    doc_type    TEXT NOT NULL DEFAULT 'Other',
    content     TEXT NOT NULL DEFAULT '',
    secure      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vault_user ON vault_documents (user_id, created_at DESC);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


class VaultStore:
    """Persistent key documents per user. Thread-safe via per-call connections."""

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _DB_PATH
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
        logger.info("Vault store ready at %s", self._db_path)

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # ------------------------------------------------------------------
    # Row -> dict
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "filename": row["filename"],
            "type": row["doc_type"],
            "content": row["content"],
            "size": f"{len(row['content'])} chars",
            "secure": bool(row["secure"]),
            "date": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add_document(
        self,
        user_id: str,
        filename: str,
        doc_type: str = "Other",
        content: str = "",
        secure: bool = True,
    ) -> dict[str, Any]:
        doc_id = f"vault-{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO vault_documents
                    (id, user_id, filename, doc_type, content, secure, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (doc_id, user_id, filename, doc_type, content, int(secure), now, now),
            )
        return self.get_document(doc_id, user_id)  # type: ignore[return-value]

    def list_documents(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM vault_documents
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [self._to_dict(r) for r in rows]

    def get_document(self, doc_id: str, user_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM vault_documents WHERE id = ? AND user_id = ?",
                (doc_id, user_id),
            ).fetchone()
        return self._to_dict(row) if row else None

    def update_document(
        self,
        doc_id: str,
        user_id: str,
        filename: Optional[str] = None,
        doc_type: Optional[str] = None,
        content: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        fields: list[str] = []
        params: list[Any] = []
        if filename is not None:
            fields.append("filename = ?")
            params.append(filename)
        if doc_type is not None:
            fields.append("doc_type = ?")
            params.append(doc_type)
        if content is not None:
            fields.append("content = ?")
            params.append(content)
        if not fields:
            return self.get_document(doc_id, user_id)
        fields.append("updated_at = ?")
        params.append(_now_iso())
        params.extend([doc_id, user_id])
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                f"UPDATE vault_documents SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
                params,
            )
            if cur.rowcount == 0:
                return None
        return self.get_document(doc_id, user_id)

    def delete_document(self, doc_id: str, user_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM vault_documents WHERE id = ? AND user_id = ?",
                (doc_id, user_id),
            )
            return cur.rowcount > 0

    def count_documents(self, user_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM vault_documents WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return int(row["n"]) if row else 0


_store: Optional[VaultStore] = None
_store_lock = threading.Lock()


def get_vault_store() -> VaultStore:
    """Process-wide singleton."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = VaultStore()
    return _store
