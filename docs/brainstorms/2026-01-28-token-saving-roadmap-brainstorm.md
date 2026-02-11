date: 2026-01-28
topic: token-saving-roadmap

# Token-Saving Roadmap (Phased)

## What We're Building
A phased roadmap of token-saving features inspired by QMD, applied to tldrs.
The goal is to reduce code payload size for both one-shot and iterative workflows
without compromising relevance or requiring major workflow changes.

## Why This Approach
A phased rollout delivers immediate, low-risk wins while preserving a clear path
to deeper savings later. It balances speed, user impact, and operational safety.

## Key Decisions
- **Phase 1 (Guardrails)**: max output caps (`--max-lines`, `--max-bytes`) and
  short vs full retrieval modes to prevent accidental large payloads.
- **Phase 2 (Selection)**: files/symbols-only listings, `--min-score`, and scoped
  search to reduce irrelevant candidates before any code is emitted.
- **Phase 3 (Reuse)**: stable ids and stronger multi-turn UNCHANGED caching to
  avoid re-sending unchanged context across sessions.
- **Rollout strategy**: maintain backward compatibility; all changes opt-in via flags.

## Open Questions
- Should any Phase 1 guardrails become defaults (or remain strictly opt-in)?
- How should we standardize score scales across backends for `--min-score`?
- What is the best storage location for scope/label metadata (repo vs .tldrs)?
- How should renames affect stable id resolution?

## Next Steps
→ Break phases into implementation plans and decide which Phase 1 feature to ship first.
