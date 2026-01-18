# Chunk Summarization Compression Prototype Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** N/A (Task reference)

**Goal:** Prototype a SCOPE-style chunk summarization compression mode for DiffLens output to reduce tokens while preserving key identifiers.

**Architecture:** Add an opt-in `--compress=chunk-summary` mode that replaces code bodies with a short structural summary per slice (keeps signature, identifiers, and line ranges). Summaries are heuristic (no LLM calls) and use simple heuristics: keep def/class line, selected identifier lines, and elide details. Output includes `summary` field and marks `code=null` for summary-only slices.

**Tech Stack:** Python, pytest

### Task 1: Add failing test for chunk-summary compression

**Files:**
- Modify: `tests/test_difflens_eval.py`

**Step 1: Write the failing test**

```python
def test_chunk_summary_mode_emits_summary(tmp_path: Path) -> None:
    from tldr_swinton.api import get_diff_context
    repo = tmp_path / "repo"
    repo.mkdir()
    import subprocess
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "diff-eval@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "DiffEval"], check=True)
    file_path = repo / "app.py"
    file_path.write_text("def foo():\n    value = 1\n    return value\n")
    subprocess.run(["git", "-C", str(repo), "add", "app.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True)
    file_path.write_text("def foo():\n    value = 2\n    return value\n")
    pack = get_diff_context(repo, base="HEAD", head="HEAD", budget_tokens=500, language="python", compress="chunk-summary")
    slices = pack.get("slices", [])
    assert any(s.get("summary") for s in slices)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_difflens_eval.py::test_chunk_summary_mode_emits_summary -v`
Expected: FAIL (unknown compress mode or missing summary)

**Step 3: Write minimal implementation**

Implement `compress="chunk-summary"` in DiffLens pipeline, adding a `summary` field (string) and nulling `code`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_difflens_eval.py::test_chunk_summary_mode_emits_summary -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_difflens_eval.py src/tldr_swinton/engines/difflens.py
 git commit -m "feat: add chunk-summary compression prototype"
```

### Task 2: Wire CLI flag and eval runner

**Files:**
- Modify: `src/tldr_swinton/cli.py`
- Modify: `src/tldr_swinton/api.py`
- Modify: `evals/difflens_eval.py`

**Step 1: Write failing test**

```python
def test_cli_diff_context_compress_chunk_summary(tmp_path: Path) -> None:
    import subprocess, sys
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "diff-eval@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "DiffEval"], check=True)
    (repo / "app.py").write_text("def foo():\n    return 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "app.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True)
    (repo / "app.py").write_text("def foo():\n    return 2\n")
    result = subprocess.run([sys.executable, "-m", "tldr_swinton.cli", "diff-context", "--project", str(repo), "--compress", "chunk-summary"], text=True, capture_output=True)
    assert result.returncode == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_context.py::test_cli_diff_context_compress_chunk_summary -v`
Expected: FAIL (unknown compress option)

**Step 3: Implement minimal wiring**

Extend CLI `--compress` choices and pass through to API; update eval runner to accept `--compress chunk-summary`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_context.py::test_cli_diff_context_compress_chunk_summary -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/tldr_swinton/cli.py src/tldr_swinton/api.py evals/difflens_eval.py tests/test_cli_context.py
 git commit -m "feat: wire chunk-summary compression"
```

### Task 3: Evaluate + note experimental mode

**Files:**
- Modify: `README.md`

**Step 1: Run eval**

Run: `python evals/difflens_eval.py --compress chunk-summary`
Expected: Metrics printed.

**Step 2: Update README**

Add a short note in DiffLens section about `--compress chunk-summary`.

**Step 3: Commit**

```bash
git add README.md
 git commit -m "docs: note chunk-summary compression mode"
```
