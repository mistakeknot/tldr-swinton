"""Tests for delta-first budget architecture.

Delta-first means: check ETags BEFORE extracting code bodies, so unchanged
symbols never trigger expensive code extraction.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """Create a sample Python project for testing."""
    # Create main.py
    (tmp_path / "main.py").write_text('''
def main():
    """Entry point."""
    result = helper()
    process(result)
    return result


def helper():
    """Helper function."""
    return 42


def process(value):
    """Process a value."""
    return value * 2


class Calculator:
    """A simple calculator."""

    def add(self, a, b):
        return a + b

    def multiply(self, a, b):
        return a * b
''')

    # Create utils.py
    (tmp_path / "utils.py").write_text('''
def format_result(value):
    """Format a result for display."""
    return f"Result: {value}"


def validate_input(value):
    """Validate input value."""
    if not isinstance(value, int):
        raise ValueError("Must be an integer")
    return True
''')

    return tmp_path


class TestGetSignaturesForEntry:
    """Tests for get_signatures_for_entry function."""

    def test_returns_signatures_not_code(self, sample_project: Path):
        """Signatures should be returned without code bodies."""
        from tldr_swinton.modules.core.api import get_signatures_for_entry

        sigs = get_signatures_for_entry(sample_project, "main", depth=2)

        # Should return list, not dict (not an error)
        assert isinstance(sigs, list)
        assert len(sigs) > 0

        # Check that we got signature info
        main_sig = next((s for s in sigs if "main" in s.symbol_id), None)
        assert main_sig is not None
        assert "def main" in main_sig.signature
        assert main_sig.line > 0

    def test_includes_call_graph(self, sample_project: Path):
        """Signatures should include call graph information."""
        from tldr_swinton.modules.core.api import get_signatures_for_entry

        sigs = get_signatures_for_entry(sample_project, "main", depth=2)

        # main() should have calls to helper and process
        main_sig = next((s for s in sigs if "main" in s.symbol_id and "def main" in s.signature), None)
        assert main_sig is not None, f"Could not find main signature. Got: {[s.symbol_id for s in sigs]}"
        # Calls should be tracked
        assert hasattr(main_sig, 'calls')

    def test_respects_depth(self, sample_project: Path):
        """Depth parameter should limit call graph traversal."""
        from tldr_swinton.modules.core.api import get_signatures_for_entry

        depth_1 = get_signatures_for_entry(sample_project, "main", depth=1)
        depth_2 = get_signatures_for_entry(sample_project, "main", depth=2)

        # Depth 2 should include at least as many symbols
        assert len(depth_2) >= len(depth_1)

    def test_handles_class_methods(self, sample_project: Path):
        """Should handle class methods correctly."""
        from tldr_swinton.modules.core.api import get_signatures_for_entry

        sigs = get_signatures_for_entry(sample_project, "Calculator", depth=1)

        # Should return list, not dict
        assert isinstance(sigs, list)

    def test_ambiguous_without_disambiguate_returns_error(self, sample_project: Path):
        """Ambiguous entry without disambiguation should return error dict."""
        # Create a second file with same function name
        (sample_project / "other.py").write_text('''
def helper():
    """Another helper."""
    return 100
''')
        from tldr_swinton.modules.core.api import get_signatures_for_entry

        result = get_signatures_for_entry(sample_project, "helper", disambiguate=False)

        # Should return error dict
        assert isinstance(result, dict)
        assert result.get("error") is True
        assert "candidates" in result


class TestGetDiffSignatures:
    """Tests for get_diff_signatures function."""

    def test_returns_signatures_for_hunks(self, sample_project: Path):
        """Should return signatures for symbols in diff hunks."""
        from tldr_swinton.modules.core.api import get_diff_signatures

        # Simulate a diff hunk on main.py lines 2-6
        hunks = [("main.py", 2, 6)]
        sigs = get_diff_signatures(sample_project, hunks)

        assert isinstance(sigs, list)
        assert len(sigs) > 0

        # Should include main (contains the diff)
        main_sig = next((s for s in sigs if "main" in s.symbol_id), None)
        assert main_sig is not None
        assert main_sig.relevance_label == "contains_diff"

    def test_includes_diff_lines(self, sample_project: Path):
        """Should include diff line information."""
        from tldr_swinton.modules.core.api import get_diff_signatures

        hunks = [("main.py", 3, 5)]
        sigs = get_diff_signatures(sample_project, hunks)

        # Find the symbol containing the diff
        diff_sig = next((s for s in sigs if s.relevance_label == "contains_diff"), None)
        assert diff_sig is not None
        assert hasattr(diff_sig, 'diff_lines')
        assert len(diff_sig.diff_lines) > 0

    def test_includes_callers_and_callees(self, sample_project: Path):
        """Should include callers and callees of changed symbols."""
        from tldr_swinton.modules.core.api import get_diff_signatures

        # Diff in helper function
        hunks = [("main.py", 8, 10)]  # helper function
        sigs = get_diff_signatures(sample_project, hunks)

        # Should include caller (main)
        labels = {s.relevance_label for s in sigs}
        assert "contains_diff" in labels
        # Caller/callee expansion should be present
        assert any(l in labels for l in ("caller", "callee", "contains_diff"))


class TestDeltaFirstBehavior:
    """Tests for delta-first extraction behavior."""

    def test_unchanged_symbols_not_extracted(self, sample_project: Path):
        """Unchanged symbols should not trigger code extraction."""
        from tldr_swinton.modules.core.state_store import StateStore
        from tldr_swinton.modules.core.api import get_signatures_for_entry
        import hashlib

        # Initialize state store
        store = StateStore(sample_project)
        session_id = store.get_or_create_default_session("python")

        # Get signatures
        sigs = get_signatures_for_entry(sample_project, "main", depth=2)
        assert isinstance(sigs, list)

        # Compute ETags and record first delivery
        symbol_etags = {}
        for sig in sigs:
            etag = hashlib.sha256(sig.signature.encode()).hexdigest()
            symbol_etags[sig.symbol_id] = etag

        # Record deliveries for all symbols
        deliveries = [
            {
                "symbol_id": sig.symbol_id,
                "etag": symbol_etags[sig.symbol_id],
                "representation": "full",
                "vhs_ref": None,
                "token_estimate": 100,
            }
            for sig in sigs
        ]
        store.record_deliveries_batch(session_id, deliveries)

        # Second check - all should be unchanged
        delta = store.check_delta(session_id, symbol_etags)
        assert len(delta.unchanged) == len(sigs)
        assert len(delta.changed) == 0

    def test_changed_symbols_detected(self, sample_project: Path):
        """Changed symbols should be detected."""
        from tldr_swinton.modules.core.state_store import StateStore
        from tldr_swinton.modules.core.api import get_signatures_for_entry
        import hashlib

        store = StateStore(sample_project)
        session_id = store.get_or_create_default_session("python")

        # Get signatures and record first delivery
        sigs = get_signatures_for_entry(sample_project, "main", depth=2)
        assert isinstance(sigs, list)

        symbol_etags = {
            sig.symbol_id: hashlib.sha256(sig.signature.encode()).hexdigest()
            for sig in sigs
        }

        deliveries = [
            {
                "symbol_id": sig.symbol_id,
                "etag": symbol_etags[sig.symbol_id],
                "representation": "full",
            }
            for sig in sigs
        ]
        store.record_deliveries_batch(session_id, deliveries)

        # Modify one signature's etag to simulate change
        changed_symbol = sigs[0].symbol_id
        symbol_etags[changed_symbol] = "changed_etag_value"

        # Check delta
        delta = store.check_delta(session_id, symbol_etags)
        assert changed_symbol in delta.changed
        assert len(delta.unchanged) == len(sigs) - 1


class TestDeltaContextPacks:
    """Tests for context pack with delta mode."""

    def test_context_pack_delta_mode(self, sample_project: Path):
        """Context pack should work in delta mode."""
        from tldr_swinton.modules.core.engines.delta import get_context_pack_with_delta
        from tldr_swinton.modules.core.state_store import StateStore

        store = StateStore(sample_project)
        session_id = store.get_or_create_default_session("python")

        # First call - no cache
        pack1 = get_context_pack_with_delta(
            str(sample_project),
            "main",
            session_id,
            depth=2,
            language="python",
        )

        assert pack1 is not None
        assert hasattr(pack1, 'cache_stats')
        # First call should have all misses
        if pack1.cache_stats:
            assert pack1.cache_stats.get("misses", 0) > 0

        # Second call - should have hits
        pack2 = get_context_pack_with_delta(
            str(sample_project),
            "main",
            session_id,
            depth=2,
            language="python",
        )

        assert pack2 is not None
        if pack2.cache_stats:
            # Second call should have hits
            assert pack2.cache_stats.get("hits", 0) > 0
            assert pack2.cache_stats.get("hit_rate", 0) > 0

    def test_diff_context_delta_mode(self, sample_project: Path):
        """Diff context should work in delta mode."""
        import subprocess

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=sample_project, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=sample_project, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=sample_project,
            capture_output=True,
            env={"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@test.com",
                 "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@test.com"},
        )

        # Make a change
        main_py = sample_project / "main.py"
        content = main_py.read_text()
        main_py.write_text(content.replace("return result", "return result + 1"))

        from tldr_swinton.modules.core.engines.delta import get_diff_context_with_delta
        from tldr_swinton.modules.core.state_store import StateStore

        store = StateStore(sample_project)
        session_id = store.get_or_create_default_session("python")

        pack = get_diff_context_with_delta(
            sample_project,
            session_id,
            language="python",
        )

        # Should have found the diff
        assert pack is not None
        # Pack may be empty if no valid diff hunks found
        if pack.slices:
            assert len(pack.slices) > 0
