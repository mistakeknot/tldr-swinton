# Disabled Variants

These variants are disabled because they cannot demonstrate value in static token-counting benchmarks.

## Why Disabled

| Variant | Issue | Required Benchmark Type |
|---------|-------|------------------------|
| `attention_pruning` | Returns symbolkite unchanged without usage history | Multi-session learning benchmark |
| `context_delegation` | Returns retrieval PLAN, not context | Agent execution benchmark |
| `coherence_verify` | ADDS tokens for error prevention | Error detection rate benchmark |

## Re-enabling

To re-enable a variant:

1. Create the appropriate benchmark type (see below)
2. Move the variant back to `variants/`
3. Add to `variants/__init__.py` VARIANTS dict
4. Add benchmark tasks to appropriate YAML

## Required Benchmark Types

### attention_pruning
Needs a benchmark that:
1. Runs multiple sessions to build usage history
2. Records which symbols agents actually use
3. Compares pruned vs unpruned context AFTER learning

### context_delegation
Needs a benchmark that:
1. Runs an agent end-to-end with delegation plan
2. Tracks total tokens across all retrieval calls
3. Compares to agent running with upfront context

### coherence_verify
Needs a benchmark that:
1. Creates test cases with intentional cross-file bugs
2. Measures detection rate (true positives)
3. Measures false positive rate
4. Does NOT measure token savings (this adds tokens by design)
