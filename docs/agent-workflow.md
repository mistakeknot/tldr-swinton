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

## Output Handling

- Use budgets to cap output size: `--budget 2000`.
- Prefer compact output: `--format ultracompact` where supported.
- Store large outputs as refs:

```bash
tldrs context main --project . --output vhs
# Later:
tldrs context main --project . --include vhs://<hash>
```

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
