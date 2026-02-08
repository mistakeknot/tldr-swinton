# tldrs Quick Reference

**Rule**: Run tldrs BEFORE using Read tool on code files. Saves 48-85% tokens (semantic search ~85%, diff-context ~48%, multi-turn 60%+).

## Quick Decision

| Task | Command | Then |
|------|---------|------|
| Start any coding task | `tldrs diff-context --project . --budget 2000` | Review changed symbols |
| Find code by concept | `tldrs find "auth logic"` | Read top results |
| Find code by structure | `tldrs structural 'pattern' --lang python` | Read matches |
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

### 4. Structural Search

```bash
tldrs structural 'def $FUNC($$$ARGS): return None' --lang python
```

**Output:**
```
Found 3 match(es):

  src/api.py:42
    def get_user(id): return None
    $FUNC = get_user

  src/utils.py:15
    def noop(): return None
    $FUNC = noop
```

**What it tells you:** Code matches by AST structure, with meta-variable bindings.

**Important:** Always single-quote patterns. `$VAR` and `$$$ARGS` are ast-grep meta-variables, not shell variables.

Included in base install (ast-grep-py).

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

## Cache-Friendly Format (Prompt Caching)

Use `--format cache-friendly` to optimize for LLM provider prompt caching:

```bash
tldrs diff-context --project . --delta --format cache-friendly
```

**Output structure:**
```
# tldrs cache-friendly output

## CACHE PREFIX (stable - cache this section)
## 3 symbols

api.py:get_user def get_user(id: int) @45 [caller]
api.py:list_users def list_users() @62 [caller]
models.py:User class User @10 [callee]

<!-- CACHE_BREAKPOINT: ~150 tokens -->

## DYNAMIC CONTENT (changes per request)
## 1 symbols, 1 with code

api.py:update_user def update_user(id, data) @82-95 [contains_diff]
```python
def update_user(id: int, data: dict) -> User:
    user = get_user(id)
    ...
```

## STATS: Prefix ~150 tokens | Dynamic ~300 tokens | Total ~450 tokens
```

**Cost savings:**
- Anthropic: ~90% on cached prefix tokens
- OpenAI: ~50% on cached prefix tokens

**How it works:**
1. Unchanged symbols go to CACHE PREFIX (sorted by ID for stability)
2. Changed symbols go to DYNAMIC CONTENT (with full code)
3. LLM providers cache the stable prefix across requests

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
