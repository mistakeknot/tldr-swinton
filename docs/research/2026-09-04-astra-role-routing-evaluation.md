---
title: "Astra Role-Routing Evaluation"
date: 2026-09-04
research_type: evaluation
component: agent-workflow
bead: Sylveste-8ia
tags: [codex, astra, evaluation, routing]
---

# Astra Role-Routing Evaluation

## Preregistered protocol

This evaluation compares the proposed Codex execution routes on six fixed,
hidden-grader tasks from the existing agent-value corpus. Every task uses the
`baseline` harness condition so model capability is the only treatment; tldrs
is neither exposed nor injected.

The fixed tasks are:

1. `neg-import-statement`
2. `cross-gitignore-nested`
3. `cross-manifest-flags`
4. `diff-path-containment`
5. `refactor-callgraph-dedupe`
6. `refactor-go-signature`

The execution tuples are:

| Route | Model | Reasoning | Service |
|---|---|---|---|
| Baseline | `gpt-5.6-sol` | `xhigh` | Standard |
| Astra execution | `gpt-6-astra` | `high` | Standard |
| Astra integration | `gpt-6-astra` | `xhigh` | Standard |

The harness passes Standard explicitly as Codex `service_tier="default"` and
records it in run metadata. Each runnable task-model cell executes once.
Failed cells and task-level functional ties are eligible for two additional
runs. A model-access or configuration 4xx is a terminal preflight result: it
blocks that model matrix without task retries or fallback to another model.

The primary outcome is hidden-grader acceptance. Secondary measures are
escaped grader defects, wall time, input/cached/output/uncached tokens, tool
calls, and trace errors. The harness does not retry agent processes, so process
retry count is zero unless a separately identified repeated cell is executed.
The main integrator consumes one result packet per completed task; this is
reported separately from the agent's internal tool turns.

## Promotion gates

- Astra must match or exceed the Sol functional pass rate.
- Astra must introduce no P0/P1 validation finding or scope violation.
- Policy/configuration blocks must not trigger retry or fallback.
- Producer and validator must resolve to different models for consequential
  work.
- Plan-to-execution success across the rollout remains at least 0.909.
- Routed decisions and verdicts remain durable and queryable.

The context target of at most 100K main-integrator tokens per turn is
observational. Quality and safety remain the promotion gates.

## Results

The GPT-5.6 Sol baseline completed all six cells on Codex 0.153.2 at source and
evaluator commit `adfb92239a9b6b021034a3981bbe0e6c4d6b0075`. All six hidden
graders passed; no cell timed out, failed at the agent-process boundary, or was
contaminated. No failure repeat was required.

| Task | Accepted | Wall time (s) | Uncached tokens | Tool calls |
|---|---:|---:|---:|---:|
| `neg-import-statement` | yes | 233.848 | 39,044 | 21 |
| `cross-gitignore-nested` | yes | 699.771 | 82,271 | 40 |
| `cross-manifest-flags` | yes | 427.154 | 59,979 | 21 |
| `diff-path-containment` | yes | 465.225 | 62,944 | 19 |
| `refactor-callgraph-dedupe` | yes | 283.724 | 55,933 | 14 |
| `refactor-go-signature` | yes | 390.925 | 72,008 | 18 |

The baseline acceptance rate was 1.000, median wall time was 409.040 seconds,
and median uncached tokens were 61,462. The six cells used 5,948,962 input
tokens, of which 5,631,104 were cached, plus 54,321 output tokens. Total
uncached tokens were 372,179 and total wall time was 2,500.647 seconds. The
agents made 133 tool calls. Traces recorded 31 non-zero exploratory commands,
mostly unavailable workspace test tooling; every agent recovered and the
external graders still passed. These are trace errors, not harness retries or
escaped defects.

Manual review found no P0/P1 issue or unrelated source edit in the six patches.
Every patch changed the mutated owner plus a focused test, and owner-change
recall was 1.0. The main integrator consumed six bounded result packets in one
integration turn. Exact main-integrator context tokens are unavailable from the
headless evaluator and are not imputed.

The live Astra preflight used the same standalone Codex 0.153.2 binary, explicit
Standard service, low effort, a read-only `/private/tmp` working directory, and
only the prompt `Reply ASTRA_READY`. OpenAI returned HTTP 400: `gpt-6-astra` is
not supported with this ChatGPT account. The high and xhigh task matrices were
therefore marked blocked before task execution. The harness issued no task
retry and did not substitute GPT-5.6 Sol. Both intended Astra commands were
also dry-run verified with explicit `service_tier="default"`.

## Verdict

**BLOCKED; do not promote Astra.** Sol clears the functional gate at 6/6, but
Astra non-inferiority, latency, token cost, ties, and high-severity retention
cannot be evaluated until account access succeeds. The policy/configuration
gate behaved correctly: the terminal 400 caused zero retries and zero fallback.
There was no Astra-produced consequential work requiring a model validator.
The opt-in profile and collected evidence remain in place for a future retry;
the base and routine routes stay on GPT-5.6 Sol.

The machine-readable summary is
[`data/astra-role-routing-evaluation-2026-09-04.json`](data/astra-role-routing-evaluation-2026-09-04.json).
Raw traces, patches, messages, and grader output remain in the gitignored local
run directory `tldr-bench/results/agent-value/astra-routing-2026-09-04-sol-xhigh-r1`.
Intercore routing decision `519` records the resolved `deep-sol` profile and
`account_access_absent` fallback reason for the `main-integrator` session.

The evaluator's focused Codex-runner and CLI suites pass 17/17. The broader
`tldr-bench/tests` run passes 122 tests and retains three pre-existing failures:
two dataset-runner tests require the absent opt-in
`tldr-bench/data/swebench_sample.jsonl`, and one OpenHands test has a stale
subprocess mock that does not accept the runner's existing `env` argument. The
same three tests fail unchanged at pre-work commit `6f6a4ec`; they are not
treated as new green coverage or as Astra-evaluation failures.

Model facts and the access-sensitive rollout policy follow the official
[Astra model specification](https://developers.openai.com/api/docs/models/gpt-6-astra)
and [latest-model guidance](https://developers.openai.com/api/docs/guides/latest-model).
