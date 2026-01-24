# tldrs Quick Reference

**Rule**: Run tldrs BEFORE using Read tool on code files. Saves 48-85% tokens (semantic search ~85%, diff-context ~48%, multi-turn 60%+).

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

**Output:**
```
P0=src/auth.py P1=src/users.py

P0:login def login(user, password)  [contains_diff]
P0:verify def verify(token)  [caller_of_diff]
P1:create_user def create_user(data)  [contains_diff]
```

### 2. Semantic Search

```bash
# First time only
tldrs index .

# Search by concept
tldrs find "authentication logic"
```

**Output:**
```
 1. [0.82] verify_token (function)
      def verify_token(token: str) -> User
      src/auth/tokens.py:42
```

### 3. Symbol Context

```bash
tldrs context handle_request --project . --depth 2 --format ultracompact
```

**Output:**
```
handle_request(request) -> Response
  calls: validate_input, process_data, format_response
  called_by: main, api_handler
```

## Workflow Examples

### Bug Fix
```bash
tldrs diff-context --project . --budget 2000    # See changes
tldrs find "error handling"                      # Find relevant code
tldrs context buggy_func --project . --depth 2   # Get context
# NOW read the file to fix it
```

### Feature Implementation
```bash
tldrs find "user registration"                   # Find similar features
tldrs context register_user --project . --depth 2 # Understand pattern
tldrs structure src/features/                    # See where to add
# Read and implement
```

## Error Handling

| Error | Fix |
|-------|-----|
| `No index found` | Run `tldrs index .` |
| `Ambiguous entry` | Use `file.py:func` syntax |
| `No changes detected` | Specify `--base` and `--head` |

## Token Budgets

| Codebase | Budget |
|----------|--------|
| Small (<50 files) | 1500 |
| Medium (50-200) | 2000 |
| Large (200+) | 3000 |

## Multi-Turn Optimization

```bash
# First turn - full output
tldrs diff-context --project . --session-id task-123

# Later turns - unchanged symbols omitted (~60% savings)
tldrs diff-context --project . --session-id task-123
```

## Language Support

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

## Full Documentation

- `tldrs quickstart` - This guide
- `tldrs --help` - All commands
- See `docs/agent-workflow.md` for advanced usage
