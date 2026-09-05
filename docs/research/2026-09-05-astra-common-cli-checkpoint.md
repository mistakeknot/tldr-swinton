---
title: "Astra common-CLI comparison: first-pass checkpoint"
date: 2026-09-05
research_type: evaluation
component: agent-workflow
bead: Sylveste-8ia
tags: [codex, astra, evaluation, routing]
---

# Astra common-CLI comparison: first-pass checkpoint

This historical checkpoint is superseded by the
[completed repeated comparison](2026-09-05-astra-common-cli-results.md): all
three routes passed 18/18, with independent review and explicit dispositions.

All three routes passed the six preregistered hidden graders. This is a checkpoint,
not a promotion verdict: two repeats of every functional tie are underway, and
independent review of Astra-produced patches remains pending.

Every cell used Codex **0.153.3**, Standard service, frozen source and evaluator
`adfb92239a9b6b021034a3981bbe0e6c4d6b0075`, and task-corpus digest
`8cd2abcd20d8d67d5fadc6803ec5089ac7d725fb6c19b5b15c6ab513f8f0edef`.
All used the baseline harness with user configuration ignored. The separate
experimental Astra profile was not selected; resolved feature-flag state was
not recorded. The six tasks and promotion
gates remain those in the [preregistered protocol](2026-09-04-astra-role-routing-evaluation.md).

| First-pass route | Accepted | Total seconds | Input tokens | Cached input | Output tokens | Tool calls |
|---|---:|---:|---:|---:|---:|---:|
| Sol/xhigh | 6/6 | 1,327.087 | 4,789,299 | 4,459,264 | 51,737 | 174 |
| Astra/high | 6/6 | 704.816 | 2,502,207 | 2,320,640 | 13,484 | 81 |
| Astra/xhigh | 6/6 | 899.042 | 2,665,990 | 2,437,504 | 19,429 | 120 |

Cached input is a subset of input, not additive. All 18 agent processes exited
zero; none timed out or triggered the harness contamination check. Traces contain
37, 30 and 37 exploratory command errors respectively. Those errors were recovered
from sufficiently to pass the graders; they are not process retries, and grader
success does not prove that no defects escaped.

The first-pass runtime totals favor Astra, but parallel runs share a host and
single runs do not establish a stable latency advantage. Per-request conditional
costs, main-integrator context/turn, independent escaped-defect findings, and the
final repeated-cell comparison are not yet reported. No main-turn count or task
cost is inferred from executor token share.

## Evidence and continuing runs

Raw metadata, traces, patches and grader output are under the gitignored
`tldr-bench/results/agent-value/` directories:

- `astra-routing-2026-09-05-sol-xhigh-r1`
- `astra-routing-2026-09-05-astra-high-r1`
- `astra-routing-2026-09-05-astra-xhigh-r1`

The two additional runs per cell use the corresponding
`astra-routing-2026-09-05-<route>-tie-repeats` directories with `--repeats 2`.
Their internal repeat numbers restart at 1; the directory distinguishes them
from first pass. Policy/configuration denials must not be retried or substituted.

The earlier 0.153.2 baseline and account-access rejection remain historical
evidence, not the current access state. Astra is now accessible. The estate
20-task/14-day canary is still unqualified: these benchmark cells and transport
probes are not counted as accepted estate tasks.
