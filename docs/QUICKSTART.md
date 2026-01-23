# tldr-swinton Quick Reference for Agents

**TL;DR**: Use `tldrs` for reconnaissance, then read full files only when editing.

## When to Use (and When Not To)

| Situation | Use tldr? | Command |
|-----------|-----------|---------|
| Exploring unfamiliar codebase | Yes | `tldrs structure src/` |
| Finding code by concept | Yes | `tldrs find "auth logic"` |
| Understanding recent changes | Yes | `tldrs diff-context --project .` |
| Getting context for a function | Yes | `tldrs context func_name --project .` |
| File is < 200 lines | No | Just read it directly |
| You need to edit a file | No | Read the full file |
| You know exactly what to change | No | Read and edit directly |

## Decision Tree

```
What are you trying to do?
│
├─ "Understand the codebase structure"
│   └─ tldrs structure src/
│
├─ "Find code related to X concept"
│   └─ tldrs find "X concept"
│
├─ "Understand recent changes"
│   └─ tldrs diff-context --project . --budget 2000
│
├─ "Get context around a specific function"
│   └─ tldrs context <func> --project . --depth 2 --format ultracompact
│
├─ "See what calls this function"
│   └─ tldrs impact <func> --depth 2
│
└─ "Edit a file"
    └─ Read the full file (tldr is for recon, not surgery)
```

## Essential Commands

### 1. Diff-First Context (Start Here for Most Tasks)
```bash
tldrs diff-context --project . --budget 2000
```
Shows changed symbols + their dependencies. Best for understanding what's been modified.

### 2. Semantic Search (Find Code by Meaning)
```bash
tldrs index .                          # Build index (once per project)
tldrs find "authentication logic"      # Search by concept
tldrs find "database connection"       # Natural language works
```

### 3. Symbol Context (Drill Into a Function)
```bash
tldrs context handle_request --project . --depth 2 --format ultracompact
```
Returns: signature, what it calls, what calls it, relevant types.

### 4. Structure Overview (Explore a Directory)
```bash
tldrs structure src/                   # Directory
tldrs structure src/auth.py            # Single file
tldrs extract src/auth.py              # Full JSON details
```

## Token Budgets

| Codebase Size | Recommended Budget |
|---------------|-------------------|
| Small (< 50 files) | 1000-1500 |
| Medium (50-200 files) | 2000-3000 |
| Large (200+ files) | 3000-5000 |

Use `--budget N` to cap token output.

## Output Formats

| Format | Use Case | Flag |
|--------|----------|------|
| ultracompact | Most agent workflows | `--format ultracompact` |
| json | Tooling/parsing | `--format json` |
| text | Human reading | (default) |

## Multi-Turn Optimization (Delta Mode)

For multi-turn conversations, use delta mode to skip unchanged symbols:

```bash
# First call - full output
tldrs diff-context --project . --session-id my-session

# Later calls - unchanged symbols omitted (~60% token savings)
tldrs diff-context --project . --session-id my-session
```

## Common Patterns

### Pattern 1: Bug Investigation
```bash
tldrs find "error handling"            # Find relevant code
tldrs context handle_error --project . # Get context
# Then read the specific file to understand/fix
```

### Pattern 2: Feature Implementation
```bash
tldrs diff-context --project .         # See current state
tldrs structure src/features/          # Find where to add
tldrs context similar_feature --project . # Understand patterns
# Then read and edit specific files
```

### Pattern 3: Code Review
```bash
tldrs diff-context --project . --base main --head HEAD
# Shows all changes with context
```

## Quick Checks

```bash
tldrs --help                           # All commands
tldrs index --info                     # Index status
tldrs context --help                   # Context options
```

## Remember

1. **tldr is for reconnaissance** - Use it to find and understand code
2. **Read files for surgery** - When editing, read the full file
3. **Budget your tokens** - Always use `--budget` for large codebases
4. **Use ultracompact** - `--format ultracompact` saves tokens
5. **Delta mode for multi-turn** - `--session-id` skips unchanged code
