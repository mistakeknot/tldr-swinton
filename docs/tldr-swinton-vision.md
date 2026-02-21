# tldr-swinton Vision and Philosophy

**Version:** 0.7.6  
**Last updated:** 2026-02-15  
**PRD:** [`docs/PRD.md`](PRD.md)

## What tldr-swinton Is

tldr-swinton is a token-efficient code reconnaissance system for AI workflows.
It turns raw project structure into compact, actionable context for tasks such as
understanding changed code, tracing behavior, and deciding where to read next.

It is not a code-writing model. It is a context engine.

## Why token-efficient context exists

LLM coding workflows usually spend the most budget on "code exploration." The same
symbol can be read repeatedly across turns, and the same repo can be scanned
multiple times with diminishing returns. tldr-swinton reduces this tax by returning:

- symbol-level summaries instead of full files
- call and data-flow slices before broad reads
- adaptive compression (`ultracompact`, `cache-friendly`, budgets, presets)
- explicit tradeoff metadata so tools can be composed under budget

The product goal is to keep humans and agents operating on fewer,
better-scored tokens without losing correctness.

## Eyes-of-the-system philosophy

tldr-swinton is the "eyes" layer in an AI engineering stack:

1. **See the boundary, not the whole mountain.** For any query, return only the
minimum context needed to act.
2. **Prefer orientation first.** Start with structure, then escalate to deeper
analysis only if needed.
3. **Preserve navigation.** Return symbol IDs, file paths, and line anchors so
agents can move from overview to precision safely.
4. **Treat tokens as attention budget, not a vanity metric.** Saving tokens is a
means to speed decisions, prevent context drift, and improve human review quality.

## Relationship to Clavain workflows

tldr-swinton is a companion plugin that feeds Clavain’s `discover → plan → execute →
review → ship` rhythm with low-cost context primitives. In practice:

- Clavain planning and review flows use `diff_context` and `context` as first-pass
  signals before raw file reads.
- Structural and semantic calls (`structural`, `search`, `semantic`, `extract`) are
  used to decompose tasks and reduce unnecessary file-level reads.
- MCP tools and hooks provide a low-friction surface for agents and workflow tools
  already orchestrated by Clavain.

This relationship is the opposite of a plugin dependency; it is a composition
relationship: Clavain orchestrates work, tldr-swinton optimizes each observation.

## Positioning

### What it does

- Structural code analysis: file tree, symbols, signatures, imports, and navigation.
- Semantic retrieval: query-by-concept search with hybrid lexical + embedding ranking.
- Execution-oriented analysis: call graph traversal, CFG/DFG/predictive slicing support.
- Workflow compression: caching, caching-friendly output shapes, and multi-turn
  deltas for repeated symbol reads.

### What it does not do

- It does not replace full code editing or model coding.
- It does not guarantee architectural correctness by itself.
- It is not a replacement for review; it is an optimization layer for better review.

## Product posture

tldr-swinton is intentionally empirical: it ships with evaluation tracks, R&D
plans (`docs/plans/`), and research artifacts (`docs/research/`, `docs/solutions/`)
so capabilities are revised only when measurable signals justify changes.

This product is the high-confidence answer to a simple question:
**"What context should the next move read to maximize value?"**
