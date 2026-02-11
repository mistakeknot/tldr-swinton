date: 2026-01-28
topic: stable-ids-refetch

# Stable IDs for Precise Re-Fetch

## What We're Building
Introduce stable, short ids for files, symbols, and slices so callers can re-
fetch exactly what they need without resending long paths or code. IDs would be
included in list outputs and context outputs, enabling commands like `get --id`
or `context --id` to pull a specific target.

## Why This Approach
Stable ids reduce token overhead in multi-step workflows and make the retrieval
API more ergonomic for agents. They also enable caching and change detection by
tying ids to a stable locator rather than a transient position in output text.

## Key Decisions
- **ID scope**: file ids (path-based), symbol ids (path + symbol signature), and
  slice ids (symbol + line range).
- **ID format**: short, human-friendly hash (e.g., base32 of a sha256 prefix).
- **Inclusion**: ids appear in `--files`, `--symbols`, and context outputs.
- **Resolution**: new flags `--id` on `get`/`context` to resolve ids to content.

## Open Questions
- How to handle renames: keep id stable via git history, or treat as new id?
- Should ids include language to avoid collisions in mixed repos?
- Should ids be opaque or optionally resolvable back to paths for debugging?

## Next Steps
→ If approved, draft an implementation plan and identify affected commands/files.
