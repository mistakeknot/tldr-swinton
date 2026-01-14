# AGENTS.md - AI Agent Instructions for tldr-bench

This repo contains token-efficiency benchmarks for tldr-swinton.

## Quickstart (uv)

```bash
uv venv
uv pip install -e ".[dev]"
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/run_bench.py --help
```

## Rules

- Use `tldrs`, not `tldr`.
- Prefer `uv run` for scripts/tests.
- Do not commit anything under `tldr-bench/results/` (gitignored).
- For CLI frontier runs, use the shim and capture token counts via JSONL logging.

## Common Commands

```bash
# List tasks
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/run_bench.py --tasks track_context --list-tasks

# Track A (static/context)
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/run_bench.py --tasks track_context --variant difflens --print-results

# Start shim (enable JSONL logging in config)
PYTHONPATH=tldr-bench uv run --with fastapi --with uvicorn python tldr-bench/tldr_bench/shim/server.py --config tldr-bench/shim/config.toml

# Track B (frontier via shim)
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/run_bench.py --tasks track_frontier --variant baselines --allow-cli --shim-log-path /tmp/tldr-shim.jsonl --print-results
```

## Tests

```bash
PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests -v
```
