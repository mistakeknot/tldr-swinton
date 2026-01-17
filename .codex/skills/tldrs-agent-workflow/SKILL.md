---
name: tldrs-agent-workflow
description: Token-efficient code reconnaissance using tldr-swinton. Use when an agent needs code context (diffs, symbol call graphs, structure, or semantic search) before opening full files. Includes diff-context, context packs, budgets, VHS refs, and JSON/etag handling.
---

# Tldrs Agent Workflow

## Overview

Use tldrs to minimize tokens and keep accuracy by fetching only the context needed for a task. Prefer diff-first and symbol-level context before opening full files.

## Workflow Decision Tree

1) Working on recent changes → diff-first context:
```
tldrs diff-context --project . --budget 2000
```

2) Need call-graph context around a symbol → symbol context:
```
tldrs context <entry> --project . --depth 2 --budget 2000 --format ultracompact
```

3) Need structure or discovery:
```
tldrs structure src/ --lang typescript
tldrs extract path/to/file.ts
```

4) Need semantic search:
```
tldrs index .
tldrs find "authentication logic"
```

5) Deep analysis helpers (optional):
```
tldrs slice <file> <func> <line>
tldrs cfg <file> <function>
tldrs dfg <file> <function>
```

## Entry Syntax

- Prefer file-qualified entries when possible: `file.py:func`, `Class.method`, `module:func`.
- If ambiguous, tldrs returns candidates; re-run with `file.py:func`.

## Output + Budgets

- Always use a budget for context: `--budget 2000`.
- For tooling, request JSON:
```
tldrs context <entry> --format json
```
- ContextPack JSON includes `etag` per slice; if your tool supports it, use `etag` for conditional fetch (`UNCHANGED`).

## VHS (Large Output Refs)

Store large outputs as refs to avoid token blowups:
```
tldrs context main --project . --output vhs
tldrs context main --project . --include vhs://<hash>
```
