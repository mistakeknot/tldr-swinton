# Brainstorm: New Token-Savings Opportunities

**Date**: 2026-02-09
**Status**: Research complete — ready for prioritization
**Beads**: tldr-swinton-s5v, tldr-swinton-4u5, tldr-swinton-0ay, tldr-swinton-e5g, tldr-swinton-9us, tldr-swinton-yw8, tldr-swinton-jja, tldr-swinton-aqm, tldr-swinton-het, tldr-swinton-jji

---

## Landscape Summary

tldr-swinton currently achieves **48-93% token savings** across its various modes:

| Mode | Savings | Mechanism |
|------|---------|-----------|
| Compact signatures | ~93% | Signatures vs full files |
| Semantic search | ~85% | Results vs full repo |
| DiffLens (diff+deps) | ~48% | Diff-focused context |
| Agent workflow (chunk-summary) | ~84% | Compressed bodies |
| Delta mode (multi-turn) | ~60% | Unchanged symbol caching |

### What's already been brainstormed (Jan 28 batch)
Max output caps ✅ shipped, files-only listing, score gating, scoped search, stable IDs, multi-turn caching improvements, context labels, candidate cap + rerank, short vs full fetch.

### What's in the optimization roadmap but not yet built
PDG-guided slicing (#3), cost-based query planner (#5), CoverageLens (#9), prompt caching integration (#10), LLMLingua compression (#12), Merkle tree indexing (#13).

### Orphaned modules (built but unwired)
`attention_pruning.py`, `edit_locality.py`, `coherence_verify.py`, `context_delegation.py` — ~2000 lines ready for integration.

---

## New Opportunities (Not Previously Explored)

The following are **genuinely new** avenues — distinct from the existing roadmap items and Jan 28 brainstorms.

---

### 1. 🔬 Structured Output Serialization Optimization (`tldr-swinton-s5v`)

**Observation**: tldrs emits JSON and ultracompact text. Research shows poor data serialization can consume 40-70% of available tokens. JSON keys like `"signature"`, `"relevance"`, `"lines"`, `"code"` are repeated per slice.

**Opportunity**: Apply schema-aware compression to ContextPack output:
- **Column-oriented encoding**: Group all signatures together, all code blocks together, instead of row-per-slice
- **Key aliasing**: `"s"` for signature, `"c"` for code, `"r"` for relevance — with a header legend
- **Positional encoding**: Drop keys entirely for fixed-schema outputs (e.g., `["id","sig","code","lines"]` header + arrays)
- **Null elision**: Drop null/empty fields entirely instead of emitting them

**Estimated impact**: 15-30% additional savings on JSON outputs
**Effort**: Low (output_formats.py only)
**Risk**: Low — opt-in via `--format packed-json` or similar

---

### 2. 🔬 Incremental Diff Delivery (Textual Delta Encoding) (`tldr-swinton-4u5`)

**Observation**: Delta mode currently sends `[UNCHANGED]` or full code. There's no middle ground for *partially changed* symbols where most of the function body is the same but a few lines changed.

**Opportunity**: Emit only the *textual diff* of a symbol's code relative to its last-delivered version, rather than re-sending the full body:
- Send signature + unified diff of the code body
- Reference the etag of the previously delivered version
- Agent reconstructs full code by applying the diff to its cached version
- Falls back to full body if etag unknown or diff is larger than body

**Estimated impact**: 30-60% savings on *changed* symbols in multi-turn sessions (currently 0% savings on changed symbols)
**Effort**: Medium (delta.py + state_store.py + output_formats.py)
**Risk**: Medium — depends on agent/LLM ability to apply diffs; may need explicit "full vs diff" mode. Works best with tool-use agents that can programmatically apply patches.

---

### 3. 🔬 Hierarchical Progressive Disclosure (Zoom Levels) (`tldr-swinton-0ay`)

**Observation**: The existing roadmap mentions hierarchical repo map, but no brainstorm covers a *multi-resolution zoom* system. Agents currently get either signatures (too little) or full code (too much).

**Opportunity**: Define 4-5 progressively detailed "zoom levels" and let callers request the appropriate one:

| Level | Content | Typical tokens |
|-------|---------|----------------|
| L0: Module map | File list + 1-line descriptions | ~50/file |
| L1: Symbol index | Signatures + docstring-first-line | ~100/symbol |
| L2: Body sketch | Signature + control flow skeleton (if/for/try, no expressions) | ~200/symbol |
| L3: Windowed body | Signature + diff-relevant code windows | ~400/symbol |
| L4: Full body | Complete implementation | variable |

The key innovation is **L2: Body sketch** — extracting control flow structure without expressions. This gives agents enough to understand code *flow* without reading every line.

**Estimated impact**: L2 could provide 50-70% savings vs full bodies while preserving most structural information
**Effort**: Medium (new formatter + AST/tree-sitter traversal for control-flow skeleton extraction)
**Risk**: Low — additive feature with clear opt-in semantics

---

### 4. 🔬 Cross-Session Symbol Popularity Index (`tldr-swinton-e5g`)

**Observation**: `attention_pruning.py` tracks per-session usage, but there's no *cross-session* learning about which symbols are globally important across agent sessions. Some symbols (entry points, core utilities) are requested by every session.

**Opportunity**: Build a lightweight popularity index:
- Track which symbols are delivered and *used* across all sessions (not just one)
- Compute a global "importance score" per symbol
- Use this to pre-rank candidates in budget allocation: high-importance symbols get budget first
- Surface a `tldrs hotspots` command showing the most-used symbols
- Enable "popular-first" budget allocation: spend tokens on symbols agents actually use

**Estimated impact**: 10-20% savings by deprioritizing rarely-used symbols in budget allocation
**Effort**: Low (extend attention_pruning.py's SQLite schema + add a simple query to ContextPackEngine)
**Risk**: Very low — passive data collection + optional reranking

---

### 5. 🔬 AST-Aware Comment & Docstring Stripping (`tldr-swinton-9us`)

**Observation**: Docstrings are currently all-or-nothing (`--with-docs`). Comments are never stripped. In many codebases, comments and docstrings constitute 20-40% of symbol bodies.

**Opportunity**: Implement fine-grained comment/docstring stripping:
- **Strip inline comments** from code bodies (often noise for editing tasks)
- **Preserve only the first line** of docstrings (brief description)
- **Strip type-hint-only annotations** that are redundant with the signature
- **Preserve `# TODO` / `# FIXME` / `# HACK`** markers (high signal-to-noise)
- Apply via tree-sitter AST traversal for precision (not regex)

**Estimated impact**: 15-30% savings on code bodies, especially for well-documented Python codebases
**Effort**: Low-Medium (tree-sitter comment node filtering in hybrid_extractor.py)
**Risk**: Low — opt-in via `--strip-comments`; preserves all code logic

---

### 6. 🔬 Type-Directed Context Pruning (`tldr-swinton-yw8`)

**Observation**: SymbolKite and DiffLens expand to callers/callees uniformly. But not all callers/callees are equally informative — a function called by 50 callers doesn't need all 50 in context.

**Opportunity**: Use the *type signature* and *call pattern* to prune the expansion graph:
- If a function's signature fully describes its contract (e.g., `def is_valid(x: str) -> bool`), its callers don't need code bodies — the signature suffices
- If a callee is a well-known stdlib/framework function, omit it entirely
- If multiple callers have identical call patterns (same args), show one exemplar + count
- Group callers by call-site pattern and deduplicate

**Estimated impact**: 20-40% savings on callee/caller expansion (the "1-hop context" portion)
**Effort**: Medium (contextpack_engine.py + symbolkite.py)
**Risk**: Medium — needs care to avoid dropping actually-relevant callers. Gate behind research eval.

---

### 7. 🔬 Output Templating / Structural Caching (`tldr-swinton-jja`)

**Observation**: The `cache-friendly` output format exists but isn't integrated with LLM provider caching APIs. Provider prompt caching (Anthropic 90% savings, OpenAI 50%) is a massive multiplier that tldrs can't directly use from CLI, but can *optimize for*.

**Opportunity**: Maximize prompt cache hit rates by:
- **Deterministic slice ordering** in outputs (sorted by stable ID, not relevance)
- **Stable header/footer templates** that never change between calls
- **Prefix-first layout**: put unchanged signatures and stable metadata in a prefix block, dynamic content after a clear breakpoint
- **Emit cache hint metadata**: `<!-- cache_prefix_end: offset=2847 -->` so consuming agents know where to set the cache breakpoint

The key insight: tldrs can't *do* the caching, but it can structure output so consuming tools get maximum cache benefit.

**Estimated impact**: 50-90% cost savings (via provider caching) on the *unchanged portion* of context
**Effort**: Low (output_formats.py — `_format_cache_friendly` exists but needs polish)
**Risk**: Very low — purely additive

---

### 8. 🔬 Import Graph Compression (`tldr-swinton-aqm`)

**Observation**: ContextPack and DiffLens currently include full import lists for each file. Import statements are highly repetitive across files in a project (e.g., every file imports `from pathlib import Path`).

**Opportunity**: Deduplicate and compress the import context:
- Build a project-wide import frequency index
- Omit "ubiquitous" imports that appear in >50% of files (they're assumed knowledge)
- Group imports by source module (show `module: [name1, name2]` instead of individual lines)
- For cross-file context, show only *differential imports* (imports unique to this file)

**Estimated impact**: 10-20% savings on import-heavy context (especially Python projects with many small modules)
**Effort**: Low (can be done in output_formats.py using existing ModuleInfo data)
**Risk**: Very low — purely formatting optimization

---

### 9. 🔬 Sub-Agent Context Distillation Protocol (`tldr-swinton-het`)

**Observation**: Research shows that sub-agent architectures get major token savings by having sub-agents explore extensively but return condensed summaries (1000-2000 tokens) to the lead agent. `context_delegation.py` exists but isn't wired to support this pattern.

**Opportunity**: Create a formal "distillation" output mode optimized for sub-agent return values:
- `tldrs distill --project . --task "fix auth bug" --budget 1500` — runs full analysis but returns only the most relevant 1500 tokens
- Internally uses DiffLens + semantic search + call graph, but output is a single compressed summary
- Format is prescriptive: "Files to edit: X, Y. Key functions: A, B. Dependencies: C, D. Risk areas: E."
- This is different from `--budget` truncation — it's *semantic compression* of the full analysis, not just cutting off at a token limit

**Estimated impact**: 70-90% savings when used as a sub-agent return value (vs returning full context pack)
**Effort**: Medium-High (new command that composes existing engines + adds summarization)
**Risk**: Medium — quality of distillation matters a lot. Start with template-based, add LLM-based later.

---

### 10. 🔬 Workspace-Scoped Precomputed Context Bundles (`tldr-swinton-jji`)

**Observation**: Agents frequently re-derive the same context (diff-context, structure, imports) at the start of each session. Even with delta mode, the *first* call is always expensive.

**Opportunity**: Precompute and cache "context bundles" that capture the current workspace state:
- On `git commit` or on-demand: compute and cache the full context pack for current HEAD vs main
- Store as a VHS ref or in `.tldrs/cache/`
- On agent start: serve the precomputed bundle instantly (0 computation)
- Include: diff-context, top-K structure, import graph digest, active branch info
- Invalidate on file change (via filesystem watcher or git hooks)
- Could integrate with `session_warm.py` to trigger precomputation in the background

**Estimated impact**: Near-zero latency on first context request; amortizes computation across sessions
**Effort**: Medium (git hook + caching layer + invalidation logic)
**Risk**: Low — worst case, it's a stale cache that gets rebuilt on next call

---

## Priority Ranking (Recommended)

Based on effort/impact ratio and compatibility with existing infrastructure:

| Rank | Opportunity | Impact | Effort | Why |
|------|------------|--------|--------|-----|
| 1 | **#1: Serialization Optimization** | 15-30% | Low | Pure formatting change, no new infrastructure |
| 2 | **#5: Comment/Docstring Stripping** | 15-30% | Low | Tree-sitter infra exists, high ROI |
| 3 | **#7: Output Templating for Caching** | 50-90% cost | Low | `_format_cache_friendly` is 80% done |
| 4 | **#4: Cross-Session Popularity** | 10-20% | Low | Extends existing attention_pruning.py |
| 5 | **#8: Import Graph Compression** | 10-20% | Low | Data already available in ModuleInfo |
| 6 | **#3: Progressive Disclosure Zoom** | 50-70% | Medium | Novel, differentiated feature |
| 7 | **#6: Type-Directed Pruning** | 20-40% | Medium | Requires careful eval gating |
| 8 | **#2: Incremental Diff Delivery** | 30-60% | Medium | High value for multi-turn, but complex |
| 9 | **#10: Precomputed Bundles** | Latency win | Medium | Good DX, not direct token savings |
| 10 | **#9: Sub-Agent Distillation** | 70-90% | High | Powerful but needs summarization quality |

---

## Evaluation Strategy

All new features should be gated by the existing eval suite:

```bash
# Baseline (run before changes)
.venv/bin/python evals/difflens_eval.py
.venv/bin/python evals/agent_workflow_eval.py
.venv/bin/python evals/token_efficiency_eval.py

# Gate: ≥10% additional savings on at least one eval, no regressions on others
```

For multi-turn features (#2, #4, #10), add a new eval:
```bash
.venv/bin/python evals/multiturn_delta_eval.py  # New eval needed
```

---

## Next Steps

1. Review and approve/reject individual opportunities
2. Select top 2-3 for immediate implementation planning
3. Create implementation plans for approved items
4. Build prototypes behind `--flag` gates
5. Evaluate against existing evals before promotion
