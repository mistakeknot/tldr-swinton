# TLDRS Benchmark Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** `tldr-swinton-m0w (tldr-bench: implement benchmark tracks)` — mandatory line tying the plan to the active bead/Task Master item.

**Goal:** Implement the three benchmark tracks (static/context, token-efficiency frontier, executable) in `tldr-bench`, capturing token/latency metrics using local Codex CLI and Claude Code.

**Architecture:** Add a runner router to select per-task execution (static vs CLI/OpenHands). Add shared metrics utilities for token counting + timing, and extend the local OpenAI-compatible shim to emit usage + timing and optional JSONL request logs. Tasks are defined in YAML suites per track, and results are summarized by a small reporting script. All commands use `tldrs` (not `tldr`).

**Tech Stack:** Python 3.10+, uv, pytest, FastAPI, tiktoken, tldrs, OpenHands benchmarks, local CLI shim.

---

Constraint: per user request, **no git worktrees**. All steps assume working in the current repo.

### Task 1: Add Token Counting + Timing Utilities

Skills: @test-driven-development @verification-before-completion

**Files:**
- Create: `tldr-bench/tldr_bench/metrics.py`
- Test: `tldr-bench/tests/test_metrics.py`

**Step 1: Write the failing test**

```python
from tldr_bench.metrics import count_tokens, TokenTiming


def test_count_tokens_known_model():
    text = "hello world"
    result = count_tokens(text, model="gpt-4o")
    assert isinstance(result, int)
    assert result > 0


def test_token_timing_records_ms():
    timing = TokenTiming()
    with timing.section("context"):
        _ = "a" * 10
    assert "context_ms" in timing.to_dict()
    assert timing.to_dict()["context_ms"] >= 0
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError: tldr_bench.metrics`.

**Step 3: Write minimal implementation**

```python
from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any

import tiktoken


def _resolve_encoding(model: str) -> tuple[str, tiktoken.Encoding]:
    normalized = (model or "").lower()
    if normalized.startswith(("gpt-", "o1", "o3", "codex")):
        enc = tiktoken.encoding_for_model("gpt-4o")
        return "tiktoken:gpt-4o", enc
    enc = tiktoken.get_encoding("cl100k_base")
    return "tiktoken:cl100k_base", enc


def count_tokens(text: str, model: str | None = None) -> int:
    tokenizer_id, enc = _resolve_encoding(model or "")
    _ = tokenizer_id  # used by callers who need it
    return len(enc.encode(text or ""))


@dataclass
class TokenTiming:
    _durations: dict[str, float] = field(default_factory=dict)

    def section(self, name: str):
        start = time.perf_counter()

        class _Section:
            def __enter__(self_inner):
                return None

            def __exit__(self_inner, exc_type, exc, tb):
                self._durations[name] = (time.perf_counter() - start) * 1000

        return _Section()

    def to_dict(self) -> dict[str, Any]:
        return {f"{name}_ms": int(ms) for name, ms in self._durations.items()}
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_metrics.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tldr-bench/tldr_bench/metrics.py tldr-bench/tests/test_metrics.py

git commit -m "feat(tldr-bench): add token counting + timing utilities"
```

### Task 2: Extend Shim Usage + Optional JSONL Request Logs

Skills: @test-driven-development @verification-before-completion

**Files:**
- Modify: `tldr-bench/tldr_bench/shim/server.py`
- Modify: `tldr-bench/tldr_bench/shim/adapter.py`
- Test: `tldr-bench/tests/test_shim_server.py`

**Step 1: Write the failing test**

```python
def test_shim_returns_usage_fields():
    app = create_app({"model_map": {"codex": "codex"}})
    app.state.runner = lambda prompt, cmd, timeout: "ok"
    client = TestClient(app)
    payload = {"model": "codex:default", "messages": [{"role": "user", "content": "hi"}]}
    resp = client.post("/v1/chat/completions", json=payload)
    body = resp.json()
    assert body["usage"]["prompt_tokens"] > 0
    assert body["usage"]["completion_tokens"] > 0
    assert body["shim"]["elapsed_ms"] >= 0
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_shim_server.py -v`
Expected: FAIL because usage tokens are `0`.

**Step 3: Write minimal implementation**

```python
from tldr_bench.metrics import count_tokens

# inside chat() after output is computed
prompt_tokens = count_tokens(prompt, model=model)
completion_tokens = count_tokens(output, model=model)
response = {
    ...,
    "usage": {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    },
    "shim": {"elapsed_ms": int(duration * 1000)},
}
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_shim_server.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tldr-bench/tldr_bench/shim/server.py tldr-bench/tests/test_shim_server.py

git commit -m "feat(tldr-bench): compute shim token usage"
```

### Task 3: Runner Router + Static Context Track (Track A)

Skills: @test-driven-development @verification-before-completion

**Files:**
- Create: `tldr-bench/tldr_bench/runners/router.py`
- Create: `tldr-bench/tldr_bench/runners/static_context_runner.py`
- Modify: `tldr-bench/scripts/run_bench.py`
- Test: `tldr-bench/tests/test_router.py`
- Test: `tldr-bench/tests/test_static_context_runner.py`

**Step 1: Write the failing test**

```python
from tldr_bench.runners.router import run_task


def test_router_selects_static_runner(tmp_path):
    task = {"id": "static-1", "runner": "static", "entry": "tldr_swinton/api.py:get_relevant_context"}
    result = run_task(task, variant="difflens", run_config={"tokenizer_model": "gpt-4o"})
    assert result["task_id"] == "static-1"
    assert result["status"] == "completed"
    assert result["context_bytes"] > 0
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_router.py -v`
Expected: FAIL with `ModuleNotFoundError`.

**Step 3: Write minimal implementation**

```python
# tldr_bench/runners/router.py
from tldr_bench.runners.static_context_runner import run_static
from tldr_bench.runners.openhands_runner import run_task as run_openhands


def run_task(task: dict, variant: str, run_config: dict | None = None) -> dict:
    runner = task.get("runner", "openhands")
    if runner == "static":
        return run_static(task, variant, run_config or {})
    return run_openhands(task, variant)
```

```python
# tldr_bench/runners/static_context_runner.py
from tldr_bench.metrics import count_tokens, TokenTiming
from tldr_bench.variants import get_variant


def run_static(task: dict, variant: str, run_config: dict) -> dict:
    timing = TokenTiming()
    with timing.section("context"):
        ctx = get_variant(variant).build_context(task)
    tokenizer_model = run_config.get("tokenizer_model")
    return {
        "task_id": task.get("id"),
        "variant_id": variant,
        "status": "completed",
        "context_bytes": len(ctx.encode("utf-8")),
        "context_tokens_estimate": count_tokens(ctx, tokenizer_model),
        **timing.to_dict(),
    }
```

```python
# scripts/run_bench.py (replace openhands runner call)
from tldr_bench.runners.router import run_task as run_task_router

...
run_config = {
    "tokenizer_model": args.resolved_model or args.model,
    "shim_log_path": args.shim_log_path,
}
result = run_task_router(task, args.variant, run_config)
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_router.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tldr-bench/tldr_bench/runners/router.py tldr-bench/tldr_bench/runners/static_context_runner.py tldr-bench/scripts/run_bench.py tldr-bench/tests/test_router.py

git commit -m "feat(tldr-bench): add runner router + static context runner"
```

### Task 4: CLI Runner (Track B/C) with Shim Usage Ingestion

Skills: @test-driven-development @verification-before-completion

**Files:**
- Create: `tldr-bench/tldr_bench/runners/cli_runner.py`
- Modify: `tldr-bench/tldr_bench/runners/router.py`
- Test: `tldr-bench/tests/test_cli_runner.py`

**Step 1: Write the failing test**

```python
from tldr_bench.runners.cli_runner import run_cli_task


def test_cli_runner_attaches_usage(tmp_path):
    log_path = tmp_path / "shim.jsonl"
    log_path.write_text('{"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}\n')
    task = {"id": "cli-1", "bench_command": ["echo", "ok"], "runner": "cli"}
    result = run_cli_task(task, variant="baselines", run_config={"shim_log_path": str(log_path)})
    assert result["prompt_tokens"] == 10
    assert result["completion_tokens"] == 5
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_cli_runner.py -v`
Expected: FAIL with `ModuleNotFoundError`.

**Step 3: Write minimal implementation**

```python
import json
import subprocess


def _read_last_log(path: str | None) -> dict:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        lines = [line for line in handle.read().splitlines() if line.strip()]
    if not lines:
        return {}
    return json.loads(lines[-1])


def run_cli_task(task: dict, variant: str, run_config: dict) -> dict:
    result = subprocess.run(task["bench_command"], text=True, capture_output=True, check=False)
    status = "completed" if result.returncode == 0 else "failed"
    shim_data = _read_last_log(run_config.get("shim_log_path"))
    usage = shim_data.get("usage", {})
    return {
        "task_id": task.get("id"),
        "variant_id": variant,
        "status": status,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.returncode,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
```

```python
# tldr_bench/runners/router.py (extend)
from tldr_bench.runners.cli_runner import run_cli_task

def run_task(task: dict, variant: str, run_config: dict | None = None) -> dict:
    runner = task.get("runner", "openhands")
    if runner == "static":
        return run_static(task, variant, run_config or {})
    if runner == "cli":
        return run_cli_task(task, variant, run_config or {})
    return run_openhands(task, variant)
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_cli_runner.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tldr-bench/tldr_bench/runners/cli_runner.py tldr-bench/tldr_bench/runners/router.py tldr-bench/tests/test_cli_runner.py

git commit -m "feat(tldr-bench): add CLI runner with shim usage ingestion"
```

### Task 5: Add Track Task Suites + Docs

Skills: @test-driven-development @verification-before-completion

**Files:**
- Create: `tldr-bench/tldr_bench/tasks/track_context.yaml`
- Create: `tldr-bench/tldr_bench/tasks/track_frontier.yaml`
- Create: `tldr-bench/tldr_bench/tasks/track_executable.yaml`
- Modify: `tldr-bench/README.md`
- Test: `tldr-bench/tests/test_tasks_loader.py`

**Step 1: Write the failing test**

```python
from tldr_bench.tasks import resolve_task_file


def test_track_task_files_resolve():
    assert resolve_task_file("track_context").name == "track_context.yaml"
    assert resolve_task_file("track_frontier").name == "track_frontier.yaml"
    assert resolve_task_file("track_executable").name == "track_executable.yaml"
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_tasks_loader.py -v`
Expected: FAIL with `FileNotFoundError`.

**Step 3: Write minimal implementation**

```python
# loader.py
if name_or_path == "track_context":
    return Path(__file__).with_name("track_context.yaml")
if name_or_path == "track_frontier":
    return Path(__file__).with_name("track_frontier.yaml")
if name_or_path == "track_executable":
    return Path(__file__).with_name("track_executable.yaml")
```

```yaml
# track_context.yaml
- id: ctx-001
  title: "Context-only: difflens"
  repo: "tldr-swinton"
  entry: "tldr_swinton/api.py:get_relevant_context"
  runner: "static"
  variant: "difflens"
  budget: 2000
```

```yaml
# track_frontier.yaml
- id: frontier-001
  title: "Frontier: codex CLI"
  repo: "local"
  runner: "cli"
  bench_command: ["codex", "--prompt", "Summarize the change request."]
```

```yaml
# track_executable.yaml
- id: exec-001
  title: "Executable: OpenHands smoke"
  repo: "tldr-swinton"
  runner: "openhands"
  benchmark: "swebench"
  llm_config: "/tmp/llm_config_codex.json"
  select: "django__django-11333"
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_tasks_loader.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tldr-bench/tldr_bench/tasks/loader.py tldr-bench/tldr_bench/tasks/track_context.yaml tldr-bench/tldr_bench/tasks/track_frontier.yaml tldr-bench/tldr_bench/tasks/track_executable.yaml tldr-bench/README.md tldr-bench/tests/test_tasks_loader.py

git commit -m "feat(tldr-bench): add benchmark task suites"
```

### Task 6: Results Summary Script (Medians + Timing Breakdown)

Skills: @test-driven-development @verification-before-completion

**Files:**
- Create: `tldr-bench/scripts/summarize_results.py`
- Create: `tldr-bench/tldr_bench/summary.py`
- Test: `tldr-bench/tests/test_summarize_results.py`

**Step 1: Write the failing test**

```python
from tldr_bench.summary import summarize_jsonl


def test_summary_median_tokens(tmp_path):
    data = tmp_path / "run.jsonl"
    data.write_text('{"total_tokens": 10, "context_ms": 5}\n{"total_tokens": 20, "context_ms": 7}\n')
    summary = summarize_jsonl(data)
    assert summary["total_tokens_median"] == 15
    assert summary["context_ms_median"] == 6
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_summarize_results.py -v`
Expected: FAIL with `ModuleNotFoundError`.

**Step 3: Write minimal implementation**

```python
# tldr_bench/summary.py
from __future__ import annotations

import json
from pathlib import Path
from statistics import median


def summarize_jsonl(path: Path) -> dict[str, float]:
    totals = []
    context_ms = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("total_tokens") is not None:
            totals.append(row["total_tokens"])
        if row.get("context_ms") is not None:
            context_ms.append(row["context_ms"])
    return {
        "total_tokens_median": median(totals) if totals else 0,
        "context_ms_median": median(context_ms) if context_ms else 0,
    }
```

```python
# scripts/summarize_results.py
from pathlib import Path
from tldr_bench.summary import summarize_jsonl

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args()
    summary = summarize_jsonl(Path(args.path))
    print(summary)
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_summarize_results.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tldr-bench/tldr_bench/summary.py tldr-bench/scripts/summarize_results.py tldr-bench/tests/test_summarize_results.py

git commit -m "feat(tldr-bench): add results summary helper"
```
