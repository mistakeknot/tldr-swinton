---
title: "External Context Gateway Validation: Python, Go, Codex, and Claude"
date: 2026-07-22
status: confirmed-model-specific
---

# External Context Gateway Validation

## Result

The Context Gateway preserves coding correctness across pinned external Python
and Go tasks under both Codex and Claude Code. The balanced 1500-character
matrix completed 32/32 hidden-grader cells successfully. It saved 14.0% of
uncached tokens in aggregate across all four repository/harness arms, but no
single cross-model budget cleared the pre-registered 20% median threshold in
every arm.

A follow-up, same-SHA Codex/Python confirmation used the public test-file path
as a deterministic source-owner hint and capped source excerpts at 750
characters. It passed 8/8 cells, saved 22.5% at the median paired cell and 26.9%
in aggregate, reduced median latency by 46.4%, and retained 100% owner recall.
This is the promoted model-aware profile. Generic and Claude use 1500.

## Frozen inputs

| Corpus | Language | Source SHA | Tasks |
|---|---|---|---:|
| `pallets/itsdangerous` | Python | `672971d66a2ef9f85151e53283113f33d642dabd` | 2 |
| `google/go-cmp` | Go | `b133f1f1932e48f466f597a3346ce6f5a49a0dc1` | 2 |

The harnesses were Codex CLI 0.144.6 with `gpt-5.6-sol` and Claude Code 2.1.215
with `sonnet` resolving to `claude-sonnet-5`. Every task was mutated from the
pinned source, graded by an external hidden grader, and run once with each
condition first across two repeats. Baseline and adaptive workspaces were
history-free and materialized from the same source SHA.

## Balanced 1500-character matrix

| Harness / corpus | Correct | Median paired savings | Aggregate savings | Median latency change | Owner recall |
|---|---:|---:|---:|---:|---:|
| Codex / Python | 8/8 | 24.6% | 19.8% | -48.1% | 100% |
| Codex / Go | 8/8 | 15.4% | 6.8% | -11.1% | 100% |
| Claude / Python | 8/8 | 11.3% | 10.5% | -21.9% | 100% |
| Claude / Go | 8/8 | 13.0% | 13.9% | -29.5% | 100% |

These results support a conservative 1500-character general default, not a
universal 20% savings claim. They also show why prompt caching cannot substitute
for counterbalancing: one-task adaptive-first screens made the second condition
look artificially cheap when its static prompt prefix received more cache hits.

## Promoted Codex owner-hint profile

The public verification command named `test_encoding.py` or `test_signer.py`.
The ranker now strips conventional `test_` / `_test` affixes, promotes a
matching non-test source stem, and exposes a Codex profile that uses 750 source
characters only when that explicit owner signal exists.

| Metric | Confirmed result |
|---|---:|
| Hidden-grader correctness | 8/8 baseline, 8/8 adaptive |
| Median paired uncached-token savings | 22.5% |
| Aggregate uncached-token savings | 26.9% |
| Median latency change | -46.4% |
| Context-owner recall | 100% |
| Agent-side tldrs calls | 0 |

The four paired savings were +54.7%, +39.8%, -16.9%, and +5.2%. The variance is
material; the aggregate and median pass are therefore reported alongside the
individual cells rather than hidden behind one average.

## Harness defects found and fixed

1. Relative grader interpreters resolved from the isolated workspace and could
   not start. The evaluator now absolutizes the virtualenv entrypoint without
   dereferencing it.
2. Retained workspaces inherited a parent `AGENTS.md`. Paid runs now use
   operating-system temporary workspaces.
3. A second `tldrs` executable remained visible through another `PATH` entry.
   Baseline and injected policies now strip every directory exposing it.
4. Claude reports absolute Read paths. The parser now normalizes paths relative
   to the workspace before owner-recall accounting.
5. Python's public test command used an unavailable generic `python`. Task files
   now expand a quoted `{python}` placeholder to the pinned interpreter.
6. Codex user skills are discovered from `$HOME/.agents/skills` even with
   `--ignore-user-config`. Each Codex cell now receives a fresh temporary HOME
   while authenticated state remains in `CODEX_HOME`.
7. Single-task screens always ran adaptive first and exposed cache-order bias.
   Confirmation uses two tasks and two repeats so each condition runs first once
   per task.

## Rejected mutations

- Packet-only at 6000 characters preserved correctness but was worse than the
  validated-runtime packet in three of four smoke arms.
- The nominal 3000-character step was skipped after deterministic rendering
  showed Python was byte-identical to 6000 and Go changed by only 337 chars.
- A rule deferring task trackers and Git ceremony reduced tool turns but raised
  median Codex/Go adaptive tokens by 20.3%; it was reverted.
- A 750-character Python packet regressed Claude aggregate tokens by 3.7%, so
  the tight budget is Codex-specific rather than the general default.

## Product decision

`tldrs packet` now defaults to a 1500-character generic profile. Harnesses can
request `--harness-profile codex`; when the known-good command names a test
file, that profile uses the confirmed 750-character owner-routed budget.
Explicit `--max-chars` always wins. The architecture remains middleware-first:
rank before model invocation, inject a known-good execution contract, and leave
full-source reading and hidden correctness verification intact.
