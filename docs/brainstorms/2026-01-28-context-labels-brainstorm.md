date: 2026-01-28
topic: context-labels

# Context Labels for Fast Triage

## What We're Building
Add short, human-authored context labels for directories or file groups (e.g.,
"payment pipeline", "auth core") that appear in list outputs. This lets agents
decide relevance without loading code and reduces the need for verbose metadata.

## Why This Approach
Compact, curated context cues can replace long descriptions or code fetches.
QMD uses context descriptions on collections to help users choose quickly; we
can mirror the idea to reduce token usage during discovery.

## Key Decisions
- **Attachment scope**: labels can be set at directory paths (recursive).
- **Output**: labels appear in list outputs (`--files`, `--symbols`).
- **Storage**: simple JSON/YAML mapping file under `.tldrs/` or repo root.
- **Editing**: CLI subcommand to add/remove labels (e.g., `tldrs label set`).

## Open Questions
- Should labels be kept in repo (shared) or in `.tldrs` (local)?
- Should we allow multiple labels per path or just one?
- Should labels be inherited or overridden by deeper paths?

## Next Steps
→ If approved, draft an implementation plan and identify affected commands/files.
