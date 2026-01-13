# tldr-bench Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** `tldr-swinton-0hq (Scaffold tldr-bench repo)`

**Goal:** Create a `tldr-bench/` repo inside tldr-swinton with uv-only setup, OpenHands dependency, basic layout, and a curated task suite.

**Architecture:** A minimal Python package with task definitions (YAML), variant stubs, and a thin runner that integrates OpenHands later. Logging is centralized in a simple JSONL logger to enable eval instrumentation from day one.

**Tech Stack:** Python 3, uv, OpenHands (dependency), PyYAML, tiktoken.

---

### Task 1: Scaffold repository layout

**Files:**
- Create: `tldr-bench/README.md`
- Create: `tldr-bench/pyproject.toml`
- Create: `tldr-bench/tldr_bench/__init__.py`
- Create: `tldr-bench/tldr_bench/config.py`
- Create: `tldr-bench/tldr_bench/logger.py`
- Create: `tldr-bench/tldr_bench/runners/__init__.py`
- Create: `tldr-bench/tldr_bench/runners/openhands_runner.py`
- Create: `tldr-bench/tldr_bench/tasks/__init__.py`
- Create: `tldr-bench/tldr_bench/tasks/curated.yaml`
- Create: `tldr-bench/tldr_bench/tasks/public_subset.yaml`
- Create: `tldr-bench/tldr_bench/variants/__init__.py`
- Create: `tldr-bench/tldr_bench/variants/baselines.py`
- Create: `tldr-bench/tldr_bench/variants/difflens.py`
- Create: `tldr-bench/tldr_bench/variants/symbolkite.py`
- Create: `tldr-bench/tldr_bench/variants/cassette.py`
- Create: `tldr-bench/tldr_bench/variants/coveragelens.py`
- Create: `tldr-bench/scripts/run_bench.py`
- Create: `tldr-bench/scripts/summarize.py`
- Create: `tldr-bench/results/.gitkeep`
- Create: `tldr-bench/docs/TASKS.md`
- Create: `tldr-bench/docs/VARIANTS.md`
- Create: `tldr-bench/docs/LOG_SCHEMA.md`

**Step 1: Create directories**

Run:
```bash
mkdir -p tldr-bench/tldr_bench/{runners,tasks,variants} tldr-bench/scripts tldr-bench/results tldr-bench/docs
```
Expected: Directories created, no output.

**Step 2: Write minimal README**

Create `tldr-bench/README.md` with:
```markdown
# tldr-bench

Token-efficiency benchmarks for tldr-swinton using the OpenHands evaluation harness.

## Quickstart (uv)

```bash
uv venv
uv pip install -e .
python scripts/run_bench.py --help
```
```

**Step 3: Write uv-only pyproject.toml**

Create `tldr-bench/pyproject.toml` with:
```toml
[project]
name = "tldr-bench"
version = "0.1.0"
description = "Token-efficiency benchmarks for tldr-swinton"
requires-python = ">=3.10"
dependencies = [
  "openhands-benchmarks",
  "pyyaml",
  "tiktoken",
]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"
```

**Step 4: Add package stubs**

Create empty `__init__.py` files and simple module placeholders.

Example `tldr-bench/tldr_bench/config.py`:
```python
from dataclasses import dataclass
from pathlib import Path

@dataclass
class BenchConfig:
    root: Path
    results_dir: Path
```

Example `tldr-bench/tldr_bench/logger.py`:
```python
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

@dataclass
class JsonlLogger:
    path: Path

    def log(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
```

**Step 5: Add scripts**

Create `tldr-bench/scripts/run_bench.py`:
```python
import argparse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--help-variants", action="store_true")
    args = parser.parse_args()
    if args.help_variants:
        print("baselines, difflens, symbolkite, cassette, coveragelens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Create `tldr-bench/scripts/summarize.py` with a placeholder `main()`.

**Step 6: Add docs placeholders**

Write `tldr-bench/docs/LOG_SCHEMA.md` with the JSONL fields from eval plan.
Write `tldr-bench/docs/TASKS.md` with task schema description.
Write `tldr-bench/docs/VARIANTS.md` with list of variants.

**Step 7: Commit**

Run:
```bash
git add tldr-bench

git commit -m "Scaffold tldr-bench repo"
```
Expected: Commit created.

---

### Task 2: Add curated task suite

**Files:**
- Modify: `tldr-bench/tldr_bench/tasks/curated.yaml`
- Modify: `tldr-bench/tldr_bench/tasks/public_subset.yaml`
- Modify: `tldr-bench/docs/TASKS.md`

**Step 1: Define task schema**

In `docs/TASKS.md`, specify required fields:
- `id`, `title`, `repo`, `entry`, `expected_files`, `expected_lines`, `type`, `notes`

**Step 2: Add curated tasks**

Populate `curated.yaml` with 5–7 example tasks referencing `tldr-swinton` paths (placeholders ok). Example:
```yaml
- id: cur-001
  title: "Optimize embed text truncation"
  repo: "tldr-swinton"
  entry: "tldr_swinton/index.py:_build_embed_text"
  expected_files: ["src/tldr_swinton/index.py"]
  expected_lines: [228, 240]
  type: "small_refactor"
  notes: "Docstring truncation logic"
```

**Step 3: Add public subset placeholder**

Populate `public_subset.yaml` with placeholders for SWE-bench IDs to fill later.

**Step 4: Commit**

Run:
```bash
git add tldr-bench/tldr_bench/tasks tldr-bench/docs/TASKS.md

git commit -m "Add initial task suite"
```

---

### Task 3: Add variant stubs and logging schema

**Files:**
- Modify: `tldr-bench/docs/LOG_SCHEMA.md`
- Modify: `tldr-bench/tldr_bench/variants/*.py`
- Modify: `tldr-bench/tldr_bench/logger.py`

**Step 1: Fill LOG_SCHEMA.md**

Add full field list from `docs/plans/2026-01-13-context-optimization-eval-plan.md`.

**Step 2: Add variant stubs**

Each variant module should expose a `VARIANT_ID` and a `build_context()` stub.
Example:
```python
VARIANT_ID = "difflens"

def build_context(task: dict) -> str:
    raise NotImplementedError
```

**Step 3: Extend logger**

Add a helper to log minimal metadata with timestamp.

**Step 4: Commit**

Run:
```bash
git add tldr-bench/docs/LOG_SCHEMA.md tldr-bench/tldr_bench/variants tldr-bench/tldr_bench/logger.py

git commit -m "Add variant stubs and logging schema"
```

---

### Task 4: Add runner placeholder with OpenHands hooks

**Files:**
- Modify: `tldr-bench/tldr_bench/runners/openhands_runner.py`
- Modify: `tldr-bench/scripts/run_bench.py`

**Step 1: Add runner interface**

Stub a `run_task()` signature accepting task + variant. Leave NotImplemented for now.

**Step 2: Wire script to runner**

Add argument parsing for `--tasks` and `--variant` and call the runner stub.

**Step 3: Commit**

Run:
```bash
git add tldr-bench/tldr_bench/runners/openhands_runner.py tldr-bench/scripts/run_bench.py

git commit -m "Add runner stub"
```

---

## Testing
No automated tests in this scaffold. Validate by:
```bash
python tldr-bench/scripts/run_bench.py --help
```
Expected: help output, exit code 0.

## Notes
- This plan avoids touching the OpenHands harness directly.
- The goal is a clean scaffold ready for integration.

