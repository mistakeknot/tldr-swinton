---
title: "Paired Agent Value Evaluation: GPT-5.6 Sol"
date: 2026-07-21
research_type: evaluation
component: agent-workflow
bead: mk-5szd
tags: [codex, evaluation, token-efficiency, routing, hidden-graders]
---

# Paired Agent Value Evaluation: GPT-5.6 Sol

## Verdict

**FAIL. Do not make tldrs reconnaissance a default pre-read requirement for the
current Codex workflow.**

Adaptive tldrs preserved aggregate task correctness and selected eligible tasks
without false-positive calls. It did not reduce end-to-end context cost. Across
27 eligible pairs, median token savings were **-11.9%**—an 11.9% regression—and
median latency across all 36 pairs regressed **17.0%**. Both missed the fixed
pilot gates.

The result distinguishes two claims:

- tldrs can compress particular command outputs and is executable in the current
  harness.
- the evaluated agent policy does **not** convert that component compression into
  total agent token or time savings.

## Question and design

The evaluation asked whether an adaptive agent with tldrs available and concise
routing guidance could preserve hidden-grader correctness while using less
uncached native Codex context than a baseline without tldrs.

Each of 12 source mutations ran in a fresh, history-free repository under two
conditions and three repeats, for 72 cells total:

- **Baseline:** no `tldrs` executable in the task environment and no tldrs routing
  guidance.
- **Adaptive:** `tldrs` available with guidance to use it for unfamiliar,
  multi-file, diff-heavy, or dependency-sensitive work and to skip localized
  controls.

Agents never received the mutation specification or grader. Success was the
external hidden grader result, not Codex exit zero or the agent's final claim.
The runner persisted native JSONL traces, patches, command/tool telemetry,
grader output, and contamination checks before calculating paired gates.

## Frozen configuration

| Field | Value |
|---|---|
| Source SHA | `d8765833775f22b2db91d8c03b4c67629b7b5816` |
| Corpus SHA-256 | `fe1b57fa8b71fb6aaca46fcd89d3aad74572e0c5218ade141842f910f7fc5a31` |
| Model | `gpt-5.6-sol` |
| Reasoning effort | `medium` |
| Codex | `codex-cli 0.144.6` |
| tldrs | `tldrs 0.7.19` |
| Python | `3.14.0` |
| Host | Darwin 25.5.0, arm64 |
| Repeats / seed | 3 / 42 |
| Timeout | 900 seconds per cell |
| Completeness | 72/72 cells, 0 contaminated, 0 missing |

The concrete `gpt-5.6-sol` ID was required by the ChatGPT-backed Codex transport;
the API-style `gpt-5.6` alias was rejected locally. The selected model matches
OpenAI's current GPT-5.6 Sol documentation, and Codex 0.144.6 exceeds the 0.144.0
minimum in OpenAI's GPT-5.6 Codex guidance. Sources: [model catalog](https://developers.openai.com/api/docs/models),
[GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol),
[latest model guidance](https://developers.openai.com/api/docs/guides/latest-model),
and [GPT-5.6 in ChatGPT](https://help.openai.com/en/articles/20001354-gpt-56-in-chatgpt).

## Fixed gates

Thresholds were declared before the pilot and were not moved after seeing the
data.

| Gate | Threshold | Observed | 95% paired bootstrap interval | Result |
|---|---:|---:|---:|---:|
| Correctness non-inferiority | <=1 additional adaptive failure | 0 net; lost 1, gained 1 | exact paired counts | PASS |
| Eligible token savings | >=20% median | **-11.9%** | -21.0% to +4.3% | **FAIL** |
| Negative-control overhead | <=5% median | -8.0% | -21.8% to +7.4% | PASS |
| Latency regression | <=10% median | **+17.0%** | +6.5% to +26.0% | **FAIL** |
| Routing precision | >=80% | 100.0% | 25 true positives, 0 false positives | PASS |

Baseline and adaptive each passed 35 of 36 cells. Routing recall was 92.6%
(25/27 eligible pairs); the adaptive agent made 43 substantive tldrs calls
across those 25 pairs and correctly made none in all nine negative controls.
Routing precision here means calls stayed within pre-labelled eligible tasks. It
does not mean every call helped.

## Where the cost went

On all 27 eligible pairs, totals moved in the wrong direction even though tool
output bytes fell:

| Metric | Baseline | Adaptive | Change |
|---|---:|---:|---:|
| Uncached native tokens | 1,961,420 | 2,125,208 | +8.4% |
| Raw-read commands | 210 | 275 | +31.0% |
| Tool calls | 453 | 592 | +30.7% |
| Tool output bytes | 5,283,160 | 4,114,726 | -22.1% |
| Model output tokens | 169,743 | 196,099 | +15.5% |
| Elapsed time | 4,738,011 ms | 5,700,993 ms | +20.3% |

The mechanism is visible: compact tldrs responses reduced transported tool
bytes, but the adaptive agent performed more tool loops and more raw reads, then
generated more output. For the 25 eligible pairs that actually invoked tldrs,
median token savings were worse still at **-14.3%**.

Task-level medians are directional only (`n=3` per task):

| Eligible task | Median token savings | tldrs calls | Baseline/adaptive passes |
|---|---:|---:|---:|
| Cross-manifest flags | +1.9% | 4 | 3/3 |
| Diff output boundary | +4.3% | 5 | 3/3 |
| Symbol registry | +10.8% | 7 | 3/3 |
| Diff preset | -2.3% | 4 | 3/3 |
| Call-graph dedupe | -11.9% | 5 | 2/2 |
| Path containment | -14.3% | 3 | 3/3 |
| Go signature | -21.0% | 4 | 3/3 |
| Cross-module init | -22.6% | 7 | 3/3 |
| Nested gitignore | -23.2% | 4 | 3/3 |

No task has enough repeats to justify a task-specific default from this table.
It is useful for choosing the next ablations.

## Correctness audit

The single adaptive loss occurred on call-graph deduplication in repeat 1; the
single adaptive gain was the same task in repeat 3 when baseline failed. Manual
inspection found the same error in both failed patches:

1. The mutation reversed the first-insertion condition in
   `CallGraphInfo.add_call()` in `ast_extractor.py`.
2. Both failed agents patched downstream `ProjectIndex` adjacency insertion
   instead.
3. Both added consumer-level tests that passed and then reported the change as
   verified.
4. The hidden grader instantiated `CallGraphInfo` directly and failed both the
   first forward edge and repeated-edge cases.

The adaptive repeat used semantic `tldrs find`, but the result led it to the
consumer rather than the owner of the invariant. This is evidence against
treating tool invocation as success. The passing manifest and symbol-registry
patches were also audited in both conditions; the implementations matched and
all corresponding hidden checks passed.

## Smoke test and excluded diagnostics

The final valid smoke used one eligible and one negative-control task. It passed
all gates with 22.4% eligible savings and 7.3% lower latency. That four-cell
result was directionally wrong for the 72-cell pilot and should be treated only
as a harness check.

Two earlier pilot directories were excluded before the final run because the
routing parser counted non-invocations: first `command -v tldrs`, then an
embedded `sys.argv=['tldrs']` literal. Regression tests were added, the parser
was fixed to recognize shell command positions, and the final pilot was started
from a new directory and frozen source SHA. No diagnostic cells were mixed into
the reported run.

## Caveats

- The treatment combines binary availability with routing guidance. It tests an
  adaptive workflow, not an isolated executable-only causal effect. A three-arm
  ablation is needed to separate tool availability from prompt policy.
- Token savings are `total_tokens - cached_input_tokens`, using Codex's native
  trace usage. Both conditions include the current global harness/skill context;
  large cached prefixes are excluded from the primary metric.
- Negative-control differences and eligible pairs with zero tldrs calls expose
  substantial model-run variance. No-call improvements are not tool savings.
- The corpus is local, balanced, and replayable but small. Results should be
  repeated on real issue replays and when model, harness, caching, or tool schema
  changes.
- The aggregate historical `tldr-bench` suite has unrelated environment and
  dataset-topology failures; the paired evaluator has its own focused tests and
  hidden corpus red/green proof.

## Decision and next evaluation

Keep tldrs available, but make the default policy selective and one-shot:

1. Skip reconnaissance for localized edits and already-scoped context.
2. Choose one tldrs command for the current navigation question.
3. Stop when it identifies the exact source and tests; do not chain commands by
   ritual.
4. Require a specific unresolved ambiguity before a second tldrs call.
5. Verify the abstraction layer that owns the behavior, not only a downstream
   consumer.

The next experiment should compare baseline, tool-only, and tool-plus-one-shot
guidance, with duplicate-read rate and task-level source precision as first-class
metrics. Promotion requires the same correctness gate and a positive lower
confidence bound for savings on a larger replay corpus.

## Reproduction

Raw run artifacts are intentionally gitignored. Recreate the frozen pilot from
the recorded source and corpus with:

```bash
PYTHONPATH=tldr-bench .venv/bin/python \
  tldr-bench/scripts/run_agent_value_eval.py \
  --model gpt-5.6-sol \
  --reasoning-effort medium \
  --repeats 3 \
  --seed 42 \
  --results-dir tldr-bench/results/agent-value/pilot-2026-07-21-v3
```

Regenerate the report without rerunning agents:

```bash
PYTHONPATH=tldr-bench .venv/bin/python \
  tldr-bench/scripts/run_agent_value_eval.py \
  --report-only \
  --results-dir tldr-bench/results/agent-value/pilot-2026-07-21-v3
```
