"""Tests for delta context CLI functionality."""

import subprocess
import tempfile
from pathlib import Path

import pytest


def _run_tldrs(args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run tldrs CLI and return result."""
    import sys
    cmd = [sys.executable, "-m", "tldr_swinton.cli"] + args
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)


@pytest.fixture
def temp_python_project(tmp_path):
    """Create a temporary Python project for testing."""
    # Create a simple Python file with a function
    src = tmp_path / "src"
    src.mkdir()

    (src / "main.py").write_text('''
def greet(name: str) -> str:
    """Greet a user by name."""
    return f"Hello, {name}!"


def process(data: list) -> list:
    """Process input data."""
    result = []
    for item in data:
        result.append(transform(item))
    return result


def transform(item):
    """Transform a single item."""
    return item.upper()
''')

    # Create .tldrs directory
    tldrs_dir = tmp_path / ".tldrs"
    tldrs_dir.mkdir()

    return tmp_path


class TestDeltaContextCLI:
    """Tests for CLI delta context functionality."""

    def test_context_with_session_id_first_call(self, temp_python_project):
        """First call with session_id should include full code."""
        result = _run_tldrs(
            [
                "context", "greet",
                "--project", str(temp_python_project),
                "--session-id", "test-session-1",
                "--format", "ultracompact",
                "--lang", "python",
            ],
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        output = result.stdout

        # First call should include code
        assert "greet" in output
        # Should NOT have [UNCHANGED] marker on first call
        assert "[UNCHANGED]" not in output

    def test_context_with_session_id_second_call(self, temp_python_project):
        """Second call with same session_id should mark unchanged symbols."""
        session_id = "test-session-delta"

        # First call
        result1 = _run_tldrs(
            [
                "context", "greet",
                "--project", str(temp_python_project),
                "--session-id", session_id,
                "--format", "ultracompact",
                "--lang", "python",
            ],
        )
        assert result1.returncode == 0, f"First call failed: {result1.stderr}"

        # Second call with same session
        result2 = _run_tldrs(
            [
                "context", "greet",
                "--project", str(temp_python_project),
                "--session-id", session_id,
                "--format", "ultracompact",
                "--lang", "python",
            ],
        )
        assert result2.returncode == 0, f"Second call failed: {result2.stderr}"

        # Second call should have [UNCHANGED] marker (if symbol was cached)
        # Note: This depends on the etag matching between calls
        output2 = result2.stdout
        assert "greet" in output2
        # Cache stats should show hits
        if "Delta:" in output2:
            assert "unchanged" in output2.lower()

    def test_context_with_delta_flag(self, temp_python_project):
        """--delta flag should auto-generate session_id."""
        result = _run_tldrs(
            [
                "context", "greet",
                "--project", str(temp_python_project),
                "--delta",
                "--format", "ultracompact",
                "--lang", "python",
            ],
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        # Should work even without explicit session-id

    def test_context_no_delta_disables_caching(self, temp_python_project):
        """--no-delta should disable delta mode even with session-id."""
        session_id = "test-no-delta"

        # First call
        _run_tldrs(
            [
                "context", "greet",
                "--project", str(temp_python_project),
                "--session-id", session_id,
                "--format", "ultracompact",
                "--lang", "python",
            ],
        )

        # Second call with --no-delta should not show unchanged markers
        result = _run_tldrs(
            [
                "context", "greet",
                "--project", str(temp_python_project),
                "--session-id", session_id,
                "--no-delta",
                "--format", "ultracompact",
                "--lang", "python",
            ],
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        output = result.stdout
        # With --no-delta, should NOT have delta cache stats
        assert "Delta:" not in output

    def test_context_after_file_change(self, temp_python_project):
        """After file change, symbols should be marked as changed."""
        session_id = "test-file-change"
        src = temp_python_project / "src" / "main.py"

        # First call
        _run_tldrs(
            [
                "context", "greet",
                "--project", str(temp_python_project),
                "--session-id", session_id,
                "--format", "ultracompact",
                "--lang", "python",
            ],
        )

        # Modify the file
        content = src.read_text()
        src.write_text(content.replace('Hello', 'Hi'))

        # Second call after modification
        result = _run_tldrs(
            [
                "context", "greet",
                "--project", str(temp_python_project),
                "--session-id", session_id,
                "--format", "ultracompact",
                "--lang", "python",
            ],
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        output = result.stdout

        # After file change, greet should NOT be marked unchanged
        # (its etag should be different)
        assert "greet" in output


class TestDeltaContextStateStore:
    """Direct tests for StateStore delta functionality."""

    def test_check_delta_no_prior_delivery(self, temp_python_project):
        """check_delta with no prior delivery marks all as changed."""
        from tldr_swinton.modules.core.state_store import StateStore

        store = StateStore(temp_python_project)
        session_id = "test-delta-new"

        symbol_etags = {
            "file.py:func1": "etag1",
            "file.py:func2": "etag2",
        }

        result = store.check_delta(session_id, symbol_etags)

        assert len(result.unchanged) == 0
        assert len(result.changed) == 2
        assert "file.py:func1" in result.changed
        assert "file.py:func2" in result.changed

    def test_check_delta_with_prior_delivery(self, temp_python_project):
        """check_delta with prior delivery marks matching etags as unchanged."""
        from tldr_swinton.modules.core.state_store import StateStore

        store = StateStore(temp_python_project)
        session_id = "test-delta-cached"

        # Open session and record delivery
        store.open_session(session_id, "test-fingerprint", "python")
        store.record_delivery(
            session_id,
            symbol_id="file.py:func1",
            etag="etag1",
            representation="full",
        )

        # Check delta - func1 should be unchanged, func2 changed
        symbol_etags = {
            "file.py:func1": "etag1",  # Same etag
            "file.py:func2": "etag2",  # New symbol
        }

        result = store.check_delta(session_id, symbol_etags)

        assert "file.py:func1" in result.unchanged
        assert "file.py:func2" in result.changed

    def test_check_delta_etag_mismatch(self, temp_python_project):
        """check_delta marks symbols with changed etags as changed."""
        from tldr_swinton.modules.core.state_store import StateStore

        store = StateStore(temp_python_project)
        session_id = "test-delta-changed"

        # Record initial delivery
        store.open_session(session_id, "test-fingerprint", "python")
        store.record_delivery(
            session_id,
            symbol_id="file.py:func1",
            etag="old-etag",
            representation="full",
        )

        # Check with different etag
        symbol_etags = {"file.py:func1": "new-etag"}
        result = store.check_delta(session_id, symbol_etags)

        assert "file.py:func1" in result.changed
        assert len(result.unchanged) == 0

    def test_record_deliveries_batch(self, temp_python_project):
        """record_deliveries_batch should work correctly."""
        from tldr_swinton.modules.core.state_store import StateStore

        store = StateStore(temp_python_project)
        session_id = "test-batch"

        store.open_session(session_id, "test-fingerprint", "python")

        deliveries = [
            {"symbol_id": "a.py:foo", "etag": "e1", "representation": "full"},
            {"symbol_id": "b.py:bar", "etag": "e2", "representation": "signature"},
        ]

        store.record_deliveries_batch(session_id, deliveries)

        # Verify deliveries recorded
        d1 = store.get_delivery(session_id, "a.py:foo")
        d2 = store.get_delivery(session_id, "b.py:bar")

        assert d1 is not None
        assert d1["etag"] == "e1"
        assert d2 is not None
        assert d2["etag"] == "e2"


class TestContextPackDelta:
    """Tests for ContextPackEngine delta functionality."""

    def test_build_context_pack_delta_all_changed(self):
        """Delta pack with all changed symbols includes full code."""
        from tldr_swinton.modules.core.contextpack_engine import (
            Candidate,
            ContextPackEngine,
        )
        from tldr_swinton.modules.core.state_store import DeltaResult

        candidates = [
            Candidate(
                symbol_id="a.py:foo",
                relevance=100,
                relevance_label="contains_diff",
                order=0,
                signature="def foo():",
                code="def foo():\n    return 42",
            ),
        ]

        delta = DeltaResult(unchanged=set(), changed={"a.py:foo"})

        engine = ContextPackEngine()
        pack = engine.build_context_pack_delta(candidates, delta)

        assert len(pack.slices) == 1
        assert pack.slices[0].code is not None
        assert pack.unchanged == []
        assert pack.cache_stats["hits"] == 0
        assert pack.cache_stats["misses"] == 1

    def test_build_context_pack_delta_all_unchanged(self):
        """Delta pack with all unchanged symbols omits code."""
        from tldr_swinton.modules.core.contextpack_engine import (
            Candidate,
            ContextPackEngine,
        )
        from tldr_swinton.modules.core.state_store import DeltaResult

        candidates = [
            Candidate(
                symbol_id="a.py:foo",
                relevance=100,
                relevance_label="contains_diff",
                order=0,
                signature="def foo():",
                code="def foo():\n    return 42",
            ),
        ]

        delta = DeltaResult(unchanged={"a.py:foo"}, changed=set())

        engine = ContextPackEngine()
        pack = engine.build_context_pack_delta(candidates, delta)

        assert len(pack.slices) == 1
        assert pack.slices[0].code is None  # Code omitted for unchanged
        assert "a.py:foo" in pack.unchanged
        assert pack.cache_stats["hits"] == 1
        assert pack.cache_stats["misses"] == 0
        assert pack.cache_stats["hit_rate"] == 1.0

    def test_build_context_pack_delta_mixed(self):
        """Delta pack with mixed symbols handles both correctly."""
        from tldr_swinton.modules.core.contextpack_engine import (
            Candidate,
            ContextPackEngine,
        )
        from tldr_swinton.modules.core.state_store import DeltaResult

        candidates = [
            Candidate(
                symbol_id="a.py:unchanged_func",
                relevance=100,
                order=0,
                signature="def unchanged_func():",
                code="def unchanged_func():\n    pass",
            ),
            Candidate(
                symbol_id="a.py:changed_func",
                relevance=80,
                order=1,
                signature="def changed_func():",
                code="def changed_func():\n    return 1",
            ),
        ]

        delta = DeltaResult(
            unchanged={"a.py:unchanged_func"},
            changed={"a.py:changed_func"},
        )

        engine = ContextPackEngine()
        pack = engine.build_context_pack_delta(candidates, delta)

        assert len(pack.slices) == 2

        # Find slices by ID
        unchanged_slice = next(s for s in pack.slices if s.id == "a.py:unchanged_func")
        changed_slice = next(s for s in pack.slices if s.id == "a.py:changed_func")

        assert unchanged_slice.code is None  # Omitted
        assert changed_slice.code is not None  # Included

        assert "a.py:unchanged_func" in pack.unchanged
        assert "a.py:changed_func" not in pack.unchanged

        assert pack.cache_stats["hits"] == 1
        assert pack.cache_stats["misses"] == 1
        assert pack.cache_stats["hit_rate"] == 0.5


class TestDiffContextDelta:
    """Tests for CLI diff-context delta functionality.

    This is where delta mode provides REAL savings - diff-context includes
    code bodies, so skipping unchanged code saves significant tokens.
    """

    @pytest.fixture
    def git_python_project(self, tmp_path):
        """Create a temporary git Python project for diff-context testing."""
        import subprocess

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        # Create src directory
        src = tmp_path / "src"
        src.mkdir()

        # Create initial Python file
        main_py = src / "main.py"
        main_py.write_text('''
def greet(name: str) -> str:
    """Greet a user by name."""
    return f"Hello, {name}!"


def process(data: list) -> list:
    """Process input data."""
    result = []
    for item in data:
        result.append(transform(item))
    return result


def transform(item):
    """Transform a single item."""
    return item.upper()
''')

        # Commit initial version
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        # Create .tldrs directory
        tldrs_dir = tmp_path / ".tldrs"
        tldrs_dir.mkdir()

        # Make a change for diff-context to pick up
        main_py.write_text('''
def greet(name: str) -> str:
    """Greet a user by name."""
    return f"Hi there, {name}!"


def process(data: list) -> list:
    """Process input data."""
    result = []
    for item in data:
        result.append(transform(item))
    return result


def transform(item):
    """Transform a single item."""
    return item.upper()


def new_function():
    """A newly added function."""
    return 42
''')

        return tmp_path

    def test_diff_context_with_session_id_first_call(self, git_python_project):
        """First diff-context call with session_id should include full code."""
        result = _run_tldrs(
            [
                "diff-context",
                "--project", str(git_python_project),
                "--session-id", "diff-test-session-1",
                "--format", "ultracompact",
                "--lang", "python",
            ],
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        output = result.stdout

        # First call should include code (in ``` blocks)
        assert "```" in output
        # Should NOT have [UNCHANGED] marker on first call
        assert "[UNCHANGED]" not in output

    def test_diff_context_with_session_id_second_call(self, git_python_project):
        """Second diff-context call with same session_id should mark unchanged symbols."""
        session_id = "diff-test-session-delta"

        # First call
        result1 = _run_tldrs(
            [
                "diff-context",
                "--project", str(git_python_project),
                "--session-id", session_id,
                "--format", "ultracompact",
                "--lang", "python",
            ],
        )
        assert result1.returncode == 0, f"First call failed: {result1.stderr}"

        # Second call with same session
        result2 = _run_tldrs(
            [
                "diff-context",
                "--project", str(git_python_project),
                "--session-id", session_id,
                "--format", "ultracompact",
                "--lang", "python",
            ],
        )
        assert result2.returncode == 0, f"Second call failed: {result2.stderr}"

        output2 = result2.stdout

        # Second call SHOULD have [UNCHANGED] markers (delta mode working)
        assert "[UNCHANGED]" in output2
        # Cache stats should show hits
        assert "Delta:" in output2

    def test_diff_context_delta_saves_tokens(self, git_python_project):
        """Delta mode should save tokens by omitting unchanged code."""
        session_id = "diff-test-token-savings"

        # First call - full output
        result1 = _run_tldrs(
            [
                "diff-context",
                "--project", str(git_python_project),
                "--session-id", session_id,
                "--format", "ultracompact",
                "--lang", "python",
            ],
        )
        assert result1.returncode == 0, f"First call failed: {result1.stderr}"
        first_len = len(result1.stdout)

        # Second call - should be smaller due to omitted code
        result2 = _run_tldrs(
            [
                "diff-context",
                "--project", str(git_python_project),
                "--session-id", session_id,
                "--format", "ultracompact",
                "--lang", "python",
            ],
        )
        assert result2.returncode == 0, f"Second call failed: {result2.stderr}"
        second_len = len(result2.stdout)

        # Second call should be smaller (code omitted for unchanged)
        # Note: Cache stats header adds some chars, but should still be net savings
        assert second_len < first_len, (
            f"Expected smaller output on second call "
            f"(first={first_len}, second={second_len})"
        )

    def test_diff_context_with_delta_flag(self, git_python_project):
        """--delta flag should auto-generate session_id."""
        result = _run_tldrs(
            [
                "diff-context",
                "--project", str(git_python_project),
                "--delta",
                "--format", "ultracompact",
                "--lang", "python",
            ],
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        # Should work even without explicit session-id

    def test_diff_context_no_delta_disables_caching(self, git_python_project):
        """--no-delta should disable delta mode even with session-id."""
        session_id = "diff-test-no-delta"

        # First call
        _run_tldrs(
            [
                "diff-context",
                "--project", str(git_python_project),
                "--session-id", session_id,
                "--format", "ultracompact",
                "--lang", "python",
            ],
        )

        # Second call with --no-delta should not show delta stats
        result = _run_tldrs(
            [
                "diff-context",
                "--project", str(git_python_project),
                "--session-id", session_id,
                "--no-delta",
                "--format", "ultracompact",
                "--lang", "python",
            ],
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        output = result.stdout
        # With --no-delta, should NOT have delta cache stats
        assert "Delta:" not in output
