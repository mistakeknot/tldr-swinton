---
name: tldrs-agent-workflow
description: Token-efficient code reconnaissance. Use BEFORE Read tool. Saves 48-85% tokens depending on command (diff-context 48-73%, semantic search 85%, structural search 60%, multi-turn 60%+).
---

# tldrs Agent Workflow

**Rule**: Run tldrs BEFORE using Read tool on code files.

## Quick Decision

| Task | Command | Then |
|------|---------|------|
| Start any coding task | `tldrs diff-context --project . --budget 2000` | Review changed symbols |
| Find code by concept | `tldrs find "auth logic"` | Read top results |
| Find code by structure | `tldrs structural 'pattern' --lang python` | Read matches |
| Understand a function | `tldrs context func --project . --depth 2 --budget 2000` | Read if editing |
| Explore structure | `tldrs structure src/` | Navigate to relevant files |

## When to Skip tldrs

- You are editing a single file under 200 lines AND you already know which file it is
- Simple config files: Read directly

## Core Commands

### 1. Diff-Context (Start Here)

```bash
tldrs diff-context --project . --budget 2000
```

With compression for large diffs (35-73% savings):
```bash
tldrs diff-context --project . --budget 1500 --compress two-stage
```

With output cap:
```bash
tldrs diff-context --project . --budget 2000 --max-lines 50
```

**Output format:**
```
P0=src/auth.py P1=src/users.py

P0:login def login(user, password)  [contains_diff]
P0:verify def verify(token)  [caller_of_diff]
```

### 2. Semantic Search

```bash
# First time only
tldrs index .

# Search by concept
tldrs find "authentication logic"
```

### 3. Structural Search (ast-grep)

Find code by shape using tree-sitter pattern matching.

**CRITICAL: Always single-quote patterns. NEVER double-quote. `$$$` will be expanded by the shell as PID.**

```bash
# Functions returning None
tldrs structural 'def $FUNC($$$ARGS): return None' --lang python

# All method calls
tldrs structural '$OBJ.$METHOD($$$ARGS)' --lang python

# Go error handling
tldrs structural 'if err != nil { $$$BODY }' --lang go
```

Pattern syntax: `$VAR` matches single node, `$$$ARGS` matches varargs.

Requires: `pip install 'tldr-swinton[structural]'`

### 4. Symbol Context

```bash
tldrs context handle_request --project . --depth 2 --format ultracompact --budget 2000
```

If ambiguous, tldrs returns candidates:
```
Ambiguous entry 'handle': found in 3 files
  src/api.py:handle_request
  src/ws.py:handle_message
```
Re-run with qualified name: `tldrs context src/api.py:handle_request --project .`

### 5. Multi-Turn Optimization

Skip unchanged symbols across turns (~60% savings):

```bash
tldrs diff-context --project . --session-id task-123 --budget 2000
```

Use a descriptive session ID per task. Reuse the same ID for all turns within one task.

## Token Budgets

| Codebase | Budget |
|----------|--------|
| Small (<50 files) | 1500 |
| Medium (50-200) | 2000 |
| Large (200+) | 3000 |

## Output Caps

Hard limits when budget alone isn't enough:

```bash
tldrs context main --project . --max-lines 50
tldrs diff-context --project . --max-bytes 4096
```

## Language Support

Default is Python. For other languages:

```bash
tldrs diff-context --project . --lang typescript
tldrs context main --project . --lang rust
```

Supported: python, typescript, javascript, rust, go, java, c, cpp, ruby, php, kotlin, swift, csharp, scala, lua, elixir

## Common Mistakes

1. **Reading files before tldrs**: Run diff-context first
2. **No budget on large codebases**: Always use `--budget`
3. **Double-quoting structural patterns**: Use single quotes for `$VAR` patterns — `$$$` expands to PID in double quotes
4. **Searching without index**: Run `tldrs index .` once for semantic search
5. **Ambiguous symbol names**: Use `file.py:symbol` format
6. **No output cap on large repos**: Add `--max-lines 50` or `--max-bytes 4096`

## Common Errors

- **"No git repository"**: diff-context requires a git repo. Use `tldrs structure` instead.
- **"No semantic index found"**: Run `tldrs index .` first (takes 30-60s).
- **"Ambiguous entry"**: Multiple symbols match. Use `file.py:symbol` format.
- **"ast-grep-py is required"**: Install with `pip install 'tldr-swinton[structural]'`.
- **Garbled structural pattern**: You likely double-quoted it. Always use single quotes.
