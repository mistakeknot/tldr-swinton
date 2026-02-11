# Prompt Cache Optimization Brainstorm

**Date:** 2026-02-10
**Bead:** tldr-swinton-jja (P2)
**Status:** Ready for planning

## What We're Building

Polish and fully integrate `_format_cache_friendly()` in output_formats.py so tldrs output maximizes LLM provider prompt cache hit rates. Anthropic's prompt caching gives 90% cost reduction on cached prefixes; OpenAI gives 50%. This is a multiplier on all other token savings features.

## Current State

The existing `_format_cache_friendly()` (output_formats.py:438-578) already:
- Separates unchanged symbols (CACHE PREFIX) from changed (DYNAMIC CONTENT)
- Sorts prefix by stable symbol ID for cache stability
- Estimates tokens via tiktoken for each section
- Emits `<!-- CACHE_BREAKPOINT: ~N tokens -->` marker
- Displays cache_stats (hit_rate, hits, misses) if available from delta mode

## Provider Caching Landscape

| Aspect | Anthropic | OpenAI |
|--------|-----------|--------|
| Activation | Explicit `cache_control` blocks (up to 4) | Automatic on prefix ≥1024 tokens |
| Match requirement | Byte-exact match up to breakpoint | Hash of first 256+ tokens for routing |
| Cost savings | 90% on cache reads (10% of input price) | 50% discount on cached tokens |
| TTL | 5 min (ephemeral) or 1 hour | 5-10 min auto-eviction |
| Developer control | Places up to 4 breakpoints | No explicit control |

**Key implication:** Anthropic requires byte-exact prefix matches. Even a single character change invalidates the cache. OpenAI is more forgiving (hash-based routing) but still benefits from stable prefixes. Our format must be deterministic to the byte.

## Gaps to Close

### Gap 1: Non-Deterministic Ordering
The dynamic section sorts by relevance label string (`contains_diff`, `caller`, etc.) then symbol ID. Relevance labels can change between calls, causing the entire section after the breakpoint to shift.

**Decision:** Sort ALL slices by `(file_path, symbol_id)` — move relevance to a metadata annotation, not an ordering axis. This makes the entire output deterministic for a given set of symbols.

### Gap 2: No Stable Header Template
Output starts with `# tldrs cache-friendly output` — no project fingerprint.

**Decision:** Add structured header: `## Context for {project_name} @ {commit_sha_short}` plus format version. Header must be byte-identical for same project state across calls. Do NOT include timestamps (they'd break caching).

### Gap 3: No Machine-Readable Cache Hints
The `CACHE_BREAKPOINT` HTML comment is human-readable but not structured.

**Decision:** Emit a JSON metadata block at the top of cache-friendly output:
```json
{"cache_hints": {"prefix_tokens": 1200, "prefix_hash": "abc123...", "breakpoint_char_offset": 4850, "commit_sha": "def456...", "format_version": 1}}
```
Always present in cache-friendly format (not behind a flag). Provider-agnostic — includes enough info for any SDK to map to its native caching API.

### Gap 4: Hollow Slices in Non-Delta Path
When `tldrs context` (non-diff) uses `--format cache-friendly`, it creates slices with `code: None` and fake `relevance: "depth_N"`.

**Decision:** For non-delta context, put ALL symbol signatures in prefix (they're stable across calls for same commit), code bodies in dynamic. This makes the non-delta path useful for caching too — signatures are a stable prefix.

## Prefix Maximization Strategy

**Key insight:** Even for *changed* symbols, signatures usually stay the same when only the body changes. We should put ALL signatures in the prefix, not just unchanged ones.

### Prefix content (ordered, all stable):
1. **Project header** — name + commit SHA + format version
2. **Cache hints JSON** — metadata block
3. **ALL symbol signatures** — sorted by (file_path, symbol_id), includes changed symbols
4. **CACHE_BREAKPOINT marker**

### Dynamic content (after breakpoint):
5. **Changed symbol code bodies only** — sorted by (file_path, symbol_id)
6. **Stats footer**

This maximizes the prefix because:
- A function body edit doesn't invalidate the prefix (signature stays the same)
- Only adding/removing/renaming functions changes the prefix
- In typical edit sessions, 80-95% of calls have identical prefixes

### Future prefix sections (extension point for other features):
- Import graph digest (from `aqm`)
- File tree summary (from `jji` bundles)
- Type stubs (from `yw8` type pruning)

## Extension Point: prefix_sections

To support future features adding stable content to the prefix, `_format_cache_friendly()` will accept an optional `prefix_sections` parameter:

```python
prefix_sections: list[tuple[str, str]]  # [(section_name, rendered_text), ...]
```

Each tuple is `(name, content)` — the formatter concatenates them in order before the breakpoint. Default sections (header, hints, signatures) are always present. Future features append to this list.

This is deliberately simple — no protocol, no ABC, just a list of named strings. Features like import compression or bundle precomputation can add sections without modifying the formatter.

## Provider-Specific Notes (in docs, not code)

**For Anthropic users:**
- Place tldrs output in a `system` message content block
- Add `cache_control: {"type": "ephemeral"}` at the character offset from `breakpoint_char_offset`
- Verify prefix stability using `prefix_hash` — if hash changes between calls, cache will miss

**For OpenAI users:**
- No code changes needed — automatic prefix caching kicks in at ≥1024 tokens
- tldrs prefix-first layout naturally aligns with OpenAI's hash-based prefix routing
- Ensure tldrs output is at the START of the prompt (before user message)

## Feature Composition Matrix

| Feature | Cache-Friendly Interaction |
|---------|---------------------------|
| Zoom L0-L4 (0ay) | L1/L2 prefixes are MORE stable than L4 (sketches change less) |
| Distillation (het) | Too small to benefit (1-2K total) — skip |
| Type pruning (yw8) | Pruned callers reduce dynamic section |
| Comment stripping (9us) | Stripped code is more cacheable (comments change more often) |
| Popularity index (e5g) | Popular symbols get prefix budget priority |
| Incremental diff (4u5) | Diffs in dynamic section are smaller |
| JSON optimization (s5v) | Key aliasing must be deterministic; packed-json needs own cache variant |
| Precomputed bundles (jji) | Bundle IS the pre-serialized prefix |
| Import compression (aqm) | Common imports become a prefix section |

**Cache-friendly is the foundation layer.** Almost every other feature either feeds content into the prefix or benefits from smaller dynamic sections.

## Key Decisions Summary

1. **ALL signatures in prefix** — even for changed symbols (signatures rarely change)
2. **Sort everything by (file_path, symbol_id)** — not relevance
3. **JSON metadata block at top** — always present, provider-agnostic
4. **prefix_sections extension point** — simple list of (name, content) tuples
5. **Non-delta path puts signatures in prefix, bodies in dynamic** — useful for caching too
6. **No timestamps in prefix** — they'd break byte-exact matching
7. **Provider-agnostic format** — document how to map to Anthropic/OpenAI in docs
8. **Populate cache_stats everywhere** — including non-delta build_context_pack()

## Open Questions

None — ready for planning.

## Scope Estimate

- **Files modified:** output_formats.py, contextpack_engine.py, cli.py
- **New files:** None (extension point is in output_formats.py)
- **Estimated lines changed:** ~200 (up from ~150 with extension point)
- **Effort:** Low-Medium (one focused session)
- **Risk:** Very low — purely additive, opt-in format

## Sources

- [Anthropic Prompt Caching Docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [OpenAI Prompt Caching](https://platform.openai.com/docs/guides/prompt-caching)
- [OpenAI Prompt Caching Cookbook](https://cookbook.openai.com/examples/prompt_caching101)
