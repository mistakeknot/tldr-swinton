# Agent Workflow (tldr-swinton)

This guide helps coding agents use tldr-swinton to minimize tokens while keeping accuracy.

## Purpose

- Use tldrs for reconnaissance (context selection) before reading full files.
- Prefer compact outputs with explicit budgets.

## Install

```bash
# tldrs
curl -fsSL https://raw.githubusercontent.com/mistakeknot/tldr-swinton/main/scripts/install.sh | bash

# Optional: tldrs-vhs for large outputs
curl -fsSL https://raw.githubusercontent.com/mistakeknot/tldrs-vhs/main/scripts/install.sh | bash
```

If non-interactive shells do not load aliases:

```bash
export TLDRS_VHS_CMD="$HOME/tldrs-vhs/.venv/bin/tldrs-vhs"
```

Verify install:
```bash
tldrs --help
tldrs context main --project . --depth 1 --budget 200 --format ultracompact
```

## Decision Tree

1) Working on recent changes? Use diff-first context:
   - `tldrs diff-context --project . --budget 2000`

2) Need call-graph context around a symbol?
   - `tldrs context <entry> --project . --depth 2 --budget 2000 --format ultracompact`

3) Need file or folder structure?
   - `tldrs structure src/ --lang typescript`
   - `tldrs extract path/to/file.ts`

4) Need semantic search?
   - `tldrs index .`
   - `tldrs find "authentication logic"`

5) Need deep analysis?
   - `tldrs slice <file> <func> <line>`
   - `tldrs cfg <file> <function>`
   - `tldrs dfg <file> <function>`

## Entry Syntax and Discovery

- Entry formats: `file.py:func`, `Class.method`, `module:func`
- Example: `tldrs context src/app.py:handle_request --project .`
- If unsure, discover names first: `tldrs structure src/`
- If ambiguous, the context command returns candidates; re-run with `file.py:func`.

## Language Flags

- Use `--lang` for non-Python repos.
- Example: `tldrs structure src/ --lang typescript`
- Example: `tldrs context src/main.rs:run --lang rust`

## Budget and Depth Tuning

- If context is thin, increase depth: `--depth 3`
- If output is large, reduce budget or use ultracompact:
  - `tldrs context <entry> --depth 3 --budget 1500 --format ultracompact`

## DiffLens Compression

- Two-stage compression:
  - `tldrs diff-context --project . --budget 1500 --compress two-stage`
- Chunk-summary compression:
  - `tldrs diff-context --project . --budget 1500 --compress chunk-summary`

## Impact / Test Selection

- Git diff to affected tests:
  - `tldrs change-impact --git --git-base HEAD~1`
- Session-modified files (run tests):
  - `tldrs change-impact --session --run`

## Call Graph and Import Helpers

- Call graph:
  - `tldrs calls . --lang python`
- Reverse call graph (callers):
  - `tldrs impact authenticate --depth 3 --lang python`
- Importers:
  - `tldrs importers tldr_swinton.api --lang python`

## Output Handling

- Use budgets to cap output size: `--budget 2000`.
- Prefer compact output: `--format ultracompact` where supported.
- For tooling, use JSON: `tldrs context <entry> --format json`.
- Store large outputs as refs:

```bash
tldrs context main --project . --output vhs
# Later:
tldrs context main --project . --include vhs://<hash>
```

- `--output vhs` prints a ref plus a short summary/preview; the ref is what saves tokens.
- Programmatic note: ContextPack JSON includes `etag` per slice for conditional fetch in the API.
  - For API usage: `get_symbol_context_pack(..., etag=...)` returns `"UNCHANGED"` when the symbol is unchanged.

## Troubleshooting

- If tldrs-vhs is not found:
  - `export TLDRS_VHS_CMD="$HOME/tldrs-vhs/.venv/bin/tldrs-vhs"`
  - Or set `TLDRS_VHS_PYTHONPATH=/path/to/tldrs-vhs/src` and use `TLDRS_VHS_CMD="python -m tldrs_vhs.cli"`
- Suppress entry warnings (optional): `export TLDRS_NO_WARNINGS=1`

## Typical Agent Flow

1) `tldrs diff-context --project . --budget 2000`
2) `tldrs context <entry> --project . --depth 2 --budget 2000 --format ultracompact`
3) `tldrs extract path/to/file.py` for precise edits
4) Read the full file only when you must modify it
