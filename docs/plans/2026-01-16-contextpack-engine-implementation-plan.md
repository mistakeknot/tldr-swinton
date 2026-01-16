# ContextPack Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** n/a (no bead in use)

**Goal:** Implement a shared ContextPack Engine that unifies DiffLens and SymbolKite outputs under one schema with shared symbol registry, budget allocation, and formatting.

**Architecture:** Introduce a new engine module that accepts candidate symbols + relevance and produces a ContextPack (slices + signatures_only). Add a SymbolRegistry for metadata lookup, a BudgetAllocator to decide full-code vs signature-only, and a formatter for text/ultracompact/json outputs. Route DiffLens and SymbolKite through the engine while preserving existing behavior as defaults.

**Tech Stack:** Python 3, pytest, tldr-swinton core modules (`engines/difflens.py`, `engines/symbolkite.py`, `output_formats.py`).

---

### Task 1: Add ContextPack data model + engine skeleton

**Files:**
- Create: `src/tldr_swinton/contextpack_engine.py`
- Test: `tests/test_contextpack_engine.py`

**Step 1: Write the failing test**

```python
from tldr_swinton.contextpack_engine import ContextPackEngine, Candidate


def test_contextpack_orders_by_relevance_and_applies_budget() -> None:
    candidates = [
        Candidate("a.py:high", relevance=100),
        Candidate("b.py:low", relevance=10),
    ]
    engine = ContextPackEngine()
    pack = engine.build_context_pack(candidates, budget_tokens=50)
    assert pack.slices
    assert pack.slices[0].id.endswith("a.py:high")
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_contextpack_engine.py::test_contextpack_orders_by_relevance_and_applies_budget -v`
Expected: FAIL with import or attribute error.

**Step 3: Write minimal implementation**

```python
# contextpack_engine.py
from dataclasses import dataclass

@dataclass
class Candidate:
    symbol_id: str
    relevance: int

@dataclass
class ContextSlice:
    id: str
    signature: str
    code: str | None
    lines: tuple[int, int] | None
    relevance: str | None = None

@dataclass
class ContextPack:
    slices: list[ContextSlice]
    signatures_only: list[str]
    budget_used: int = 0

class ContextPackEngine:
    def build_context_pack(self, candidates, budget_tokens: int | None = None) -> ContextPack:
        # minimal stub to satisfy test (no real budget yet)
        slices = [ContextSlice(id=candidates[0].symbol_id, signature="", code=None, lines=None)]
        return ContextPack(slices=slices, signatures_only=[])
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_contextpack_engine.py::test_contextpack_orders_by_relevance_and_applies_budget -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/tldr_swinton/contextpack_engine.py tests/test_contextpack_engine.py
git commit -m "Add ContextPack engine skeleton"
```

---

### Task 2: Add SymbolRegistry for file-qualified symbol lookup

**Files:**
- Create: `src/tldr_swinton/symbol_registry.py`
- Test: `tests/test_symbol_registry.py`

**Step 1: Write the failing test**

```python
from pathlib import Path
from tldr_swinton.symbol_registry import SymbolRegistry


def test_symbol_registry_resolves_signature(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text("def foo(x):\n    return x\n")
    registry = SymbolRegistry(tmp_path, language="python")
    info = registry.get("mod.py:foo")
    assert info.signature.startswith("def foo")
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_symbol_registry.py::test_symbol_registry_resolves_signature -v`
Expected: FAIL with missing registry.

**Step 3: Write minimal implementation**

```python
# symbol_registry.py
from pathlib import Path
from .hybrid_extractor import HybridExtractor

class SymbolInfo:
    def __init__(self, signature: str, file: str, lines: tuple[int, int] | None):
        self.signature = signature
        self.file = file
        self.lines = lines

class SymbolRegistry:
    def __init__(self, root: str | Path, language: str = "python"):
        self.root = Path(root)
        self.language = language

    def get(self, symbol_id: str) -> SymbolInfo:
        file_part, name = symbol_id.split(":", 1)
        file_path = self.root / file_part
        extractor = HybridExtractor()
        info = extractor.extract(str(file_path))
        for func in info.functions:
            if func.name == name:
                return SymbolInfo(func.signature(), file_part, (func.line_number, func.line_number))
        raise KeyError(symbol_id)
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_symbol_registry.py::test_symbol_registry_resolves_signature -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/tldr_swinton/symbol_registry.py tests/test_symbol_registry.py
git commit -m "Add SymbolRegistry for ContextPack"
```

---

### Task 3: Implement budget allocation + full-code retrieval

**Files:**
- Modify: `src/tldr_swinton/contextpack_engine.py`
- Modify: `src/tldr_swinton/symbol_registry.py`
- Test: `tests/test_contextpack_budget.py`

**Step 1: Write the failing test**

```python
from pathlib import Path
from tldr_swinton.contextpack_engine import ContextPackEngine, Candidate
from tldr_swinton.symbol_registry import SymbolRegistry


def test_budget_allocates_full_then_signature(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def hi():\n    return 1\n")
    (tmp_path / "b.py").write_text("def lo():\n    return 2\n")
    registry = SymbolRegistry(tmp_path, language="python")
    engine = ContextPackEngine(registry=registry)
    pack = engine.build_context_pack(
        [Candidate("a.py:hi", relevance=100), Candidate("b.py:lo", relevance=10)],
        budget_tokens=30,
    )
    assert pack.slices[0].id.endswith("a.py:hi")
    assert "b.py:lo" in pack.signatures_only
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_contextpack_budget.py::test_budget_allocates_full_then_signature -v`
Expected: FAIL (budget logic missing).

**Step 3: Write minimal implementation**

- Add `ContextPackEngine(registry=SymbolRegistry)` dependency
- Add token estimator (reuse `output_formats._estimate_tokens` or inline)
- Allocate full code for top‑ranked candidates until budget, then signatures_only

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_contextpack_budget.py::test_budget_allocates_full_then_signature -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/tldr_swinton/contextpack_engine.py src/tldr_swinton/symbol_registry.py tests/test_contextpack_budget.py
git commit -m "Implement ContextPack budget allocation"
```

---

### Task 4: Add ContextPack formatter (text/ultracompact/json)

**Files:**
- Modify: `src/tldr_swinton/output_formats.py`
- Test: `tests/test_contextpack_format.py`

**Step 1: Write the failing test**

```python
from tldr_swinton.contextpack_engine import ContextPack, ContextSlice
from tldr_swinton.output_formats import format_context_pack


def test_contextpack_json_format() -> None:
    pack = ContextPack(slices=[ContextSlice(id="a.py:hi", signature="def hi()", code=None, lines=None)], signatures_only=[])
    out = format_context_pack(pack, fmt="json")
    assert "a.py:hi" in out
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_contextpack_format.py::test_contextpack_json_format -v`
Expected: FAIL because format_context_pack doesn’t accept ContextPack object.

**Step 3: Write minimal implementation**

- Update `format_context_pack` to accept either `dict` or `ContextPack`
- Add encoder to serialize `ContextPack` to dict

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_contextpack_format.py::test_contextpack_json_format -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/tldr_swinton/output_formats.py tests/test_contextpack_format.py
git commit -m "Add ContextPack formatting support"
```

---

### Task 5: Route DiffLens through ContextPack Engine

**Files:**
- Modify: `src/tldr_swinton/engines/difflens.py`
- Modify: `src/tldr_swinton/api.py`
- Test: `tests/test_difflens_contextpack.py`

**Step 1: Write the failing test**

```python
from pathlib import Path
from tldr_swinton.api import get_diff_context


def test_difflens_uses_contextpack_engine(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def hi():\n    return 1\n")
    pack = get_diff_context(tmp_path, budget_tokens=50)
    assert "slices" in pack
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_difflens_contextpack.py::test_difflens_uses_contextpack_engine -v`
Expected: FAIL if no ContextPack integration.

**Step 3: Write minimal implementation**

- In DiffLens, build candidate list from hunks + relevance
- Call ContextPackEngine to build pack
- Preserve existing schema keys (`slices`, `signatures_only`)

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_difflens_contextpack.py::test_difflens_uses_contextpack_engine -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/tldr_swinton/engines/difflens.py src/tldr_swinton/api.py tests/test_difflens_contextpack.py
git commit -m "Route DiffLens through ContextPack engine"
```

---

### Task 6: Add SymbolKite ContextPack adapter

**Files:**
- Modify: `src/tldr_swinton/engines/symbolkite.py`
- Modify: `src/tldr_swinton/api.py`
- Test: `tests/test_symbolkite_contextpack.py`

**Step 1: Write the failing test**

```python
from pathlib import Path
from tldr_swinton.api import get_symbol_context_pack


def test_symbolkite_contextpack(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("def foo():\n    return 1\n")
    pack = get_symbol_context_pack(tmp_path, "foo", budget_tokens=50)
    assert pack["slices"]
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_symbolkite_contextpack.py::test_symbolkite_contextpack -v`
Expected: FAIL (no adapter yet).

**Step 3: Write minimal implementation**

- Add `get_symbol_context_pack()` in `api.py`
- In `symbolkite.py`, create candidate list from BFS traversal
- Use ContextPackEngine + formatter for output

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_symbolkite_contextpack.py::test_symbolkite_contextpack -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/tldr_swinton/engines/symbolkite.py src/tldr_swinton/api.py tests/test_symbolkite_contextpack.py
git commit -m "Add SymbolKite ContextPack adapter"
```

---

### Task 7: CLI/MCP wiring for unified ContextPack output

**Files:**
- Modify: `src/tldr_swinton/cli.py`
- Modify: `src/tldr_swinton/daemon.py`
- Modify: `src/tldr_swinton/mcp_server.py`
- Test: `tests/test_cli_contextpack.py`

**Step 1: Write the failing test**

```python
import subprocess


def test_cli_contextpack_command(tmp_path):
    (tmp_path / "m.py").write_text("def foo():\n    return 1\n")
    result = subprocess.run(
        ["tldrs", "context", "foo", "--project", str(tmp_path), "--format", "ultracompact"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cli_contextpack.py::test_cli_contextpack_command -v`
Expected: FAIL if format not routed through ContextPack.

**Step 3: Write minimal implementation**

- Route `context` output through ContextPack engine when format requests ultracompact/json
- MCP `context` returns formatted string from same formatter

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_cli_contextpack.py::test_cli_contextpack_command -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/tldr_swinton/cli.py src/tldr_swinton/daemon.py src/tldr_swinton/mcp_server.py tests/test_cli_contextpack.py
git commit -m "Wire ContextPack output into CLI/MCP"
```

---

### Task 8: Final verification

**Step 1: Run new tests together**

```bash
.venv/bin/python -m pytest \
  tests/test_contextpack_engine.py \
  tests/test_symbol_registry.py \
  tests/test_contextpack_budget.py \
  tests/test_contextpack_format.py \
  tests/test_difflens_contextpack.py \
  tests/test_symbolkite_contextpack.py \
  tests/test_cli_contextpack.py
```

Expected: All PASS.

---

## Notes
- Keep existing output formats stable by default; add ContextPack path behind format selection.
- All new symbols must be file-qualified (`rel_path:qualified_name`).
- Use `iter_workspace_files` for traversal to respect `.tldrsignore`.
