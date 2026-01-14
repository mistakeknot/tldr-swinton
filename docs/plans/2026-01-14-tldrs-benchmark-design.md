# TLDRS Benchmark Design

**Goal:** Benchmark tldrs token savings without sacrificing task success, using both fast static-context evals and full executable benchmarks.

**Tracks:**
1. **Static/Context Track (fast)**
   - No Docker, no test execution.
   - Baseline context: raw file excerpts or naive `rg` snippets.
   - Treatment context: `tldrs structure/context/slice` outputs.
   - Scoring: rubric or diff‑match for expected outputs.

2. **Token‑Efficiency Frontier (A/B)**
   - Same tasks, same model settings; only context source differs.
   - Primary metric: tokens saved per successful task.
   - Secondary: success rate delta, latency delta.

3. **Executable Track (gold standard)**
   - OpenHands benchmarks (commit0/swebench/gaia/openagentsafety).
   - Uses CLI shim for Codex/Claude Code as LLM backend.
   - Docker/remote workspace required; validates real test outcomes.

## Metrics

**Token + context:**
- prompt_tokens
- completion_tokens
- tool_calls
- context_bytes
- context_tokens_estimate
- compression_ratio

**Success:**
- success (binary)
- retries
- notes

**Latency breakdown:**
- t_context_build_ms
- t_llm_ms
- t_exec_ms
- t_total_ms

**Run metadata:**
- run_id, task_suite, variant_id, model, agent, config_id
- host_os, host_arch, python_version
- docker_arch (if applicable)

## Instrumentation

- **Context build timing**: start/end of context assembly.
- **LLM timing**: before/after CLI shim call.
- **Exec timing**: workspace setup + test execution for executable track.
- **Cache indicators**: tldrs index hit, Docker image reuse.

## Reporting

- JSONL per task; summary CSV/markdown per run.
- p50/p90/p99 latency by track and variant.
- “Tokens saved per success” and “time per success.”
- Segment results by architecture (arm64 vs amd64 emulation).

## Apple Silicon Notes

- Prefer native arm64 images when available.
- Many benchmark base images are amd64‑only today; emulation is slower.
- Remote workspace recommended for amd64‑only benchmarks.

## Rollout

1) Implement static/context track + smoke suite.
2) Add A/B frontier track and baseline comparison report.
3) Wire executable track and run periodic validation.
4) Document runbook and troubleshooting.
