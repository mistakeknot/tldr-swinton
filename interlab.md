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
