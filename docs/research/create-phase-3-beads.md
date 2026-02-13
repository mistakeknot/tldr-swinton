# Phase 3: Output Format Polish — Beads Issues

Created: 2026-02-12

## Overview

Phase 3 of the token efficiency review targets output format polish — reducing token waste in serialized output that Claude Code consumes. These are low-risk, high-value changes that don't affect internal data structures or analysis quality.

**Total estimated savings:** ~864-923 tokens per typical request (~43-46% of 2000-token budget), with individual savings ranging from 3-5 tokens (wrapper unwrap) to 390 tokens (impact field stripping).

## Issues Created

### P3 (Medium Priority) — 5 issues

| Bead ID | Title | Type | Estimated Savings | Key Files |
|---------|-------|------|-------------------|-----------|
| `tldr-swinton-1vw` | Sparse meta dicts in diff-context output | task | ~96-128 tokens (~5-6%) | difflens.py:760-765, 827-828 |
| `tldr-swinton-u3k` | Truncate ETags to 16 chars in output serialization | task | ~160 tokens (~8%) | contextpack_engine.py:572 |
| `tldr-swinton-osi` | Strip redundant fields from impact tool output | task | ~390 tokens | mcp_server.py:335-345, daemon.py |
| `tldr-swinton-zza` | Apply path compression in distill output and omit empty sections | task | ~200+ tokens | distill_formatter.py:100-153, 115-124 |
| `tldr-swinton-zhd` | Fix distill_formatter token estimator to use shared token_utils | bug | N/A (accuracy fix) | distill_formatter.py:21-22 |

### P4 (Low Priority) — 2 issues

| Bead ID | Title | Type | Estimated Savings | Key Files |
|---------|-------|------|-------------------|-----------|
| `tldr-swinton-3bo` | Remove blank line separators in ultracompact format | task | ~15-20 tokens | output_formats.py:444-460 |
| `tldr-swinton-4nf` | Unwrap daemon status:ok wrapper in MCP tools | task | ~3-5 tokens/call | mcp_server.py:90-119 |

## Issue Details

### 1. Sparse meta dicts in diff-context output (`tldr-swinton-1vw`)

**Problem:** Every diff-context slice includes `block_count:0`, `dropped_blocks:0`, `summary:null`, `diff_lines:[]` for non-diff symbols. These zero/null/empty values are pure waste for the ~80% of symbols that aren't in a diff.

**Fix:** Only include meta fields with non-default values. Use a sparse dict constructor that skips defaults.

**Files:** `difflens.py:760-765` (meta construction), `difflens.py:827-828` (meta unpacking).

**Savings:** ~96-128 tokens per request (~5-6% of 2000-token budget).

### 2. Truncate ETags to 16 chars in output serialization (`tldr-swinton-u3k`)

**Problem:** ETags are full 64-char SHA-256 hex digests. For project-scale cardinality (<100k symbols), 16 chars (64 bits) provides negligible collision probability (birthday bound: ~4 billion before 50% collision chance).

**Fix:** Truncate only in `_contextpack_to_dict` serialization path, keeping full ETags internally for `state_store` compatibility. This is output-only truncation.

**Files:** `contextpack_engine.py:572`.

**Savings:** ~160 tokens per 20-slice request (~8% of budget). Each ETag saves 48 chars = ~12 tokens, times ~13 ETags per request.

### 3. Strip redundant fields from impact tool output (`tldr-swinton-osi`)

**Problem:** Impact tool output has 17% redundant fields:
- `truncated:false` on all nodes (only meaningful when `true`)
- Empty `callers:[]` on leaf nodes
- Derivable `caller_count` on all nodes (Claude can count the array)

**Fix:** Strip these in MCP layer or daemon before returning to Claude Code.

**Files:** `mcp_server.py:335-345`, `daemon.py`.

**Savings:** ~390 tokens per impact call. This is the single largest win in Phase 3.

### 4. Apply path compression in distill output and omit empty sections (`tldr-swinton-zza`)

**Problem:** The distill Key Functions section uses full file paths in call targets, while ultracompact format already has path dictionary compression. Also, Dependencies and Risk Areas sections render `- None` when empty — wasting tokens on nothing.

**Fix:** Apply the same path dictionary compression as ultracompact format. Omit sections entirely when their content is empty/none.

**Files:** `distill_formatter.py:100-153`, `115-124`.

**Savings:** ~200+ tokens per distill call.

### 5. Remove blank line separators in ultracompact format (`tldr-swinton-3bo`)

**Problem:** Ultracompact format emits an empty line after every symbol (`output_formats.py:458`). For 20 symbols this adds 20 blank lines. The format name implies maximum density. Additionally, there's a double-space before relevance tags when `line_info` is empty.

**Fix:** Remove the blank line separator. Fix the conditional spacing for relevance tags.

**Files:** `output_formats.py:444-460`.

**Savings:** ~15-20 tokens per request. Small but consistent.

### 6. Unwrap daemon status:ok wrapper in MCP tools (`tldr-swinton-4nf`)

**Problem:** All daemon-proxied MCP tools return `{status:ok, result:{...}}` wrapper. The `status:ok` field is never consumed by Claude Code — it only reads the `result`.

**Fix:** Unwrap in `_send_command` or create a `_send_and_unwrap` helper that returns just the result dict.

**Files:** `mcp_server.py:90-119`.

**Savings:** ~3-5 tokens per call. Tiny but trivially easy to implement.

### 7. Fix distill_formatter token estimator to use shared token_utils (`tldr-swinton-zhd`)

**Problem:** `distill_formatter.py:21-22` uses a local `_estimate_tokens` function that does `chars // 4` instead of the shared `token_utils.estimate_tokens` which tries tiktoken first for accurate counts. The inaccurate fallback can underestimate by 20-30% for code with special characters, causing budget overruns.

**Fix:** Import and use `token_utils.estimate_tokens` instead of the local function.

**Files:** `distill_formatter.py:21-22`.

**Savings:** Not a token savings issue — this is a correctness bug that can cause budget overruns when tiktoken is available but not used.

## Implementation Notes

- All changes are output-layer only — no changes to analysis engines or internal data structures
- The P3 issues can be done in any order; they are independent
- Issue `tldr-swinton-zhd` (bug) should arguably be done first since it affects budget calculations for other formatters
- Issues `tldr-swinton-osi` (impact stripping) and `tldr-swinton-u3k` (ETag truncation) together save ~550 tokens — over 25% of budget
- Consider batching all P3 issues into a single commit since they are all small, independent output-layer changes

## Command Output

```
Created issue: tldr-swinton-1vw  (Sparse meta dicts in diff-context output)
Created issue: tldr-swinton-u3k  (Truncate ETags to 16 chars in output serialization)
Created issue: tldr-swinton-osi  (Strip redundant fields from impact tool output)
Created issue: tldr-swinton-zza  (Apply path compression in distill output and omit empty sections)
Created issue: tldr-swinton-3bo  (Remove blank line separators in ultracompact format)
Created issue: tldr-swinton-4nf  (Unwrap daemon status:ok wrapper in MCP tools)
Created issue: tldr-swinton-zhd  (Fix distill_formatter token estimator to use shared token_utils)
```
