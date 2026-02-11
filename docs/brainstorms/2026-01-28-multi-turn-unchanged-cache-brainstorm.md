date: 2026-01-28
topic: multi-turn-unchanged-cache

# Multi-Turn UNCHANGED Caching Improvements

## What We're Building
Expand and harden multi-turn delta behavior so repeated requests do not re-send
unchanged code. Build on current session tracking to return compact "UNCHANGED"
markers with ids, and only send code for changed symbols or slices.

## Why This Approach
Iterative workflows are where token usage explodes. By remembering what was
already delivered and skipping unchanged content, we can cut repeated payloads
dramatically while preserving correctness. This also aligns with "context-saving"
as a headline capability.

## Key Decisions
- **Session reuse**: require a `--session-id` or `--delta` flag for explicit
  multi-turn behavior.
- **Granularity**: track deliveries at the symbol or slice level (etag-based).
- **Output**: replace unchanged code with a short marker and id reference.
- **Expiration**: keep the existing 24-hour expiry, with an option to override.

## Open Questions
- Should delta apply to `context` (signatures) or only to code-emitting commands?
- How to surface "cache hit" stats without adding noisy output?
- How to handle partial overlaps when a slice is truncated by caps?

## Next Steps
→ If approved, draft an implementation plan and identify affected commands/files.
