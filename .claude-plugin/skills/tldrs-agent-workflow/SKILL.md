---
name: tldrs-agent-workflow
description: Token-efficient code reconnaissance using tldr-swinton. Use BEFORE opening files with Read tool to save 85%+ tokens.
---

# Tldrs Agent Workflow

Use this skill BEFORE opening files with Read tool.

## Core Flow

1. **Diff-first context** for recent changes:
```bash
tldrs diff-context --project . --budget 2000
```

2. **Semantic search** to find code by concept:
```bash
tldrs index .                      # Once per project
tldrs find "authentication logic"
```

3. **Symbol context** around an entry point:
```bash
tldrs context <entry> --project . --depth 2 --format ultracompact
```

4. **Structure discovery**:
```bash
tldrs structure src/
tldrs extract path/to/file.py
```

5. **Open full files only when editing**.

## Quick Reference

| Need | Command |
|------|---------|
| Recent changes | `tldrs diff-context --project . --budget 2000` |
| Find by concept | `tldrs find "auth logic"` |
| Symbol context | `tldrs context func --project . --depth 2 --format ultracompact` |
| Structure | `tldrs structure src/` |
| Full reference | `tldrs quickstart` |

## When NOT to Use

- File < 200 lines (just read it)
- You know exactly what to edit
- You need full implementation code (read the file)

## Multi-Turn Optimization

Use session IDs to skip unchanged code (~60% savings):
```bash
tldrs diff-context --project . --session-id my-session
```

## Common Mistakes

- Opening full files before running diff/context/structure
- Skipping `--budget` (causes token blowups)
- Forgetting `--lang` for non-Python repos

## Entry Syntax

- File-qualified: `file.py:func`, `Class.method`
- If ambiguous, re-run with qualified entry

## Token Budgets

| Codebase | Budget |
|----------|--------|
| Small | 1500 |
| Medium | 2000 |
| Large | 3000 |
