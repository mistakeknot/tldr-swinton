---
name: tldrs-explore-file
description: "Use when asked to debug a function, understand control flow, trace variable usage, or analyze a file's structure before reading it raw. Provides function-level analysis in ~85% fewer tokens than reading the full file."
allowed-tools:
  - Bash
---

# Explore File Internals

Run BEFORE reading a file when you need to understand its structure, debug a function, or trace data flow.

## Decision Tree

### What are you doing?

**Need file overview (functions, classes, imports):**
```bash
tldrs extract <file>
```

**Debugging a function (branches, loops, early returns):**
```bash
tldrs cfg <file> <function_name>
```

**Tracing data flow (variable definitions, uses, chains):**
```bash
tldrs dfg <file> <function_name>
```

**Need cross-file relationships:**
Use `tldrs context <symbol> --project . --preset compact` instead.

## Workflow

1. `tldrs extract <file>` → see what's in the file
2. `tldrs cfg <file> <function>` → understand control flow
3. `tldrs dfg <file> <function>` → trace data flow
4. Read only the specific lines you need to edit

## When to Skip

- File is under 100 lines — just Read it directly
- You need cross-file relationships — use `tldrs context <symbol> --project . --preset compact` instead
- You only need a function signature — use `tldrs context <symbol> --project . --preset compact --depth 1`
