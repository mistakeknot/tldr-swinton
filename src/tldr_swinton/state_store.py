from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .vhs_store import Store as VHSStore


@dataclass
class Delivery:
    session_id: str
    symbol_id: str
    etag: str
    representation: str
    vhs_ref: str | None
    token_estimate: int | None
    last_accessed: str


class StateStore:
    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.root = self.project_root / ".tldrs"
        self.vhs = VHSStore(root=self.root)
        self.db_path = self.vhs.db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    last_accessed TEXT NOT NULL,
                    repo_fingerprint TEXT NOT NULL,
                    default_language TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS deliveries (
                    session_id TEXT NOT NULL,
                    symbol_id TEXT NOT NULL,
                    etag TEXT NOT NULL,
                    representation TEXT NOT NULL,
                    vhs_ref TEXT,
                    token_estimate INTEGER,
                    last_accessed TEXT NOT NULL,
                    PRIMARY KEY(session_id, symbol_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_deliveries_last_accessed ON deliveries(last_accessed)"
            )

    def open_session(self, session_id: str, repo_fingerprint: str, default_language: str | None = None) -> None:
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO sessions
                (session_id, created_at, last_accessed, repo_fingerprint, default_language)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, now, now, repo_fingerprint, default_language),
            )
            conn.execute(
                "UPDATE sessions SET last_accessed = ? WHERE session_id = ?",
                (now, session_id),
            )

    def record_delivery(
        self,
        session_id: str,
        symbol_id: str,
        etag: str,
        representation: str,
        vhs_ref: str | None = None,
        token_estimate: int | None = None,
    ) -> None:
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO deliveries
                (session_id, symbol_id, etag, representation, vhs_ref, token_estimate, last_accessed)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, symbol_id) DO UPDATE SET
                    etag = excluded.etag,
                    representation = excluded.representation,
                    vhs_ref = excluded.vhs_ref,
                    token_estimate = excluded.token_estimate,
                    last_accessed = excluded.last_accessed
                """,
                (session_id, symbol_id, etag, representation, vhs_ref, token_estimate, now),
            )

    def get_delivery(self, session_id: str, symbol_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT session_id, symbol_id, etag, representation, vhs_ref, token_estimate, last_accessed
                FROM deliveries WHERE session_id = ? AND symbol_id = ?
                """,
                (session_id, symbol_id),
            ).fetchone()
        if not row:
            return None
        keys = [
            "session_id",
            "symbol_id",
            "etag",
            "representation",
            "vhs_ref",
            "token_estimate",
            "last_accessed",
        ]
        return dict(zip(keys, row))

    def cleanup_expired(self, ttl_seconds: int) -> dict:
        cutoff = datetime.now(timezone.utc).timestamp() - ttl_seconds
        deleted_sessions = 0
        deleted_deliveries = 0
        with self._conn() as conn:
            rows = conn.execute("SELECT session_id, last_accessed FROM sessions").fetchall()
            expired: list[str] = []
            for session_id, last_accessed in rows:
                try:
                    ts = datetime.fromisoformat(last_accessed).timestamp()
                except Exception:
                    ts = 0
                if ts < cutoff:
                    expired.append(session_id)
            for session_id in expired:
                delivery_count = conn.execute(
                    "SELECT COUNT(*) FROM deliveries WHERE session_id = ?",
                    (session_id,),
                ).fetchone()[0]
                conn.execute("DELETE FROM deliveries WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                deleted_sessions += 1
                deleted_deliveries += int(delivery_count)
        return {"sessions": deleted_sessions, "deliveries": deleted_deliveries}
