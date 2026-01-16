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
- `--shim-log-path /path/to/shim.jsonl` (use last JSONL line for CLI usage)
- `--seed 42` (tag JSONL output)
- `--prompt-budget 4000` (tag JSONL output)
- `--context-strategy custom` (tag JSONL output)
- `--daemon-enabled` (tag JSONL output)
- `--results-file /path/to/file.jsonl` (write JSONL to specific path)
- `--results-prefix run-` (write JSONL with timestamped prefix)
- `--results-dir /path/to/dir` (override results directory)

Track task suites:

- `track_context` (static/context-only)
- `track_frontier` (CLI frontier, local Codex/Claude)
- `track_executable` (OpenHands / executable harness)
- `track_dataset` (dataset prompt stats only)
- `track_dataset_context` (dataset prompt + context token stats)

Token savings snapshots are tool-specific. Use your variant outputs plus the
baseline runners to compute savings for your own strategy.

## Official datasets (SWE-bench / RepoBench / LongBench)

The official dataset files live in the `tldr-bench/data` submodule and are
tracked via Git LFS in that repo. The dataset files are under
`tldr-bench/data/data/`.

Setup:

```bash
git submodule update --init --recursive
cd tldr-bench/data
git lfs install
git lfs pull
cd -
python scripts/data/verify_datasets.py
```

Token-only runs against the official datasets:

```
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/run_bench.py \
  --tasks official_datasets --variant baselines --print-results
```

If `git lfs install` fails due to existing hooks, run:

```
bash tldr-bench/scripts/data/lfs_setup.sh
```

Track B (frontier/CLI) via shim:

1) Start shim with logging enabled (see `tldr-bench/shim/README.md`).
2) Run:
   `PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/run_bench.py --tasks track_frontier --variant baselines --allow-cli --shim-log-path /tmp/tldr-shim.jsonl --print-results`

Dataset context (token-savings only):

```
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/run_bench.py \
  --tasks track_dataset_context --variant symbolkite --print-results \
  --instance-ids psf__requests-2674,django__django-11333
```

Savings report (baseline vs variant):

```
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/report_savings.py \
  --baseline tldr-bench/results/baseline.jsonl \
  --variant tldr-bench/results/symbolkite.jsonl
```

Compare results (baseline vs many variants):

```
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/compare_results.py \
  --baseline tldr-bench/results/baseline.jsonl \
  --variants tldr-bench/results/symbolkite.jsonl tldr-bench/results/coveragelens.jsonl
```

Sweep helper (baseline + variants):

```
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/run_savings_sweep.py \
  --instance-ids psf__requests-2674,django__django-11333
```

## Module Selection (Frontier / Agent Runs)

When a frontier agent needs context, prefer tools in this order:

```bash
# 1) Diff-first context for recent changes
tldrs diff-context --project . --budget 2000

# 2) Symbol-level context for a specific entry
tldrs context <entry> --project . --depth 2 --budget 2000 --format ultracompact

# 3) Structure / extract for files or folders
tldrs structure src/
tldrs extract path/to/file.py

# 4) Semantic search (requires index)
tldrs index .
tldrs find "authentication logic"

# 5) Deep analysis helpers (optional)
tldrs slice <file> <func> <line>
tldrs cfg <file> <function>
tldrs dfg <file> <function>
```

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
