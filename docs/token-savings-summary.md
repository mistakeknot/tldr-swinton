# Token Savings Summary (tldr-bench)

Date: 2026-01-24

## Official Datasets Context Benchmark

14 tasks spanning small (<100 LOC) to extra-large (1000+ LOC) files.
Entry points are functions/methods (not classes) to exercise symbolkite's call graph traversal.

**Baseline:** Full file content
**Variant:** Symbolkite (depth 1-2, following call graph)

### Aggregate Results

```
variant: symbolkite
tasks: 14
metric              baseline  variant  savings  savings_pct
context_tokens      84115     6242     77873    92.6%
total_tokens_total  168594    12848    155746   92.4%
```

### Per-Task Breakdown

| Task | File Size | Baseline | Symbolkite | Savings |
|------|-----------|----------|------------|---------|
| swebench-ctx-small-001 | <100 LOC | 135 | 374 | **-177%** (worse) |
| swebench-ctx-small-002 | <100 LOC | 206 | 385 | **-87%** (worse) |
| swebench-ctx-medium-001 | 100-500 | 814 | 190 | 76.7% |
| swebench-ctx-medium-002 | 100-500 | 1348 | 377 | 72.0% |
| swebench-ctx-medium-003 | 100-500 | 1824 | 127 | 93.0% |
| swebench-ctx-medium-004 | 100-500 | 2322 | 59 | 97.5% |
| swebench-ctx-large-001 | 500-1000 | 6395 | 2255 | 64.7% |
| swebench-ctx-large-002 | 500-1000 | 7380 | 110 | 98.5% |
| swebench-ctx-large-003 | 500-1000 | 5163 | 598 | 88.4% |
| swebench-ctx-xlarge-001 | 1000+ | 7603 | 182 | 97.6% |
| swebench-ctx-xlarge-002 | 1000+ | 11078 | 67 | 99.4% |
| swebench-ctx-xlarge-003 | 1000+ | 25849 | 155 | 99.4% |
| swebench-ctx-compact-001 | 500-1000 | 6395 | 1261 | 80.3% |
| swebench-ctx-compact-002 | 1000+ | 7603 | 102 | 98.7% |

### Key Insights

1. **Small files (<100 LOC):** Symbolkite returns MORE tokens than baseline because
   it follows the call graph and includes dependencies from other files. For a small
   well-factored file, the baseline (full file) is often more efficient.

2. **Medium-to-XL files:** Symbolkite saves 65-99% because the target function is
   a small part of a large file.

3. **Trade-off:** Symbolkite trades context completeness for efficiency. It gives
   you the call graph around a symbol, not the whole file context.

### When to Use What

| Scenario | Recommendation |
|----------|----------------|
| Small files (<100 LOC) | Use baseline (full file) |
| Large files, focused edit | Use symbolkite |
| Understanding call flow | Use symbolkite with depth 2+ |
| Full file context needed | Use baseline |

### Reproduce

```bash
# Run benchmarks
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/run_bench.py \
  --tasks official_datasets_context --variant baselines \
  --print-results --results-file tldr-bench/results/official_datasets_ctx_baselines.jsonl

PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/run_bench.py \
  --tasks official_datasets_context --variant symbolkite \
  --print-results --results-file tldr-bench/results/official_datasets_ctx_symbolkite.jsonl

# Compare
PYTHONPATH=tldr-bench uv run python tldr-bench/scripts/compare_results.py \
  --baseline tldr-bench/results/official_datasets_ctx_baselines.jsonl \
  --variants tldr-bench/results/official_datasets_ctx_symbolkite.jsonl
```

---

## Historical: Single-Task Results (2026-01-16)

Previous benchmark on a single task (`dataset-ctx-001`):

```
variant: symbolkite (1 task)
context_tokens      3181      779      2402     75.5%
total_tokens_total  6388      1584     4804     75.2%
```

This was replaced by the 14-task comprehensive benchmark above.
