---
artifact_type: plan
bead: mk-5szd
stage: design
---
# Paired Agent Value Evaluation Implementation Plan

> **For Codex:** Execute this plan sequentially in the current session using TDD. The runner, corpus, and report share contracts and must not be delegated into conflicting workspaces.

**Bead:** `mk-5szd`

**Goal:** Determine whether adaptive tldrs preserves coding-task correctness while reducing context cost, and whether it correctly skips already-scoped work.

**Architecture:** Extend `tldr-bench` with a paired Codex runner. Every task is materialized into two fresh, history-free repositories from the same committed source snapshot; a baseline condition removes tldrs from `PATH`, while an adaptive condition exposes it and installs concise routing guidance. Agents never receive grader files. Codex JSONL traces, git diffs, and external grader results feed paired metrics and explicit pass/fail gates.

**Tech Stack:** Python 3.11+, dataclasses, PyYAML, subprocess, Codex CLI JSONL, pytest, JSONL/JSON/Markdown reports.

**Prior Learnings:** Existing token-only evals deliberately avoid full runtime scoring. February reviews concluded that adoption must be judged by code quality, tokens, latency, and tool selection—not invocation alone—and explicitly requested 5-10 selection-quality tasks. The current OpenHands adapter only maps process exit code to success and sets treatment environment variables that no consumer reads. This plan replaces those proxies rather than extending them.

---

## Must-Haves

**Truths**

- Baseline and adaptive runs start from byte-identical task repositories and differ only in tldrs availability and routing guidance.
- A run succeeds only when its external grader passes; Codex process exit zero is not sufficient.
- Graders and mutation specifications are unavailable inside the agent workspace.
- Results preserve model, harness version, condition, repeat, token usage, tool calls, tldrs calls, raw-read commands, elapsed time, patch hash, grader output, and contamination flags.
- The report evaluates correctness non-inferiority, eligible-task savings, negative-control overhead, latency, and routing precision.
- A 12-task corpus covers known single-file negative controls, unfamiliar cross-file bugs, diff/regression diagnosis, and dependency-sensitive refactors.

**Artifacts**

- `tldr-bench/tldr_bench/agent_eval/schema.py` defines task, condition, trace, outcome, and gate contracts.
- `tldr-bench/tldr_bench/agent_eval/workspace.py` materializes clean task repositories, applies hidden mutations, and runs external graders.
- `tldr-bench/tldr_bench/agent_eval/codex_runner.py` constructs isolated Codex commands and parses JSONL traces.
- `tldr-bench/tldr_bench/agent_eval/analysis.py` computes paired metrics and gates.
- `tldr-bench/tldr_bench/tasks/agent_value.yaml` declares 12 tasks without embedding grader code in agent prompts.
- `tldr-bench/agent_eval/graders/` and `tldr-bench/agent_eval/mutations/` hold hidden evaluation assets excluded from task workspaces.
- `tldr-bench/scripts/run_agent_value_eval.py` runs smoke, pilot, resume, and report modes.
- `docs/research/paired-agent-value-eval-2026-07.md` records the real pilot configuration, results, caveats, and verdict.

**Key Links**

- The CLI loads task specs, then asks `workspace.py` for one fresh workspace per `(task, condition, repeat)` before invoking `codex_runner.py`.
- `codex_runner.py` writes the raw trace before `workspace.py` runs the grader, so agent failure and grader failure remain distinct.
- `analysis.py` pairs baseline/adaptive outcomes by `(task_id, repeat)` and refuses to report paired gates for missing or contaminated cells.
- The task materializer excludes `tldr-bench/agent_eval`, task YAML, `.codex`, `.claude-plugin`, `AGENTS.md`, and `CLAUDE.md`, then writes condition-specific guidance.

### Task 1: Define evaluation contracts and task loading

**Files:**

- Create: `tldr-bench/tldr_bench/agent_eval/__init__.py`
- Create: `tldr-bench/tldr_bench/agent_eval/schema.py`
- Create: `tldr-bench/tldr_bench/agent_eval/tasks.py`
- Test: `tldr-bench/tests/test_agent_eval_schema.py`

1. Write failing tests for strict task loading, four task categories, `eligible_for_tldrs`, mutation/grader paths, repeat/condition identity, and JSON round-tripping.
2. Run the test and confirm imports fail because `tldr_bench.agent_eval` does not exist.
3. Implement frozen dataclasses/enums for `Condition`, `TaskCategory`, `Replacement`, `TaskSpec`, `TraceMetrics`, `GradeResult`, `RunOutcome`, `GateThresholds`, and `EvaluationReport`.
4. Make task loading reject duplicate IDs, missing external assets, fewer than 12 tasks in pilot mode, and task prompts containing hidden grader or mutation paths.
5. Re-run tests and commit.

<verify>
- run: `PYTHONPATH=tldr-bench uv run python -m pytest tldr-bench/tests/test_agent_eval_schema.py -q`
  expect: exit 0
</verify>

### Task 2: Materialize isolated workspaces and grade externally

**Files:**

- Create: `tldr-bench/tldr_bench/agent_eval/workspace.py`
- Create: `tldr-bench/tests/fixtures/agent_eval_repo/`
- Test: `tldr-bench/tests/test_agent_eval_workspace.py`

1. Write failing tests that materialize baseline and adaptive workspaces and assert their source trees are identical before condition guidance.
2. Assert evaluator code, mutation files, hidden graders, original history, root harness instructions, and treatment-only binaries are absent from baseline.
3. Assert replacements require exactly one old-text match and fail closed on drift.
4. Assert grading runs outside the agent workspace and records exit status, passed/total tests, stdout, and stderr independently from agent exit status.
5. Implement archive/copy materialization, hidden replacement application, history-free git initialization, sanitized environment construction, condition guidance, patch hashing, and external grader execution.
6. Re-run tests and commit.

<verify>
- run: `PYTHONPATH=tldr-bench uv run python -m pytest tldr-bench/tests/test_agent_eval_workspace.py -q`
  expect: exit 0
</verify>

### Task 3: Run Codex and parse real traces

**Files:**

- Create: `tldr-bench/tldr_bench/agent_eval/codex_runner.py`
- Create: `tldr-bench/tests/fixtures/codex_trace_success.jsonl`
- Create: `tldr-bench/tests/fixtures/codex_trace_failure.jsonl`
- Test: `tldr-bench/tests/test_agent_eval_codex.py`

1. Capture one minimal `codex exec --ephemeral --ignore-user-config --json` trace to establish the current event contract.
2. Write failing parser tests for model/token usage, command/tool events, tldrs calls, raw file reads, compaction events, errors, final message, and malformed lines.
3. Write failing command-builder tests requiring fixed model/config, ephemeral mode, ignored user config/rules, workspace-write sandboxing, no approvals, JSONL, output capture, and explicit working root.
4. Add a fake executable integration test proving timeouts, non-zero agent exits, stdout trace persistence, and environment sanitization.
5. Implement the command builder, runner, and trace parser without treating agent exit zero as task success.
6. Re-run tests and commit.

<verify>
- run: `PYTHONPATH=tldr-bench uv run python -m pytest tldr-bench/tests/test_agent_eval_codex.py -q`
  expect: exit 0
</verify>

### Task 4: Add paired analysis and explicit gates

**Files:**

- Create: `tldr-bench/tldr_bench/agent_eval/analysis.py`
- Create: `tldr-bench/tldr_bench/agent_eval/report.py`
- Test: `tldr-bench/tests/test_agent_eval_analysis.py`

1. Write failing tests for pairing by task/repeat, incomplete-cell rejection, correctness deltas, eligible-task token savings, negative-control overhead, latency delta, routing precision/recall, and contamination.
2. Encode the agreed pilot gates: no more than one additional adaptive failure; at least 20% median token savings on eligible tasks; below 5% median overhead on negative controls; no more than 10% median latency regression; at least 80% routing precision.
3. Use paired bootstrap intervals for continuous deltas and exact paired counts for binary outcomes; retain raw cells in every report.
4. Generate JSON plus a concise Markdown verdict with PASS/FAIL/INCONCLUSIVE per gate and explicit sample size/caveats.
5. Re-run tests and commit.

<verify>
- run: `PYTHONPATH=tldr-bench uv run python -m pytest tldr-bench/tests/test_agent_eval_analysis.py -q`
  expect: exit 0
</verify>

### Task 5: Build the 12-task hidden-grader corpus

**Files:**

- Create: `tldr-bench/tldr_bench/tasks/agent_value.yaml`
- Create: `tldr-bench/agent_eval/mutations/*.yaml`
- Create: `tldr-bench/agent_eval/graders/test_*.py`
- Test: `tldr-bench/tests/test_agent_value_tasks.py`

1. Select three tasks in each category: negative control, cross-file bug, diff/regression diagnosis, and dependency-sensitive refactor.
2. Write each external grader first against the unmutated source and confirm it passes.
3. Add one minimal deterministic replacement mutation and confirm the grader fails for the intended reason.
4. Validate that applying the expected repair makes the grader pass again.
5. Ensure prompts never disclose exact files for eligible exploratory tasks; negative controls may name their target file.
6. Add corpus tests requiring 12 unique tasks, category balance, grader red/green validity, deterministic materialization, and no answer leakage.
7. Commit the corpus.

<verify>
- run: `PYTHONPATH=tldr-bench uv run python -m pytest tldr-bench/tests/test_agent_value_tasks.py -q`
  expect: exit 0
</verify>

### Task 6: Add the executable CLI and resume-safe logging

**Files:**

- Create: `tldr-bench/scripts/run_agent_value_eval.py`
- Modify: `tldr-bench/README.md`
- Modify: `tldr-bench/docs/LOG_SCHEMA.md`
- Test: `tldr-bench/tests/test_agent_value_cli.py`

1. Write failing CLI tests for `--list-tasks`, `--smoke`, `--conditions`, `--repeats`, `--model`, `--results-dir`, `--resume`, `--report-only`, and dry-run command rendering.
2. Implement append-only per-run JSONL with stable cell IDs and resume deduplication.
3. Write raw Codex traces, patches, grader logs, environment metadata, summarized outcomes, JSON report, and Markdown report beneath one run directory.
4. Document exact smoke, pilot, resume, and report commands.
5. Re-run the full `tldr-bench` test suite and commit.

<verify>
- run: `PYTHONPATH=tldr-bench uv run python -m pytest tldr-bench/tests -q`
  expect: exit 0
- run: `PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/run_agent_value_eval.py --list-tasks`
  expect: contains "12 tasks"
</verify>

### Task 7: Execute and publish the real Codex pilot

**Files:**

- Create: `docs/research/paired-agent-value-eval-2026-07.md`

1. Record `codex --version`, resolved model, repository SHA, tldrs version, host metadata, task corpus hash, conditions, limits, and seed.
2. Run one negative-control and one eligible task once per condition as a smoke test; inspect traces to verify baseline has zero tldrs calls and adaptive treatment is available.
3. Fix runner/corpus defects only through new failing tests, then repeat the smoke until graders and telemetry are trustworthy.
4. Run all 12 tasks under baseline and adaptive conditions for three repeats (72 cells), using resume mode after interruptions.
5. Generate paired JSON/Markdown reports and manually audit at least one passing and one failing trace from each condition.
6. Publish the observed verdict without moving thresholds or deleting unfavorable cells. Mark the result inconclusive if cells are missing, treatment is contaminated, or native token usage is unavailable.
7. Run final tests, plugin validation, git diff checks, update/close Beads, rebase, push, and verify `main` is synchronized.

<verify>
- run: `PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/run_agent_value_eval.py --report-only --results-dir tldr-bench/results/agent-value/latest`
  expect: exit 0
- run: `PYTHONPATH=tldr-bench uv run python -m pytest tldr-bench/tests -q`
  expect: exit 0
- run: `git status --short --branch`
  expect: contains "main...origin/main"
</verify>

## Execution Decision

The tasks are sequentially coupled through shared schemas, runner behavior, and corpus contracts. The user explicitly requested immediate execution, so continue in this session without an additional handoff question. Do not dispatch subagents; implement each red-green unit directly and commit after each logical unit.
