# VHS Preview Output Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** [none] (no bead provided)

**Goal:** Add summary + mixed‑cap preview when `tldrs context --output vhs` is used, while keeping the ref as the first output line.

**Architecture:** Introduce small helper functions in the CLI to generate a summary and preview. Update CLI behavior for `--output vhs` to print ref + preview. Add focused tests for preview logic and CLI output ordering.

**Tech Stack:** Python 3, argparse, pytest

### Task 1: Add failing tests for preview helpers and CLI output

**Files:**
- Create: `tests/test_vhs_preview.py`
- Modify: `tests/test_cli_context.py`

**Step 1: Write the failing test (preview mixed caps)**

```python
from tldr_swinton.cli import _make_vhs_preview

def test_preview_caps():
    text = "line1\n" + ("x" * 3000) + "\nline3\n"
    preview = _make_vhs_preview(text, max_lines=30, max_bytes=2048)
    assert "line1" in preview
    assert "line3" not in preview
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_vhs_preview.py::test_preview_caps -q`
Expected: FAIL (function not found)

**Step 3: Write the failing test (ref is first line)**

```python
result = subprocess.run([... "context", "foo", "--output", "vhs" ...])
lines = result.stdout.strip().splitlines()
assert lines[0].startswith("vhs://")
assert any("# Summary" in l for l in lines[1:])
```

**Step 4: Run test to verify it fails**

Run: `python -m pytest tests/test_cli_context.py::test_cli_context_output_vhs_preview -q`
Expected: FAIL (no summary/preview)

**Step 5: Commit**

```bash
git add tests/test_vhs_preview.py tests/test_cli_context.py
git commit -m "test: add vhs preview coverage"
```

### Task 2: Implement preview helpers and CLI output

**Files:**
- Modify: `src/tldr_swinton/cli.py`

**Step 1: Implement summary helper**

```python
def _make_vhs_summary(ctx: RelevantContext) -> str:
    files = {Path(f.file).name for f in ctx.functions if f.file}
    return f"Entry {ctx.entry_point} depth={ctx.depth} functions={len(ctx.functions)} files={len(files)}"
```

**Step 2: Implement preview helper with mixed caps**

```python
def _make_vhs_preview(text, max_lines=30, max_bytes=2048):
    out, used = [], 0
    for line in text.splitlines():
        if len(out) >= max_lines:
            break
        line_bytes = len((line + "\n").encode("utf-8"))
        if used + line_bytes > max_bytes:
            break
        out.append(line)
        used += line_bytes
    return "\n".join(out)
```

**Step 3: Update vhs output path**

```python
ref = _vhs_put(output)
summary = _make_vhs_summary(ctx)
preview = _make_vhs_preview(output)
print(ref)
print(f"# Summary: {summary}")
print("# Preview:")
print(preview)
```

**Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_vhs_preview.py::test_preview_caps tests/test_cli_context.py::test_cli_context_output_vhs_preview -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/tldr_swinton/cli.py
git commit -m "feat: add vhs preview output"
```

### Task 3: Full verification

**Files:**
- None

**Step 1: Run test suite**

Run: `python -m pytest -q`
Expected: PASS

**Step 2: Commit (if needed)**

```bash
git status --short
```

