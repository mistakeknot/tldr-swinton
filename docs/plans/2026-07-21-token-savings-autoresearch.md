# End-to-End Token Savings Autoresearch Implementation Plan

> **For Claude:** Execute this plan sequentially in the current session. The
> experiment loop must keep one behavioral mutation per benchmark iteration.

**Goal:** Reduce median uncached end-to-end agent tokens by at least 25% with a
positive paired lower confidence bound while improving the frozen corpus from
35/36 to 36/36 hidden-grader successes.

**Architecture:** Keep the current history-free paired evaluator as the source
of truth. Add an adaptive-policy dimension without disturbing the baseline,
add behavioral telemetry that explains token changes, and stage increasingly
integrated context policies. Run cheap smoke and task-stratified screens before
promoting a variant to the full repeated corpus.

**Tech Stack:** Python 3.14, pytest, Codex CLI JSONL traces, tldrs 0.7.19,
external hidden graders, paired bootstrap intervals, Bash metric wrapper.

**Bead:** `mk-gimi`

**Result:** Completed 2026-07-21. The confirmed packet + runtime policy achieved
36/36 hidden-grader successes versus 35/36 baseline and 32.1% median eligible
token savings (95% interval 25.2% to 41.1%). Production surface: `tldrs packet`.
See `docs/research/2026-07-21-context-gateway-token-savings.md`.

## Prior Learnings

- The 72-cell GPT-5.6 Sol evaluation passed 35/36 in both conditions but the
  adaptive arm regressed eligible median tokens by 11.9% and latency by 17%.
- Tool-output bytes fell 22.1% while raw reads rose 31%, tool calls 30.7%, and
  model output 15.5%. Optimize the whole run, not command payloads.
- The single correctness miss localized a downstream consumer rather than the
  behavior owner. Owner-file and owner-symbol hits must become first-class.
- Plugin guidance and PostToolUse injection previously added context after an
  expensive read. The next policy must prevent or replace loops.
- `tldrs distill` currently resolves no target for the call-graph task and the
  installed semantic backend is unavailable. Do not base the first gateway on
  those paths.
- Session search found no more specific prior paired-eval transcript than the
  persisted report and current code.

## Must-Haves

### Truths

- Every promoted arm is compared with a freshly paired baseline under the same
  model, effort, source SHA, corpus, and randomized order.
- Hidden-grader correctness is a hard constraint; the target is 36/36, not
  merely non-inferiority.
- One experiment changes one context-policy behavior.
- Token, cache, tool/read, duplicate-read, owner-file, and latency metrics are
  persisted before a keep/discard decision.
- Negative controls do not pay material tldrs overhead.

### Artifacts

- `tldr-bench/tldr_bench/agent_eval/policy.py` defines named adaptive policies.
- The existing evaluator records the selected policy in frozen metadata.
- Trace/outcome schemas include duplicate-read and changed-file evidence.
- A deterministic summarizer emits `METRIC name=value` lines from a results
  directory.
- `interlab.md` and `interlab.ideas.md` record the living campaign until it is
  archived under `campaigns/`.

### Key Links

- CLI `--adaptive-policy` → frozen metadata → workspace guidance/environment.
- Codex trace command paths → duplicate-read metrics.
- Captured patch paths + mutation replacement paths → owner-file precision.
- Hidden graders + token metrics → keep/discard decision.

## Task 1: Add an isolated adaptive-policy dimension

**Files:**

- Create: `tldr-bench/tldr_bench/agent_eval/policy.py`
- Modify: `tldr-bench/tldr_bench/agent_eval/workspace.py`
- Modify: `tldr-bench/tldr_bench/agent_eval/cli.py`
- Test: `tldr-bench/tests/test_agent_eval_workspace.py`
- Test: `tldr-bench/tests/test_agent_value_cli.py`

1. Write failing tests proving `tool_only` exposes tldrs without routing text,
   `one_shot` contains an explicit one-call stop contract, and metadata freezes
   the policy.
2. Run:

   ```bash
   PYTHONPATH=tldr-bench .venv/bin/python -m pytest \
     tldr-bench/tests/test_agent_eval_workspace.py \
     tldr-bench/tests/test_agent_value_cli.py -q
   ```

   Expect the new tests to fail because `--adaptive-policy` does not exist.
3. Implement `AdaptivePolicy` with `current`, `tool_only`, and `one_shot`.
   Preserve `Condition.BASELINE` and `Condition.ADAPTIVE` so paired analysis
   remains stable.
4. Pass the policy to workspace materialization only for the adaptive arm and
   record it in metadata/resume validation.
5. Re-run the focused tests and the complete `tldr-bench/tests` suite.

## Task 2: Add behavioral and source-owner telemetry

**Files:**

- Modify: `tldr-bench/tldr_bench/agent_eval/schema.py`
- Modify: `tldr-bench/tldr_bench/agent_eval/codex_runner.py`
- Modify: `tldr-bench/tldr_bench/agent_eval/workspace.py`
- Modify: `tldr-bench/tldr_bench/agent_eval/cli.py`
- Modify: `tldr-bench/tldr_bench/agent_eval/analysis.py`
- Modify: `tldr-bench/tldr_bench/agent_eval/report.py`
- Test: `tldr-bench/tests/test_agent_eval_codex.py`
- Test: `tldr-bench/tests/test_agent_eval_schema.py`
- Test: `tldr-bench/tests/test_agent_eval_analysis.py`

1. Write failing trace-parser tests for repeated exact raw-read paths and for
   commands that must not be misclassified as file reads.
2. Write failing outcome/analysis tests for changed paths, mutation owner paths,
   owner-file Hit@1, changed-file precision, and duplicate-read rate.
3. Run the focused tests and confirm expected failures.
4. Implement conservative shell-path extraction. Count only paths that can be
   resolved inside the evaluation workspace; unknown commands remain unscored.
5. Persist changed paths from the captured patch without exposing mutation data
   to the agent.
6. Add the new metrics to JSON and Markdown reports.
7. Re-run focused and full evaluator tests.

## Task 3: Add a deterministic campaign metric wrapper

**Files:**

- Create: `tldr-bench/scripts/summarize_agent_value_experiment.py`
- Create: `tldr-bench/tests/test_summarize_agent_value_experiment.py`
- Modify: `interlab.sh`

1. Write a failing fixture-driven test requiring these lines:

   ```text
   METRIC correctness_rate=<0..1>
   METRIC eligible_uncached_tokens=<integer>
   METRIC eligible_token_savings=<fraction>
   METRIC duplicate_read_rate=<fraction>
   METRIC owner_file_hit_rate=<fraction>
   METRIC latency_ms=<integer>
   ```

2. Verify the test fails because the summarizer does not exist.
3. Implement a read-only summarizer over `metadata.json`, `outcomes.jsonl`, and
   `report.json`; fail closed on incomplete or contaminated cells.
4. Make `interlab.sh` summarize `INTERLAB_RESULTS_DIR` when set and retain the
   existing unit-test mode otherwise.
5. Run focused and full tests.

## Task 4: Run the three-arm causal screen

**Artifacts:** ignored results under `tldr-bench/results/agent-value/` and
experiment entries in `interlab.md`.

1. Run unit tests and freeze current model/harness versions.
2. Run a task-stratified screen with fresh baselines for `tool_only` and
   `one_shot`: one negative control, one cross-file task, one diff regression,
   and the call-graph owner failure; one repeat first.
3. Discard any policy that loses correctness, adds more than 20% to a secondary
   metric, or increases tool/read loops.
4. Promote the winner to three repeats on all 12 tasks.
5. Keep it only if it improves tokens and does not lose correctness. Update
   `interlab.md` after every run.

## Task 5: Prototype transparent deterministic injection

**Files:** determined after Task 4 from the winning trace; likely:

- Create: `tldr-bench/tldr_bench/agent_eval/context_packet.py`
- Modify: `tldr-bench/tldr_bench/agent_eval/policy.py`
- Modify: `tldr-bench/tldr_bench/agent_eval/workspace.py`
- Test: `tldr-bench/tests/test_agent_eval_context_packet.py`

1. Write a failing test for a model-free packet built only from the public task,
   repository source, and deterministic lexical/structural signals.
2. Require exact file/line excerpts, owner/test role labels, a token/line budget,
   provenance, omissions, and degraded/fail-open health.
3. Verify failure, then implement the smallest packet generator that can resolve
   the call-graph owner and at least two other eligible task strata.
4. Inject the packet into the adaptive workspace before the model's first turn;
   hide the tldrs executable so this arm cannot create a second tool loop.
5. Run the same screen and promote only if owner-file hits and correctness rise
   while logical tokens fall.

## Task 6: Hill-climb packet selection one change at a time

Candidate mutations, tried in order only when prior evidence supports them:

1. lexical identifier/error anchors,
2. definition-owner boost,
3. direct test/import/call expansion,
4. exact line-window budget,
5. utility gate for negative controls,
6. deduplication against stable packet handles,
7. local reranker only if deterministic scoring plateaus.

For each mutation: tests → stratified screen → keep/discard → log. Stop when five
experiments improve by less than 1%, ten consecutive ideas fail, or the target
gate is met and confirmed.

## Task 7: Confirm, publish, and land

1. Run the best policy versus fresh baseline for at least five repeats while
   variance remains material.
2. Require 36/36 or better equivalent correctness on the original three-repeat
   corpus before claiming coding improvement.
3. Publish the full run configuration, CIs, raw aggregate metrics, failures,
   dead ends, and causal interpretation under `docs/research/`.
4. Archive the campaign under `campaigns/`, update its index, close `mk-gimi`,
   commit, pull/rebase, and push `main`.
