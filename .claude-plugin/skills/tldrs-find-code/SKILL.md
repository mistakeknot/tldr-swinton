---
name: tldrs-find-code
description: "Use when searching for code by concept, pattern, or text, or when asked 'where is X handled/defined/implemented'. Prefer over grep or Read-and-scan. Semantic search finds by meaning. Structural search finds by code shape."
allowed-tools:
  - Bash
---

# Find Code by Meaning or Structure

Use instead of Grep tool or Read-and-scan when looking for code.

## Decision Tree

### What kind of search?

**Know the concept, not the name:**
```bash
tldrs find "authentication logic"
tldrs find "error handling in payment"
```
Requires one-time index: `tldrs index .`

**Know the code shape (pattern matching):**
```bash
# CRITICAL: Always single-quote the pattern. NEVER double-quote.
tldrs structural 'def $FUNC($$$ARGS): return None' --lang python
tldrs structural '$OBJ.$METHOD($$$ARGS)' --lang python
tldrs structural 'if err != nil { $$$BODY }' --lang go
```
Pattern syntax: `$VAR` = any single AST node, `$$$ARGS` = zero or more nodes.

**Know the exact text:**
```bash
tldrs search "TODO|FIXME" src/
tldrs search "def authenticate" src/ --ext .py
```

## Rules

- Always try `tldrs find` before Grep for code files
- Use structural search for pattern-matching (all functions returning None, all error handlers, etc.)

## Next Step

After finding results, use `tldrs context <symbol> --project . --preset compact` to understand the matched function.

## When to Skip

- You know the exact file and line — just Read it
- Searching for a filename — use Glob tool instead
