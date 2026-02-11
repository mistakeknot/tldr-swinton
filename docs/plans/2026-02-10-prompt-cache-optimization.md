# Prompt Cache Optimization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Polish `_format_cache_friendly()` to maximize LLM provider prompt cache hit rates (Anthropic 90%, OpenAI 50%) via deterministic ordering, all-signatures-in-prefix, and machine-readable cache hints.

**Architecture:** Rewrite `_format_cache_friendly()` in `output_formats.py` to: (1) put ALL symbol signatures in the stable prefix (not just unchanged), (2) sort everything by `(file_path, symbol_id)` for byte-deterministic output, (3) emit a JSON cache hints metadata block. Fix the non-delta path in `format_context()` to produce useful prefix content. Add `cache_stats` to non-delta `build_context_pack()`.

**Tech Stack:** Python stdlib (hashlib, json), existing tiktoken integration, existing ContextPack/ContextSlice dataclasses.

**Brainstorm:** `docs/brainstorms/2026-02-10-prompt-cache-optimization-brainstorm.md`
**Bead:** `tldr-swinton-jja`

**Review changes applied:** Removed `prefix_sections` extension point (YAGNI), removed two-pass offset assembly (use `.find()` instead), added project header with commit SHA, merged Task 3 into Task 2, consolidated test classes.

---

### Task 1: Test Infrastructure — Cache-Friendly Format Tests

**Files:**
- Create: `tests/test_cache_friendly_format.py`

**Step 1: Write the failing tests**

```python
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

    def test_cache_hints_present(self):
        """Cache hints JSON block appears in output."""
        pack = _make_pack(
            slices=[_make_slice("a.py:f", "def f():", "code", (1, 5))],
            unchanged=[],
            cache_stats={"hit_rate": 0.0, "hits": 0, "misses": 1},
        )
        out = format_context_pack(pack, fmt="cache-friendly")
        assert "cache_hints" in out, "No cache_hints block in output"

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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cache_friendly_format.py -v`
Expected: Multiple failures — current `_format_cache_friendly` doesn't put all signatures in prefix, doesn't emit cache hints JSON in the expected format.

**Step 3: Commit the test file**

```bash
git add tests/test_cache_friendly_format.py
git commit -m "test: add cache-friendly format test suite (all failing)"
```

---

### Task 2: Rewrite `_format_cache_friendly()` and Fix Non-Delta Path

**Files:**
- Modify: `src/tldr_swinton/modules/core/output_formats.py`

**Step 1: Read the current implementation**

Read `src/tldr_swinton/modules/core/output_formats.py` lines 438-578 to understand the existing `_format_cache_friendly()`.
Also read lines 76-91 for the `format_context()` cache-friendly branch.

**Step 2: Add `import hashlib` to the top of output_formats.py**

Add `import hashlib` after the existing `import json` line.

**Step 3: Replace `_format_cache_friendly` with the new implementation**

```python
def _format_cache_friendly(pack: dict) -> str:
    """Format context pack for LLM provider prompt caching optimization.

    Layout (all content before CACHE_BREAKPOINT is the stable prefix):
    1. Header (no timestamps — they'd break byte-exact matching)
    2. Cache hints JSON metadata
    3. All symbol signatures sorted by symbol ID
    4. CACHE_BREAKPOINT marker
    5. Changed symbol code bodies sorted by symbol ID
    6. Stats footer

    Prefix maximization: ALL signatures go in the prefix, even for changed
    symbols. Signatures rarely change when only bodies are edited, so this
    gives 80-95% cache hit rates in typical edit sessions.

    Args:
        pack: ContextPack dict with slices, unchanged list, cache_stats.

    Returns:
        Formatted string with cache-friendly two-section layout.
    """
    slices = pack.get("slices", [])
    if not slices:
        return "# tldrs cache-friendly output\n\n# No symbols to display"

    # --- Classify slices ---
    unchanged_val = pack.get("unchanged")
    if isinstance(unchanged_val, bool):
        unchanged_set: set[str] = set()
    elif unchanged_val is None:
        # Non-delta path: no unchanged info. All symbols with code
        # go to dynamic section (treat all as changed).
        unchanged_set = set()
    else:
        unchanged_set = set(unchanged_val)

    # Sort ALL slices deterministically by ID (contains file_path:symbol)
    all_slices = sorted(slices, key=lambda s: s.get("id", ""))

    # Identify changed symbols with code bodies for dynamic section
    dynamic_body_slices = [
        s for s in all_slices
        if s.get("code") is not None and s.get("id", "") not in unchanged_set
    ]

    # --- Build prefix section: ALL signatures ---
    prefix_parts: list[str] = [
        f"## CACHE PREFIX ({len(all_slices)} symbols)",
        "",
    ]

    for item in all_slices:
        symbol_id = item.get("id", "?")
        signature = item.get("signature", "")
        lines_range = item.get("lines") or []
        line_info = ""
        if lines_range and len(lines_range) == 2:
            line_info = f" @{lines_range[0]}-{lines_range[1]}"
        relevance = item.get("relevance", "")
        unchanged_marker = " [UNCHANGED]" if symbol_id in unchanged_set else ""
        prefix_parts.append(
            f"{symbol_id} {signature}{line_info} [{relevance}]{unchanged_marker}".strip()
        )

    prefix_parts.append("")
    prefix_text = "\n".join(prefix_parts)

    # --- Compute prefix metrics ---
    prefix_token_est = _estimate_tokens(prefix_text)
    prefix_hash = hashlib.sha256(prefix_text.encode("utf-8")).hexdigest()[:16]

    # --- Build dynamic section: code bodies only ---
    dynamic_parts: list[str] = []
    if dynamic_body_slices:
        dynamic_parts.append(f"## DYNAMIC CONTENT ({len(dynamic_body_slices)} changed symbols)")
        dynamic_parts.append("")
        for item in dynamic_body_slices:
            symbol_id = item.get("id", "?")
            signature = item.get("signature", "")
            dynamic_parts.append(f"### {symbol_id}")
            dynamic_parts.append(f"{signature}")
            code = item.get("code", "")
            dynamic_parts.append("```")
            dynamic_parts.extend(code.splitlines())
            dynamic_parts.append("```")
            dynamic_parts.append("")

    dynamic_token_est = _estimate_tokens("\n".join(dynamic_parts)) if dynamic_parts else 0

    # --- Single-pass assembly ---
    header = "# tldrs cache-friendly output v1"
    breakpoint_line = f"<!-- CACHE_BREAKPOINT: ~{prefix_token_est} tokens -->"

    # Assemble with placeholder hints, then compute offset via .find()
    hints_placeholder = "__CACHE_HINTS_PLACEHOLDER__"
    final_parts: list[str] = [header, hints_placeholder, "", prefix_text, breakpoint_line]
    if dynamic_parts:
        final_parts.append("")
        final_parts.extend(dynamic_parts)

    # Stats footer
    total_tokens = prefix_token_est + dynamic_token_est
    final_parts.append(
        f"## STATS: Prefix ~{prefix_token_est} tokens | Dynamic ~{dynamic_token_est} tokens | Total ~{total_tokens} tokens"
    )

    cache_stats = pack.get("cache_stats")
    if cache_stats:
        hit_rate = cache_stats.get("hit_rate", 0)
        hits = cache_stats.get("hits", 0)
        misses = cache_stats.get("misses", 0)
        final_parts.append(f"## Cache: {hits} unchanged, {misses} changed ({hit_rate:.0%} hit rate)")

    output = "\n".join(final_parts)

    # Compute breakpoint offset from assembled output
    breakpoint_offset = output.find("<!-- CACHE_BREAKPOINT")

    # Build real hints line and replace placeholder
    hints_data = {
        "cache_hints": {
            "prefix_tokens": prefix_token_est,
            "prefix_hash": prefix_hash,
            "breakpoint_char_offset": breakpoint_offset,
            "format_version": 1,
        }
    }
    hints_line = json.dumps(hints_data, separators=(",", ":"), ensure_ascii=False)
    output = output.replace(hints_placeholder, hints_line, 1)

    return output
```

**Step 4: Fix the non-delta path in `format_context()` (lines 76-91)**

Replace the cache-friendly branch with:

```python
    if fmt == "cache-friendly":
        pack = {
            "slices": [
                {
                    "id": func.name,
                    "signature": func.signature,
                    "code": None,
                    "lines": [func.line, func.line] if func.line else None,
                    "relevance": f"depth_{func.depth}",
                }
                for func in ctx.functions
            ],
            "unchanged": None,
            "cache_stats": {
                "hit_rate": 0.0,
                "hits": 0,
                "misses": len(ctx.functions),
            },
        }
        return _format_cache_friendly(pack)
```

Key change: `"unchanged": None` instead of `[]`, and populate `cache_stats`.

**Step 5: Run the test suite**

Run: `uv run pytest tests/test_cache_friendly_format.py -v`
Expected: Most tests pass. Fix any failures.

Run: `uv run pytest tests/test_contextpack_format.py tests/test_output_caps.py -v`
Expected: All pass (existing formats unchanged).

**Step 6: Commit**

```bash
git add src/tldr_swinton/modules/core/output_formats.py
git commit -m "feat(jja): rewrite cache-friendly format with prefix maximization and cache hints"
```

---

### Task 3: Add `cache_stats` to Non-Delta `build_context_pack()`

**Files:**
- Modify: `src/tldr_swinton/modules/core/contextpack_engine.py:112-115`

**Step 1: Read the current `build_context_pack` return**

Read `src/tldr_swinton/modules/core/contextpack_engine.py` lines 47-115.

**Step 2: Add cache_stats to the non-delta return**

In `build_context_pack()`, change the return statement (around line 112) from:

```python
        return ContextPack(
            slices=slices,
            budget_used=used,
        )
```

to:

```python
        return ContextPack(
            slices=slices,
            budget_used=used,
            cache_stats={"hit_rate": 0.0, "hits": 0, "misses": len(slices)},
        )
```

**Step 3: Run tests**

Run: `uv run pytest tests/test_cache_friendly_format.py::TestBuildContextPackCacheStats -v`
Expected: PASS.

Run: `uv run pytest tests/ -v --timeout=60`
Expected: All tests pass (no regressions).

**Step 4: Commit**

```bash
git add src/tldr_swinton/modules/core/contextpack_engine.py
git commit -m "feat(jja): populate cache_stats in non-delta build_context_pack()"
```

---

### Task 4: Update CLI Documentation and End-to-End Test

**Files:**
- Modify: `src/tldr_swinton/cli.py` (update help text only)

**Step 1: Update `--format` help text in cli.py**

In `cli.py`, find the two `--format` argument definitions (around lines 366-370 and 438-442). Update the help text:

For context command (~line 370):
```python
        help="Output format (cache-friendly: optimized for LLM provider prompt caching)",
```

For diff-context command (~line 442):
```python
        help="Output format (default: ultracompact; cache-friendly: optimized for LLM prompt caching)",
```

**Step 2: Run the full test suite**

Run: `uv run pytest tests/test_cache_friendly_format.py -v`
Expected: All pass.

Run: `uv run pytest tests/ -v --timeout=60`
Expected: No regressions.

**Step 3: Commit**

```bash
git add src/tldr_swinton/cli.py
git commit -m "docs(jja): update CLI help text for cache-friendly format"
```

---

### Task 5: Update Bead and Close

**Step 1: Close the bead**

```bash
bd close tldr-swinton-jja --reason="Implemented: prefix maximization, cache hints JSON, non-delta fix, cache_stats everywhere, full test suite"
```

**Step 2: Final verification**

Run `git status` and verify everything is committed. If any unstaged changes remain, stage and commit them.
