---
name: tldrs-agent-workflow
description: Use when an agent needs token-efficient code reconnaissance (diffs, call graphs, structure discovery, semantic search, change impact) before opening full files.
---

# Tldrs Agent Workflow

Use this skill BEFORE opening files with Read tool.

## Core Flow (Fast Path)

1) Diff-first context for recent changes:
```
tldrs diff-context --project . --budget 2000
```

2) Symbol-level context around an entry:
```
tldrs context <entry> --project . --depth 2 --budget 2000 --format ultracompact
```

3) Structure or discovery:
```
tldrs structure src/ --lang typescript
tldrs extract path/to/file.ts
```

4) Semantic search:
```
tldrs index .
tldrs find "authentication logic"
```

## Quick Reference

| Need | Command |
| --- | --- |
| Recent changes | `tldrs diff-context --project . --budget 2000` |
| Symbol context | `tldrs context <entry> --project . --depth 2 --budget 2000 --format ultracompact` |
| Structure | `tldrs structure src/ --lang typescript` |
| Semantic search | `tldrs index .` then `tldrs find "authentication logic"` |
| Change impact | `tldrs change-impact --git --git-base HEAD~1` |

## Entry Syntax

- Prefer file-qualified entries when possible: `file.py:func`, `Class.method`, `module:func`.
- If ambiguous, tldrs returns candidates; re-run with `file.py:func`.

## Language Flags

- Use `--lang` for non-Python repos.
- Example: `tldrs structure src/ --lang typescript`
- Example: `tldrs context src/main.rs:run --lang rust`

## Output + Budgets

- Always use a budget for context: `--budget 2000`.
- For tooling, request JSON:
```
tldrs context <entry> --format json
```
- ContextPack JSON includes `etag` per slice; if your tool supports it, use `etag` for conditional fetch (`UNCHANGED`).

## Advanced / Optional

### Deep Analysis Helpers

```
tldrs slice <file> <func> <line>
tldrs cfg <file> <function>
tldrs dfg <file> <function>
```

### DiffLens Compression

- Two-stage:
  - `tldrs diff-context --project . --budget 1500 --compress two-stage`
- Chunk-summary:
  - `tldrs diff-context --project . --budget 1500 --compress chunk-summary`

### Change Impact / Test Selection

- Git diff to affected tests:
  - `tldrs change-impact --git --git-base HEAD~1`
- Session-modified files (run tests):
  - `tldrs change-impact --session --run`

### Call Graph Helpers

- Forward calls:
  - `tldrs calls . --lang python`
- Reverse (callers):
  - `tldrs impact authenticate --depth 3 --lang python`
- Importers:
  - `tldrs importers tldr_swinton.api --lang python`

### VHS (Large Output Refs)

Store large outputs as refs to avoid token blowups:
```
tldrs context main --project . --output vhs
tldrs context main --project . --include vhs://<hash>
```

## Typical Agent Flow

1) `tldrs diff-context --project . --budget 2000`
2) `tldrs context <entry> --project . --depth 2 --budget 2000 --format ultracompact`
3) `tldrs extract path/to/file.py`
4) Open the full file only if you must edit it

## Common Mistakes

- Opening full files before running diff/context/structure commands
- Skipping `--budget` and getting oversized outputs
- Forgetting `--lang` in non-Python repos
- Not re-running with file-qualified entries after ambiguous results

## Red Flags

- "I'll just open the file first"
- "Budget does not matter here"

## Rationalizations vs Reality

| Excuse | Reality |
| --- | --- |
| "Opening full files is faster" | Diff/context is faster and cheaper for most tasks |
| "Budgets are optional" | Budgets prevent token blowups and keep outputs usable |
