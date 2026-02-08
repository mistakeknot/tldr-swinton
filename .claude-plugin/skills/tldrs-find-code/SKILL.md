---
name: tldrs-find-code
description: "Use when searching for code by concept or structural pattern instead of grep/Read. Semantic search saves 60-85% tokens. Structural search finds code by shape (all if-statements, returns, method calls)."
---

# Find Code by Meaning or Structure

Use instead of grep, Grep tool, or Read-and-scan when looking for code.

## Decision Table

| Need | Command |
|------|---------|
| Find by concept/meaning | `tldrs find "query"` |
| Find by code shape | `tldrs structural 'pattern'` |
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

**CRITICAL: Always single-quote the pattern to prevent shell expansion of `$` meta-variables.**

```bash
# Functions returning None
tldrs structural 'def $FUNC($$$ARGS): $$$BODY return None' --lang python

# All method calls on an object
tldrs structural '$OBJ.$METHOD($$$ARGS)' --lang python

# All if statements
tldrs structural 'if $COND: $$$BODY' --lang python

# Go function definitions
tldrs structural 'func $FUNC($$$ARGS) $$$RET { $$$BODY }' --lang go
```

Pattern syntax:
- `$VAR` matches any single AST node
- `$$$ARGS` matches zero or more nodes (varargs)

**NEVER double-quote patterns. `$$$` will be expanded by the shell.**

Requires: `pip install 'tldr-swinton[structural]'`

## Regex Search (exact text)

```bash
tldrs search "TODO|FIXME" src/
tldrs search "def authenticate" src/ --ext .py
```

## When to Skip

- You know the exact file and line: just Read it
- Searching for a filename: use Glob tool instead
