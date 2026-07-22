---
title: "Context Gateway Token Savings: Coding Performance Confirmation"
date: 2026-07-21
research_type: evaluation
component: agent-workflow
bead: mk-gimi
tags: [codex, evaluation, token-efficiency, middleware, hidden-graders]
---

# Context Gateway Token Savings

## Verdict

**PASS. Promote deterministic, harness-side context packets with a validated
test runtime.**

Across 12 hidden-grader coding tasks and three repeats, the winning gateway
completed **36/36** cells versus **35/36** for the frozen baseline. On the 27
pre-labelled eligible pairs it saved a median **32.1%** uncached end-to-end
tokens, with a 95% paired bootstrap interval of **25.2% to 41.1%**. Median
latency across all 36 pairs fell **34.7%** (95% interval 26.7% to 47.4%).

This reverses the earlier model-initiated policy, which preserved only 35/36
and regressed eligible tokens by 11.9%. The successful change was architectural:
move context selection out of the agent loop, inject at most three ranked source
windows, and tell the agent which verified test runtime to use.

## Winning architecture

```text
public task + visible source
            |
            v
deterministic source-owner ranker (top 3, <= 6000 source characters)
            |
            v
bounded source packet + known-good test command
            |
            v
coding agent -> exact-source edit -> external hidden grader
```

The ranker uses lexical identifiers, path concepts, local line windows, source-
directory bias, explicit paths, and one high-value local-invariant check for a
reversed deduplication guard. It requires no embedding model or semantic index.
The agent-facing `tldrs` executable is hidden in this condition; zero agent-side
tldrs calls is the intended result, not a routing failure.

The production surface is:

```bash
tldrs packet "<public task text>" --project . \
  --test-command "<known-good focused test command>"
```

Use global `--machine` to receive ranked excerpts as JSON for direct harness
composition.

## Experimental ladder

Every screen changed one policy behavior. Correctness failures were rejected
regardless of token movement.

| Arm | Correctness | Eligible median savings | Decision |
|---|---:|---:|---|
| Original model-initiated policy, full corpus | 35/36 | -11.9% | reject |
| Broad guidance, four-task screen | 3/4 | -35.8% | reject |
| Tool exposure only | 3/4 | -37.0% | reject |
| Strict one-shot tool use | 4/4 | -11.8% | reject |
| Automatic bounded source packet | 4/4 | +24.2% | keep, below target |
| Packet + validated test runtime | 4/4 | +45.0% | promote |
| Packet + runtime, full confirmation | 36/36 | +32.1% | pass |

The broad and tool-only arms repeatedly invoked semantic `find` without a usable
backend, then patched a downstream consumer rather than the hidden behavior
owner. A one-call cap repaired correctness but not cost. Precomputation removed
the routing/index turn. The execution contract then removed interpreter and
package-manager probing that dominated the remaining outlier.

## Confirmation results

| Gate | Result | Fixed threshold | Status |
|---|---:|---:|---:|
| Hidden-grader correctness | 36/36 vs 35/36 | no additional failures | pass |
| Eligible median token savings | 32.1% | at least 20% | pass |
| Eligible savings 95% interval | 25.2% to 41.1% | lower bound above zero | pass |
| Negative-control median overhead | -20.6% | no more than 5% | pass |
| Median latency regression | -34.7% | no more than 10% | pass |
| Eligible owner-change recall | 100%, 0 misses in 27 | at least 95% | pass |
| Contaminated or missing cells | 0 | 0 | pass |

Negative overhead means the adaptive condition used fewer tokens. Its 95%
interval ranged from 47.4% savings to 3.8% overhead, so the direction on
negative controls remains uncertain even though the predeclared median gate
passes.

Eligible aggregate behavior moved in the same direction as the median:

| Metric | Baseline | Context gateway | Change |
|---|---:|---:|---:|
| Uncached tokens | 1,961,420 | 1,304,615 | -33.5% |
| Tool calls | 453 | 272 | -40.0% |
| Raw-read calls | 210 | 109 | -48.1% |
| Elapsed time | 4,738,011 ms | 2,802,015 ms | -40.9% |

All nine eligible task types had positive task-level median savings. The range
was 22.1% to 53.7%. Individual cells still varied; the call-graph task included
one 12.7% regression and one 63.4% saving.

## Coding-performance improvement

The recovered cell was `refactor-callgraph-dedupe`, repeat 3:

| Condition | Correct | Uncached tokens |
|---|---:|---:|
| Baseline | no | 108,121 |
| Context gateway | yes | 39,612 |

The old failure patched a downstream graph consumer. The gateway exposed the
definition owner, the agent changed that owner, and the hidden grader passed.
The same cell used 63.4% fewer uncached tokens. Across all eligible cells,
owner-change recall was 27/27.

## Frozen configuration and comparability

| Field | Value |
|---|---|
| Task corpus SHA-256 | `fe1b57fa8b71fb6aaca46fcd89d3aad74572e0c5218ade141842f910f7fc5a31` |
| Model / effort | `gpt-5.6-sol` / `medium` |
| Codex | `codex-cli 0.144.6` |
| tldrs | `0.7.19` |
| Python / host | `3.14.0` / Darwin 25.5.0 arm64 |
| Tasks / repeats / seed | 12 / 3 / 42 |
| Bootstrap samples | 20,000 paired median resamples |
| Frozen baseline source | `d8765833775f22b2db91d8c03b4c67629b7b5816` |
| Gateway run source | `b23db680c07490ad0999543a18ac7618be39ab84` |
| Production packet commit | `3e881c5` |

The confirmation reused the same-day frozen baseline rather than spending 36
more baseline model runs. Model, effort, Codex, host, corpus hash, task IDs,
repeats, and seed match. The source SHAs differ because the gateway run added
evaluator, documentation, and two harness-guidance test assertions. A source
diff over `src`, `tests`, `pyproject.toml`, and `uv.lock` found only those two
assertions; they were not among the injected top-three candidates. This makes
the comparison controlled enough for promotion, but a release-scale external
replay should restore same-SHA paired baselines.

## Reproduction

Raw run artifacts are gitignored under:

- `tldr-bench/results/agent-value/pilot-2026-07-21-v3`
- `tldr-bench/results/agent-value/confirm-20260721-injected-runtime-r3`

The confirmation adaptive cells were produced with:

```bash
PYTHONPATH=tldr-bench .venv/bin/python \
  tldr-bench/scripts/run_agent_value_eval.py \
  --conditions adaptive \
  --adaptive-policy injected_runtime \
  --model gpt-5.6-sol \
  --reasoning-effort medium \
  --repeats 3 \
  --seed 42 \
  --results-dir \
    tldr-bench/results/agent-value/confirm-20260721-injected-runtime-r3
```

Pair the baseline outcomes from the pilot directory with adaptive outcomes from
the confirmation directory and call `analyze_outcomes(...,
routing_gate="context_owner", bootstrap_samples=20000, seed=42)`. The analysis
fails closed on duplicate, missing, contaminated, or unknown task cells.

## Limits and next experiments

- This is one Python repository, one model, and 12 local mutation tasks. Repeat
  on external issue replays, other languages, and at least one other model.
- Ablate `max_files` and `max_chars` to find the Pareto boundary below three
  files and 6,000 characters without losing owner recall.
- Separate the packet and execution-contract effects on a larger corpus.
- Add a harness adapter that generates the packet and injects it directly into
  Codex, Claude Code, and MCP request construction.
- Measure provider prompt-cache savings separately; do not count cached-prefix
  economics as logical-token savings.
- Re-run this evaluation whenever model, harness, tool schema, compaction, or
  default test runtime behavior changes.

The key product lesson is narrow: do not ask a frontier coding model to decide
whether to spend a turn discovering context when deterministic middleware can
already provide the likely owner and a valid path to verification.
