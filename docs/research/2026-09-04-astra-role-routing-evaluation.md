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

Pending execution. Machine-readable summaries and the final promotion verdict
will be added after the runnable matrices complete.
