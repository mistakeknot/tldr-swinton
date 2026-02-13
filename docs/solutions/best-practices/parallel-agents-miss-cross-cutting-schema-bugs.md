---
title: "Parallel agents miss cross-cutting schema bugs"
category: best-practices
tags: [multi-agent, quality-gates, schema-consistency, code-review]
severity: medium
root_cause: "Each implementing agent optimizes for its own scope without cross-referencing sibling outputs"
solution: "Run quality gates with dedicated review agents after parallel implementation"
date: 2026-02-12
---

# Parallel Agents Miss Cross-Cutting Schema Bugs

## Problem

When dispatching multiple agents in parallel to implement related changes, each agent optimizes for its immediate task without awareness of what sibling agents produce. This creates cross-cutting inconsistencies that no single agent catches.

## Example: `line` vs `line_number`

Four parallel agents implemented Phase 1 token efficiency changes:

- **Agent 3ia** added `compact_extract()` in `api.py`, choosing `"line"` as the dict key (shorter = fewer tokens, aligned with its token-saving goal)
- **Agent 7kb** changed MCP `context()` defaults in `mcp_server.py`
- The existing `extract_file()` uses `"line_number"` as the dict key

The schema inconsistency (`"line"` in compact vs `"line_number"` in full extract) was invisible to every implementing agent because:

1. Agent 3ia never read the full extract schema — it was focused on creating the compact version
2. The MCP `extract()` tool wraps both paths, so callers see different key names depending on `compact=True/False`
3. No tests existed for schema key consistency across modes

## How It Was Caught

The **quality gates** step launched 3 review agents (fd-architecture, fd-quality, fd-api-surface) *after* all implementation was done. All three independently flagged the `line` vs `line_number` inconsistency:

- fd-architecture: "Schema inconsistency that will cause subtle bugs"
- fd-api-surface: "Callers writing code for both modes will break"
- fd-quality: "Noted as intentional brevity but inconsistent with full extract"

## Fix

Changed `compact_extract()` to use `"line_number"` (matching full extract) — 3 lines changed, zero risk.

## Pattern: Why Multi-Agent Review Catches What Implementation Misses

Implementing agents are **anchored to their task goal**. Agent 3ia's goal was "make extract output smaller" — shorter key names serve that goal perfectly. Review agents evaluate from the **consumer's perspective** — "can I write code that works with both modes?" — which reveals the inconsistency.

This is the same dynamic as human code review: the author knows *why* they chose something, the reviewer asks *what happens when someone else encounters it*.

## Reusable Rules

1. **After parallel agent implementation, always run quality gates** — don't skip even if each agent's work looks correct in isolation
2. **Schema consistency is a cross-cutting concern** — no single agent owns it unless you explicitly assign one
3. **Review agents should be given the full unified diff**, not individual agent diffs, so they can spot cross-agent inconsistencies
4. **Key naming in dict-based APIs should match across all modes** — brevity is not worth schema fragmentation

## Related

- Quality gate reports: `docs/research/qg-fd-*.md`
- Compact extract implementation: `src/tldr_swinton/modules/core/api.py:714`
- Fix commit: `5b57da6`
