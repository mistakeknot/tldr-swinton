# Context Optimization Eval Plan

Date: 2026-01-13

## Goal
Measure real token savings and workflow quality for the four roadmap phases (DiffLens, SymbolKite, Cassette, CoverageLens). The eval should quantify token reduction without hurting task success, and identify which prototypes deliver practical savings.

## Scope
Features covered:
- DiffLens (diff-first context packs)
- SymbolKite (symbol slicing + ETag delta retrieval)
- Cassette integration (content-addressed references)
- CoverageLens (coverage-guided context selection)

Outputs:
- A/B results for each feature and combined variants
- Token/latency/quality metrics per task
- Pass/fail gates per phase
- Lessons learned per phase

## Success Metrics
Core metrics per run:
- Prompt tokens (input-only)
- Total context tokens over full task
- Tool calls / round trips
- Time to first correct patch
- Task success rate
- Accuracy coverage (did context include lines ultimately modified?)

Feature-specific metrics:
- DiffLens: diff-hit rate, budget adherence, coverage of modified lines
- SymbolKite: ETag hit rate, bytes returned on unchanged
- Cassette: % outputs stored as refs, % refs needing inline expansion
- CoverageLens: coverage-hit rate, rank of modified functions

## Task Suite
10–15 tasks spanning:
- Bug fix, refactor, feature tweak
- Small diffs vs multi-file changes
- Dynamic imports or weak call graphs
- Large docstring files
- At least 2 failing-test tasks for CoverageLens

Each task must have:
- A fixed “gold” outcome (expected patch or line edits)
- Known diff ranges
- Ground-truth touched lines for hit-rate scoring

## Baselines and Variants
Baselines:
- A: Full file reads for files touched + nearby files
- B: Current tldrs outputs (`tldrs context`, `tldrs extract`, `tldrs structure`)
- C: Minimal grep+read (targeted file reads)

Variants:
- D: DiffLens context pack
- E: SymbolKite slice for changed symbols
- F: Cassette refs with inline fallback
- G: CoverageLens ranked context for failing tests

Combined:
- H: DiffLens + SymbolKite + Cassette
- I: DiffLens + CoverageLens

## A/B Protocol
- Same prompt template across all variants
- Same max budgets (e.g., 800 / 1600 / 3200)
- One retry allowed; count total tokens across retries
- Log tool calls, latency, success, and token usage
- Manual pilot for 3–5 tasks allowed to calibrate budgets

## Instrumentation
Store JSONL logs under `evals/results/` with:
- task_id, variant_id, budget, prompt_tokens, completion_tokens
- tool_calls, elapsed_ms, success, retries
- context_bytes, context_tokens_estimate
- diff_hit_rate, coverage_hit_rate
- symbol_etag_hit, cassette_ref_ratio
- notes

Token accounting:
- Use a stable tokenizer (log model name used)
- Store bytes and token estimates for each context output

## Phase Gates
Phase 0 (pilot):
- >50% token reduction
- ≥80% diff-hit rate

Phase 1 (DiffLens):
- Median ≥60% token reduction
- ≥90% diff-hit rate
- No >10% success-rate regression

Phase 2 (SymbolKite):
- ≥60% repeat-query “UNCHANGED”
- Meaningful byte reduction on unchanged reads
- No increase in retries

Phase 3 (Cassette):
- ≥40% outputs stored as refs
- ≤10% refs require inline expansion

Phase 4 (CoverageLens):
- ≥50% token reduction vs static context
- ≥80% fixes include high-coverage lines

If a phase fails its gate, iterate on ranking/budgeting before advancing.

## Reporting
- Summaries in `evals/results/summary-<date>.md`
- Keep raw logs for reproducibility
- Record “lessons learned” per phase

