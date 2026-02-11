---
name: tldrs-find-code
description: "Use when searching for code by concept, pattern, or text, or when asked 'where is X handled/defined/implemented'. Prefer over grep or Read-and-scan. Semantic search finds by meaning. Structural search finds by code shape."
allowed-tools:
  - Bash
---

# Find Code by Meaning or Structure

Use instead of grep, Grep tool, or Read-and-scan when looking for code.

## Quick Decision

| Need | Command |
|------|---------|
| Find by concept/meaning | `tldrs find "query"` |
| Find by code shape | `tldrs structural 'pattern' --lang python` |
| Find exact text | `tldrs search "regex"` |

## Semantic Search (by concept)

Requires one-time index: `tldrs index .`

```bash
tldrs find "authentication logic"
tldrs find "error handling in payment"
```

Results ranked by similarity:
```
 1. [0.82] verify_token (function)
      def verify_token(token: str) -> User
      src/auth/tokens.py:42
```

## Structural Search (by code shape)

Find code patterns using ast-grep tree-sitter matching.

**CRITICAL: Always single-quote the pattern. NEVER double-quote. `$$$` will be expanded by the shell as PID.**

```bash
# Functions returning None
tldrs structural 'def $FUNC($$$ARGS): return None' --lang python

# All method calls on an object
tldrs structural '$OBJ.$METHOD($$$ARGS)' --lang python

# All if statements
tldrs structural 'if $COND: $$$BODY' --lang python

# Go error handling
tldrs structural 'if err != nil { $$$BODY }' --lang go
```

Pattern syntax:
- `$VAR` matches any single AST node
- `$$$ARGS` matches zero or more nodes (varargs)

Requires: `pip install 'tldr-swinton[structural]'`

## Regex Search (exact text)

```bash
tldrs search "TODO|FIXME" src/
tldrs search "def authenticate" src/ --ext .py
```

## Next Step

After finding results, use `tldrs context <symbol> --project .` to understand the matched function, or Read the file if you need to edit it.

## Common Errors

- **"No semantic index found"**: Run `tldrs index .` first (takes 30-60s for medium repos).
- **"ast-grep-py is required"**: Install with `pip install 'tldr-swinton[structural]'`.
- **Empty structural results**: Check language flag matches file extensions. Try a simpler pattern first.
- **Garbled structural pattern**: You likely double-quoted the pattern. Always use single quotes.

## When to Skip

- You know the exact file and line: just Read it
- Searching for a filename: use Glob tool instead
