---
name: tldrs-map-codebase
description: "Use when asked to understand a codebase's architecture, explore an unfamiliar project, onboard to a new repo, identify which modules exist, find entry points, or get a bird's-eye view before diving into code. Also use when the user says 'what does this project do' or 'show me the structure'. Provides structural overview without reading individual files."
allowed-tools:
  - Bash
---

# Map Codebase Architecture

Run when you need a bird's-eye view of a project before diving into code.

## Decision Tree

### New repo or unfamiliar project?

Start with architecture overview:
```bash
tldrs arch --lang python .
```
Then drill into interesting directories:
```bash
tldrs structure src/
```

### Known repo, exploring a new area?

```bash
tldrs structure src/path/to/area/
```

### Just need the file layout?

```bash
tldrs tree src/
```
Lighter than `structure` — just file paths, no symbols.

## Workflow

1. `tldrs arch --lang <lang> .` → big picture (layers, dependencies)
2. `tldrs structure <dir>` → symbols in each file
3. `tldrs tree <dir>` → file listing for large directories
4. Drill in with `tldrs context <entry_point> --project . --preset compact`

## Rules

- Use `tree` only for orientation, `structure` for real work
- For non-Python projects: `tldrs arch --lang typescript src/`

## When to Skip

- You already know where to look — go straight to `tldrs context <symbol> --project . --preset compact` or Read
- Project is tiny (<10 files) — just `tldrs structure .`
- User specified the exact file to work on
