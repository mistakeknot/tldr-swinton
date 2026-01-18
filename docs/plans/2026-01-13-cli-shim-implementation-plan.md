# CLI Shim Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** `tldr-swinton-8lw (CLI shim for OpenHands benchmarks)`

**Goal:** Add a local OpenAI-compatible HTTP shim that shells out to `codex` or `claude` per request for OpenHands benchmarks without paid API usage.

**Architecture:** A small FastAPI app with endpoints `/v1/chat/completions`, `/v1/models`, and `/v1/health`. It builds prompts from chat messages, routes by model prefix, and spawns `codex`/`claude` with a timeout. Configuration is stored in a TOML file and can be overridden via environment.

**Tech Stack:** Python 3, FastAPI, Uvicorn, PyYAML, tiktoken, pytest.

---

### Task 1: Add shim dependencies + scaffold files

**Files:**
- Modify: `tldr-bench/pyproject.toml`
- Create: `tldr-bench/shim/config.toml`
- Create: `tldr-bench/tldr_bench/shim/server.py`
- Create: `tldr-bench/tldr_bench/shim/__init__.py`

**Step 1: Add dependencies (no behavior)**

Update `tldr-bench/pyproject.toml`:
- Add `fastapi` and `uvicorn` to core dependencies.
- Add `httpx` to `dev` optional deps for tests.

**Step 2: Create config stub**

Create `tldr-bench/shim/config.toml` with fields:
- `port`, `timeout_seconds`
- `model_map` (mapping model prefix → CLI command)

**Step 3: Create module stubs**

Create empty `tldr-bench/tldr_bench/shim/server.py` and `tldr-bench/tldr_bench/shim/__init__.py` placeholders.

**Step 4: Commit**

```bash
git add tldr-bench/pyproject.toml tldr-bench/shim tldr-bench/tldr_bench/shim

git commit -m "Add shim scaffolding"
```

---

### Task 2: Prompt assembly + model routing (TDD)

**Files:**
- Create: `tldr-bench/tldr_bench/shim/adapter.py`
- Create: `tldr-bench/tests/test_shim_adapter.py`

**Step 1: Write failing test**

Create `tldr-bench/tests/test_shim_adapter.py`:
```python
from tldr_bench.shim.adapter import assemble_prompt, resolve_model_command


def test_assemble_prompt_basic():
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "Do thing"},
    ]
    prompt = assemble_prompt(messages)
    assert "SYSTEM:" in prompt
    assert "USER:" in prompt
    assert "ASSISTANT:" in prompt
    assert "Do thing" in prompt


def test_resolve_model_command():
    model_map = {"codex": "codex", "claude": "claude"}
    assert resolve_model_command("codex:default", model_map) == "codex"
    assert resolve_model_command("claude:sonnet", model_map) == "claude"
```

**Step 2: Run test to verify it fails**

```bash
PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_shim_adapter.py
```
Expected: FAIL (module not found).

**Step 3: Implement minimal adapter**

Create `tldr-bench/tldr_bench/shim/adapter.py`:
```python
from __future__ import annotations

from typing import Iterable


def assemble_prompt(messages: Iterable[dict]) -> str:
    parts = []
    for msg in messages:
        role = msg.get("role", "user").upper()
        content = msg.get("content", "")
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


def resolve_model_command(model: str, model_map: dict[str, str]) -> str:
    prefix = model.split(":", 1)[0]
    if prefix in model_map:
        return model_map[prefix]
    raise ValueError(f"Unknown model prefix: {prefix}")
```

**Step 4: Run tests to verify pass**

```bash
PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_shim_adapter.py
```
Expected: PASS.

**Step 5: Commit**

```bash
git add tldr-bench/tldr_bench/shim/adapter.py tldr-bench/tests/test_shim_adapter.py

git commit -m "Add shim prompt assembly"
```

---

### Task 3: HTTP server endpoints (TDD)

**Files:**
- Modify: `tldr-bench/tldr_bench/shim/server.py`
- Create: `tldr-bench/tests/test_shim_server.py`

**Step 1: Write failing test**

Create `tldr-bench/tests/test_shim_server.py`:
```python
from fastapi.testclient import TestClient

from tldr_bench.shim.server import create_app


def test_models_endpoint():
    app = create_app({"model_map": {"codex": "codex"}})
    client = TestClient(app)
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data


def test_chat_completion_basic():
    app = create_app({"model_map": {"codex": "codex"}})
    app.state.runner = lambda prompt, cmd, timeout: "ok"
    client = TestClient(app)
    payload = {
        "model": "codex:default",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
    }
    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["choices"][0]["message"]["content"] == "ok"
```

**Step 2: Run test to verify it fails**

```bash
PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_shim_server.py
```
Expected: FAIL (create_app not implemented).

**Step 3: Implement minimal server**

Implement `create_app()` in `tldr-bench/tldr_bench/shim/server.py` using FastAPI. Include:
- `/v1/models` returning model IDs from config
- `/v1/chat/completions` building prompt, routing to runner, returning OpenAI-like response
- Reject `stream=True`
- `/v1/health` returning status

**Step 4: Run tests to verify pass**

```bash
PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_shim_server.py
```
Expected: PASS.

**Step 5: Commit**

```bash
git add tldr-bench/tldr_bench/shim/server.py tldr-bench/tests/test_shim_server.py

git commit -m "Add shim HTTP server"
```

---

### Task 4: CLI spawn + timeout (TDD)

**Files:**
- Modify: `tldr-bench/tldr_bench/shim/server.py`
- Create: `tldr-bench/tests/test_shim_cli.py`

**Step 1: Write failing test**

Create `tldr-bench/tests/test_shim_cli.py`:
```python
from tldr_bench.shim.server import run_cli


def test_run_cli_echo():
    result = run_cli("hello", "/bin/echo", 5)
    assert result.strip() == "hello"
```

**Step 2: Run test to verify it fails**

```bash
PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_shim_cli.py
```
Expected: FAIL (run_cli missing).

**Step 3: Implement run_cli**

Add `run_cli(prompt, command, timeout)` to `server.py` using `subprocess.run` with `timeout`. Pass prompt on stdin, return stdout. Raise on non-zero exit.

**Step 4: Run tests to verify pass**

```bash
PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_shim_cli.py
```
Expected: PASS.

**Step 5: Commit**

```bash
git add tldr-bench/tldr_bench/shim/server.py tldr-bench/tests/test_shim_cli.py

git commit -m "Add CLI runner with timeout"
```

---

### Task 5: Docs + example config

**Files:**
- Modify: `tldr-bench/README.md`
- Create: `tldr-bench/shim/README.md`

**Step 1: Write docs**

Document how to start the shim:
```bash
PYTHONPATH=tldr-bench uv run python tldr-bench/tldr_bench/shim/server.py --config tldr-bench/shim/config.toml
```

Provide example `.llm_config` snippet for OpenHands.

**Step 2: Commit**

```bash
git add tldr-bench/README.md tldr-bench/shim/README.md

git commit -m "Document CLI shim usage"
```

---

## Testing
Run all shim tests:
```bash
PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_shim_*.py
```

## Notes
- Use spawn-per-request only; no session persistence.
- Avoid streaming until basic functionality is stable.
