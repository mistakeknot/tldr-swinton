date: 2026-01-28
topic: files-only-listing

# Files-Only / Symbols-Only Listing Mode

## What We're Building
Add a lightweight output mode that lists candidate files or symbols without
including any code bodies. The listing includes enough metadata (path, symbol
name, signature, line numbers, score, and a stable id) for a caller to decide
what to fetch next. This is intended as a first-pass triage to minimize tokens.

## Why This Approach
Sending code too early wastes tokens when the user or agent has not decided what
is relevant. A files-only or symbols-only view encourages a two-step workflow:
discover -> choose -> fetch. This keeps one-shot outputs small and gives
iterative workflows a clear selection stage.

## Key Decisions
- **New flags**: `--files` and `--symbols` on relevant commands (e.g., `find`,
  `context`, `structure`) to return metadata only.
- **Output shape**: include path, symbol name, signature, line number, language,
  score (if available), and a short stable id.
- **Sorting**: preserve current ranking logic; just omit code bodies.
- **Back-compat**: default output unchanged unless the new flags are used.

## Open Questions
- Should `--files` aggregate to file-level scores, or list top symbols per file?
- Should listings optionally include a short summary line (docstring only)?
- Should this be a separate command (e.g., `tldrs list`) instead of flags?

## Next Steps
→ If approved, draft an implementation plan and identify affected commands/files.
