# Benchmark Metadata Logging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** `tldr-swinton-bde (Add benchmark metadata logging)` — mandatory line tying the plan to the active bead/Task Master item.

**Goal:** Add benchmark/run metadata flags and system metadata to JSONL outputs from `run_bench.py`.

**Architecture:** Extend CLI args in `run_bench.py`, enrich each task result dict before logging, and document the new fields in `docs/LOG_SCHEMA.md` + `README.md`.

**Tech Stack:** Python, argparse, pytest, JSONL logger.

### Task 1: Expand metadata test coverage

**Files:**
- Modify: `tldr-bench/tests/test_run_bench_metadata.py`

**Step 1: Write the failing test**

```python
assert "\"host_os\"" in content
assert "\"host_arch\"" in content
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_run_bench_metadata.py`
Expected: FAIL with unrecognized args / missing metadata fields.

**Step 3: Write minimal implementation**

Add CLI flags in `run_bench.py` and log fields in the result dict. Import `system_metadata()` and merge into result.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_run_bench_metadata.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add tldr-bench/tests/test_run_bench_metadata.py tldr-bench/scripts/run_bench.py tldr-bench/tldr_bench/meta.py

git commit -m "feat: log benchmark metadata"
```

### Task 2: Document metadata fields

**Files:**
- Modify: `tldr-bench/docs/LOG_SCHEMA.md`
- Modify: `tldr-bench/README.md`

**Step 1: Update log schema**

List new fields: run_id, task_suite, benchmark, dataset, split, instance_ids, workspace, max_iterations, timeout_seconds, tldrs_version, shim_config, seed, prompt_budget, context_strategy, daemon_enabled, host_os, host_release, host_arch, python_version.

**Step 2: Update README flags list**

Add new CLI flags and descriptions.

**Step 3: Optional verification**

Re-run test if needed: `PYTHONPATH=tldr-bench uv run --with pytest python -m pytest tldr-bench/tests/test_run_bench_metadata.py`

**Step 4: Commit**

```bash
git add tldr-bench/docs/LOG_SCHEMA.md tldr-bench/README.md

git commit -m "docs: document benchmark metadata fields"
```
