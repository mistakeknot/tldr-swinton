# tldr-bench

Token-efficiency benchmarks for tldr-swinton using the OpenHands evaluation harness.

## Quickstart (uv)

```bash
uv venv
uv pip install -e .
python scripts/run_bench.py --help
python scripts/run_bench.py --tasks curated --list-tasks
```

Common flags:

- `--filter cur-001,cur-002` (substring match on task IDs)
- `--print-results` (emit JSON per task)
- `--allow-cli` (execute `bench_command` tasks)
- `--dry-run` (print tasks without executing)
- `--agent codex-cli` (tag JSONL output)
- `--model codex:default` (tag JSONL output)
- `--model-alias sonnet` (tag JSONL output)
- `--resolved-model claude-sonnet-4-20250514` (tag JSONL output)
- `--config-id shim-local` (tag JSONL output)
- `--cli-version codex-1.2.3` (tag JSONL output)
- `--run-id run-123` (tag JSONL output)
- `--task-suite curated-v1` (tag JSONL output)
- `--benchmark swebench` (tag JSONL output)
- `--dataset SWE-bench_Verified` (tag JSONL output)
- `--split test` (tag JSONL output)
- `--instance-ids django__django-11333` (tag JSONL output, comma-separated list; IDs must not contain commas)
- `--workspace docker` (tag JSONL output)
- `--max-iterations 5` (tag JSONL output)
- `--timeout-seconds 120` (tag JSONL output)
- `--tldrs-version 0.2.0` (tag JSONL output)
- `--shim-config shim.toml` (tag JSONL output)
- `--seed 42` (tag JSONL output)
- `--prompt-budget 4000` (tag JSONL output)
- `--context-strategy difflens` (tag JSONL output)
- `--daemon-enabled` (tag JSONL output)
- `--results-file /path/to/file.jsonl` (write JSONL to specific path)
- `--results-prefix run-` (write JSONL with timestamped prefix)
- `--results-dir /path/to/dir` (override results directory)

## CLI Shim (Codex/Claude Code)

See `tldr-bench/shim/README.md` for running the local OpenAI-compatible shim.

## OpenHands Benchmarks (required for real runs)

This repo includes the OpenHands benchmarks as a submodule:

```bash
git submodule update --init --recursive
```

Follow the upstream instructions inside `tldr-bench/vendor/openhands-benchmarks`
to install its dependencies (they use `uv sync` and a local Agent SDK).

Set `OH_BENCH_DIR` if you keep the benchmarks elsewhere:

```bash
export OH_BENCH_DIR=/path/to/OpenHands/benchmarks
```
