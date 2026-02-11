date: 2026-01-28
topic: max-output-caps

# Max Output Caps for Context Retrieval

## What We're Building
Add explicit output caps to tldrs context-producing commands so they never emit more
than a caller-specified budget. The caps apply to code payloads (lines or bytes),
giving predictable, hard limits that save tokens in both one-shot and iterative use.

## Why This Approach
We want immediate, universal token savings with minimal risk. Output caps reduce
payload size regardless of retrieval quality, and they are easy to explain and
adopt without requiring users to change their workflows.

## Key Decisions
- **Primary controls**: `--max-lines` and `--max-bytes` flags for any command that
  emits code or full symbol bodies.
- **Behavior on truncation**: annotate output with a short "TRUNCATED" marker and
  the exact cap used to make the limit explicit.
- **Default behavior**: no cap unless explicitly set (backward-compatible).
- **Scope**: apply to `context`, `diff-context`, and any `get`/slice-like outputs.

## Open Questions
- Should we also add a global env var for caps (e.g., `TLDRS_MAX_BYTES`)?
- Should truncation prefer the "center" around the symbol line rather than the
  top portion only?
- Should truncation include a small header/footer to preserve structure?

## Next Steps
→ If approved, draft an implementation plan and identify affected commands/files.
