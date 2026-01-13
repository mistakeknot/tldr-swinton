# tldr-bench Design (OpenHands-based)

Date: 2026-01-13

## Overview
`tldr-bench` is a dedicated benchmark repo (inside `tldr-swinton/`) for measuring token efficiency of tldr-swinton context tooling. It uses OpenHands evaluation harness via `uv` dependency, and keeps only lightweight wrappers, task definitions, and logging instrumentation.

Primary goal: run A/B evaluations of context strategies (DiffLens, SymbolKite, Cassette, CoverageLens) with consistent budgets and token accounting.

## Repository Layout
Root path: `tldr-swinton/tldr-bench/`

Proposed structure:
```
 tldr-bench/
   README.md
   pyproject.toml
   uv.lock
   tldr_bench/
     __init__.py
     config.py
     logger.py
     runners/
       __init__.py
       openhands_runner.py
     tasks/
       __init__.py
       curated.yaml
       public_subset.yaml
     variants/
       __init__.py
       baselines.py
       difflens.py
       symbolkite.py
       cassette.py
       coveragelens.py
     scripts/
       run_bench.py
       summarize.py
   results/
     .gitkeep
   docs/
     TASKS.md
     VARIANTS.md
     LOG_SCHEMA.md
```

## Dependencies (uv)
- `openhands` or `openhands-benchmarks` via `uv` dependency
- Tokenizer package (e.g., `tiktoken`) for consistent token counts
- YAML parser (e.g., `pyyaml`) for task suites

The repo will be uv-only (no pip fallback).

## Task Sources (Mixed)
- **Curated suite** for fast iteration and specific token-efficiency scenarios
- **Public subset** (e.g., SWE-bench Verified slice) for external credibility

Both are defined as YAML task lists with:
- repo target
- entry point / expected patch
- diff range
- required tooling

## Variants
Baselines:
- Full file reads
- Current tldrs context outputs
- Minimal grep+read

Experimental:
- DiffLens
- SymbolKite
- Cassette
- CoverageLens
- Combined variants

Variants map to OpenHands tool configurations. The wrapper injects the variant-specific context retrieval method, and logs the output size.

## Logging Schema
JSONL per run with:
- task_id, variant_id, budget
- prompt_tokens, completion_tokens
- context_bytes, context_tokens_estimate
- tool_calls, elapsed_ms, retries
- success, diff_hit_rate, coverage_hit_rate
- symbol_etag_hit, cassette_ref_ratio
- notes

## Execution
- `scripts/run_bench.py`: runs tasks for a given variant set
- `scripts/summarize.py`: produces markdown summaries
- `results/`: raw JSONL outputs

## Next Steps
1) Scaffold `tldr-bench/` directory and minimal files
2) Add UV config + dependency pins
3) Implement `logger.py` and a no-op `openhands_runner.py`
4) Add sample tasks in curated.yaml

