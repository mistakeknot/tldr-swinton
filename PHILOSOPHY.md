# tldr-swinton Philosophy

## Purpose
Token-efficient code reconnaissance for LLMs. Autonomous skills save 48-85% tokens via diff-context, semantic search, structural patterns, and symbol analysis. Includes MCP server for direct tool integration.

## North Star
Push token-efficient code understanding while preserving correctness: compression, retrieval, and ranking changes must stay explainable and testable.

## Working Priorities
- Token efficiency
- Context fidelity
- Retrieval quality

## Brainstorming Doctrine
1. Start from outcomes and failure modes, not implementation details.
2. Generate at least three options: conservative, balanced, and aggressive.
3. Explicitly call out assumptions, unknowns, and dependency risk across modules.
4. Prefer ideas that improve clarity, reversibility, and operational visibility.

## Planning Doctrine
1. Convert selected direction into small, testable, reversible slices.
2. Define acceptance criteria, verification steps, and rollback path for each slice.
3. Sequence dependencies explicitly and keep integration contracts narrow.
4. Reserve optimization work until correctness and reliability are proven.

## Decision Filters
- Does this reduce ambiguity for future sessions?
- Does this improve reliability without inflating cognitive load?
- Is the change observable, measurable, and easy to verify?
- Can we revert safely if assumptions fail?

## Evidence Base
- Brainstorms analyzed: 15
- Plans analyzed: 53
- Source confidence: artifact-backed (15 brainstorm(s), 53 plan(s))
- Representative artifacts:
  - `docs/plans/2026-02-10-prompt-cache-optimization.md`
  - `docs/plans/2026-02-10-token-savings-implementation-plans.md`
  - `docs/plans/2026-02-11-maximize-agent-adoption-plan.md`
  - `docs/plans/2026-02-11-maximize-agent-tldrs-adoption-design.md`
  - `docs/plans/2026-02-12-bump-v0.7.2.md`
  - `docs/plans/2026-02-12-longcodezip-block-compression.md`
  - `docs/plans/2026-02-14-colbert-search-backend.md`
  - `docs/plans/context-optimization-roadmap.md`
