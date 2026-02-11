date: 2026-01-28
topic: score-gating

# Score Gating for Output Reduction

## What We're Building
Introduce a `--min-score` threshold on search and listing outputs so low-confidence
results are filtered out before any content is emitted. This reduces noise and
token load without changing core retrieval logic.

## Why This Approach
Many token costs come from low-quality candidates included "just in case." A
simple score gate avoids emitting these entirely, mirroring QMD’s `--min-score`
flag used in agent workflows.

## Key Decisions
- **Flag**: `--min-score` with a float range [0, 1] or [0, 100] (choose one).
- **Scope**: applies to `find`, `diff-context` listings, and any `--files`/`--symbols` output.
- **Defaults**: off by default to preserve behavior; on when explicitly set.
- **Diagnostics**: optionally report how many results were filtered.

## Open Questions
- What is the score scale in each command today, and can we standardize it?
- Should we allow different thresholds per backend (lexical vs semantic)?
- How do we treat items with no score (e.g., structure listings)?

## Next Steps
→ If approved, draft an implementation plan and identify affected commands/files.
