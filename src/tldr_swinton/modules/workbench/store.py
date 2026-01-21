"""Storage layer for tldrs-workbench.

Provides SQLite for metadata and content-addressed blob storage for large content.
"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from .capsule import Capsule

# Default threshold for inline vs blob storage (4KB)
BLOB_THRESHOLD = 4096

# Schema version for migrations
SCHEMA_VERSION = 4


def get_workbench_dir(project_root: Path | None = None) -> Path:
    """Get the .workbench directory, creating if needed."""
    root = project_root or Path.cwd()
    workbench_dir = root / ".workbench"
    return workbench_dir


class WorkbenchStore:
    """SQLite + blob storage for workbench artifacts."""

    def __init__(self, project_root: Path | None = None) -> None:
        """Initialize store for a project.

        Args:
            project_root: Project root directory. Uses cwd if not specified.
        """
        self.workbench_dir = get_workbench_dir(project_root)
        self.db_path = self.workbench_dir / "state.db"
        self.blob_dir = self.workbench_dir / "blobs"
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        """Ensure storage directories and database exist."""
        self.workbench_dir.mkdir(parents=True, exist_ok=True)
        self.blob_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._connect() as conn:
            # Check if we need to initialize
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='meta'"
            )
            if cursor.fetchone() is None:
                self._create_schema(conn)
            else:
                # Check for migrations
                self._migrate_schema(conn)

    def _create_schema(self, conn: sqlite3.Connection) -> None:
        """Create initial database schema."""
        conn.executescript("""
            -- Meta table for schema version
            CREATE TABLE meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            -- Capsules table (Phase 1)
            CREATE TABLE capsules (
                id TEXT PRIMARY KEY,
                command TEXT NOT NULL,
                cwd TEXT NOT NULL,
                env_fingerprint TEXT NOT NULL,
                exit_code INTEGER NOT NULL,
                stdout_ref TEXT,
                stdout_inline TEXT,
                stderr_ref TEXT,
                stderr_inline TEXT,
                started_at TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            -- Index for listing by time
            CREATE INDEX idx_capsules_created ON capsules(created_at DESC);

            -- Index for filtering by exit code
            CREATE INDEX idx_capsules_exit_code ON capsules(exit_code);

            -- Index for command search
            CREATE INDEX idx_capsules_command ON capsules(command);

            -- Decisions table (Phase 2)
            CREATE TABLE decisions (
                id TEXT PRIMARY KEY,
                statement TEXT NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL,
                superseded_by TEXT REFERENCES decisions(id)
            );

            -- Index for listing active decisions
            CREATE INDEX idx_decisions_created ON decisions(created_at DESC);
            CREATE INDEX idx_decisions_active ON decisions(superseded_by);

            -- Decision symbol refs (Phase 2)
            CREATE TABLE decision_refs (
                decision_id TEXT NOT NULL REFERENCES decisions(id),
                symbol_id TEXT NOT NULL,
                PRIMARY KEY (decision_id, symbol_id)
            );
            CREATE INDEX idx_decision_refs_symbol ON decision_refs(symbol_id);

            -- Hypotheses table (Phase 3)
            CREATE TABLE hypotheses (
                id TEXT PRIMARY KEY,
                statement TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                test TEXT,
                disconfirmer TEXT,
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                resolution_note TEXT
            );

            -- Index for listing by status and time
            CREATE INDEX idx_hypotheses_created ON hypotheses(created_at DESC);
            CREATE INDEX idx_hypotheses_status ON hypotheses(status);

            -- Hypothesis evidence links (Phase 3)
            CREATE TABLE hypothesis_evidence (
                hypothesis_id TEXT NOT NULL REFERENCES hypotheses(id),
                artifact_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                relation TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (hypothesis_id, artifact_id)
            );
            CREATE INDEX idx_hypothesis_evidence_artifact ON hypothesis_evidence(artifact_id);

            -- Generic links table (Phase 4)
            CREATE TABLE links (
                src_id TEXT NOT NULL,
                src_type TEXT NOT NULL,
                dst_id TEXT NOT NULL,
                dst_type TEXT NOT NULL,
                relation TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (src_id, dst_id, relation)
            );
            CREATE INDEX idx_links_src ON links(src_id, src_type);
            CREATE INDEX idx_links_dst ON links(dst_id, dst_type);
            CREATE INDEX idx_links_relation ON links(relation);
        """)
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        """Apply schema migrations if needed."""
        cursor = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'")
        row = cursor.fetchone()
        current_version = int(row["value"]) if row else 1

        if current_version < 2:
            # Migration: Add decisions tables
            conn.executescript("""
                -- Decisions table (Phase 2)
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    statement TEXT NOT NULL,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    superseded_by TEXT REFERENCES decisions(id)
                );

                -- Index for listing active decisions
                CREATE INDEX IF NOT EXISTS idx_decisions_created ON decisions(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_decisions_active ON decisions(superseded_by);

                -- Decision symbol refs (Phase 2)
                CREATE TABLE IF NOT EXISTS decision_refs (
                    decision_id TEXT NOT NULL REFERENCES decisions(id),
                    symbol_id TEXT NOT NULL,
                    PRIMARY KEY (decision_id, symbol_id)
                );
                CREATE INDEX IF NOT EXISTS idx_decision_refs_symbol ON decision_refs(symbol_id);
            """)
            current_version = 2

        if current_version < 3:
            # Migration: Add hypotheses tables
            conn.executescript("""
                -- Hypotheses table (Phase 3)
                CREATE TABLE IF NOT EXISTS hypotheses (
                    id TEXT PRIMARY KEY,
                    statement TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    test TEXT,
                    disconfirmer TEXT,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    resolution_note TEXT
                );

                -- Index for listing by status and time
                CREATE INDEX IF NOT EXISTS idx_hypotheses_created
                    ON hypotheses(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_hypotheses_status ON hypotheses(status);

                -- Hypothesis evidence links (Phase 3)
                CREATE TABLE IF NOT EXISTS hypothesis_evidence (
                    hypothesis_id TEXT NOT NULL REFERENCES hypotheses(id),
                    artifact_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (hypothesis_id, artifact_id)
                );
                CREATE INDEX IF NOT EXISTS idx_hypothesis_evidence_artifact
                    ON hypothesis_evidence(artifact_id);
            """)
            current_version = 3

        if current_version < 4:
            # Migration: Add generic links table (Phase 4)
            conn.executescript("""
                -- Generic links table (Phase 4)
                CREATE TABLE IF NOT EXISTS links (
                    src_id TEXT NOT NULL,
                    src_type TEXT NOT NULL,
                    dst_id TEXT NOT NULL,
                    dst_type TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (src_id, dst_id, relation)
                );
                CREATE INDEX IF NOT EXISTS idx_links_src ON links(src_id, src_type);
                CREATE INDEX IF NOT EXISTS idx_links_dst ON links(dst_id, dst_type);
                CREATE INDEX IF NOT EXISTS idx_links_relation ON links(relation);
            """)

        conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            (str(SCHEMA_VERSION),),
        )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Get a database connection with proper settings."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # Blob storage

    def store_blob(self, content: bytes) -> str:
        """Store content in blob storage, return blob ref.

        Args:
            content: Bytes to store.

        Returns:
            Blob reference string (blob:<sha256>).
        """
        hash_hex = hashlib.sha256(content).hexdigest()
        # Use first 2 chars as subdirectory for filesystem efficiency
        subdir = self.blob_dir / hash_hex[:2]
        blob_path = subdir / hash_hex
        if not blob_path.exists():
            subdir.mkdir(parents=True, exist_ok=True)
            blob_path.write_bytes(content)
        return f"blob:{hash_hex}"

    def load_blob(self, ref: str) -> bytes:
        """Load content from blob ref.

        Args:
            ref: Blob reference (blob:<sha256>).

        Returns:
            Blob content as bytes.

        Raises:
            FileNotFoundError: If blob doesn't exist.
        """
        hash_hex = ref.removeprefix("blob:")
        blob_path = self.blob_dir / hash_hex[:2] / hash_hex
        return blob_path.read_bytes()

    def should_use_blob(self, content: str) -> bool:
        """Check if content should be stored as blob."""
        return len(content.encode("utf-8")) > BLOB_THRESHOLD

    # Capsule storage

    def store_capsule(self, capsule: Capsule) -> str:
        """Store a capsule in the database.

        Args:
            capsule: Capsule to store.

        Returns:
            Capsule ID.
        """
        # Handle stdout - inline or blob
        stdout_ref = None
        stdout_inline = None
        if capsule.stdout:
            if self.should_use_blob(capsule.stdout):
                stdout_ref = self.store_blob(capsule.stdout.encode("utf-8"))
            else:
                stdout_inline = capsule.stdout

        # Handle stderr - inline or blob
        stderr_ref = None
        stderr_inline = None
        if capsule.stderr:
            if self.should_use_blob(capsule.stderr):
                stderr_ref = self.store_blob(capsule.stderr.encode("utf-8"))
            else:
                stderr_inline = capsule.stderr

        created_at = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO capsules (
                    id, command, cwd, env_fingerprint, exit_code,
                    stdout_ref, stdout_inline, stderr_ref, stderr_inline,
                    started_at, duration_ms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    capsule.id,
                    capsule.command,
                    capsule.cwd,
                    capsule.env_fingerprint,
                    capsule.exit_code,
                    stdout_ref,
                    stdout_inline,
                    stderr_ref,
                    stderr_inline,
                    capsule.started_at.isoformat(),
                    capsule.duration_ms,
                    created_at,
                ),
            )

        return capsule.id

    def get_capsule(self, capsule_id: str) -> dict | None:
        """Get a capsule by ID.

        Args:
            capsule_id: Capsule ID (with or without 'capsule:' prefix).

        Returns:
            Capsule data as dict, or None if not found.
        """
        # Strip prefix if present
        if capsule_id.startswith("capsule:"):
            capsule_id = capsule_id[8:]

        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM capsules WHERE id = ? OR id LIKE ?",
                (capsule_id, f"{capsule_id}%"),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            result = dict(row)

            # Resolve stdout
            if result["stdout_ref"]:
                result["stdout"] = self.load_blob(result["stdout_ref"]).decode("utf-8")
            else:
                result["stdout"] = result["stdout_inline"] or ""

            # Resolve stderr
            if result["stderr_ref"]:
                result["stderr"] = self.load_blob(result["stderr_ref"]).decode("utf-8")
            else:
                result["stderr"] = result["stderr_inline"] or ""

            return result

    def list_capsules(
        self,
        limit: int = 20,
        failed_only: bool = False,
        command_filter: str | None = None,
    ) -> list[dict]:
        """List capsules with optional filters.

        Args:
            limit: Max number of capsules to return.
            failed_only: Only show capsules with non-zero exit code.
            command_filter: Filter by command substring.

        Returns:
            List of capsule dicts (without full stdout/stderr).
        """
        query = """
            SELECT id, command, cwd, exit_code, started_at, duration_ms, created_at
            FROM capsules
        """.strip()
        conditions = []
        params: list = []

        if failed_only:
            conditions.append("exit_code != 0")

        if command_filter:
            conditions.append("command LIKE ?")
            params.append(f"%{command_filter}%")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def capsule_exists(self, capsule_id: str) -> bool:
        """Check if a capsule exists."""
        if capsule_id.startswith("capsule:"):
            capsule_id = capsule_id[8:]

        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM capsules WHERE id = ? OR id LIKE ?",
                (capsule_id, f"{capsule_id}%"),
            )
            return cursor.fetchone() is not None

    # Decision storage (Phase 2)

    def store_decision(self, decision: "Decision") -> str:  # noqa: F821
        """Store a decision in the database.

        Args:
            decision: Decision to store.

        Returns:
            Decision ID.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO decisions (id, statement, reason, created_at, superseded_by)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    decision.id,
                    decision.statement,
                    decision.reason,
                    decision.created_at.isoformat(),
                    decision.superseded_by,
                ),
            )

            # Store symbol refs
            for ref in decision.refs:
                conn.execute(
                    "INSERT INTO decision_refs (decision_id, symbol_id) VALUES (?, ?)",
                    (decision.id, ref),
                )

        return decision.id

    def get_decision(self, decision_id: str) -> dict | None:
        """Get a decision by ID.

        Args:
            decision_id: Decision ID (with or without 'dec-' prefix).

        Returns:
            Decision data as dict, or None if not found.
        """
        # Normalize ID - handle various formats
        if decision_id.startswith("decision:"):
            decision_id = decision_id[9:]

        # Ensure dec- prefix for matching
        if not decision_id.startswith("dec-"):
            decision_id = f"dec-{decision_id}"

        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM decisions WHERE id = ? OR id LIKE ?",
                (decision_id, f"{decision_id}%"),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            result = dict(row)

            # Get symbol refs
            refs_cursor = conn.execute(
                "SELECT symbol_id FROM decision_refs WHERE decision_id = ?",
                (result["id"],),
            )
            result["refs"] = [r["symbol_id"] for r in refs_cursor.fetchall()]

            return result

    def list_decisions(
        self,
        limit: int = 20,
        include_superseded: bool = False,
        refs_filter: str | None = None,
    ) -> list[dict]:
        """List decisions with optional filters.

        Args:
            limit: Max number of decisions to return.
            include_superseded: Include superseded decisions.
            refs_filter: Filter by symbol ref pattern (supports * wildcard).

        Returns:
            List of decision dicts.
        """
        query = "SELECT * FROM decisions"
        conditions = []
        params: list = []

        if not include_superseded:
            conditions.append("superseded_by IS NULL")

        if refs_filter:
            # Join with decision_refs to filter by symbol
            query = """
                SELECT DISTINCT d.* FROM decisions d
                JOIN decision_refs r ON d.id = r.decision_id
            """
            # Convert * wildcard to SQL LIKE pattern
            pattern = refs_filter.replace("*", "%")
            conditions.append("r.symbol_id LIKE ?")
            params.append(pattern)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            cursor = conn.execute(query, params)
            results = []
            for row in cursor.fetchall():
                d = dict(row)
                # Get refs for each decision
                refs_cursor = conn.execute(
                    "SELECT symbol_id FROM decision_refs WHERE decision_id = ?",
                    (d["id"],),
                )
                d["refs"] = [r["symbol_id"] for r in refs_cursor.fetchall()]
                results.append(d)
            return results

    def supersede_decision(
        self,
        old_decision_id: str,
        new_statement: str,
        new_reason: str | None = None,
    ) -> str:
        """Supersede an existing decision with a new one.

        Args:
            old_decision_id: ID of decision to supersede.
            new_statement: Statement for the new decision.
            new_reason: Optional reason for the new decision.

        Returns:
            New decision ID.

        Raises:
            ValueError: If old decision not found or already superseded.
        """
        from .decision import Decision

        old = self.get_decision(old_decision_id)
        if old is None:
            raise ValueError(f"Decision not found: {old_decision_id}")

        if old["superseded_by"] is not None:
            raise ValueError(
                f"Decision {old['id']} already superseded by {old['superseded_by']}"
            )

        # Create new decision with same refs
        new_decision = Decision.create(
            statement=new_statement,
            reason=new_reason,
            refs=old["refs"],
        )

        # Store new decision
        self.store_decision(new_decision)

        # Update old decision to point to new one
        with self._connect() as conn:
            conn.execute(
                "UPDATE decisions SET superseded_by = ? WHERE id = ?",
                (new_decision.id, old["id"]),
            )

        return new_decision.id

    def decision_exists(self, decision_id: str) -> bool:
        """Check if a decision exists."""
        return self.get_decision(decision_id) is not None

    # Hypothesis storage (Phase 3)

    def store_hypothesis(self, hypothesis: "Hypothesis") -> str:  # noqa: F821
        """Store a hypothesis in the database.

        Args:
            hypothesis: Hypothesis to store.

        Returns:
            Hypothesis ID.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO hypotheses (
                    id, statement, status, test, disconfirmer,
                    created_at, resolved_at, resolution_note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hypothesis.id,
                    hypothesis.statement,
                    hypothesis.status.value,
                    hypothesis.test,
                    hypothesis.disconfirmer,
                    hypothesis.created_at.isoformat(),
                    hypothesis.resolved_at.isoformat() if hypothesis.resolved_at else None,
                    hypothesis.resolution_note,
                ),
            )

        return hypothesis.id

    def get_hypothesis(self, hypothesis_id: str) -> dict | None:
        """Get a hypothesis by ID.

        Args:
            hypothesis_id: Hypothesis ID (with or without 'hyp-' prefix).

        Returns:
            Hypothesis data as dict, or None if not found.
        """
        # Normalize ID
        if hypothesis_id.startswith("hypothesis:"):
            hypothesis_id = hypothesis_id[11:]

        if not hypothesis_id.startswith("hyp-"):
            hypothesis_id = f"hyp-{hypothesis_id}"

        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM hypotheses WHERE id = ? OR id LIKE ?",
                (hypothesis_id, f"{hypothesis_id}%"),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            result = dict(row)

            # Get evidence links
            evidence_cursor = conn.execute(
                """
                SELECT artifact_id, artifact_type, relation, created_at
                FROM hypothesis_evidence WHERE hypothesis_id = ?
                """,
                (result["id"],),
            )
            result["evidence"] = [dict(e) for e in evidence_cursor.fetchall()]

            return result

    def list_hypotheses(
        self,
        limit: int = 20,
        status_filter: str | None = None,
        include_resolved: bool = False,
    ) -> list[dict]:
        """List hypotheses with optional filters.

        Args:
            limit: Max number of hypotheses to return.
            status_filter: Filter by specific status ('active', 'confirmed', 'falsified').
            include_resolved: Include resolved hypotheses (if no status_filter).

        Returns:
            List of hypothesis dicts.
        """
        query = "SELECT * FROM hypotheses"
        conditions = []
        params: list = []

        if status_filter:
            conditions.append("status = ?")
            params.append(status_filter)
        elif not include_resolved:
            conditions.append("status = 'active'")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            cursor = conn.execute(query, params)
            results = []
            for row in cursor.fetchall():
                h = dict(row)
                # Get evidence for each hypothesis
                evidence_cursor = conn.execute(
                    """
                    SELECT artifact_id, artifact_type, relation, created_at
                    FROM hypothesis_evidence WHERE hypothesis_id = ?
                    """,
                    (h["id"],),
                )
                h["evidence"] = [dict(e) for e in evidence_cursor.fetchall()]
                results.append(h)
            return results

    def confirm_hypothesis(
        self,
        hypothesis_id: str,
        note: str | None = None,
        evidence_id: str | None = None,
    ) -> None:
        """Mark a hypothesis as confirmed.

        Args:
            hypothesis_id: ID of hypothesis to confirm.
            note: Optional resolution note.
            evidence_id: Optional evidence artifact ID.

        Raises:
            ValueError: If hypothesis not found or already resolved.
        """
        hyp = self.get_hypothesis(hypothesis_id)
        if hyp is None:
            raise ValueError(f"Hypothesis not found: {hypothesis_id}")

        if hyp["status"] != "active":
            raise ValueError(
                f"Hypothesis {hyp['id']} already resolved as {hyp['status']}"
            )

        resolved_at = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE hypotheses
                SET status = 'confirmed', resolved_at = ?, resolution_note = ?
                WHERE id = ?
                """,
                (resolved_at, note, hyp["id"]),
            )

            # Add evidence link if provided
            if evidence_id:
                self._add_evidence(conn, hyp["id"], evidence_id, "supports")

    def falsify_hypothesis(
        self,
        hypothesis_id: str,
        note: str | None = None,
        evidence_id: str | None = None,
    ) -> None:
        """Mark a hypothesis as falsified.

        Args:
            hypothesis_id: ID of hypothesis to falsify.
            note: Optional resolution note.
            evidence_id: Optional evidence artifact ID.

        Raises:
            ValueError: If hypothesis not found or already resolved.
        """
        hyp = self.get_hypothesis(hypothesis_id)
        if hyp is None:
            raise ValueError(f"Hypothesis not found: {hypothesis_id}")

        if hyp["status"] != "active":
            raise ValueError(
                f"Hypothesis {hyp['id']} already resolved as {hyp['status']}"
            )

        resolved_at = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE hypotheses
                SET status = 'falsified', resolved_at = ?, resolution_note = ?
                WHERE id = ?
                """,
                (resolved_at, note, hyp["id"]),
            )

            # Add evidence link if provided
            if evidence_id:
                self._add_evidence(conn, hyp["id"], evidence_id, "falsifies")

    def add_evidence(
        self,
        hypothesis_id: str,
        artifact_id: str,
        relation: str = "supports",
    ) -> None:
        """Add evidence link to a hypothesis.

        Args:
            hypothesis_id: Hypothesis ID.
            artifact_id: Evidence artifact ID (e.g., 'capsule:abc123').
            relation: 'supports' or 'falsifies'.

        Raises:
            ValueError: If hypothesis not found.
        """
        hyp = self.get_hypothesis(hypothesis_id)
        if hyp is None:
            raise ValueError(f"Hypothesis not found: {hypothesis_id}")

        with self._connect() as conn:
            self._add_evidence(conn, hyp["id"], artifact_id, relation)

    def _add_evidence(
        self,
        conn: sqlite3.Connection,
        hypothesis_id: str,
        artifact_id: str,
        relation: str,
    ) -> None:
        """Internal: Add evidence link within a transaction."""
        from .hypothesis import parse_artifact_ref

        artifact_type, artifact_id_clean = parse_artifact_ref(artifact_id)
        created_at = datetime.now(timezone.utc).isoformat()

        conn.execute(
            """
            INSERT OR REPLACE INTO hypothesis_evidence
            (hypothesis_id, artifact_id, artifact_type, relation, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (hypothesis_id, artifact_id_clean, artifact_type, relation, created_at),
        )

    def hypothesis_exists(self, hypothesis_id: str) -> bool:
        """Check if a hypothesis exists."""
        return self.get_hypothesis(hypothesis_id) is not None

    # Link methods (Phase 4)

    def create_link(
        self,
        src_id: str,
        src_type: str,
        dst_id: str,
        dst_type: str,
        relation: str,
    ) -> None:
        """Create a link between two artifacts.

        Args:
            src_id: Source artifact ID.
            src_type: Source artifact type (capsule, decision, hypothesis, symbol, patch, task).
            dst_id: Destination artifact ID.
            dst_type: Destination artifact type.
            relation: Relationship type (evidence, falsifies, implements,
                refs, supersedes, related).

        Raises:
            ValueError: If link already exists.
        """
        created_at = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO links (src_id, src_type, dst_id, dst_type, relation, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (src_id, src_type, dst_id, dst_type, relation, created_at),
                )
            except sqlite3.IntegrityError:
                raise ValueError(
                    f"Link already exists: {src_type}:{src_id} --{relation}--> {dst_type}:{dst_id}"
                )

    def delete_link(
        self,
        src_id: str,
        dst_id: str,
        relation: str,
    ) -> bool:
        """Delete a link between two artifacts.

        Args:
            src_id: Source artifact ID.
            dst_id: Destination artifact ID.
            relation: Relationship type.

        Returns:
            True if link was deleted, False if it didn't exist.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM links WHERE src_id = ? AND dst_id = ? AND relation = ?",
                (src_id, dst_id, relation),
            )
            return cursor.rowcount > 0

    def get_outgoing_links(
        self,
        artifact_id: str,
        artifact_type: str | None = None,
        relation: str | None = None,
    ) -> list[dict]:
        """Get links originating from an artifact.

        Args:
            artifact_id: Source artifact ID.
            artifact_type: Optional filter by source type.
            relation: Optional filter by relation.

        Returns:
            List of link dicts.
        """
        query = "SELECT * FROM links WHERE src_id = ?"
        params: list = [artifact_id]

        if artifact_type:
            query += " AND src_type = ?"
            params.append(artifact_type)

        if relation:
            query += " AND relation = ?"
            params.append(relation)

        query += " ORDER BY created_at DESC"

        with self._connect() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_incoming_links(
        self,
        artifact_id: str,
        artifact_type: str | None = None,
        relation: str | None = None,
    ) -> list[dict]:
        """Get links pointing to an artifact.

        Args:
            artifact_id: Destination artifact ID.
            artifact_type: Optional filter by destination type.
            relation: Optional filter by relation.

        Returns:
            List of link dicts.
        """
        query = "SELECT * FROM links WHERE dst_id = ?"
        params: list = [artifact_id]

        if artifact_type:
            query += " AND dst_type = ?"
            params.append(artifact_type)

        if relation:
            query += " AND relation = ?"
            params.append(relation)

        query += " ORDER BY created_at DESC"

        with self._connect() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_all_links(
        self,
        relation: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get all links, optionally filtered by relation.

        Args:
            relation: Optional filter by relation.
            limit: Maximum number of links to return.

        Returns:
            List of link dicts.
        """
        query = "SELECT * FROM links"
        params: list = []

        if relation:
            query += " WHERE relation = ?"
            params.append(relation)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_artifact_graph(
        self,
        artifact_id: str,
        artifact_type: str,
        depth: int = 1,
    ) -> dict:
        """Get a subgraph around an artifact.

        Args:
            artifact_id: Central artifact ID.
            artifact_type: Central artifact type.
            depth: How many hops to traverse (default 1).

        Returns:
            Dict with 'nodes' (list of artifacts) and 'edges' (list of links).
        """
        nodes: dict[str, dict] = {}  # id -> artifact info
        edges: list[dict] = []
        visited: set[tuple[str, str]] = set()

        def traverse(aid: str, atype: str, current_depth: int) -> None:
            if current_depth > depth:
                return
            key = (aid, atype)
            if key in visited:
                return
            visited.add(key)

            # Add node
            nodes[f"{atype}:{aid}"] = {"id": aid, "type": atype}

            # Get outgoing links
            outgoing = self.get_outgoing_links(aid, atype)
            for link in outgoing:
                edges.append(link)
                traverse(link["dst_id"], link["dst_type"], current_depth + 1)

            # Get incoming links
            incoming = self.get_incoming_links(aid, atype)
            for link in incoming:
                edges.append(link)
                traverse(link["src_id"], link["src_type"], current_depth + 1)

        traverse(artifact_id, artifact_type, 0)

        # Deduplicate edges
        seen_edges: set[tuple[str, str, str]] = set()
        unique_edges = []
        for edge in edges:
            key = (edge["src_id"], edge["dst_id"], edge["relation"])
            if key not in seen_edges:
                seen_edges.add(key)
                unique_edges.append(edge)

        return {
            "nodes": list(nodes.values()),
            "edges": unique_edges,
        }

    # Export methods (Phase 4)

    def export_artifact(self, artifact_id: str, artifact_type: str) -> dict | None:
        """Export a single artifact with its links.

        Args:
            artifact_id: Artifact ID.
            artifact_type: Artifact type.

        Returns:
            Dict with artifact data and links, or None if not found.
        """
        # Get the artifact
        artifact = None
        if artifact_type == "capsule":
            artifact = self.get_capsule(artifact_id)
        elif artifact_type == "decision":
            artifact = self.get_decision(artifact_id)
        elif artifact_type == "hypothesis":
            artifact = self.get_hypothesis(artifact_id)

        if artifact is None:
            return None

        # Get links
        outgoing = self.get_outgoing_links(artifact_id, artifact_type)
        incoming = self.get_incoming_links(artifact_id, artifact_type)

        return {
            "type": artifact_type,
            "data": artifact,
            "outgoing_links": outgoing,
            "incoming_links": incoming,
        }

    def export_timeline(
        self,
        artifact_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Export a timeline of artifacts sorted by creation time.

        Args:
            artifact_types: Filter by artifact types (default: all).
            limit: Maximum artifacts per type.

        Returns:
            List of artifact dicts sorted by created_at descending.
        """
        types = artifact_types or ["capsule", "decision", "hypothesis"]
        timeline: list[dict] = []

        if "capsule" in types:
            capsules = self.list_capsules(limit=limit)
            for cap in capsules:
                timeline.append({
                    "type": "capsule",
                    "id": cap["id"],
                    "created_at": cap["created_at"],
                    "summary": cap["command"],
                    "data": cap,
                })

        if "decision" in types:
            decisions = self.list_decisions(limit=limit, include_superseded=True)
            for dec in decisions:
                timeline.append({
                    "type": "decision",
                    "id": dec["id"],
                    "created_at": dec["created_at"],
                    "summary": dec["statement"],
                    "data": dec,
                })

        if "hypothesis" in types:
            hypotheses = self.list_hypotheses(limit=limit, include_resolved=True)
            for hyp in hypotheses:
                timeline.append({
                    "type": "hypothesis",
                    "id": hyp["id"],
                    "created_at": hyp["created_at"],
                    "summary": hyp["statement"],
                    "data": hyp,
                })

        # Sort by created_at descending
        timeline.sort(key=lambda x: x["created_at"], reverse=True)

        return timeline[:limit]
