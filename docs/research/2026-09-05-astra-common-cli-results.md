---
title: "Astra common-CLI comparison: completed repeated battery"
date: 2026-09-05
research_type: evaluation
component: agent-workflow
bead: Sylveste-8ia
tags: [codex, astra, evaluation, routing]
---

# Astra common-CLI comparison

All three routes passed **18/18** hidden-grader runs: one first pass and two
repeats of each of the six functional ties. Different-model review found no newly
introduced P0/P1 defect. This supports the planned narrow canary, not a bulk
route switch or a completed estate rollout.

Every cell used Codex **0.153.3**, explicit Standard service, frozen source and
evaluator `adfb92239a9b6b021034a3981bbe0e6c4d6b0075`, and corpus digest
`8cd2abcd20d8d67d5fadc6803ec5089ac7d725fb6c19b5b15c6ab513f8f0edef`.
The frozen harness passed `--ignore-user-config`, `--ignore-rules` and
`--strict-config`; it did not select the separate experimental Astra profile.
Resolved feature-flag state was not captured, so this is not an evaluation of
experimental context management. Task selection and repeat policy follow the
[preregistered protocol](2026-09-04-astra-role-routing-evaluation.md).

## Results

| Route | Accepted | Aggregate task seconds | Input tokens | Cached input subset | Output tokens | Tool calls |
|---|---:|---:|---:|---:|---:|---:|
| Sol/xhigh | 18/18 | 4,696.195 | 18,661,212 | 17,530,880 | 175,814 | 519 |
| Astra/high | 18/18 | 2,015.389 | 7,491,942 | 6,916,224 | 39,290 | 249 |
| Astra/xhigh | 18/18 | 2,598.620 | 8,143,274 | 7,412,864 | 58,387 | 329 |

Astra/high used 57.1% less aggregate task time than Sol in this run; Astra/xhigh
used 44.7% less. These are observed sums, not fleet makespan or causal latency
estimates: runs overlapped on one host, and this is a small fixed mutation
battery. It does not establish general reliability or high-severity review
retention. Astra/xhigh showed no acceptance advantage over high here.

No agent process failed, timed out, or tripped contamination checks. All changed
paths were the task's mutated owner or tests. Exploratory command errors totaled
117 / 93 / 122 respectively, including unavailable or mismatched test tooling.
They are not whole-agent retries: the harness retried no process. The 36 planned
tie repeats are separate cells. The harness's `INCONCLUSIVE` label concerns its
baseline-versus-tldrs-condition comparison; this experiment intentionally ran
only the baseline condition and compares model cells separately.

## Independent review and dispositions

Fable 5.1 reviewed all 36 Astra cells in two sealed packets (16 unique patches
per packet), without grader outcomes or the other review's findings. Actual
transcripts confirmed `claude-fable-5-1`, not just a requested routing alias.
The main Astra integrator reviewed all 18 Sol patches; that baseline review was
not blinded to grader results. Reviews were static; the harness executed the
hidden graders, and the main integrator ran the additional Git-parity probe.

- Astra/high's first-pass verdict was **NEEDS_ATTENTION** solely for a low
  scope question: recursive matching for trailing-slash basename patterns such
  as `cache/` also fixes a limitation in the frozen reference. Native
  `git check-ignore --no-index` agreed with the extension on all nine checked
  cases, including anchoring, negation and sibling boundaries. The main
  integrator accepts it under the brief's Git-compatibility requirement.
- Astra/xhigh's first-pass verdict was **CLEAN**, with the same scope observation.
  Its Markdown-formatted verdict produced a conservative warning sidecar; that
  warning was not converted into automatic acceptance.
- Sol's directory-pattern extensions receive the same disposition. Its final
  path-containment candidate also fixes an inherited dot-free absolute escape.
  The Astra/high reviewer independently surfaced that limitation. It is reproduced
  and retained as **Sylveste-lca**, not counted as a new Astra defect or silently
  lost. No evaluation candidate was applied to the live production source.

One earlier review attempt could not read its external packet. Its coverage is
zero and it is excluded, not treated as a clean review. The successful attempts
received their packets directly in the prompt. Intercore task-store records
18 and 21 (high), and 19 and 20 (xhigh), retain distinct producer/validator identities and
lifecycle evidence; detailed first-pass findings and main dispositions are
preserved in the receipt below.

## Cost and context observations

| Route | Executor cost bounds, total | Bounds per completed benchmark task |
|---|---:|---:|
| Sol/xhigh | $15.05–$28.34 | $0.84–$1.57 |
| Astra/high | $14.64–$26.29 | $0.81–$1.46 |
| Astra/xhigh | $17.64–$32.70 | $0.98–$1.82 |

These are **Standard-equivalent bounds**, not bills or complete task costs.
The ephemeral exec traces retain one aggregate usage event per task, not each
model request's context. The lower bound uses base prices. The conservative
upper bound applies the long-context multipliers to all eligible aggregate
usage; when total task input is at most 272K, no constituent request can exceed
the threshold and the bounds coincide. Cached input is subtracted from ordinary
input before pricing. Cache-write usage was zero in this battery. Applying the
surcharge to the whole task as if it were one request would invent precision.
Rates and full-request multipliers follow the official
[Astra](https://developers.openai.com/api/docs/models/gpt-6-astra) and
[Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol) specifications.

A separate, explicitly attributed main-integrator window from 07:55 to 08:30
UTC contained 59 model requests: mean context **145,285**, maximum **247,448**,
46 above 100K and none above 272K. Its Standard-equivalent cost was **$13.24**.
The 100K observational target was not met. This window mixes integration work;
neither completed-task count nor cost per task is imputed. Per-cell main
integration turns were not instrumented. Token share is not an offload gate.

## Rollout disposition and durable evidence

Observed plan-to-execution acceptance is 1.000 in each route, above the 0.909
threshold, without claiming a population reliability bound. Policy-denial
precedence and no-fallback behavior are covered by the separate control-plane
regressions and live routing evidence, not inferred from this all-success batch.

Keep Astra/high as the opt-in deep candidate, Astra/xhigh for the user-selected
integrator, and routine/bulk work on Sol. At comparison close, the estate canary
was **pending release gates, with zero accepted estate tasks**: protected-main Interflux
landing, scoped plugin publication, and signer-gated closure are not bypassed.
Benchmark cells and transport probes do not count toward its 20-task/14-day
window. No interserve class is promoted without the missing parity corpus.

Release follow-up (2026-09-05): those release gates subsequently cleared. The
[reviewed rollout packet](https://github.com/mistakeknot/Clavain/blob/e53ca59cbf36491e7d27526511c2cb827ae25955/docs/runbooks/astra-rollout.md)
opens explicit Mac-only enrollment under Intercore decision 547, still with zero
tasks. Its 20-terminal-task/14-day checkpoint is not automatic promotion. This
does not alter the benchmark receipt, its original release-authority disposition,
or the exclusion of these 54 cells from estate task counts.

The [machine-readable receipt](data/astra-common-cli-2026-09-05.json) contains all
54 cell outcomes, exact metadata, usage, costs, artifact hashes, review identities,
dispositions and the native-Git replay. The
[49 unique patches](data/astra-common-cli-2026-09-05-patches.json) are retained by
SHA-256. Original sealed findings are preserved for
[Astra/high](data/astra-high-independent-review-2026-09-05.md) and
[Astra/xhigh](data/astra-xhigh-independent-review-2026-09-05.md).
Full raw traces remain local in the six gitignored run directories described in
the [first-pass checkpoint](2026-09-05-astra-common-cli-checkpoint.md).

Fresh evaluator checks: **17/17** Codex-runner/CLI tests pass. The older broad
suite's three documented baseline failures are not relabeled green here.
