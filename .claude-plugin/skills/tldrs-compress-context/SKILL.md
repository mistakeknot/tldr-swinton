---
name: tldrs-compress-context
description: "Use when context output is too large or in multi-turn sessions. Two-stage compression saves 35-73% tokens. Session IDs skip unchanged symbols across turns for ~60% additional savings."
---

# Compress and Cache Context

Use when dealing with large outputs or repeated context fetches.

## Multi-Turn Sessions (Delta Mode)

Skip unchanged symbols across conversation turns (~60% savings):

```bash
# First turn: full output, records what was sent
tldrs diff-context --project . --session-id task-name --budget 2000

# Later turns: unchanged symbols omitted automatically
tldrs diff-context --project . --session-id task-name --budget 2000
```

Delta mode is most valuable for iterative Q&A on unchanged code.

## Two-Stage Compression

For large diffs, compress with knapsack-based block pruning (35-73% savings):

```bash
tldrs diff-context --project . --budget 1500 --compress two-stage
```

Keeps: diff-containing blocks, adjacent context, control-flow blocks.
Drops: unrelated code sections within changed files.

## Output Caps

Hard limits when budget alone isn't enough:

```bash
tldrs context main --project . --max-lines 50
tldrs diff-context --project . --max-bytes 4096
```

When truncated, output shows: `[TRUNCATED: output exceeded --max-lines=50]`

## VHS Refs (Store Large Outputs)

Store large output by content hash and reference later:

```bash
tldrs context main --project . --output vhs
# Returns: vhs://abc123 + summary

# Later, include previous context:
tldrs context main --project . --include vhs://abc123
```

## When to Use What

| Situation | Technique |
|-----------|-----------|
| Multi-turn conversation | `--session-id task-name` |
| Single large diff | `--compress two-stage --budget 1500` |
| Need hard output limit | `--max-lines N` or `--max-bytes N` |
| Storing context for later | `--output vhs` |
