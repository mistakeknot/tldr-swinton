---
name: tldrs-agent-workflow
description: Token-efficient code reconnaissance. Use BEFORE Read tool. Saves 48-85% tokens depending on command (diff-context 48%, semantic search 85%, multi-turn 60%+).
---

# tldrs Agent Workflow

**Rule**: Run tldrs BEFORE using Read tool on code files.

## Quick Decision

| Task | Command | Then |
|------|---------|------|
| Start any coding task | `tldrs diff-context --project . --budget 2000` | Review changed symbols |
| Find code by concept | `tldrs find "auth logic"` | Read top results |
| Understand a function | `tldrs context func --project . --depth 2` | Read if editing |
| Explore structure | `tldrs structure src/` | Navigate to relevant files |

## When to Skip tldrs

- File < 200 lines → just Read it
- You know exactly what to edit → Read and Edit directly
- Simple config files → Read directly

## Core Commands

### 1. Diff-Context (Start Here)

```bash
tldrs diff-context --project . --budget 2000
```

**Output format:**
```
P0=src/auth.py P1=src/users.py

P0:login def login(user, password)  [contains_diff]
P0:verify def verify(token)  [caller_of_diff]
P1:create_user def create_user(data)  [contains_diff]
```

**What it tells you:** Changed symbols (P0, P1...), their signatures, and relationship to diff.

### 2. Semantic Search

```bash
# First time only - build index
tldrs index .

# Search by concept
tldrs find "authentication logic"
```

**Output format:**
```
 1. [0.82] verify_token (function)
      def verify_token(token: str) -> User
      src/auth/tokens.py:42

 2. [0.79] login (function)
      def login(username: str, password: str) -> Session
      src/auth/login.py:15
```

**What it tells you:** Ranked results with similarity score, signature, location.

### 3. Symbol Context

```bash
tldrs context handle_request --project . --depth 2 --format ultracompact
```

**Output format:**
```
handle_request(request) -> Response
  calls: validate_input, process_data, format_response
  called_by: main, api_handler
  types: Request, Response
```

**What it tells you:** Call graph, callers, and related types.

## Workflow Examples

### Bug Fix

```bash
# 1. See what changed
tldrs diff-context --project . --budget 2000

# 2. Find error handling
tldrs find "error handling"

# 3. Get context for the buggy function
tldrs context buggy_func --project . --depth 2

# 4. NOW read the file to fix it
# Use Read tool on src/module.py
```

### Feature Implementation

```bash
# 1. Find similar features
tldrs find "user registration"

# 2. Understand the pattern
tldrs context register_user --project . --depth 2

# 3. See structure of target directory
tldrs structure src/features/

# 4. Read and implement
```

### Code Review

```bash
# See all changes with context
tldrs diff-context --project . --budget 3000 --base main
```

## Error Handling

| Error | Cause | Fix |
|-------|-------|-----|
| `No index found` | Semantic search needs index | Run `tldrs index .` |
| `Ambiguous entry` | Multiple symbols match | Use `file.py:func` syntax |
| `No changes detected` | Clean working tree | Specify `--base` and `--head` |
| `Command not found` | tldrs not installed | See install below |

## Installation Check

```bash
# Verify tldrs works
tldrs --version

# Check if index exists (for semantic search)
ls -la .tldrs/index 2>/dev/null || echo "No index - run: tldrs index ."
```

## Token Budgets

| Codebase | Budget |
|----------|--------|
| Small (<50 files) | 1500 |
| Medium (50-200) | 2000 |
| Large (200+) | 3000 |

## Multi-Turn Optimization

Skip unchanged symbols across turns (~60% savings):

```bash
# First turn
tldrs diff-context --project . --session-id task-123

# Later turns - unchanged symbols omitted
tldrs diff-context --project . --session-id task-123
```

## Language Support

Default is Python. For other languages:

```bash
tldrs structure src/ --lang typescript
tldrs context main --project . --lang rust
```

Supported: `python`, `typescript`, `javascript`, `rust`, `go`, `java`, `c`, `cpp`

## Common Mistakes

1. **Reading files before tldrs** → Run diff-context first
2. **No budget on large codebases** → Always use `--budget`
3. **Searching without index** → Run `tldrs index .` once
4. **Ambiguous symbol names** → Use `file.py:symbol` format
