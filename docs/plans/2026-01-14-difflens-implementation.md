# DiffLens Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** [none] (no bead provided)

**Goal:** Implement real diff‑first context packs (DiffLens) with ultracompact CLI output and JSON ContextPack option.

**Architecture:** Add `get_diff_context` to API, `tldrs diff-context` to CLI, diff parsing + symbol mapping via AST, 1‑hop call expansion, budgeted output.

**Tech Stack:** Python 3, git CLI, pytest

### Task 1: Add failing tests

**Files:**
- Create: `tests/test_difflens.py`

**Step 1: Write failing test for diff parsing**

```python
def test_parse_unified_diff_extracts_ranges():
    diff = """diff --git a/a.py b/a.py\n@@ -1,0 +1,2 @@\n+def foo():\n+    return 1\n"""
    hunks = parse_unified_diff(diff)
    assert hunks == [("a.py", 1, 2)]
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_difflens.py::test_parse_unified_diff_extracts_ranges -q`
Expected: FAIL (function missing)

**Step 3: Write failing test for hunk→symbol mapping**

```python
symbols = map_hunks_to_symbols(project, hunks, language="python")
assert "a.py:foo" in symbols
```

**Step 4: Run test to verify it fails**

Run: `python -m pytest tests/test_difflens.py::test_map_hunks_to_symbols -q`
Expected: FAIL

**Step 5: Commit**

```bash
git add tests/test_difflens.py
git commit -m "test: add difflens coverage"
```

### Task 2: Implement diff parsing + symbol mapping

**Files:**
- Modify: `src/tldr_swinton/api.py`

**Step 1: Add `parse_unified_diff` helper**

```python
# returns list of (file_path, start_line, end_line)
```

**Step 2: Add `map_hunks_to_symbols` helper using HybridExtractor**

```python
# extract function ranges, match hunk line into range
```

**Step 3: Run tests**

Run: `python -m pytest tests/test_difflens.py::test_parse_unified_diff_extracts_ranges tests/test_difflens.py::test_map_hunks_to_symbols -q`
Expected: PASS

**Step 4: Commit**

```bash
git add src/tldr_swinton/api.py
git commit -m "feat: add difflens diff parsing"
```

### Task 3: Implement get_diff_context + CLI

**Files:**
- Modify: `src/tldr_swinton/api.py`
- Modify: `src/tldr_swinton/cli.py`
- Modify: `src/tldr_swinton/output_formats.py`

**Step 1: Add `get_diff_context` (ContextPack builder)**

```python
# build slices: contains_diff + 1-hop callers/callees
# budget: full code for top; signatures for overflow
```

**Step 2: Add CLI subcommand `diff-context`**

```python
# args: --base, --head, --budget, --format text|json
```

**Step 3: Update tldr-bench difflens variant to use new API**

Files: `tldr-bench/tldr_bench/variants/difflens.py`

**Step 4: Run tests**

Run: `python -m pytest tests/test_difflens.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/tldr_swinton/api.py src/tldr_swinton/cli.py src/tldr_swinton/output_formats.py tldr-bench/tldr_bench/variants/difflens.py
git commit -m "feat: implement difflens context packs"
```

### Task 4: Full verification

**Files:**
- None

**Step 1: Run tests (project tests only)**

Run: `python -m pytest tests -q`
Expected: PASS

**Step 2: Commit (if needed)**

```bash
git status --short
```

