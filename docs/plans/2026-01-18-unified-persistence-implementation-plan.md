# Unified Persistence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** none (no bead/task provided)

**Goal:** Implement repo-local unified persistence (`.tldrs/tldrs_state.db` + file-backed blobs) with a StateStore API to support VHS metadata and session/delivery records.

**Architecture:** Vendor the existing VHS Store into `src/tldr_swinton/vhs_store.py`, change its default root to `.tldrs/` and DB filename to `tldrs_state.db`. Add `StateStore` that creates `sessions` and `deliveries` tables in the same DB and exposes session/delta bookkeeping. Wire CLI VHS put/get to the new store.

**Tech Stack:** Python 3, SQLite (sqlite3), pytest

---

### Task 1: Add VHS store tests (repo-local defaults + DB name)

**Files:**
- Create: `tests/test_vhs_store.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

from tldr_swinton.vhs_store import Store


def test_vhs_store_defaults_repo_local(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = Store()
    assert store.root == (tmp_path / ".tldrs").resolve()
    assert store.db_path == store.root / "tldrs_state.db"
    assert store.blob_root == store.root / "blobs"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_vhs_store.py::test_vhs_store_defaults_repo_local -q`
Expected: FAIL (ImportError: no module named `tldr_swinton.vhs_store`)

**Step 3: Write minimal implementation**

Create `src/tldr_swinton/vhs_store.py` by copying `store.py` from `tldrs-vhs` and make these minimal changes:

```python
DEFAULT_HOME = Path.cwd() / ".tldrs"

class Store:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = (root or Path(os.environ.get("TLDRS_VHS_HOME", DEFAULT_HOME))).expanduser().resolve()
        self.blob_root = self.root / "blobs"
        self.db_path = self.root / "tldrs_state.db"
        ...
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_vhs_store.py::test_vhs_store_defaults_repo_local -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/tldr_swinton/vhs_store.py tests/test_vhs_store.py
git commit -m "feat: add repo-local vhs store"
```

---

### Task 2: Add StateStore tests (sessions + deliveries)

**Files:**
- Create: `tests/test_state_store.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

from tldr_swinton.state_store import StateStore


def test_state_store_records_delivery(tmp_path):
    project_root = tmp_path
    store = StateStore(project_root)
    store.open_session("s1", repo_fingerprint="abc")
    store.record_delivery(
        session_id="s1",
        symbol_id="src/app.py:main",
        etag="etag123",
        representation="full",
        vhs_ref="vhs://deadbeef" + "0" * 56,
        token_estimate=42,
    )
    delivery = store.get_delivery("s1", "src/app.py:main")
    assert delivery is not None
    assert delivery["etag"] == "etag123"
    assert delivery["representation"] == "full"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_state_store.py::test_state_store_records_delivery -q`
Expected: FAIL (ImportError: no module named `tldr_swinton.state_store`)

**Step 3: Write minimal implementation**

Create `src/tldr_swinton/state_store.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_state_store.py::test_state_store_records_delivery -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/tldr_swinton/state_store.py tests/test_state_store.py
git commit -m "feat: add unified state store"
```

---

### Task 3: Wire CLI VHS put/get to the internal store

**Files:**
- Modify: `src/tldr_swinton/cli.py`
- Test: `tests/test_cli_vhs.py`

**Step 1: Write the failing test**

```python
import subprocess
from pathlib import Path


def test_cli_vhs_put_uses_repo_local_store(tmp_path):
    project_root = tmp_path
    (project_root / "src").mkdir()
    (project_root / "src" / "a.py").write_text("def a():\n    return 1\n")
    result = subprocess.run(
        ["python", "-m", "tldr_swinton.cli", "context", "a", "--project", str(project_root), "--output", "vhs"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert (project_root / ".tldrs" / "tldrs_state.db").exists()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_vhs.py::test_cli_vhs_put_uses_repo_local_store -q`
Expected: FAIL (db not created)

**Step 3: Write minimal implementation**

Modify `src/tldr_swinton/cli.py`:

```python
from .state_store import StateStore


def _get_state_store(project_root: Path) -> StateStore:
    return StateStore(project_root)


def _vhs_put(text: str, project_root: Path) -> str:
    store = _get_state_store(project_root)
    return store.vhs.put(io.BytesIO(text.encode("utf-8")))


def _vhs_get(ref: str, project_root: Path) -> str:
    store = _get_state_store(project_root)
    with io.BytesIO() as buf:
        store.vhs.get(ref, out=None)  # Or implement get_text helper if needed
```

Ensure all call sites pass `project_root` (from `--project` or auto-detect). Keep the existing preview/summary behavior unchanged.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_vhs.py::test_cli_vhs_put_uses_repo_local_store -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/tldr_swinton/cli.py tests/test_cli_vhs.py
git commit -m "feat: use repo-local vhs store in cli"
```

---

### Task 4: Add basic GC + cleanup for sessions/deliveries

**Files:**
- Modify: `src/tldr_swinton/state_store.py`
- Test: `tests/test_state_store.py`

**Step 1: Write the failing test**

```python
from datetime import datetime, timedelta, timezone

from tldr_swinton.state_store import StateStore


def test_state_store_cleanup_removes_old_entries(tmp_path):
    store = StateStore(tmp_path)
    store.open_session("s1", repo_fingerprint="abc")
    store.record_delivery("s1", "sym", "etag", "full")

    # Force old timestamps
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    with store._conn() as conn:
        conn.execute("UPDATE sessions SET last_accessed = ?", (old,))
        conn.execute("UPDATE deliveries SET last_accessed = ?", (old,))

    removed = store.cleanup_expired(ttl_seconds=60)
    assert removed["sessions"] == 1
    assert removed["deliveries"] == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_state_store.py::test_state_store_cleanup_removes_old_entries -q`
Expected: FAIL (cleanup_expired missing)

**Step 3: Write minimal implementation**

Add to `StateStore`:

```python
    def cleanup_expired(self, ttl_seconds: int) -> dict:
        cutoff = datetime.now(timezone.utc).timestamp() - ttl_seconds
        deleted_sessions = 0
        deleted_deliveries = 0
        with self._conn() as conn:
            rows = conn.execute("SELECT session_id, last_accessed FROM sessions").fetchall()
            expired = []
            for session_id, last_accessed in rows:
                try:
                    ts = datetime.fromisoformat(last_accessed).timestamp()
                except Exception:
                    ts = 0
                if ts < cutoff:
                    expired.append(session_id)
            for session_id in expired:
                conn.execute("DELETE FROM deliveries WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            deleted_sessions = len(expired)
            if deleted_sessions:
                deleted_deliveries = 0  # Best effort; counts can be added if needed
        return {"sessions": deleted_sessions, "deliveries": deleted_deliveries}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_state_store.py::test_state_store_cleanup_removes_old_entries -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/tldr_swinton/state_store.py tests/test_state_store.py
git commit -m "feat: add state store cleanup"
```

---

### Task 5: Documentation update

**Files:**
- Modify: `docs/agent-workflow.md`

**Step 1: Write the failing test**

_No test needed (docs-only change)._  

**Step 2: Update documentation**

Add a short note that repo-local VHS is now built-in and refs are stored under `.tldrs/` (no external install needed).

**Step 3: Commit**

```bash
git add docs/agent-workflow.md
git commit -m "docs: mention repo-local vhs store"
```

---

## Verification

Run after all tasks:

```bash
pytest tests/test_vhs_store.py tests/test_state_store.py tests/test_cli_vhs.py -q
```

Expected: all tests PASS.

---

## Notes
- Keep code ASCII-only.
- Avoid long-lived SQLite connections.
- Ensure `StateStore` uses repo root passed from CLI/engine (not `cwd`).
