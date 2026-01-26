# Task Definitions

Tasks are defined as YAML lists. Required fields vary by runner type.

## Benchmark Tracks

tldr-bench organizes benchmarks into tracks by purpose:

| Track | Runner | Purpose |
|-------|--------|---------|
| `track_context` | static | Context-only token counts (no LLM calls) |
| `track_frontier` | cli | Frontier LLM runs via shim |
| `track_dataset` | dataset | Prompt token counts from datasets |
| `track_dataset_context` | dataset_context | Context + prompt tokens from datasets |
| `track_executable` | openhands | OpenHands SWE-bench runs |
| `official_datasets_context` | dataset_context | 14-task official benchmark suite |

## Runner Types

### static
Measures context generation token counts without LLM calls.
```yaml
- id: ctx-001
  runner: "static"
  entry: "src/tldr_swinton/modules/core/engines/symbolkite.py:get_relevant_context"
  budget: 2000
```

### cli
Executes bench_command for CLI smoke tests or shim runs.
```yaml
- id: frontier-001
  runner: "cli"
  bench_command: ["uv", "run", "python", "tldr-bench/scripts/shim_client.py", ...]
```

### dataset
Counts prompt tokens from dataset instances.
```yaml
- id: dataset-001
  runner: "dataset"
  dataset_path: "data/swebench_sample.jsonl"
  dataset_kind: "swebench"
```

### dataset_context
Combines dataset prompts with context generation.
```yaml
- id: swebench-ctx-001
  runner: "dataset_context"
  dataset_path: "tldr-bench/data/data/swebench_sample.jsonl"
  dataset_kind: "swebench"
  entry: "src/tldr_swinton/modules/core/engines/symbolkite.py:get_relevant_context"
  depth: 2
  context_format: "ultracompact"
```

### openhands
Runs OpenHands benchmark harness.
```yaml
- id: exec-001
  runner: "openhands"
  benchmark: "swebench"
  llm_config: "/tmp/llm_config.json"
  select: "django__django-11333"
  max_iterations: 1
```

## Built-in Task Files

| File | Tasks | Purpose |
|------|-------|---------|
| `curated.yaml` | 8 | Hand-picked development tasks |
| `track_context.yaml` | 1 | Static context benchmark |
| `track_frontier.yaml` | 4 | CLI shim frontier runs |
| `track_dataset.yaml` | 1 | Dataset prompt tokens |
| `track_dataset_context.yaml` | 1 | Dataset + context tokens |
| `official_datasets_context.yaml` | 14 | Official benchmark suite |
| `track_executable.yaml` | 1 | OpenHands smoke test |
| `track_new_features.yaml` | 5 | Token efficiency benchmarks (compression features) |

## New Features Track

The `track_new_features` track benchmarks compression features that can demonstrate
actual token savings in static benchmarks:

| Variant | Avg Savings | Description |
|---------|-------------|-------------|
| `symbolkite` | ~90% | Signature-based context extraction |
| `edit_locality` | ~36% | Edit-focused context with boundaries and invariants |

**Note:** Savings vary by task. edit_locality includes function bodies + boundaries,
so it's larger than symbolkite (signatures only) but smaller than full files.

### Disabled Variants

The following variants were disabled because they cannot demonstrate value
in static token-counting benchmarks. See `variants/disabled/README.md` for details:

| Variant | Issue | Required Benchmark |
|---------|-------|-------------------|
| `attention_pruning` | Needs usage history | Multi-session learning |
| `context_delegation` | Returns plan, not context | Agent execution |
| `coherence_verify` | Adds tokens (quality feature) | Error detection rate |

Run the compression benchmark:
```bash
uv run python tldr-bench/scripts/run_new_features_bench.py
```

## Common Commands

```bash
# List tasks in a track
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/run_bench.py \
  --tasks track_context --list-tasks

# Run track with variant
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/run_bench.py \
  --tasks track_context --variant baselines --print-results

# Compare variants
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/compare_results.py \
  --baseline results/baselines.jsonl \
  --variants results/symbolkite.jsonl
```

## bench_command Tasks

Tasks can include a `bench_command` list for CLI shims. Use `--allow-cli` flag.

```yaml
- id: cur-cli-codex
  repo: "local"
  entry: "codex"
  type: "cli_smoke"
  bench_command: ["codex", "exec", "Say 'ok' only."]
```
