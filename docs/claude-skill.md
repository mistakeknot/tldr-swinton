---
name: tldrs-agent-workflow
description: Token-efficient code reconnaissance with tldr-swinton. Use when an agent needs diff context, symbol call-graph context, structure discovery, or semantic search before opening full files.
---

# tldrs Agent Workflow (Claude Skill)

## Goal

Use tldrs to fetch only the context needed for a task and keep token usage low.

## Decision Tree

1) Working on recent changes:
```
tldrs diff-context --project . --budget 2000
```

2) Need call-graph context for a symbol:
```
tldrs context <entry> --project . --depth 2 --budget 2000 --format ultracompact
```

3) Need structure/discovery:
```
tldrs structure src/ --lang typescript
tldrs extract path/to/file.ts
```

4) Need semantic search:
```
tldrs index .
tldrs find "authentication logic"
```

## Entry Syntax

- Prefer file-qualified entries: `file.py:func`, `Class.method`, `module:func`
- If ambiguous, tldrs returns candidates; re-run with `file.py:func`

## Output + Budgets

- Always use a budget: `--budget 2000`
- For tooling, use JSON:
```
tldrs context <entry> --format json
```
- ContextPack JSON includes `etag` per slice; use it for conditional fetch (UNCHANGED)

## VHS (Large Output Refs)

```
tldrs context main --project . --output vhs
tldrs context main --project . --include vhs://<hash>
```
