# Token-Savings Benchmarks from Official Evals (Design)

Date: 2026-01-15

## Goal

Replicate three widely used evals (SWE-bench, RepoBench, LongBench) inside
`tldr-bench` to measure token savings from tldr-swinton context packs. We vendor
the dataset files locally (no Docker images) and normalize them into a common
task schema to run token-only or agent-backed evaluations.

## Non-Goals

- No Docker images or SWE-bench runtime environments.
- No model-hosted API usage required for token-only runs.
- No attempt to reimplement official scoring beyond optional, lightweight
  quality proxies.

## Datasets (Vendored with Git LFS)

We vendor raw dataset files using Git LFS under `tldr-bench/data/`:

- `swebench_lite/` (SWE-bench Lite split files)
- `swebench_verified/` (SWE-bench Verified split files)
- `repobench_python_v1.1/` (RepoBench data files)
- `longbench_v2/` (LongBench v2 data file)

Each dataset directory includes:

- `manifest.json` with source URLs, upstream dataset name/version, file sizes,
  and SHA256 checksums.
- `README.md` with task counts and a brief usage note.

Git LFS patterns target large data files (parquet/json) under
`tldr-bench/data/**`.

## Layout

```
tldr-bench/
  data/
    swebench_lite/
    swebench_verified/
    repobench_python_v1.1/
    longbench_v2/
  tldr_bench/
    datasets/
      swebench.py
      repobench.py
      longbench.py
      schema.py
```

## Dataset Normalization

Each adapter outputs a `TaskRecord`:

- `task_id` (stable id)
- `split` (train/dev/test)
- `prompt` (issue + context or completion prompt)
- `reference` (expected completion or patch, if available)
- `repo` / `context_sources` (for SWE-bench tasks)

Adapters must only read local files under `data/` and fail fast when data is
missing.

## Eval Modes

1) Token-only: compute token counts for raw context vs tldrs context.
2) Quality proxy: optional completion evaluation via CLI shims (Codex/Claude).
3) Full agent (optional): SWE-bench style workflow when desired.

Token metrics (per task):

- `input_tokens_raw`
- `input_tokens_tldrs`
- `savings_abs`
- `savings_pct`
- `tldrs_index_ms`, `tldrs_context_ms`

## CLI + Results

Commands (examples):

```
tldr-bench run swebench-lite --mode tokens
tldr-bench run repobench --mode tokens
tldr-bench run longbench --mode tokens
```

Results are stored in:

```
results/<dataset>/<timestamp>/
  tasks.jsonl
  summary.csv
```

## Tooling

Scripts and CLI helpers:

- `scripts/data/lfs_setup.sh` to install Git LFS and validate tracking patterns.
- `scripts/data/verify_datasets.py` to verify manifests and checksums.
- `tldr-bench data list` and `tldr-bench data verify` commands.

CI behavior:

- Default CI uses fixture-based adapter tests (no LFS download).
- Optional nightly/manual job can run `data verify` and small token-only sweeps.

## Risks / Tradeoffs

- Large LFS footprints (~1GB total). Acceptable for local datasets only.
- LFS must be installed for contributors; doc this clearly in README.
- LongBench/RepoBench are large single files; checksum validation is critical.

## Next Steps

1) Add Git LFS config and vendored datasets.
2) Implement adapters + schema and minimal tests.
3) Add token-only runners and summary reporting.
4) Update `tldr-bench` README with setup and data verification steps.
