from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

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


@dataclass
class DeltaResult:
    """Result of checking symbols against session cache."""
    unchanged: set[str] = field(default_factory=set)
    changed: set[str] = field(default_factory=set)
    rehydrate: dict[str, str] = field(default_factory=dict)  # symbol_id -> vhs_ref


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

    def check_delta(
        self,
        session_id: str,
        symbol_etags: dict[str, str],
    ) -> DeltaResult:
        """Check which symbols are unchanged vs changed since last delivery.

        Args:
            session_id: Session identifier
            symbol_etags: Map of symbol_id -> current_etag

        Returns:
            DeltaResult with unchanged/changed sets and rehydration refs
        """
        result = DeltaResult()
        if not symbol_etags:
            return result

        with self._conn() as conn:
            placeholders = ",".join("?" for _ in symbol_etags)
            rows = conn.execute(
                f"""
                SELECT symbol_id, etag, vhs_ref
                FROM deliveries
                WHERE session_id = ? AND symbol_id IN ({placeholders})
                """,
                (session_id, *symbol_etags.keys()),
            ).fetchall()

        cached = {row[0]: (row[1], row[2]) for row in rows}

        for symbol_id, current_etag in symbol_etags.items():
            if symbol_id in cached:
                cached_etag, vhs_ref = cached[symbol_id]
                if cached_etag == current_etag:
                    result.unchanged.add(symbol_id)
                    if vhs_ref:
                        result.rehydrate[symbol_id] = vhs_ref
                else:
                    result.changed.add(symbol_id)
            else:
                result.changed.add(symbol_id)

        return result

    def record_deliveries_batch(
        self,
        session_id: str,
        deliveries: list[dict],
    ) -> None:
        """Record multiple deliveries in a single transaction.

        Args:
            session_id: Session identifier
            deliveries: List of dicts with keys: symbol_id, etag, representation, vhs_ref, token_estimate
        """
        now = self._now()
        with self._conn() as conn:
            conn.executemany(
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
                [
                    (
                        session_id,
                        d["symbol_id"],
                        d["etag"],
                        d["representation"],
                        d.get("vhs_ref"),
                        d.get("token_estimate"),
                        now,
                    )
                    for d in deliveries
                ],
            )

    def get_session_stats(self, session_id: str) -> dict:
        """Get statistics for a session."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(token_estimate), 0) FROM deliveries WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            session_row = conn.execute(
                "SELECT created_at, last_accessed FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()

        return {
            "session_id": session_id,
            "delivery_count": row[0] if row else 0,
            "total_tokens_delivered": row[1] if row else 0,
            "created_at": session_row[0] if session_row else None,
            "last_accessed": session_row[1] if session_row else None,
        }

    def get_or_create_default_session(self, default_language: str | None = None) -> str:
        """Get or create a default session for this repo.

        The default session ID is stable across CLI invocations.
        """
        session_file = self.root / "default_session_id"
        if session_file.exists():
            session_id = session_file.read_text().strip()
            if session_id:
                # Touch session to update last_accessed
                fingerprint = _compute_repo_fingerprint(self.project_root)
                self.open_session(session_id, fingerprint, default_language)
                return session_id

        # Generate new session ID
        session_id = hashlib.sha256(os.urandom(32)).hexdigest()[:16]
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.write_text(session_id)

        fingerprint = _compute_repo_fingerprint(self.project_root)
        self.open_session(session_id, fingerprint, default_language)
        return session_id


def _compute_repo_fingerprint(project_root: Path) -> str:
    """Compute a fingerprint for the repo state.

    Uses git HEAD if available, otherwise hashes directory mtime.
    """
    git_dir = project_root / ".git"
    if git_dir.exists():
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return f"git:{result.stdout.strip()[:12]}"
        except Exception:
            pass

    # Fallback: hash of directory mtime
    try:
        mtime = project_root.stat().st_mtime
        return f"mtime:{int(mtime)}"
    except Exception:
        return "unknown"
