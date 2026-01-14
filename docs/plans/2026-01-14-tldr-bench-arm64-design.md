# tldr-bench arm64 benchmark harness design

Date: 2026-01-14

## Goal

Create an arm64-native benchmark harness inside `tldr-bench/` that measures token savings for tldr-swinton without sacrificing task quality. The harness should run locally with Codex CLI and Claude Code via a shim (no API spend) and produce reproducible metrics for baseline vs tldrs-context variants.

## Scope

- Use SWE-bench Lite and commit0 datasets as primary sources.
- Implement a lean runner that does not depend on OpenHands agent-server.
- Support multiple context variants:
  - raw file context (baseline)
  - tldrs context only
  - hybrid (tldrs + targeted file excerpts)
- Track token counts, latency, and quality results in a unified run report.

## Architecture and components

- `tldr-bench/data/`
  - Normalized dataset fixtures (SWE-bench Lite + commit0) with a minimal schema.
- `tldr-bench/runner/`
  - Workdir manager: clone/checkout repo + apply baseline state.
  - Prompt builder: produces task prompt + context payload (raw, tldrs, hybrid).
  - Agent shim: local Codex CLI + Claude Code execution via HTTP shim.
  - Validator: apply patch + run dataset tests.
- `tldr-bench/metrics/`
  - Token counting (prompt vs context vs total). 
  - Latency metrics (prompt build, agent run, tests).
  - Diff metrics (files touched, LoC changed).
- `tldr-bench/runs/<run_id>/`
  - `run.json` metadata
  - `results.jsonl` per instance
  - `summary.json` aggregate report

## Data flow and pipeline

1) Load dataset instance and create per-instance workdir.
2) Build prompt using a variant strategy:
   - raw file context
   - tldrs context
   - hybrid (tldrs + selected file excerpts)
3) Invoke local agent via shim and capture transcript + patch.
4) Apply patch and run dataset-specific tests.
5) Collect metrics and store outputs for later analysis.

All outputs are deterministic and stored in a stable run directory for comparison.

## Metrics and evaluation

Measure three classes of metrics:

- Quality:
  - pass rate
  - test pass/fail
  - regression signals where available
- Token efficiency:
  - prompt tokens
  - context payload tokens
  - total input tokens
  - output tokens
  - token savings % vs baseline
- Latency:
  - prompt build time
  - agent runtime
  - test runtime
  - end-to-end time

A successful tldrs variant should match or exceed baseline pass rate while reducing context tokens by 30-50% or more. Report efficiency ratio as `pass_rate / median_input_tokens`.

## Runbook

1) Prepare dataset (SWE-bench Lite or commit0) in `tldr-bench/data/`.
2) Select config: `raw`, `tldrs`, or `hybrid`.
3) Run:
   - `tldr-bench run --track swebench-lite --variant tldrs --model codex`
4) Review:
   - `tldr-bench report --run <run_id>`
5) Compare variants and capture summary table for docs.

## Open questions

- Which SWE-bench subset should be default for fast local runs?
- What is the minimal “hybrid” context policy that provides consistent wins?
- How strict should regression checks be for commit0 tasks?
