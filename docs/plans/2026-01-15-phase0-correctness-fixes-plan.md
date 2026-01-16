# Phase 0 Correctness Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** n/a (no bead in use)

**Goal:** Ensure Phase‑0 correctness guarantees (symbol identity, ignore rules, signature fidelity, import correctness, and context formatting) are enforced by tests and fixed where needed.

**Architecture:** Add focused regression tests that encode Phase‑0 guarantees, then make minimal, targeted changes in the call‑graph, workspace filtering, and output formatting layers to satisfy those tests. Reuse `iter_workspace_files` for traversal and `FunctionInfo.signature()` for language‑aware signatures.

**Tech Stack:** Python 3, pytest, tldr-swinton core modules (`symbolkite`, `analysis`, `workspace`, `api`).

---

### Task 1: Symbol identity is file‑qualified in call graph + impact analysis

**Files:**
- Create: `tests/test_symbol_identity.py`
- Modify (if failing): `src/tldr_swinton/analysis.py`, `src/tldr_swinton/cross_file_calls.py`, `src/tldr_swinton/engines/symbolkite.py`

**Step 1: Write the failing test**

```python
from pathlib import Path
from tldr_swinton.cross_file_calls import build_project_call_graph
from tldr_swinton.analysis import impact_analysis
from tldr_swinton.engines.symbolkite import get_relevant_context

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_symbol_identity_is_file_qualified(tmp_path: Path) -> None:
    _write(tmp_path / "a.py", "def dup():\n    return 1\n")
    _write(tmp_path / "b.py", "def dup():\n    return 2\n")
    _write(tmp_path / "c.py", "from a import dup\n\n" "def caller():\n    return dup()\n")

    graph = build_project_call_graph(str(tmp_path), language="python")
    result = impact_analysis(graph, "dup", target_file="a.py")

    assert "error" not in result
    assert any("a.py:dup" in k for k in result["targets"].keys())

    ctx = get_relevant_context(tmp_path, "a.py:dup", depth=1, language="python")
    names = [f.name for f in ctx.functions]
    assert any(n.endswith("a.py:dup") for n in names)
    assert all("b.py:dup" not in n for n in names)
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_symbol_identity.py::test_symbol_identity_is_file_qualified -v`
Expected: FAIL if identity is not file‑qualified (e.g., ambiguous symbol or wrong file chosen).

**Step 3: Write minimal implementation**

If failing, ensure file‑qualified IDs are used consistently:

```python
# analysis.py: ensure target lookup respects file-qualified names
if target_file is None and ":" in target_func:
    target_file, target_func = target_func.split(":", 1)
```

```python
# symbolkite.py: ensure adjacency + visited uses full rel_path:qualified_name
symbol_id = f"{rel_path}:{qualified_name}"
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_symbol_identity.py::test_symbol_identity_is_file_qualified -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_symbol_identity.py src/tldr_swinton/analysis.py src/tldr_swinton/cross_file_calls.py src/tldr_swinton/engines/symbolkite.py
git commit -m "Add file-qualified symbol identity regression test"
```

---

### Task 2: `.tldrsignore` respected by context traversal

**Files:**
- Create: `tests/test_workspace_ignore.py`
- Modify (if failing): `src/tldr_swinton/engines/symbolkite.py`, `src/tldr_swinton/api.py`

**Step 1: Write the failing test**

```python
from pathlib import Path
from tldr_swinton.engines.symbolkite import get_relevant_context


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_tldrsignore_excludes_files(tmp_path: Path) -> None:
    _write(tmp_path / ".tldrsignore", "ignored.py\n")
    _write(tmp_path / "ignored.py", "def ignored():\n    return 1\n")
    _write(tmp_path / "main.py", "def entry():\n    return 2\n")

    ctx = get_relevant_context(tmp_path, "entry", depth=1, language="python")
    names = [f.name for f in ctx.functions]
    assert all("ignored.py" not in name for name in names)
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_workspace_ignore.py::test_tldrsignore_excludes_files -v`
Expected: FAIL if ignore rules are not applied.

**Step 3: Write minimal implementation**

If failing, ensure context traversal uses `iter_workspace_files` (with ignore enabled):

```python
for file_path in iter_workspace_files(project, extensions=extensions):
    ...
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_workspace_ignore.py::test_tldrsignore_excludes_files -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_workspace_ignore.py src/tldr_swinton/engines/symbolkite.py src/tldr_swinton/api.py
git commit -m "Verify .tldrsignore filtering in context traversal"
```

---

### Task 3: Language-aware signatures used in semantic export paths

**Files:**
- Create: `tests/test_semantic_signatures.py`
- Modify (if failing): `src/tldr_swinton/api.py`, `src/tldr_swinton/semantic.py`

**Step 1: Write the failing test**

```python
from pathlib import Path
from tldr_swinton.semantic import _get_signature_via_extractor


def test_semantic_signature_uses_language(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.ts"
    file_path.write_text("export async function foo(x: number): Promise<void> { return; }\n")

    signature = _get_signature_via_extractor(file_path, "foo")
    assert signature is not None
    assert signature.strip().startswith("async function foo(")
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_semantic_signatures.py::test_semantic_signature_uses_language -v`
Expected: FAIL if TypeScript signatures still look like Python `def`.

**Step 3: Write minimal implementation**

If failing, route all signature building through `FunctionInfo.signature()`:

```python
# semantic.py
return func.signature()
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_semantic_signatures.py::test_semantic_signature_uses_language -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_semantic_signatures.py src/tldr_swinton/api.py src/tldr_swinton/semantic.py
git commit -m "Ensure semantic signatures are language-aware"
```

---

### Task 4: Guard against `tldr.*` imports (must use `tldr_swinton.*`)

**Files:**
- Create: `tests/test_no_tldr_imports.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_no_tldr_imports() -> None:
    repo = Path(__file__).resolve().parents[1]
    matches = []
    for path in repo.rglob("*.py"):
        if "dist" in path.parts or "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "from tldr" in text or "import tldr" in text:
            matches.append(str(path))
    assert matches == []
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_no_tldr_imports.py::test_no_tldr_imports -v`
Expected: FAIL if any `tldr.*` imports remain.

**Step 3: Write minimal implementation**

If failing, replace remaining imports with `tldr_swinton.*` in the indicated files.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_no_tldr_imports.py::test_no_tldr_imports -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_no_tldr_imports.py src/tldr_swinton/*.py
git commit -m "Prevent tldr.* imports"
```

---

### Task 5: `RelevantContext.to_llm_string()` indents by BFS depth (not enumeration)

**Files:**
- Create: `tests/test_context_formatting.py`
- Modify (if failing): `src/tldr_swinton/engines/symbolkite.py`

**Step 1: Write the failing test**

```python
from tldr_swinton.engines.symbolkite import RelevantContext, FunctionContext


def test_context_indent_uses_depth() -> None:
    ctx = RelevantContext(
        entry_point="root",
        depth=2,
        functions=[
            FunctionContext(name="root", file="root.py", line=1, signature="def root():", depth=0),
            FunctionContext(name="child", file="child.py", line=5, signature="def child():", depth=2),
        ],
    )
    rendered = ctx.to_llm_string().splitlines()
    root_line = next(line for line in rendered if "root.py" in line)
    child_line = next(line for line in rendered if "child.py" in line)
    assert child_line.startswith("    ")
    assert not root_line.startswith("    ")
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_context_formatting.py::test_context_indent_uses_depth -v`
Expected: FAIL if indentation uses enumerate index instead of depth.

**Step 3: Write minimal implementation**

If failing, compute indent from `func.depth`:

```python
indent = "  " * min(func.depth, self.depth)
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_context_formatting.py::test_context_indent_uses_depth -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_context_formatting.py src/tldr_swinton/engines/symbolkite.py
git commit -m "Fix context indentation to use BFS depth"
```

---

### Task 6: Verify all new Phase‑0 tests together

**Files:**
- None (verification only)

**Step 1: Run full Phase‑0 test set**

Run:
```bash
.venv/bin/python -m pytest \
  tests/test_symbol_identity.py \
  tests/test_workspace_ignore.py \
  tests/test_semantic_signatures.py \
  tests/test_no_tldr_imports.py \
  tests/test_context_formatting.py
```

Expected: All PASS.

**Step 2: Commit (if any fixes were made in this task)**

```bash
git status -sb
```
If clean, no commit needed.

---

## Notes
- If a test passes immediately, keep it as a regression guard and skip code changes for that task.
- Follow TDD: do not change production code before a failing test.
- Keep changes minimal and isolated; avoid unrelated refactors.
