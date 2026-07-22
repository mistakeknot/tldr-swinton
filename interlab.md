# interlab: end-to-end agent token savings

## Objective

Hill-climb tldr-swinton context policy until it reduces eligible-task median
uncached end-to-end tokens by at least 25% with a positive paired lower
confidence bound while improving the frozen hidden-grader result from 35/36 to
36/36.

## Metrics

- **Primary:** eligible uncached total tokens (tokens, lower is better)
- **Hard constraint:** hidden-grader correctness (target 36/36)
- **Secondary:** eligible savings CI, negative-control overhead, model requests,
  tool calls, tldrs calls, raw reads, duplicate-read rate, owner-file hit rate,
  changed-file precision, model output tokens, and elapsed time

## How to Run

Unit mode:

```bash
bash interlab.sh
```

Agent-result mode after a paired run:

```bash
INTERLAB_RESULTS_DIR=/absolute/results/path bash interlab.sh
```

Both modes must emit `METRIC name=value` lines.

## Files in Scope

- `tldr-bench/tldr_bench/agent_eval/`
- `tldr-bench/scripts/`
- `tldr-bench/tests/`
- `interlab.sh`
- `interlab.md`
- `interlab.ideas.md`
- `campaigns/`
- final plan/research documentation

## Constraints

- One context-policy behavior change per measured experiment.
- Tests fail first for every production behavior change.
- Hidden external graders own correctness.
- No threshold changes after observing results.
- No result is kept on token savings if correctness regresses.
- Secondary degradation above 20% discards the mutation.
- No model-generated summary may replace exact source for edits.
- Do not expose mutation files, graders, evaluation code, or repository history
  to the coding agent.
- Preserve unrelated worktree changes.

## Baseline

Frozen GPT-5.6 Sol / Codex 0.144.6 / tldrs 0.7.19, 12 tasks × 2 conditions ×
3 repeats (72 cells):

- correctness: baseline 35/36; adaptive 35/36
- eligible median token savings: -11.9% (95% CI -21.0% to +4.3%)
- negative-control median overhead: -8.0%
- median latency regression: +17.0%
- eligible uncached tokens: 1,961,420 baseline; 2,125,208 adaptive
- raw reads: 210 baseline; 275 adaptive
- tool calls: 453 baseline; 592 adaptive
- tool-output bytes: 5,283,160 baseline; 4,114,726 adaptive

## What's Been Tried

1. **Baseline measurement — keep as reference.** Component compression did not
   translate to run-level savings; added turns and reads dominated.
2. **Gateway primitive reconnaissance — dead end in current runtime.** `distill`
   returned no target for the known call-graph task and `find` has no installed
   semantic backend. The first injected packet cannot depend on those paths.

## Campaign State

Setup and implementation plan complete. Next experiment: add the isolated
`tool_only` and `one_shot` adaptive policies with TDD, then run a stratified
screen against fresh baselines.

## 2026-07-21 Stratified Policy Screen

Model and harness: `gpt-5.6-sol`, medium reasoning, Codex `0.144.6`, source
`634756b`. Tasks: one known-file negative control plus cross-file, diff, and
owner-sensitive refactor tasks. The current-policy run produced fresh paired
baselines. The byte-identical baseline cells were reused for the two subsequent
adaptive-only arms, avoiding eight redundant model runs.

| Policy | Correct | Eligible median savings | Eligible tldrs calls | Refactor owner recall | Decision |
|---|---:|---:|---:|---:|---|
| Baseline | 4/4 | reference | 0/3 | 100% | control |
| Current broad guidance | 3/4 | -35.8% | 3/3 | 0% | reject |
| Tool exposure only | 3/4 | -37.0% | 1/3 | 0% | reject |
| Strict one-shot | 4/4 | -11.8% | 3/3 | 100% | reject for savings; retain owner/cap idea |

Negative-control savings were noisy: current 19.0%, tool-only 22.4%, and
one-shot 40.9%, all correct and with zero tldrs calls. They are not attributed
to the tool.

The decisive failure mechanism was stable across current and exposure-only:
the agent invoked `tldrs find`, the installed runtime had no usable semantic
backend, and the agent then edited a downstream consumer rather than hidden
owner `ast_extractor.py`. Current used 111,632 tokens and exposure-only used
199,615 versus the 76,892-token passing baseline. Strict one-shot restored
owner read/change recall and correctness, but still cost 85,202 tokens.

Decision: model-initiated reconnaissance is exhausted as the primary product
path. Next mutation is a deterministic, automatically injected, bounded packet
derived only from the public task and visible source. The model will not spend a
tool call deciding whether or how to discover context.

## 2026-07-21 Automatic Bounded Packet

Source `51e492d` added a deterministic lexical/local-invariant gateway. It runs
before the agent, derives candidates only from public task text and the visible
materialized workspace, injects at most three excerpts, and hides the
agent-facing executable. Offline top-three hidden-owner recall is 12/12 after
the evaluator surface is removed.

On the same four-task screen the packet was correct on 4/4 and used zero tldrs
calls. Eligible median savings improved from -11.8% for the best model-initiated
policy to +24.2%:

| Task | Baseline tokens | Packet tokens | Savings | Correct |
|---|---:|---:|---:|---:|
| Known-file control | 70,550 | 57,702 | 18.2% | yes |
| Cross-file ignore | 70,153 | 71,024 | -1.2% | yes |
| Diff boundary | 60,764 | 46,074 | 24.2% | yes |
| Owner refactor | 76,892 | 42,126 | 45.2% | yes |

The packet eliminated the prior refactor escape: it edited the hidden owner and
passed while saving 45.2%. The cross-file outlier spent 22 tool calls and
155,522 output bytes probing unavailable test runtimes and package managers.
The source owner was already correct. Next mutation: add a validated execution
contract naming the working test interpreter and discourage runtime probing.
