# interlab: end-to-end agent token savings

## 2026-07-22 External Same-SHA Campaign

Objective: validate the shipped 0.8.1 Context Gateway on pinned third-party
Python and Go repositories under both Codex and Claude Code, then reduce the
default packet budget only when hidden-grader correctness is non-inferior.

- **Hard gate:** no adaptive correctness loss within any repository/model arm.
- **Primary optimization metric:** paired median uncached total-token savings.
- **Secondary metrics:** latency, tool calls, raw reads, duplicate reads,
  owner-file recall/precision, and changed-file precision.
- **Frozen sources:** `pallets/itsdangerous@672971d` and
  `google/go-cmp@b133f1f` from `tldr-bench/agent_eval/external/sources.yaml`.
- **Harnesses/models:** Codex `gpt-5.6-sol` and Claude Code `sonnet` (resolved
  model IDs and harness versions are recorded per result directory).
- **Initial treatment:** `injected_runtime`, three ranked files, 6000 source
  characters, public language-specific test command.
- **Hill-climb order:** smoke baseline/runtime at 6000; packet-only isolation;
  then one-variable `packet_max_chars` trials at 3000 and 1500. Promote only a
  correctness-preserving budget with lower paired token use.
- **Comparability:** baseline and adaptive cells within a run archive the same
  source SHA and mutation; cross-harness token totals are reported separately,
  not treated as directly interchangeable prices.

Pre-spend corpus gate: 4/4 mutations fail their hidden grader and the exact
reference repair passes; source preparation is clean, detached, and SHA-pinned.

### Smoke attempt 1 — infrastructure reject

All four first adaptive model cells completed, but no hidden grader could start:
the CLI preserved a relative `.venv/bin/python` path and the grader subprocess
resolved it from the isolated workspace. No outcome rows were written, so this
attempt is excluded from correctness and token comparisons. A fake-harness
regression now proves the grader executable is absolutized before materializing
any workspace. Reruns use fresh result directories and the new evaluator SHA.

### Smoke attempt 2 — methodological reject

The first complete external matrix passed all eight hidden-grader cells, but it
is excluded from savings claims. The one-pair screens ranged from 17.5% savings
to 18.6% overhead under Codex and from 2.7% savings to 18.0% overhead under
Claude. Three harness defects made those token values non-comparable:

- retained workspaces lived below `/Users/sma/projects`, so Codex inherited the
  parent `AGENTS.md` and loaded unrelated workflow skills;
- the Python public verification command resolved `python` from an environment
  where it was unavailable, causing avoidable runtime probing even though the
  hidden grader passed the eventual repair; and
- Claude reported absolute `Read` paths, so owner-read accounting failed to
  match repository-relative owner paths.

The baseline contamination audit also found a second `tldrs` installation in
the evaluator virtualenv after the configured install directory was removed.
The corrected harness now strips every `PATH` entry exposing `tldrs` for
baseline and injected policies, expands a quoted `{python}` placeholder to the
pinned evaluator interpreter, normalizes Claude reads relative to the isolated
workspace, and uses operating-system temporary workspaces. Each correction has
a focused regression test. Attempt 3 starts from a new evaluator SHA and fresh
result directories.

### Balanced external confirmation — retain model-aware profile

After isolating Codex user skills with a temporary `HOME`, the 1500-character
runtime packet completed 32/32 balanced cells across the two pinned repositories
and two harnesses. Each task ran once with each condition first. Median paired
savings were 24.6% for Codex/Python, 15.4% for Codex/Go, 11.3% for
Claude/Python, and 13.0% for Claude/Go; all four arms reduced median latency and
retained 100% owner recall. The aggregate cross-model saving was 14.0%, so 1500
is retained as a conservative general default rather than a universal 20%
claim.

The public Python test paths exposed a stronger deterministic owner signal.
Mapping `test_encoding.py` and `test_signer.py` to matching non-test source
stems enabled a 750-character Codex profile. Its released-0.8.2,
counterbalanced four-repeat confirmation passed 16/16 cells with 41.8% median
paired savings (95% bootstrap interval +35.3% to +51.3%), 38.7% aggregate
savings, 40.1% lower median latency, and 100% owner recall. The 750 budget
regressed Claude/Python aggregate tokens by 3.7%, so it is promoted only for
Codex with an explicit test-file owner hint.

A bounded-work instruction removed task-tracker and Git ceremony and reduced
tool calls to 3–4, but raised median Codex/Go adaptive tokens from 19,401 to
23,335 (+20.3%). It was reverted under the primary-metric rule.

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

Target cleared and independently confirmed. The retained policy is a
deterministic, pre-model source packet plus a validated test execution contract.
It is now exposed through `tldrs packet` and the evaluator imports the production
implementation. Follow-up generalization experiments are recorded in
`interlab.ideas.md` and the final report.

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

## 2026-07-21 Validated Runtime Screen

The first runtime-contract implementation accidentally dereferenced the
virtualenv interpreter symlink to a bare uv Python. A regression test exposed
the mismatch; preserving the absolute symlink path restored the environment.
The corrected four-task screen passed 4/4 with zero agent-side tldrs calls and
45.0% median eligible savings:

| Task | Baseline tokens | Packet + runtime tokens | Savings |
|---|---:|---:|---:|
| Known-file control | 70,550 | 25,851 | 63.4% |
| Cross-file ignore | 70,153 | 36,476 | 48.0% |
| Diff boundary | 60,764 | 33,432 | 45.0% |
| Owner refactor | 76,892 | 51,284 | 33.3% |

Decision: promote to the full three-repeat corpus.

## 2026-07-21 Full Confirmation

The adaptive confirmation ran all 12 tasks for three repeats under GPT-5.6 Sol,
medium reasoning, Codex 0.144.6, and the same task corpus hash as the frozen
baseline. The paired analysis used 20,000 bootstrap resamples and the source-
owner routing gate.

| Metric | Result |
|---|---:|
| Correctness | 36/36 vs baseline 35/36 |
| Eligible median token savings | 32.1% |
| Eligible savings 95% interval | 25.2% to 41.1% |
| Negative-control median overhead | -20.6% |
| Median latency regression | -34.7% |
| Context-owner recall | 100%, 0/27 misses |
| Agent-side tldrs calls | 0 |

All five promotion gates pass. The gateway recovered the frozen baseline miss
on `refactor-callgraph-dedupe` repeat 3 while reducing that cell from 108,121 to
39,612 uncached tokens. Eligible aggregate tokens fell from 1,961,420 to
1,304,615; tool calls from 453 to 272; raw reads from 210 to 109.

Final decision: retain and ship. The complete methodology, comparability caveat,
dead ends, and next generalization experiments are in
`docs/research/2026-07-21-context-gateway-token-savings.md`.
