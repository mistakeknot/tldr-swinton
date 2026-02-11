---
title: "feat: Token-saving roadmap"
type: feat
date: 2026-01-28
---

# feat: Token-saving roadmap

## Enhancement Summary

**Deepened on:** 2026-01-28  
**Sections enhanced:** 9  
**Research agents used:** best-practices-researcher, performance-oracle, architecture-strategist

### Key Improvements
1. Aligned CLI output/caps with human-first + machine-readable guidance.
2. Added performance guardrails for caps, budget estimation, and caching touchpoints.
3. Clarified architectural boundaries for caps/ids/delta to avoid coupling.

### New Considerations Discovered
- Ensure truncation remains machine-readable in JSON modes.
- Standardize score scales before applying `--min-score` globally.

## Overview
Deliver a phased set of token-saving features inspired by QMD, focused on reducing
code payload size for both one-shot and iterative workflows. The roadmap prioritizes
safe, opt-in guardrails first, then selection improvements, then multi-turn reuse.

### Research Insights
**Best Practices:**
- CLI guidance recommends human-first output with machine-readable options (e.g., JSON) when requested.
- Keep outputs composable for pipes and scripts; provide plain modes when formatting would break line-based tools.

**Implementation Details:**
- Ensure any truncation metadata is structured (fields) in JSON formats.
- Prefer standard flag names (`--json`, `--quiet`, `--output`) to reduce cognitive load.

**References:**
- https://clig.dev/#output
- https://clig.dev/#arguments-and-flags

## Problem Statement
tldrs already reduces context size, but output payloads can still grow quickly in
mixed workflows. Users need predictable caps, better candidate filtering, and
stronger reuse of unchanged context so they can keep coding token usage low without
manually curating every output.

### Research Insights
**Best Practices:**
- CLI guidelines emphasize "saying just enough"—too much output is as harmful as too little.

**Edge Cases:**
- Truncation without a clear marker can confuse users and lead to repeated fetches.

**References:**
- https://clig.dev/#saying-just-enough

## Proposed Solution
Implement the roadmap in three phases:
1) **Guardrails**: hard output caps and short vs full retrieval modes.
2) **Selection**: metadata-only listings, score gating, and scoped search.
3) **Reuse**: stable ids and stronger multi-turn UNCHANGED caching.

All changes remain opt-in to preserve current behavior.

### Research Insights
**Best Practices:**
- QMD exposes `--files`, `--min-score`, scoped collections, and `--full` as explicit opt-ins for larger payloads.

**Implementation Details:**
- Mirror QMD’s pattern of listing-only outputs and threshold gates to reduce unnecessary content.

**References:**
- https://github.com/tobi/qmd#quick-start
- https://github.com/tobi/qmd#using-with-ai-agents

## Technical Approach

### Architecture
Leverage existing context packing and delta mode facilities:
- CLI already supports delta/session flags (add new flags alongside these).  
  `src/tldr_swinton/cli.py:700`
- ContextPack supports slices, etags, and unchanged markers.  
  `src/tldr_swinton/modules/core/contextpack_engine.py:9`
- Output formatting already handles UNCHANGED responses.  
  `src/tldr_swinton/modules/core/output_formats.py:134`
- Workspace scoping exists via `.claude/workspace.json`.  
  `src/tldr_swinton/modules/core/workspace.py:40`
- DiffLens already computes line ranges for slices (useful for caps).  
  `src/tldr_swinton/modules/core/engines/difflens.py:621`

### Research Insights
**Architecture Overview:**
- Keep new behavior centralized in ContextPack/CLI layers to avoid per-engine drift.

**Change Assessment:**
- Output caps and short/full modes should be applied after candidate selection but before formatting.

**Risk Analysis:**
- Duplicating cap logic across engines increases divergence and maintenance risk.

### Implementation Phases

#### Phase 1: Guardrails
- Add `--max-lines` / `--max-bytes` caps for code-emitting commands
  (context, diff-context, slice, and any future get-like output).
- Add short vs full retrieval (`--full` opt-in) so default output is compact.
- Ensure truncation is explicit in output (e.g., TRUNCATED marker + cap details).

##### Research Insights
**Performance Considerations:**
- Enforce caps during slice construction to avoid building full strings unnecessarily.
- Track a "cap-hit" metric to understand how often truncation occurs.

#### Phase 2: Selection
- Add metadata-only listing modes (`--files`, `--symbols`).
- Add `--min-score` gating for search-derived results.
- Add scoped search (path/glob or named scope) to limit candidate sets.
- Optional: surface context labels for path groups (future, if desired).

##### Research Insights
**Performance Considerations:**
- Apply `--min-score` before code extraction to avoid wasted work.
- Scope filtering should happen early in file enumeration (workspace iterator).

#### Phase 3: Reuse
- Introduce stable ids for files/symbols/slices (short hashes).
- Expand delta behavior to return UNCHANGED with ids + compact references.
- Ensure delta works alongside caps (unchanged slices should remain minimal).

##### Research Insights
**Implementation Details:**
- Stable ids should be derived from deterministic inputs (path + signature + language).
- Delta + caps should return signature-only if a slice would otherwise be truncated.

## Alternative Approaches Considered
- **Single big release**: higher risk, harder to validate token savings; rejected.
- **Integrate QMD directly**: out of scope; this roadmap focuses on tldrs-native
  token controls.

## Acceptance Criteria

### Functional Requirements
- [ ] `--max-lines` and `--max-bytes` caps are available on relevant commands and
      enforce limits without crashing or malformed output.
- [ ] `--full` is opt-in; default outputs are measurably shorter.
- [ ] `--files`/`--symbols` modes emit metadata-only listings (no code bodies).
- [ ] `--min-score` filters results without affecting existing defaults.
- [ ] Scoped search limits candidate sets by path/glob or named scope.
- [ ] Stable ids are emitted and resolvable for precise re-fetch.
- [ ] Delta outputs use UNCHANGED markers and skip re-sending unchanged code.

### Non-Functional Requirements
- [ ] No regression in current output formats when new flags are not used.
- [ ] Token savings are measurable on existing evals (difflens + agent workflow).
- [ ] New flags are documented in CLI help and README usage notes.

### Research Insights
**Best Practices:**
- Keep machine-readable formats stable; avoid embedding truncation markers in plain text.
- Use standard flag names and document defaults clearly.

**References:**
- https://clig.dev/#output
- https://clig.dev/#arguments-and-flags

### Quality Gates
- [ ] Unit/CLI tests cover caps, flags, and edge cases.
- [ ] Manual smoke checks for context/diff-context with delta + caps.
- [ ] Eval scripts confirm reductions without correctness regressions.

## Success Metrics
- ≥10% reduction in median output tokens on difflens eval for Phase 1.
- ≥15% reduction in median output tokens on agent workflow eval for Phase 2.
- ≥25% reduction in multi-turn sessions when delta + ids are used (Phase 3).

### Research Insights
**Performance Considerations:**
- Track "cap hit rate" and "avg slices returned" to validate guardrails.
- Track delta cache hit rate and "unchanged bytes avoided" in multi-turn runs.

## Dependencies & Prerequisites
- Existing delta infrastructure (session-id, etags) is already in place.  
  `src/tldr_swinton/cli.py:700`
- Workspace scoping config can be reused for path scoping.  
  `src/tldr_swinton/modules/core/workspace.py:40`

### Research Insights
**Architecture Considerations:**
- Consider aligning scope configuration with existing workspace config to avoid duplicate filters.

## Risk Analysis & Mitigation
- **Cap interactions with JSON outputs**: ensure truncation markers are valid
  JSON fields rather than inline text.
- **Score scale inconsistency**: define a normalized score scale or gate only
  where scores are already comparable.
- **Stable id collisions**: use deterministic hash of path+symbol signature.
- **Renames**: treat as new ids; document behavior.

### Research Insights
**Best Practices:**
- If human-readable output changes formatting, provide a plain output mode for scripts.

**References:**
- https://clig.dev/#output

## Resource Requirements
- 1–2 engineers for Phase 1 (1–2 days)
- 1 engineer for Phase 2 (2–3 days)
- 1 engineer for Phase 3 (2–4 days, requires extra testing)

## Future Considerations
- Context labels for directories (curated, optional metadata)
- Candidate caps + reranking if/when LLM rerank is introduced
- LLM cache if any expansion/rerank is added

## Documentation Plan
- Update CLI docs and `tldrs quickstart` with new flags.
- Add a “Token-saving workflow” section in README.
- Document recommended usage patterns (caps + listings + delta).

### Research Insights
**Best Practices:**
- Include concrete examples in `--help` output and docs to improve discoverability.

**References:**
- https://clig.dev/#help

## References & Research

### Internal References
- Delta flags and options: `src/tldr_swinton/cli.py:700`
- Context pack and etags: `src/tldr_swinton/modules/core/contextpack_engine.py:9`
- UNCHANGED output formatting: `src/tldr_swinton/modules/core/output_formats.py:134`
- Workspace scoping config: `src/tldr_swinton/modules/core/workspace.py:40`
- Line-range extraction in difflens: `src/tldr_swinton/modules/core/engines/difflens.py:621`

### External References
- QMD README (token-saving patterns and CLI flags)
- https://github.com/tobi/qmd#quick-start
- https://github.com/tobi/qmd#using-with-ai-agents
- https://clig.dev/#output
- https://clig.dev/#arguments-and-flags

### Related Work
- Token savings eval plans in `docs/plans/` (difflens and workflow evals)
