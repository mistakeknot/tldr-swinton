---
name: tldrs-explore-file
description: "Use when asked to debug a function, understand control flow, trace variable usage, or analyze a file's structure before reading it raw. Provides function-level analysis in ~85% fewer tokens than reading the full file."
allowed-tools:
  - Bash
---

# Explore File Internals

Run this BEFORE reading a file when you need to understand its structure, debug a function, or trace data flow.

## File Overview

Get all functions, classes, and imports in a file without reading the full source:

```bash
tldrs extract <file>
```

Output shows structured metadata:

```
FILE: src/auth.py (142 lines)
IMPORTS: jwt, hashlib, datetime, .models.User
CLASSES:
  AuthManager (lines 15-142)
FUNCTIONS:
  login(username, password) -> Token  [lines 20-45]
  verify(token) -> User  [lines 47-68]
  refresh(token) -> Token  [lines 70-92]
  _hash_password(password) -> str  [lines 94-110]
```

## Control Flow Analysis

Trace the control flow of a specific function:

```bash
tldrs cfg <file> <function_name>
```

Shows branching, loops, early returns, and exception paths. Use when debugging:
- Why does this function sometimes return None?
- Where are the error paths?
- What conditions lead to which branches?

## Data Flow Analysis

Trace how variables are defined and used within a function:

```bash
tldrs dfg <file> <function_name>
```

Shows variable definitions, uses, and def-use chains. Use when:
- Tracking where a value comes from
- Finding unused variables
- Understanding data transformations within a function

## Workflow

1. Start with `tldrs extract <file>` to see what's in the file
2. Use `tldrs cfg <file> <function>` to understand control flow
3. Use `tldrs dfg <file> <function>` to trace data flow
4. Only then Read the specific lines you need to edit

## When to Skip

- File is under 100 lines (just Read it directly)
- You need cross-file relationships (use `tldrs context <symbol>` instead)
- You only need a function signature (use `tldrs context <symbol> --depth 1`)
- You already know the file structure from a previous call

## Next Step

After identifying the structure:
- Use `tldrs context <symbol> --project . --depth 2` for cross-file dependencies
- Read the specific lines you need to edit (you now know exact line numbers)

## Common Errors

- **"No functions found"**: File may use a different naming convention. Try `tldrs structure <dir>` first.
- **"Function not found"**: Use the exact function name from `tldrs extract` output.
- **Very large output**: Focus on one function at a time with cfg/dfg.
