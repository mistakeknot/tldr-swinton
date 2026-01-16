# Token Savings Summary (tldr-bench)

Date: 2026-01-16

Scope: `track_dataset_context` on SWE-bench sample (task `dataset-ctx-001`).
Baseline: `tldr-bench/results/official_datasets_context_baselines.jsonl`
Variants: symbolkite, cassette (tldrs-vhs), coveragelens.

Command:

```
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/compare_results.py \
  --baseline tldr-bench/results/official_datasets_context_baselines.jsonl \
  --variants tldr-bench/results/official_datasets_context_symbolkite.jsonl \
             tldr-bench/results/official_datasets_context_cassette.jsonl \
             tldr-bench/results/official_datasets_context_coveragelens.jsonl
```

Output:

```
variant: tldr-bench/results/official_datasets_context_symbolkite.jsonl
tasks: 1
metric              baseline  variant  savings  savings_pct
context_tokens      3181      779      2402     75.5%
total_tokens_total  6388      1584     4804     75.2%

variant: tldr-bench/results/official_datasets_context_cassette.jsonl
tasks: 1
metric              baseline  variant  savings  savings_pct
context_tokens      3181      653      2528     79.5%
total_tokens_total  6388      1332     5056     79.1%

variant: tldr-bench/results/official_datasets_context_coveragelens.jsonl
tasks: 1
metric              baseline  variant  savings  savings_pct
context_tokens      3181      779      2402     75.5%
total_tokens_total  6388      1584     4804     75.2%
```
