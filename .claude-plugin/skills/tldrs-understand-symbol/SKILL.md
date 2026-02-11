---
name: tldrs-understand-symbol
description: "Use when asked about how a function or class works, what calls it, what it depends on, or before modifying/extending a symbol. Gets call graph, signatures, and callers in ~85% fewer tokens than reading the full file."
allowed-tools:
  - Bash
---

# Understand a Symbol

Run BEFORE reading a file when you need to understand a function or class.

## Decision Tree

### What do you need?

**Callers (who calls this?):**
```bash
tldrs impact <symbol> --depth 3
```

**Callees (what does this call?):**
```bash
tldrs context <symbol> --project . --preset compact
```

**Both callers and callees:**
```bash
tldrs context <symbol> --project . --preset compact --depth 2
```

### About to modify a symbol?

**Always check callers before modifying a public function:**
```bash
tldrs impact <symbol> --depth 3
```

Review the callers list. If callers depend on the current signature or return type, plan how to update them.

### Symbol name is ambiguous?

If tldrs returns multiple matches, re-run with qualified name:
```bash
tldrs context src/api.py:handle_request --project . --preset compact
```

### Don't know the symbol name?

```bash
tldrs structure src/path/to/dir/
```

## Import Dependencies

```bash
# What does this file import?
tldrs imports <file>

# Who imports this module? (essential before renaming/moving)
tldrs importers <module_name> .
```

## Rules

- Always use `--preset compact`
- Always check callers (via `tldrs impact`) before modifying a public function
- Use `--depth 1` for minimal tokens, `--depth 3` for broad unfamiliar context

## When to Skip

- File is under 200 lines and you already know its structure
- You need the full implementation body, not architecture
