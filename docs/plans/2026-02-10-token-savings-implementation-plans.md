# Token Savings: Implementation Plans & Parallelization Analysis

**Date:** 2026-02-10
**Covers:** 10 open beads from the token-savings roadmap
**Goal:** Actionable plans + dependency graph to enable maximum parallelism

---

## Dependency Graph

```
                    ┌──────────────────────────────────────────────────┐
                    │            INDEPENDENT (Parallel Wave 1)         │
                    ├──────────────────────────────────────────────────┤
                    │                                                  │
  ┌─────────────┐  │  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │
  │  yqm (P3)   │  │  │  0ay (P1)   │  │  9us (P2)   │  │ s5v (P2) │ │
  │ dedup token │  │  │ zoom levels │  │ strip cmts  │  │ packed   │ │
  │  estimator  │──┼──│ zoom.py NEW │  │ strip.py NEW│  │ JSON     │ │
  └─────────────┘  │  └──────┬──────┘  └─────────────┘  └──────────┘ │
                    │         │                                        │
                    │  ┌──────────────┐  ┌─────────────┐              │
                    │  │  aqm (P3)    │  │  e5g (P2)   │              │
                    │  │ import       │  │ popularity  │              │
                    │  │ compression  │  │ index       │              │
                    │  └──────────────┘  └─────────────┘              │
                    └──────────────────────────────────────────────────┘

                    ┌──────────────────────────────────────────────────┐
                    │            DEPENDENT (Parallel Wave 2)           │
                    ├──────────────────────────────────────────────────┤
                    │                                                  │
                    │  ┌─────────────┐  ┌─────────────┐               │
                    │  │  yw8 (P2)   │  │  4u5 (P2)   │               │
                    │  │ type prune  │  │ incremental  │               │
                    │  │ (needs 0ay  │  │ diff (needs  │               │
                    │  │  for zoom)  │  │ state_store) │               │
                    │  └─────────────┘  └─────────────┘               │
                    └──────────────────────────────────────────────────┘

                    ┌──────────────────────────────────────────────────┐
                    │          INTEGRATION (Sequential Wave 3)         │
                    ├──────────────────────────────────────────────────┤
                    │                                                  │
                    │  ┌─────────────┐  ┌─────────────┐               │
                    │  │  het (P2)   │  │  jji (P3)    │               │
                    │  │ distillation│  │ precomputed  │               │
                    │  │ (wires many │  │ bundles      │               │
                    │  │  modules)   │  │ (needs delta │               │
                    │  └─────────────┘  │  + warm)     │               │
                    │                   └──────────────┘               │
                    └──────────────────────────────────────────────────┘
```

## Parallelization Summary

### Wave 1 — Fully Independent (6 beads, all parallelizable)

| Bead | Feature | Touches | Why Independent |
|------|---------|---------|-----------------|
| **yqm** | Dedup `_estimate_tokens()` | contextpack_engine.py, output_formats.py | Extracts shared utility, no API change |
| **0ay** | Zoom levels L0-L4 | NEW zoom.py, contextpack_engine.py, output_formats.py, cli.py | Adds new module + parameter, additive |
| **9us** | Comment/docstring stripping | NEW strip.py, contextpack_engine.py, cli.py | Adds new module + parameter, additive |
| **s5v** | Packed/columnar JSON | output_formats.py, cli.py | New output formats only |
| **aqm** | Import compression | NEW import_compress.py, output_formats.py, cli.py | New module + output modification |
| **e5g** | Popularity index | attention_pruning.py, state_store.py, cli.py | Extends existing tracker, additive |

**Coordination needed**: Wave 1 beads that touch the same file (e.g., multiple beads modify `output_formats.py`) should coordinate on merge order. Recommend: `yqm` first (smallest), then others in any order.

### Wave 2 — Soft Dependencies (2 beads, parallelizable with each other)

| Bead | Feature | Depends On | Why |
|------|---------|------------|-----|
| **yw8** | Type-directed pruning | 0ay (soft) | Benefits from zoom levels for pruned symbols |
| **4u5** | Incremental diff | None (hard) | Extends state_store.py schema |

Both can start after Wave 1 lands (or in parallel with Wave 1 if willing to resolve merge conflicts).

### Wave 3 — Integration (2 beads, need most infrastructure in place)

| Bead | Feature | Depends On | Why |
|------|---------|------------|-----|
| **het** | Distillation protocol | 0ay, 9us, e5g (soft) | Orchestrates DiffLens + semantic + call graph into compressed output |
| **jji** | Precomputed bundles | delta.py stable, session_warm.py | Caches what delta produces |

---

## Individual Plans

---

### Plan: yqm — Deduplicate `_estimate_tokens()`

**Priority:** P3 | **Effort:** XS (30 min) | **Wave:** 1
**Risk:** Very low — pure refactoring

**Current state:** Two identical implementations:
- `output_formats.py:222` — takes `str | Iterable[str]`
- `contextpack_engine.py:490` — takes `str` only

**Plan:**
1. Create `src/tldr_swinton/modules/core/token_utils.py`:
   - Move the more general version (from output_formats.py) there
   - Also move `_get_tiktoken_encoder()` (shared lazy singleton)
2. Replace both call sites with `from .token_utils import estimate_tokens`
3. Drop the leading underscore (it's now a public utility)
4. Run `uv run pytest tests/ -v --timeout=60` — no behavior change expected
5. Commit

**Files:** NEW token_utils.py, MODIFY contextpack_engine.py, MODIFY output_formats.py

---

### Plan: 0ay — Hierarchical Progressive Disclosure (Zoom L0-L4)

**Priority:** P1 | **Effort:** M (half day) | **Wave:** 1
**Risk:** Low — additive, gated behind `--zoom` flag

**Key insight:** L2 (body sketch) is the innovation — extract control flow skeleton via tree-sitter, stripping expressions. Gives 50-70% savings vs full bodies.

**Plan:**
1. **Tests first** — create `tests/test_zoom.py`:
   - Test `extract_body_sketch()` on Python/TS/Go fixtures
   - Test `ZoomLevel` enum and `format_at_zoom()` for each level
   - Test L2 is 50%+ smaller than L4 on sample functions
2. **New module** — `modules/core/zoom.py` (~200 lines):
   - `ZoomLevel` enum: L0 (module map), L1 (symbol index), L2 (body sketch), L3 (windowed), L4 (full)
   - `extract_body_sketch(source, language)` — tree-sitter walk, emit only control flow + signatures
   - `format_at_zoom(candidate, level)` — dispatch per level
   - Reuse parsers from `hybrid_extractor.py`
3. **Modify `contextpack_engine.py`:**
   - Add `zoom_level: ZoomLevel = ZoomLevel.L4` param to `build_context_pack()`
   - In budget loop, call `format_at_zoom()` for token estimation
   - L0/L1 skip code extraction entirely
4. **Modify `output_formats.py`:**
   - Handle zoom-annotated slices (L2 gets `# ... (sketch)` markers)
   - L0 format: flat file list
5. **Modify `cli.py`:**
   - Add `--zoom` / `-z` to `context` and `diff-context`
   - Values: L0-L4, default L4
6. Run tests, commit

**Files:** NEW zoom.py, NEW test_zoom.py, MODIFY contextpack_engine.py, MODIFY output_formats.py, MODIFY cli.py

---

### Plan: 9us — AST-Aware Comment/Docstring Stripping

**Priority:** P2 | **Effort:** M (half day) | **Wave:** 1
**Risk:** Low — opt-in via `--strip-comments`

**Plan:**
1. **Tests first** — `tests/test_strip.py`:
   - Test Python: inline comments stripped, TODO/FIXME preserved
   - Test docstring truncation (keep first line only)
   - Test line number preservation (empty lines where comments were)
   - Test unsupported language falls through unchanged
2. **New module** — `modules/core/strip.py` (~200 lines):
   - `StripConfig` dataclass with toggles
   - `strip_code(source, language, config)` — tree-sitter walk, identify comment/docstring nodes
   - Node type mapping per language (Python `comment`, JS `comment`, Go `comment`, etc.)
   - Preserve TODO/FIXME/HACK/XXX/NOTE markers
   - `estimate_savings(source, language)` for diagnostics
3. **Modify `contextpack_engine.py`:**
   - Add `strip_comments: bool = False` to `build_context_pack()`
   - Apply after code extraction, before budget estimation
4. **Modify `cli.py`:**
   - Add `--strip-comments` flag, default off
   - Presets: `minimal`, `aggressive`, `default`
5. Run tests, commit

**Files:** NEW strip.py, NEW test_strip.py, MODIFY contextpack_engine.py, MODIFY cli.py

---

### Plan: s5v — Structured Output Serialization Optimization

**Priority:** P2 | **Effort:** S (2-3 hours) | **Wave:** 1
**Risk:** Very low — new format options, existing formats unchanged

**Plan:**
1. **Tests first** — `tests/test_packed_json.py`:
   - Round-trip: pack → unpack preserves all data
   - Key aliasing produces smaller output
   - Columnar encoding/decoding
   - Null elision doesn't drop required fields
2. **New module** — `modules/core/json_codec.py` (~100 lines):
   - `pack_json(data, aliases)` / `unpack_json(packed)`
   - `to_columnar(slices)` / `from_columnar(columnar)`
   - Alias map: `{"i":"id", "g":"signature", "c":"code", "l":"lines", "r":"relevance"}`
3. **Modify `output_formats.py`:**
   - Add `_format_packed_json(pack)` — key aliasing + null elision + path dict
   - Add `_format_columnar_json(pack)` — column-oriented layout
   - Register in `format_context_pack()` dispatcher
4. **Modify `cli.py`:**
   - Extend `--format` choices: add `packed-json`, `columnar-json`
5. Run tests, commit

**Files:** NEW json_codec.py, NEW test_packed_json.py, MODIFY output_formats.py, MODIFY cli.py

---

### Plan: aqm — Import Graph Compression

**Priority:** P3 | **Effort:** S (2-3 hours) | **Wave:** 1
**Risk:** Very low — purely formatting

**Plan:**
1. **Tests first** — `tests/test_import_compress.py`:
   - Frequency index computation
   - Ubiquitous import detection at different thresholds
   - Grouped format output
   - Unique import extraction per file
2. **New module** — `modules/core/import_compress.py` (~150 lines):
   - `ImportFrequencyIndex.build(modules)` — scan + count
   - `get_ubiquitous(threshold=0.5)` — imports in >50% of files
   - `compress_imports(modules, threshold)` → common + per-file unique
   - `format_common_imports(common)` — single-line grouped format
3. **Modify `output_formats.py`:**
   - When compression enabled, emit "Common Imports" header once, per-file unique only
   - Apply in ultracompact and JSON formats
4. **Modify `contextpack_engine.py`:**
   - Add `compress_imports: bool = False` param
   - Compute ImportFrequencyIndex when enabled
5. **Modify `cli.py`:**
   - Add `--compress-imports` flag
6. Run tests, commit

**Files:** NEW import_compress.py, NEW test_import_compress.py, MODIFY output_formats.py, MODIFY contextpack_engine.py, MODIFY cli.py

---

### Plan: e5g — Cross-Session Symbol Popularity Index

**Priority:** P2 | **Effort:** M (half day) | **Wave:** 1
**Risk:** Very low — passive collection + optional reranking

**Plan:**
1. **Tests first** — `tests/test_popularity.py`:
   - Global popularity aggregation from mock sessions
   - Score blending (session vs global)
   - Cold start behavior (no global data → pure session score)
   - Hotspots command output
2. **Extend `attention_pruning.py`:**
   - Add `global_popularity` SQLite table
   - `update_global_popularity(session_id)` — aggregate from completed session
   - `get_global_popularity(symbol_ids)` → dict[str, float]
   - Modify `compute_attention_score()` to blend: `0.5 * session + 0.5 * global`
   - Cold start: pure session score for first 3 sessions
3. **Modify `state_store.py`:**
   - Add `close_session(session_id)` — triggers popularity update
4. **Modify `contextpack_engine.py`:**
   - Use global popularity to break ties in budget allocation
5. **Modify `cli.py`:**
   - Add `tldrs hotspots` command with `--top N`, `--since DAYS`, `--format json`
6. Run tests, commit

**Files:** MODIFY attention_pruning.py, MODIFY state_store.py, MODIFY contextpack_engine.py, MODIFY cli.py, NEW test_popularity.py

---

### Plan: yw8 — Type-Directed Context Pruning

**Priority:** P2 | **Effort:** M-L (half to full day) | **Wave:** 2
**Risk:** Medium — over-pruning could remove important context
**Soft dependency:** Benefits from 0ay (zoom levels for pruned symbols)

**Plan:**
1. **Tests first** — `tests/test_type_pruner.py`:
   - Self-documenting detection (typed vs untyped, simple vs complex)
   - Stdlib/framework detection
   - Caller grouping by pattern
   - Fan-out capping
2. **New module** — `modules/core/type_pruner.py` (~250 lines):
   - `is_self_documenting(func)` — full type annotations + simple body
   - `is_stdlib_or_framework(module_path, func_name)` — allowlist
   - `group_callers_by_pattern(callers)` → exemplar + count per group
   - `prune_expansion(candidates, callee_info)` → pruned list
3. **Modify `engines/symbolkite.py`:**
   - Apply `prune_expansion()` after BFS expansion
4. **Modify `engines/difflens.py`:**
   - Apply same pruning after `map_hunks_to_symbols()`
5. **Modify `contextpack_engine.py`:**
   - Add `enable_type_pruning: bool = False` param
   - Run as post-processor before budget allocation
6. **Modify `cli.py`:**
   - Add `--type-prune` flag
7. Run tests + evals, commit

**Files:** NEW type_pruner.py, NEW test_type_pruner.py, MODIFY symbolkite.py, MODIFY difflens.py, MODIFY contextpack_engine.py, MODIFY cli.py

---

### Plan: 4u5 — Incremental Diff Delivery

**Priority:** P2 | **Effort:** M (half day) | **Wave:** 2
**Risk:** Medium — depends on agent/LLM ability to apply diffs

**Plan:**
1. **Tests first** — `tests/test_incremental_diff.py`:
   - compute_symbol_diff with small/large changes
   - is_diff_worthwhile threshold logic
   - format_incremental output format
   - End-to-end: multi-turn with incremental changes
2. **New module** — `modules/core/incremental_diff.py` (~120 lines):
   - `compute_symbol_diff(old_code, new_code)` → unified diff or None
   - `is_diff_worthwhile(diff, full_code, threshold=0.7)` — diff saves >30%
   - `format_incremental(symbol_id, signature, diff, base_etag)` — output format
3. **Modify `state_store.py`:**
   - Add `code_snapshot TEXT` column to deliveries (migration logic)
   - `get_previous_code(session_id, symbol_id)` → Optional[str]
   - UPSERT to keep only latest snapshot per symbol
4. **Modify `engines/delta.py`:**
   - After identifying changed symbols, try incremental diff
   - If worthwhile → use diff representation; else → full code
   - Add `representation='incremental'` to delivery records
5. **Modify `output_formats.py`:**
   - Handle `representation='incremental'` in all format modes
6. **Modify `cli.py`:**
   - Add `--incremental` flag (only valid with `--delta`)
7. Run tests, commit

**Files:** NEW incremental_diff.py, NEW test_incremental_diff.py, MODIFY state_store.py, MODIFY delta.py, MODIFY output_formats.py, MODIFY cli.py

---

### Plan: het — Sub-Agent Context Distillation Protocol

**Priority:** P2 | **Effort:** L (full day) | **Wave:** 3
**Risk:** Medium — quality of distillation matters
**Dependencies:** Benefits from 0ay (zoom for fallback), 9us (stripping), e5g (popularity ranking)

**Plan:**
1. **Tests first** — `tests/test_distill.py`:
   - Distillation on mock candidates produces structured output
   - Budget enforcement (sections trimmed from bottom)
   - Format variants (text, json)
   - Fallback to L1 zoom when budget < 500 tokens
2. **Revive `context_delegation.py`:**
   - Add `distill(project_root, task, budget, session_id)` → DistilledContext
   - Orchestrate: DiffLens → semantic search → SymbolKite → merge + rank → compress
3. **New module** — `modules/core/distill_formatter.py` (~150 lines):
   - `DistilledContext` dataclass: files_to_edit, key_functions, dependencies, risk_areas, summary
   - `format_distilled(context, budget)` — prescriptive format
   - Budget enforcement: trim sections from bottom (risk → deps → functions → files)
4. **Modify `cli.py`:**
   - Add `tldrs distill` command
   - `--task` (required), `--budget` (default 1500), `--session-id`, `--format`
5. Run tests + quality eval, commit

**Files:** MODIFY context_delegation.py, NEW distill_formatter.py, NEW test_distill.py, MODIFY cli.py

---

### Plan: jji — Workspace-Scoped Precomputed Context Bundles

**Priority:** P3 | **Effort:** M-L (half to full day) | **Wave:** 3
**Risk:** Low — worst case is stale cache that rebuilds
**Dependencies:** Needs delta.py stable, session_warm.py

**Plan:**
1. **Tests first** — `tests/test_bundle.py`:
   - build_bundle produces valid bundle
   - is_bundle_stale detects file changes
   - bundle_to_context_pack conversion
   - Prebuild → context command uses bundle (no live computation)
2. **New module** — `modules/core/bundle.py` (~250 lines):
   - `Bundle` dataclass: diff_context, structure, import_graph, branch_info, metadata
   - `build_bundle(project_root, base_ref)` — run DiffLens + SymbolKite + imports + git info
   - `load_bundle(project_root)` → Optional[Bundle] — check cache
   - `is_bundle_stale(bundle, project_root)` — SHA + mtime comparison
   - `cleanup_old_bundles(project_root, keep=5)`
3. **Modify `session_warm.py`:**
   - Integrate bundle building into `maybe_warm_background()`
4. **Modify `engines/delta.py`:**
   - Check bundle cache before live computation
   - `bundle_to_context_pack(bundle)` conversion
5. **Modify `cli.py`:**
   - Add `tldrs prebuild` command with `--install-hook`
   - Transparent cache use in `context` and `diff-context`
6. Run tests + benchmark, commit

**Files:** NEW bundle.py, NEW test_bundle.py, MODIFY session_warm.py, MODIFY delta.py, MODIFY cli.py

---

## Shared File Conflict Matrix

Shows which beads touch the same files — key for parallelization planning:

| File | yqm | 0ay | 9us | s5v | aqm | e5g | yw8 | 4u5 | het | jji |
|------|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|
| contextpack_engine.py | ✓ | ✓ | ✓ | | ✓ | ✓ | ✓ | | | |
| output_formats.py | ✓ | ✓ | | ✓ | ✓ | | | ✓ | | |
| cli.py | | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| delta.py | | | | | | | | ✓ | | ✓ |
| attention_pruning.py | | | | | | ✓ | | | | |
| state_store.py | | | | | | ✓ | | ✓ | | |
| session_warm.py | | | | | | | | | | ✓ |
| symbolkite.py | | | | | | | ✓ | | | |
| difflens.py | | | | | | | ✓ | | | |
| context_delegation.py | | | | | | | | | ✓ | |
| hybrid_extractor.py | | | | | | | | | | |

**Hottest files:** `cli.py` (9/10 beads), `contextpack_engine.py` (6/10), `output_formats.py` (5/10).

**Recommended merge order for Wave 1:**
1. **yqm** first (smallest, cleans up shared code others depend on)
2. **s5v** next (only touches output_formats.py + cli.py — narrow scope)
3. **aqm** next (new module + light output_formats.py changes)
4. **9us** and **0ay** in either order (both add new modules + contextpack_engine.py params)
5. **e5g** last in wave (extends attention_pruning.py + state_store.py independently)

---

## Recommended Execution Strategy

**Fastest path to maximum impact:**

1. Land **yqm** immediately (30-min tech debt cleanup, unblocks clean imports)
2. Start **0ay** (P1, highest impact, medium effort)
3. Simultaneously start **s5v** + **9us** + **aqm** (no overlap with 0ay's core files)
4. Start **e5g** after reviewing attention_pruning.py changes from #2
5. Once Wave 1 is merged, start **yw8** + **4u5** in parallel
6. Finally, **het** + **jji** integrate everything

**Total estimated effort:** ~4-5 days for one engineer sequentially, or ~2-3 days with 2 parallel tracks.
