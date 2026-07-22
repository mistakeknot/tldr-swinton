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

## Paired agent value evaluation

The agent-value runner measures whether adaptive tldrs use preserves externally
graded coding correctness while reducing uncached native Codex tokens. Every
baseline/adaptive cell starts from a fresh history-free repository with a hidden
mutation; hidden graders run only after the agent exits. The 12-task pilot has
three negative controls and three tasks in each exploratory category.

The July 2026 GPT-5.6 Sol pilot failed the end-to-end value gate despite passing
correctness and routing: eligible tasks had -11.9% median token savings (an
11.9% regression) and 17.0% median latency regression. See
[`docs/research/paired-agent-value-eval-2026-07.md`](../docs/research/paired-agent-value-eval-2026-07.md).
Treat older command-output savings as component benchmarks, not proof that an
agent workflow saves total context.

GPT-5.6 Sol is the default current Codex model. The Codex ChatGPT transport uses
the concrete `gpt-5.6-sol` ID (the API's `gpt-5.6` alias may be rejected). The
pilot fixes reasoning effort at `medium`; use the same model and effort for both
conditions. Run a four-cell smoke test first:

```bash
PYTHONPATH=tldr-bench python3 tldr-bench/scripts/run_agent_value_eval.py \
  --smoke \
  --model gpt-5.6-sol \
  --reasoning-effort medium \
  --results-dir tldr-bench/results/agent-value/smoke
```

Run the full 72-cell pilot (12 tasks × 2 conditions × 3 repeats):

```bash
PYTHONPATH=tldr-bench python3 tldr-bench/scripts/run_agent_value_eval.py \
  --model gpt-5.6-sol \
  --reasoning-effort medium \
  --repeats 3 \
  --results-dir tldr-bench/results/agent-value/pilot-2026-07
```

Resume the exact same run without duplicating completed cells:

```bash
PYTHONPATH=tldr-bench python3 tldr-bench/scripts/run_agent_value_eval.py \
  --model gpt-5.6-sol \
  --reasoning-effort medium \
  --repeats 3 \
  --results-dir tldr-bench/results/agent-value/pilot-2026-07 \
  --resume
```

Regenerate reports from append-only outcomes:

```bash
PYTHONPATH=tldr-bench python3 tldr-bench/scripts/run_agent_value_eval.py \
  --report-only \
  --results-dir tldr-bench/results/agent-value/pilot-2026-07
```

Use `--list-tasks` to inspect the corpus, `--dry-run` to render stable cell IDs
and Codex commands without creating files, and `--keep-workspaces` only for a
targeted audit. Resume rejects source, corpus, model, condition, repeat, effort,
timeout, or seed drift.

Track task suites:

- `track_context` (static/context-only)
- `track_frontier` (CLI frontier, local Codex/Claude)
- `track_executable` (OpenHands / executable harness)
- `track_dataset` (dataset prompt stats only)
- `track_dataset_context` (dataset prompt + context token stats)
- `track_new_features` (compression feature benchmarks: symbolkite, edit_locality)

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

Preset (dataset-context):

```
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/compare_results.py \
  --track dataset-context --json
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
