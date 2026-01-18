# ContextPack Engine Design (Phase 1)

**Goal:** Unify DiffLens and SymbolKite behind a shared ContextPack Engine that owns symbol identity, budget allocation, output formatting, and ETag caching.

**Architecture:** Add a core engine module with a Symbol Registry, Budget Allocator, and ContextPack Formatter. DiffLens and SymbolKite become query planners that produce candidate symbols + relevance; the engine builds a stable ContextPack output. MCP/CLI use the same engine output for consistency.

**Scope:** Phase 1 refactor for unified output + budget logic; no change to underlying analyzers beyond adapter layers.

## Components

### ContextPack Engine
- Inputs: candidate list (`symbol_id`, `relevance`, `reason`, optional `depth`)
- Outputs: `ContextPack` (ordered slices + metadata; signature-only slices use `code: null`)
- Responsibilities:
  - Normalize and resolve symbol IDs
  - Rank candidates by relevance + depth
  - Allocate budget tiers (full code vs signature-only)
  - Materialize slices (signature, code, line ranges)
  - Attach ETag hashes

### Symbol Registry
- Canonical ID: `rel_path:qualified_name`
- Resolves metadata:
  - signature (language-aware)
  - file, lines
  - etag (content hash)
- De-duplicates ambiguous names; returns candidate list

### Budget Allocator
- Determines per-symbol inclusion tier
- Keeps output under token budget
- Strategy: include full code for highest relevance, signatures for rest

### Output Formatter
- Text, ultracompact, JSON
- Single formatter used by DiffLens and SymbolKite

### Disambiguation
- Returns candidates for ambiguous symbol queries
- Avoids silent selection

## Data Flow

1. **Planner** (DiffLens/SymbolKite) builds candidate list with relevance.
2. **Engine** resolves symbols and ranks candidates.
3. **Allocator** applies budget to decide full vs signature.
4. **Formatter** emits unified ContextPack output.

## Migration Plan

1. Add new engine/registry modules without changing behavior.
2. Route DiffLens output through engine formatter.
3. Route SymbolKite output through engine formatter.
4. Move budget logic into engine.
5. Update MCP tools to return engine output.

## Risks
- Budget estimation accuracy
- Ambiguous symbol resolution edge cases
- Consistency across languages

## Testing
- Unit tests for registry, allocator, formatter
- Regression tests for DiffLens/SymbolKite equivalence
- MCP/CLI integration tests
