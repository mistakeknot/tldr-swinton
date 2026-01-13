# Context Optimization Roadmap

Token-efficient context retrieval features for tldr-swinton.

## Overview

These features build on tldr-swinton's existing infrastructure (AST parsing, call graphs, semantic search) to provide smarter, more targeted context retrieval for AI coding agents.

| Phase | Feature | Effort | Token Savings | Status |
|-------|---------|--------|---------------|--------|
| 0 | Quick Wins (Oracle Review) | 1-2 days | 2x+ | **Priority** |
| 1 | DiffLens | 2-3 days | 60-80% | Planned |
| 2 | SymbolKite | 1-2 days | 40-60% | Planned |
| 3 | Cassette Integration | 3-5 days | 70-90% | Planned |
| 4 | CoverageLens | 2-3 days | 50-70% | Planned |

---

## Phase 0: Quick Wins (Oracle Review)

**"Fix the foundation before building higher."**

These are immediate fixes identified through Oracle (GPT-5.2 Pro) review of the codebase. Each provides >2x token reduction with minimal effort.

### 0.1 Fix Call Graph Node Identity (Critical)

**Problem:** Call graph uses plain function names (`validate_token`) instead of qualified names (`auth.py:validate_token`). This causes:
- Ambiguous lookups when multiple files have same function name
- Incorrect caller/callee relationships
- Phantom connections between unrelated code

**Fix:**
```python
# Before (in call_graph.py)
edges.append((caller_name, callee_name))

# After
edges.append((f"{rel_path}:{caller_name}", f"{callee_path}:{callee_name}"))
```

**Files:** `src/tldr_swinton/call_graph.py`, `src/tldr_swinton/semantic.py`

**Impact:** Correct call graphs = correct context retrieval = massive token savings

### 0.2 Apply SKIP_DIRS Consistently

**Problem:** `get_relevant_context()` in `semantic.py` doesn't filter SKIP_DIRS, including `venv/`, `node_modules/`, etc.

**Fix:** Apply same filtering as index.py to all file traversal.

**Files:** `src/tldr_swinton/semantic.py`

### 0.3 Add Real Token Budget to `tldrs context`

**Problem:** Current `--depth` flag limits hop count, not token count. Depth 2 could be 50 tokens or 5000 tokens.

**Fix:**
```bash
# Add --budget flag
tldrs context validate_token --budget 2000  # Stop at 2000 tokens
```

**Implementation:**
- Add `tiktoken` for accurate token counting (or character approximation)
- Budget allocator: full code for highest-relevance, signatures for rest
- Stop expanding when budget exhausted

**Files:** `src/tldr_swinton/semantic.py`, `src/tldr_swinton/cli.py`

### 0.4 Add `--ultracompact` Output Format

**Problem:** Even "compact" format repeats file paths and has verbose structure.

**Dictionary-coded format:**
```
# Header: path dictionary
P0=src/auth.py P1=src/middleware.py P2=src/routes.py

# Body: compressed references
P0:validate_token(tok:str)->bool @45-72
  calls: P0:decode_jwt, P1:check_expiry
  callers: P2:login_handler
```

**Token savings:** 2-4x over current compact format

**Files:** `src/tldr_swinton/output_formats.py` (new)

### 0.5 Default `include_docstrings=False`

**Problem:** Docstrings often 30-50% of function size, rarely needed for modifications.

**Fix:** Change default, add `--with-docs` flag when needed.

**Files:** `src/tldr_swinton/cli.py`, `src/tldr_swinton/tree_sitter_extract.py`

### 0.6 Fix MCP Context Formatting

**Problem:** MCP server returns verbose dict representations instead of formatted output.

**Fix:** Apply same formatters used by CLI to MCP tool responses.

**Files:** `src/tldr_swinton/mcp_server.py`

### Success Metrics

- **Call graph accuracy**: Zero ambiguous node lookups
- **Token reduction**: >50% vs current output
- **Budget compliance**: Output within 5% of requested budget

---

## Innovation Opportunities (From Oracle Review)

These are more ambitious ideas for future consideration:

### Identifier Aliasing / Alpha-Renaming
Replace verbose identifiers with short aliases:
```python
# Original
def calculate_monthly_subscription_revenue(customer_id: str) -> Decimal

# Alpha-renamed (with legend)
def A(B:str)->C  # A=calculate_monthly_subscription_revenue, B=customer_id, C=Decimal
```
**Potential:** 20-40% additional savings

### Cost-Based Context Query Planner
Like database query optimization - given a task and budget, find the cheapest query plan that retrieves sufficient context.

### PDG-Guided Minimal Slices
Program Dependence Graph analysis to include only statements that affect the modification point. Often only 10-30% of a function body is relevant.

### Near-Duplicate Clustering
Use MinHash to detect near-duplicate functions (copy-paste code). Represent cluster with one exemplar + diff annotations.

### Hierarchical Repo Map
Graph coarsening: show modules at high level, expand only relevant subtrees.

### Stateful Delta-Context Protocol
Track what context the LLM has seen, send only deltas. 5-20x savings over multi-turn sessions.

---

## Phase 1: DiffLens

**"The only context that matters is the diff."**

Diff-first AST slicing that returns only the code relevant to current changes.

### Why It Matters

Current workflow:
```
Agent reads entire file (500 lines) → Makes small change → Reads file again
= 1000+ lines of context for a 10-line change
```

With DiffLens:
```
Agent gets diff hunks + enclosing functions + callers/callees (50-100 lines)
= 90% token reduction
```

### Commands

```bash
# Get context pack for current working tree changes
tldrs diff-context --base main

# Get context for a specific commit range
tldrs diff-context --base HEAD~3 --head HEAD

# With token budget
tldrs diff-context --base main --budget 2000

# Output formats
tldrs diff-context --base main --format json
tldrs diff-context --base main --format compact
```

### MCP Tools

```python
difflens.context(base_ref: str, budget: int = 4000) -> ContextPack
difflens.slice(symbol: str, depth: int = 1, budget: int = 1000) -> str
difflens.deps(symbol: str, direction: "callers" | "callees", depth: int = 1) -> list[Symbol]
```

### Algorithm

1. **Get diff hunks**: Parse `git diff --unified=0` output
2. **Map to symbols**: For each hunk, find enclosing function/class using AST
3. **Expand context**: Add 1-hop callers and callees from call graph
4. **Rank by relevance**:
   - Symbols containing diff hunks (highest)
   - Direct callers/callees
   - Test files referencing changed symbols
5. **Budget constraint**: Include full code for top items, signatures only for rest
6. **Output**: Ordered slices with stable IDs

### Output Format

```json
{
  "base": "main",
  "head": "HEAD",
  "budget_used": 1847,
  "slices": [
    {
      "id": "src/auth.ts:validateToken",
      "relevance": "contains_diff",
      "signature": "async function validateToken(token: string): Promise<boolean>",
      "code": "async function validateToken(token: string): Promise<boolean> {\n  ...\n}",
      "lines": [45, 72],
      "diff_lines": [52, 53, 58]
    },
    {
      "id": "src/middleware.ts:authMiddleware",
      "relevance": "caller",
      "signature": "function authMiddleware(req, res, next): void",
      "code": null,  // Over budget, signature only
      "lines": [12, 45]
    }
  ],
  "signatures_only": [
    "src/routes/api.ts:handleLogin",
    "src/routes/api.ts:handleLogout"
  ]
}
```

### Implementation

Builds on existing:
- `tldrs calls` / `tldrs impact` for call graph
- AST parsing from tree-sitter
- File hashing from index system

New code:
- Git diff parser
- Hunk-to-symbol mapper
- Budget allocator
- Context pack formatter

### Success Metrics

- **Tokens per PR review**: Target 70% reduction vs full-file reads
- **Relevance hit rate**: >90% of actual changes covered by context pack
- **Latency**: <500ms for typical diffs

---

## Phase 2: SymbolKite Enhancements

**"Repo map, but queryable."**

Enhanced symbol querying with budget-aware slicing and delta retrieval.

### Why It Matters

Current: Agent reads entire files to understand an API
With SymbolKite: Agent queries for exactly the symbols it needs

### Commands

```bash
# Find symbols by name/pattern
tldrs symbol find "PaymentService"
tldrs symbol find "validate*" --kind function

# Get minimal context for a symbol
tldrs symbol slice PaymentService --depth 1 --budget 1200

# Get callers/callees
tldrs symbol callers PaymentService.refund --limit 10
tldrs symbol callees PaymentService.refund --depth 2

# Get symbol with ETag for caching
tldrs symbol get src/auth.ts:validateToken --etag
```

### MCP Tools

```python
symbols.search(query: str, kind: str = None, limit: int = 20) -> list[SymbolMatch]
symbols.slice(symbol_id: str, depth: int = 1, budget: int = 1000) -> SymbolSlice
symbols.get(symbol_id: str, etag: str = None) -> SymbolContent | "UNCHANGED"
symbols.callers(symbol_id: str, limit: int = 10) -> list[CallSite]
symbols.callees(symbol_id: str, depth: int = 1) -> list[Symbol]
```

### Delta Retrieval (ETag Support)

```python
# First request
result = symbols.get("src/auth.ts:validateToken")
# Returns: { etag: "a1b2c3", content: "...", lines: [45, 72] }

# Subsequent request with etag
result = symbols.get("src/auth.ts:validateToken", etag="a1b2c3")
# Returns: "UNCHANGED" if no changes
# Returns: { etag: "d4e5f6", diff: "...", content: "..." } if changed
```

### Implementation

Enhance existing symbol index:
- Add ETag (content hash) to symbol metadata
- Add depth-limited dependency closure
- Add budget-aware output truncation

### Success Metrics

- **Cache hit rate**: >60% of repeated symbol reads return UNCHANGED
- **Query latency**: <100ms for symbol lookups
- **Slice accuracy**: Dependency closure includes all compile-time deps

---

## Phase 3: Cassette Integration

**"Stop pasting logs. Paste hashes."**

Integration with Cassette content-addressed object store for tool outputs.

### Why It Matters

Current: Agent runs tests → 2000 lines dumped into context
With Cassette: Agent gets `cass://a1b2c3` → fetches only relevant 30 lines

### Commands

```bash
# Store tldrs output in Cassette
tldrs diff-context --base main --output cassette
# Returns: cass://9f3a2c

# Reference Cassette objects in context
tldrs context validateToken --include cass://9f3a2c
```

### MCP Tools

```python
# tldrs tools that work with Cassette references
difflens.context(..., store_in_cassette: bool = False) -> str | CassetteRef
symbols.slice(..., store_in_cassette: bool = False) -> str | CassetteRef
```

### Integration Points

1. **Output to Cassette**: Any tldrs output can be stored as a Cassette object
2. **Reference in context packs**: Context packs can include Cassette refs instead of inline code
3. **Hybrid retrieval**: Mix inline code (small) + Cassette refs (large)

### Prerequisites

- Cassette CLI and MCP server must be installed
- Cassette daemon running locally

### Implementation

- Add `--output cassette` flag to relevant commands
- Add Cassette ref support to context pack format
- Add `cassette.store()` calls for large outputs

---

## Phase 4: CoverageLens

**"Use execution to choose context."**

Coverage-guided context selection that uses runtime data to rank relevance.

### Why It Matters

Static analysis guesses what's relevant. Coverage knows what actually ran.

### Commands

```bash
# Generate context from coverage data
tldrs coverage-context --coverage-file coverage.json --budget 2000

# Run tests with coverage and get context for failures
tldrs coverage-context --run "pytest --cov" --failures-only

# Combine with diff context
tldrs diff-context --base main --coverage coverage.json
```

### MCP Tools

```python
coverage.context(coverage_file: str, budget: int = 2000) -> ContextPack
coverage.rank_files(coverage_file: str, top_n: int = 20) -> list[RankedFile]
coverage.slice(coverage_file: str, file: str, hit_lines_only: bool = True) -> str
```

### Supported Coverage Formats

| Tool | Format | Language |
|------|--------|----------|
| pytest-cov | .coverage / coverage.json | Python |
| nyc / c8 | coverage/lcov.info | JavaScript/TypeScript |
| go test | coverprofile | Go |
| cargo tarpaulin | cobertura.xml | Rust |

### Algorithm

1. **Parse coverage**: Extract file → line hits mapping
2. **Map to symbols**: Convert hit lines to functions/methods
3. **Rank by coverage**:
   - Functions with failing assertions (highest)
   - Functions with most hits in failing tests
   - Functions in call path to failures
4. **Budget allocation**: Prioritize high-coverage functions
5. **Output**: Coverage-ranked context pack

### Implementation

- Coverage file parsers (pytest-cov, nyc, go cover)
- Coverage-to-symbol mapper
- Coverage-aware ranking in context packs

### Success Metrics

- **Failure fix rate**: >80% of failures fixed with coverage-guided context
- **Tokens per fix**: 50% reduction vs static analysis only
- **Supported ecosystems**: Python, JS/TS, Go, Rust

---

## Architecture

All features share core infrastructure:

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI / MCP Server                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ DiffLens    │  │ SymbolKite  │  │ CoverageLens            │ │
│  │             │  │             │  │                         │ │
│  │ diff-context│  │ slice       │  │ coverage-context        │ │
│  │ diff hunks  │  │ search      │  │ rank files              │ │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘ │
│         │                │                     │               │
│         └────────────────┼─────────────────────┘               │
│                          │                                     │
│                   ┌──────▼──────┐                              │
│                   │ Context     │                              │
│                   │ Budget      │                              │
│                   │ Allocator   │                              │
│                   └──────┬──────┘                              │
│                          │                                     │
├──────────────────────────┼──────────────────────────────────────┤
│                   ┌──────▼──────┐                              │
│                   │   Existing  │                              │
│                   │   Index     │                              │
│                   │             │                              │
│                   │ • Symbols   │                              │
│                   │ • Call graph│                              │
│                   │ • Embeddings│                              │
│                   │ • File hash │                              │
│                   └─────────────┘                              │
│                                                                 │
│              .tldrs/index/{vectors.faiss, units.json}          │
└─────────────────────────────────────────────────────────────────┘
```

## Timeline

| Week | Deliverable |
|------|-------------|
| 1 | DiffLens MVP: `tldrs diff-context` with basic budget |
| 2 | DiffLens polish: MCP tools, compact format, tests |
| 3 | SymbolKite: `tldrs symbol slice`, ETag support |
| 4 | Cassette integration (if Cassette available) |
| 5-6 | CoverageLens: pytest-cov + nyc support |

## Open Questions

1. **Budget units**: Tokens (requires tokenizer) or characters/lines (simpler)?
2. **MCP server**: Extend existing daemon or separate server?
3. **Cassette dependency**: Optional or required for some features?
4. **Coverage persistence**: Store coverage data in .tldrs/ or ephemeral?
