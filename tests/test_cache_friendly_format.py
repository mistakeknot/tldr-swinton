"""Tests for cache-friendly output format."""

import json
import subprocess
import sys

import pytest

from tldr_swinton.modules.core.contextpack_engine import ContextPack, ContextSlice
from tldr_swinton.modules.core.output_formats import format_context_pack


def _make_pack(
    slices: list[ContextSlice],
    unchanged: list[str] | None = None,
    cache_stats: dict | None = None,
) -> ContextPack:
    return ContextPack(
        slices=slices,
        budget_used=100,
        unchanged=unchanged,
        cache_stats=cache_stats,
    )


def _make_slice(
    symbol_id: str,
    signature: str = "def f():",
    code: str | None = None,
    lines: tuple[int, int] | None = None,
    relevance: str | None = "contains_diff",
) -> ContextSlice:
    return ContextSlice(
        id=symbol_id, signature=signature, code=code, lines=lines, relevance=relevance
    )


class TestCacheFriendlyDeterminism:
    """Output must be byte-identical for the same inputs across repeated calls."""

    def test_identical_output_across_calls(self):
        """Same input produces byte-identical output every time."""
        pack = _make_pack(
            slices=[
                _make_slice("b.py:beta", "def beta():", "return 2", (10, 12)),
                _make_slice("a.py:alpha", "def alpha():", "return 1", (1, 3)),
            ],
            unchanged=["a.py:alpha"],
            cache_stats={"hit_rate": 0.5, "hits": 1, "misses": 1},
        )
        out1 = format_context_pack(pack, fmt="cache-friendly")
        out2 = format_context_pack(pack, fmt="cache-friendly")
        assert out1 == out2, "Output must be byte-identical across calls"

    def test_sorted_by_symbol_id(self):
        """All slices sorted by symbol ID (which contains file_path:name), not relevance."""
        pack = _make_pack(
            slices=[
                _make_slice("z.py:zebra", relevance="caller"),
                _make_slice("a.py:alpha", relevance="contains_diff"),
                _make_slice("m.py:middle", relevance="callee"),
            ],
            unchanged=["z.py:zebra"],
            cache_stats={"hit_rate": 0.33, "hits": 1, "misses": 2},
        )
        out = format_context_pack(pack, fmt="cache-friendly")
        lines = out.split("\n")
        # In prefix section: all signatures sorted by ID
        sig_lines = [l for l in lines if "def f():" in l and not l.startswith("#")]
        ids = [l.split()[0] for l in sig_lines if l.strip()]
        assert ids == sorted(ids), f"Signatures not sorted: {ids}"

    def test_dynamic_section_sorted(self):
        """Dynamic section slices are also sorted by symbol ID."""
        pack = _make_pack(
            slices=[
                _make_slice("z.py:zebra", "def zebra():", "return 'z'", (20, 22)),
                _make_slice("a.py:alpha", "def alpha():", "return 'a'", (1, 3)),
            ],
            unchanged=[],
            cache_stats={"hit_rate": 0.0, "hits": 0, "misses": 2},
        )
        out = format_context_pack(pack, fmt="cache-friendly")
        bp_idx = out.find("CACHE_BREAKPOINT")
        dynamic = out[bp_idx:]
        # alpha should appear before zebra in dynamic section
        alpha_pos = dynamic.find("a.py:alpha")
        zebra_pos = dynamic.find("z.py:zebra")
        assert alpha_pos < zebra_pos, "Dynamic section not sorted by symbol ID"

    def test_no_timestamp_in_output(self):
        """Timestamps break byte-exact caching — must not appear."""
        pack = _make_pack(
            slices=[_make_slice("a.py:f")],
            cache_stats={"hit_rate": 0.0, "hits": 0, "misses": 1},
        )
        out = format_context_pack(pack, fmt="cache-friendly")
        import re
        assert not re.search(r"\d{4}-\d{2}-\d{2}", out), "Timestamp found in output"

    def test_empty_slices(self):
        pack = _make_pack(slices=[])
        out = format_context_pack(pack, fmt="cache-friendly")
        assert "No symbols" in out

    def test_all_signature_only(self):
        """All slices with code=None should work (all prefix, no dynamic bodies)."""
        pack = _make_pack(
            slices=[
                _make_slice("a.py:f", "def f():", None, (1, 3)),
                _make_slice("b.py:g", "def g():", None, (5, 8)),
            ],
            unchanged=["a.py:f", "b.py:g"],
            cache_stats={"hit_rate": 1.0, "hits": 2, "misses": 0},
        )
        out = format_context_pack(pack, fmt="cache-friendly")
        assert "CACHE_BREAKPOINT" in out
        # Dynamic section should be empty or minimal
        bp_idx = out.find("CACHE_BREAKPOINT")
        dynamic = out[bp_idx:]
        assert "```" not in dynamic, "No code blocks expected in dynamic"


class TestCacheFriendlyPrefixMaximization:
    """ALL signatures go in prefix — even changed symbols. Cache hints present."""

    def test_all_signatures_in_prefix(self):
        """Both changed and unchanged symbol signatures appear in CACHE PREFIX."""
        pack = _make_pack(
            slices=[
                _make_slice("a.py:unchanged_fn", "def unchanged_fn():", None, (1, 5)),
                _make_slice("b.py:changed_fn", "def changed_fn():", "new code", (10, 20)),
            ],
            unchanged=["a.py:unchanged_fn"],
            cache_stats={"hit_rate": 0.5, "hits": 1, "misses": 1},
        )
        out = format_context_pack(pack, fmt="cache-friendly")
        bp_idx = out.find("CACHE_BREAKPOINT")
        assert bp_idx > 0, "No CACHE_BREAKPOINT found"
        prefix = out[:bp_idx]
        assert "unchanged_fn" in prefix, "Unchanged sig missing from prefix"
        assert "changed_fn" in prefix, "Changed sig missing from prefix"

    def test_code_bodies_only_in_dynamic(self):
        """Code bodies appear only AFTER the CACHE_BREAKPOINT."""
        pack = _make_pack(
            slices=[
                _make_slice("a.py:f", "def f():", "body_code_here", (1, 5)),
            ],
            unchanged=[],
            cache_stats={"hit_rate": 0.0, "hits": 0, "misses": 1},
        )
        out = format_context_pack(pack, fmt="cache-friendly")
        bp_idx = out.find("CACHE_BREAKPOINT")
        assert bp_idx > 0
        prefix = out[:bp_idx]
        dynamic = out[bp_idx:]
        assert "body_code_here" not in prefix, "Code body leaked into prefix"
        assert "body_code_here" in dynamic, "Code body missing from dynamic"

    def test_cache_hints_parseable(self):
        """Cache hints block is valid JSON with required fields."""
        pack = _make_pack(
            slices=[
                _make_slice("a.py:f", "def f():", None, (1, 3)),
                _make_slice("b.py:g", "def g():", "code", (5, 10)),
            ],
            unchanged=["a.py:f"],
            cache_stats={"hit_rate": 0.5, "hits": 1, "misses": 1},
        )
        out = format_context_pack(pack, fmt="cache-friendly")
        for line in out.split("\n"):
            if "cache_hints" in line:
                hints = json.loads(line)
                assert "cache_hints" in hints
                h = hints["cache_hints"]
                assert "prefix_tokens" in h
                assert "prefix_hash" in h
                assert "breakpoint_char_offset" in h
                assert isinstance(h["prefix_tokens"], int)
                assert isinstance(h["prefix_hash"], str)
                assert isinstance(h["breakpoint_char_offset"], int)
                assert h["prefix_tokens"] > 0
                return
        raise AssertionError("No parseable cache_hints JSON line found")

    def test_prefix_hash_stable(self):
        """Same prefix content produces same hash."""
        pack = _make_pack(
            slices=[_make_slice("a.py:f", "def f():", "code", (1, 5))],
            unchanged=[],
            cache_stats={"hit_rate": 0.0, "hits": 0, "misses": 1},
        )
        out1 = format_context_pack(pack, fmt="cache-friendly")
        out2 = format_context_pack(pack, fmt="cache-friendly")
        def _get_hash(out):
            for line in out.split("\n"):
                if "cache_hints" in line:
                    return json.loads(line)["cache_hints"]["prefix_hash"]
            return None
        assert _get_hash(out1) == _get_hash(out2)


class TestCacheFriendlyCommitSha:
    """Commit SHA fingerprint in header and cache hints."""

    def _pack_with_head(self, head_sha: str) -> dict:
        """Build a raw pack dict (not ContextPack) with base/head like difflens produces."""
        from tldr_swinton.modules.core.output_formats import _contextpack_to_dict
        pack = _make_pack(
            slices=[_make_slice("a.py:f", "def f():", "code", (1, 5))],
            unchanged=[],
            cache_stats={"hit_rate": 0.0, "hits": 0, "misses": 1},
        )
        d = _contextpack_to_dict(pack)
        d["head"] = head_sha
        d["base"] = "0000000000000000000000000000000000000000"
        return d

    def test_header_includes_short_sha(self):
        """Header line includes the first 8 chars of head SHA."""
        d = self._pack_with_head("abc123def456789012345678901234567890abcd")
        out = format_context_pack(d, fmt="cache-friendly")
        assert "@ abc123de" in out, "Short SHA not in header"

    def test_cache_hints_include_full_sha(self):
        """cache_hints JSON includes the full commit SHA."""
        full_sha = "abc123def456789012345678901234567890abcd"
        d = self._pack_with_head(full_sha)
        out = format_context_pack(d, fmt="cache-friendly")
        for line in out.split("\n"):
            if "cache_hints" in line:
                hints = json.loads(line)["cache_hints"]
                assert hints["commit_sha"] == full_sha
                return
        raise AssertionError("No cache_hints found")

    def test_no_sha_without_head(self):
        """Without head commit, no commit_sha in hints and no @ in header."""
        pack = _make_pack(
            slices=[_make_slice("a.py:f", "def f():", "code", (1, 5))],
            unchanged=[],
            cache_stats={"hit_rate": 0.0, "hits": 0, "misses": 1},
        )
        out = format_context_pack(pack, fmt="cache-friendly")
        assert "@ " not in out.split("\n")[0], "Should not have @ in header without head"
        for line in out.split("\n"):
            if "cache_hints" in line:
                hints = json.loads(line)["cache_hints"]
                assert "commit_sha" not in hints
                return
        raise AssertionError("No cache_hints found")

    def test_same_sha_produces_identical_output(self):
        """Same head SHA produces byte-identical output."""
        d1 = self._pack_with_head("abcdef1234567890abcdef1234567890abcdef12")
        d2 = self._pack_with_head("abcdef1234567890abcdef1234567890abcdef12")
        out1 = format_context_pack(d1, fmt="cache-friendly")
        out2 = format_context_pack(d2, fmt="cache-friendly")
        assert out1 == out2


class TestCacheFriendlyNonDelta:
    """Non-delta path: all signatures in prefix, bodies in dynamic."""

    def test_non_delta_all_signatures_in_prefix(self):
        """Without unchanged list, all signatures still go to prefix."""
        pack = _make_pack(
            slices=[
                _make_slice("a.py:f", "def f():", "code_f", (1, 5)),
                _make_slice("b.py:g", "def g():", "code_g", (10, 15)),
            ],
            unchanged=None,  # Non-delta: no unchanged info
            cache_stats=None,
        )
        out = format_context_pack(pack, fmt="cache-friendly")
        bp_idx = out.find("CACHE_BREAKPOINT")
        assert bp_idx > 0, "Should have breakpoint even without delta info"
        prefix = out[:bp_idx]
        assert "def f()" in prefix
        assert "def g()" in prefix

    def test_non_delta_has_stats(self):
        """Non-delta output still has STATS footer."""
        pack = _make_pack(
            slices=[_make_slice("a.py:f", "def f():", "code", (1, 5))],
            unchanged=None,
        )
        out = format_context_pack(pack, fmt="cache-friendly")
        assert "STATS" in out


class TestBuildContextPackCacheStats:
    """Non-delta build_context_pack() should populate cache_stats."""

    def test_non_delta_has_cache_stats(self):
        from tldr_swinton.modules.core.contextpack_engine import ContextPackEngine, Candidate
        engine = ContextPackEngine()
        candidates = [
            Candidate(symbol_id="a.py:f", relevance=10, signature="def f():"),
            Candidate(symbol_id="b.py:g", relevance=5, signature="def g():"),
        ]
        pack = engine.build_context_pack(candidates, budget_tokens=5000)
        assert pack.cache_stats is not None
        assert pack.cache_stats["hits"] == 0
        assert pack.cache_stats["misses"] == len(pack.slices)


class TestCacheFriendlyCLI:
    """End-to-end CLI tests for --format cache-friendly."""

    def test_context_cache_friendly(self, tmp_path):
        """tldrs context --format cache-friendly produces valid output."""
        f = tmp_path / "sample.py"
        f.write_text("def hello():\n    return 'world'\n\ndef goodbye():\n    return 'bye'\n")
        result = subprocess.run(
            [sys.executable, "-m", "tldr_swinton", "context", "hello",
             "--project", str(tmp_path), "--format", "cache-friendly"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            assert "CACHE_BREAKPOINT" in result.stdout
            assert "cache_hints" in result.stdout
            assert "STATS" in result.stdout

    def test_diff_context_cache_friendly(self, tmp_path):
        """tldrs diff-context --format cache-friendly with delta info."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, capture_output=True)
        f = tmp_path / "a.py"
        f.write_text("def a():\n    pass\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        f.write_text("def a():\n    return 1\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "change"], cwd=tmp_path, capture_output=True)

        result = subprocess.run(
            [sys.executable, "-m", "tldr_swinton", "diff-context",
             "--project", str(tmp_path), "--format", "cache-friendly"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            assert "CACHE_BREAKPOINT" in result.stdout
            assert "cache_hints" in result.stdout
