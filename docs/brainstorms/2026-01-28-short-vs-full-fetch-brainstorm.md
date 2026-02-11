date: 2026-01-28
topic: short-vs-full-fetch

# Short vs Full Fetch Modes

## What We're Building
Define a "short" retrieval mode as the default for code/content fetches, with
an explicit `--full` flag to override. Short mode can limit body size, omit
nonessential sections, or return only a focused slice around the symbol.

## Why This Approach
QMD treats `--full` as an opt‑in for whole‑file retrieval. Adopting a similar
default makes token‑heavy outputs deliberate rather than accidental.

## Key Decisions
- **Default**: short mode unless `--full` is specified.
- **Short mode shape**: return the symbol body and a small surrounding context.
- **Visibility**: clearly annotate outputs as SHORT or FULL.
- **Compatibility**: preserve current behavior behind a config flag if needed.

## Open Questions
- Should short mode be a percentage cap or a line/byte cap?
- How do we define "surrounding context" across languages?
- Should `--full` imply "ignore max caps" or still respect them?

## Next Steps
→ If approved, draft an implementation plan and identify affected commands/files.
