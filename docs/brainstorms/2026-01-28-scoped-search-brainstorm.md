date: 2026-01-28
topic: scoped-search

# Scoped Search / Path Filters

## What We're Building
Add a scoping mechanism (paths, glob, or named scopes) so searches only consider
part of the codebase. This reduces candidate sets and token output without
changing ranking logic.

## Why This Approach
QMD’s collections enable `-c` scoped searches. For tldrs, explicit scoping lets
users and agents narrow intent early, avoiding irrelevant files and context.

## Key Decisions
- **Interface**: `--scope <path|glob>` and/or `--scope-name <label>` to target paths.
- **Behavior**: scope applies to both search and output expansion.
- **Defaults**: no scope = full project (current behavior).
- **Visibility**: show the active scope in output headers.

## Open Questions
- Should scopes be created dynamically (ad hoc path) or named and saved?
- Should multiple scopes be allowed in a single command?
- How do scopes interact with existing `--project` and `--include` options?

## Next Steps
→ If approved, draft an implementation plan and identify affected commands/files.
