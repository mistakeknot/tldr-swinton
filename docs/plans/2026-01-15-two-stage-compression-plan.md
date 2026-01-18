# Two-Stage Compression Prototype Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** N/A (Task reference)

**Goal:** Prototype a LongCodeZip-style two-stage compression mode for DiffLens/ContextPack to improve token savings under tight budgets.

**Architecture:** Add an opt-in `--compress=two-stage` mode to DiffLens output that first ranks functions (diff proximity + call graph + heuristic relevance), then prunes within functions to include only high-value blocks (diff-adjacent windows + optional PDG block selection). Keep output in ultracompact format and include a per-slice `block_count` + `dropped_blocks` summary.

**Tech Stack:** Python, pytest

### Task 1: Add failing tests for two-stage compression selection

**Files:**
- Modify: `tests/test_difflens_eval.py`

**Step 1: Write the failing test**

```python
def test_two_stage_compress_prunes_blocks(tmp_path: Path) -> None:
    from evals import difflens_eval as de
    repo = tmp_path / "repo"
    repo.mkdir()
    de._write_multifile_repo(repo)
    pack = de.get_diff_context(repo, base="HEAD", head="HEAD", budget_tokens=500, language="python", compress="two-stage")
    slices = pack.get("slices", [])
    assert any(s.get("dropped_blocks", 0) > 0 for s in slices)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_difflens_eval.py::test_two_stage_compress_prunes_blocks -v`
Expected: FAIL (unsupported compress mode or missing fields)

**Step 3: Write minimal implementation**

Implement `compress="two-stage"` in DiffLens pipeline with block pruning and `dropped_blocks` metadata.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_difflens_eval.py::test_two_stage_compress_prunes_blocks -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_difflens_eval.py src/tldr_swinton/engines/difflens.py src/tldr_swinton/output_formats.py
git commit -m "feat: add two-stage compression prototype"
```

### Task 2: Add CLI flag + wire through ContextPack

**Files:**
- Modify: `src/tldr_swinton/cli.py`
- Modify: `src/tldr_swinton/engines/difflens.py`
- Modify: `src/tldr_swinton/api.py`

**Step 1: Write the failing test**

```python
def test_difflens_compress_flag(tmp_path: Path) -> None:
    from tldr_swinton.cli import parse_args
    args = parse_args(["diff-context", "--compress", "two-stage"])
    assert args.compress == "two-stage"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_difflens_compress_flag -v`
Expected: FAIL (flag not recognized)

**Step 3: Write minimal implementation**

Add `--compress` flag to diff-context and thread into `get_diff_context` and the engine.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::test_difflens_compress_flag -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/tldr_swinton/cli.py src/tldr_swinton/api.py tests/test_cli.py
git commit -m "feat: add diff-context compress flag"
```

### Task 3: Evaluate + document

**Files:**
- Modify: `evals/difflens_eval.py`
- Modify: `README.md`

**Step 1: Add eval mode**

Add a `--compress` option in eval runner and report savings vs diff+deps baseline for two-stage mode.

**Step 2: Run evals**

Run: `python evals/difflens_eval.py --compress two-stage`
Expected: Prints new savings/latency line.

**Step 3: Update README**

Add a short note in DiffLens section about the experimental compression mode.

**Step 4: Commit**

```bash
git add evals/difflens_eval.py README.md
git commit -m "docs: note two-stage compression prototype"
```
