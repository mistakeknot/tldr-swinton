# Context Optimization Roadmap

Token-efficient context retrieval features for tldr-swinton.

---

## Current Priority: Next 3 Features

Based on Oracle evaluation (2026-01-17), these are the highest-impact improvements:

| # | Feature | Impact | Effort | Status | Plan |
|---|---------|--------|--------|--------|------|
| **1** | **Automatic ETag/Delta Context** | 2-5x multi-turn savings | 3-5 days | **Next** | [Plan](2026-01-17-automatic-etag-delta-context.md) |
| **2** | Frictionless VHS Refs | 90%+ large output savings | 2-3 days | Planned | [Plan](2026-01-17-frictionless-vhs-refs.md) |
| **3** | PDG-Guided Slicing | 30-50% function body savings | 3-4 days | Planned | [Plan](2026-01-17-pdg-guided-slicing.md) |

### Why This Order

1. **ETag/Delta first** - Targets the #1 token sink (multi-turn repetition). Primitives exist, need session-level automation.
2. **VHS second** - Quick win: vendor ~330 LOC, eliminate install friction. Enables auto-switch for large outputs.
3. **PDG third** - Requires more careful testing (edit-safety). Has promotion gate (≥10% savings, no regressions).

### Full Priority Queue

After top 3 features, here's the complete prioritized backlog:

| # | Feature | Impact | Effort | Status | Rationale |
|---|---------|--------|--------|--------|-----------|
| **4** | **Hybrid BM25+Embedding+Rerank** | Scale-robust retrieval | Low | Research | Sourcegraph's insight: pure embeddings fail at scale. Quick win. |
| **5** | **Cost-based Query Planner** | Reduces wrong-command churn | Medium | Research | Oracle recommends moving earlier. Heuristic "glue layer" first. |
| **6** | **Structural Search (ast-grep)** | Precise AST patterns | Low | Research | Embeddings weak at precise patterns. Add as retrieval lane. |
| **7** | **Prompt Caching Integration** | Latency + cost reduction | Low | Research | Structure prompts for stable prefixes. Works with all providers. |
| **8** | **CoverageLens** | 50-70% for test failures | Medium | Planned | Coverage-guided context for debugging. |
| **9** | **Incremental Semantic Search** | Always-on find | Medium | Research | Remove indexing friction → fewer grep+paste fallbacks. |
| **10** | **VoyageCode3 Embeddings** | Better search accuracy | Low | Research | Evaluate against nomic-embed-text. |
| **11** | **LLMLingua Compression** | 5-10x additional | Medium | Research | For text-heavy sections only (not code). |
| **12** | **Merkle Tree Indexing** | Faster incremental updates | Medium | Research | Cursor's approach. Cheap "what changed?" detection. |

### Research Backlog (Not Yet Prioritized)

These require spikes or evaluation before prioritizing:

| Project/Technique | Potential Impact | Integration Effort | Notes |
|-------------------|------------------|-------------------|-------|
| **Aider Repo Map** | Validation + optimizations | Low | Similar to tldrs `structure`. [Repo](https://github.com/paul-gauthier/aider) |
| **Continue.dev** | MCP patterns | Low | Reference for MCP integration. [Repo](https://github.com/continuedev/continue) |
| **SPLADE Sparse Expansion** | Bridge lexical+semantic | Medium | [Paper](https://arxiv.org/abs/2107.05720) |
| **Repomix** | Codebase packing reference | Low | Tree-sitter compression (~70%). [Repo](https://github.com/yamadashy/repomix) |
| **Moatless Tools** | SWE-bench patterns | Low | State-machine context retrieval. [Repo](https://github.com/aorwall/moatless-tools) |
| **Agentless** | Simple 3-phase architecture | Low | Hierarchical localization. [Repo](https://github.com/OpenAutoCoder/Agentless) |
| **CodeSage / Jina Reranker** | Alternative embeddings | Low | [Jina Reranker](https://jina.ai/reranker/) |
| **CodeBERT / GraphCodeBERT** | Baseline embeddings | Low | [GraphCodeBERT](https://arxiv.org/abs/2009.08366) |
| **ColBERT-style Late Interaction** | Multi-vector retrieval | Medium | Better for code queries. Higher indexing cost. |
| **MemGPT** | Memory tiers | Medium | VHS as "disk tier". [Paper](https://arxiv.org/abs/2310.08560) |
| **RAGCache / TurboRAG** | Cached retrieval states | Medium | [RAGCache](https://arxiv.org/abs/2404.12457) |
| **CodeQL / Joern** | PDG validation reference | High | [CodeQL](https://docs.github.com/en/code-security/codeql-for-vs-code), [Joern](https://docs.joern.io/) |
| **SCIP/LSIF** | Code intelligence formats | Medium | [SCIP](https://github.com/sourcegraph/scip) |
| **Context Distillation** | Internalize prompts | High | Used by Anthropic/Llama. |
| **cAST (AST-aware chunking)** | Better code chunks | Medium | [Paper](https://arxiv.org/abs/2506.15655) |
| **GNN for Code Graphs** | Learned PDG enhancements | High | GGNN, GAT. Requires model training. |

### Key Insights from Research

1. **Sourcegraph moved away from pure embeddings** - They found keyword search (BM25F) more reliable at scale than embeddings alone. Now use embeddings for reranking. Validates tldrs' hybrid approach.

2. **Augment Code processes 200k tokens** - Their Context Engine uses custom GPU kernels. Shows what's achievable; their blog posts describe chunking strategies worth studying.

3. **LLMLingua claims 20x compression** - With minimal performance loss. Most promising for text-heavy sections (summaries, comments). Careful with code tokens.

4. **Cursor's Merkle trees** - Enable efficient incremental sync of large codebases. Could improve tldrs index update performance for repos with frequent changes.

5. **SWE-bench patterns (Moatless, Agentless)** - Hierarchical localization + state-machine workflows outperform pure agentic approaches. Simple 3-phase (localize → repair → validate) achieves 32%+ at low cost.

6. **Provider prefix caching** - Stable prompt prefixes get cached by Claude/OpenAI. Structure context for maximal prefix stability to reduce latency + cost even before perfect delta.

7. **Two-stage retrieval is standard** - BM25/embedding first-pass → cross-encoder rerank. Reranking is often the difference between "plausible" and "correct".

8. **AST-aware chunking beats naive chunking** - cAST shows 5.5 points gain on RepoEval. Code should be chunked at function/class level, not arbitrary lines.

9. **Context rot is real** - Chroma research (2025) shows LLM performance degrades as context grows. "Lost in the middle" effect persists. Thoughtful chunking + overlap matters.

---

## Completed Phases

| Phase | Feature | Token Savings | Status |
|-------|---------|---------------|--------|
| 0 | Quick Wins (Oracle Review 2026-01-13) | 2x+ | Done |
| 1 | ContextPack Engine + DiffLens/SymbolKite | 60-80% | Done |
| 2 | Cassette/VHS Integration | 70-90% | Done |

---

## Oracle Evaluation (2026-01-17)

GPT-5.2-Pro evaluated the full codebase (~1.67M tokens) and identified the top 3 priorities above.

### Key Insights

1. **Multi-turn repetition is the biggest token sink** - Agents re-request unchanged symbols. ETag primitives exist but aren't automatic.

2. **VHS adoption friction causes blob pasting** - Extra install + env vars = agents paste blobs instead of refs.

3. **Include less exact code > summarize** - PDG slicing keeps exact code (edit-safe) while cutting 30-50% of function bodies.

4. **Semantic search is underused** - Indexing friction causes fallback to grep + paste.

5. **Cost-based query planning** - A single `tldrs plan "<task>" --budget N` could reduce wrong-command churn.

---

## Oracle Plan Review (2026-01-17)

Second Oracle review of the 3 implementation plans + research findings. Confirmed priorities are correct with these implementation concerns:

### Priority 1: ETag/Delta Context - Concerns

1. **Delta assumes model retains prior code** - If conversation truncated, "unchanged" becomes incorrect
   - **Mitigation**: Add rehydration path via VHS refs: `unchanged_refs: {symbol_id: vhs://...}`

2. **CLI default-to-delta unsafe for humans** - Humans don't retain prior output in LLM context
   - **Mitigation**: Require explicit `--session-id` for delta in CLI; MCP can default delta

3. **Session ID collisions** - Include repo fingerprint + branch/commit in session header
   - **Mitigation**: Auto-reset on large diff (if repo changed too much since last seen)

4. **Use SQLite instead of JSON** - Already used for VHS; simplifies concurrency, partial updates, bounded size

### Priority 2: VHS Refs - Concerns

1. **Preview quality is make-or-break** - First 30 lines often not the useful part
   - **Mitigation**: Compact TOC (files/symbols + line ranges) + first N lines of *highest relevance slice*

2. **Ref sprawl & garbage collection** - Add per-repo quotas, TTL-based expiry, purge-by-repo command

3. **Unify VHS with ETag** - Make VHS content-addressed (hash → blob), then ETag can reference existing blob (no duplication)

### Priority 3: PDG Slicing - Concerns

1. **"Exact code" vs continuity markers** - Inserting `...` violates exact source
   - **Mitigation**: Return *ranges* and render separators outside code fences

2. **Slicing completeness** - Always include: function signature + docstring, import/type/constant definitions, small forward slice when changes affect downstream

3. **Language coverage realism** - TS/Rust/Go PDG correctness tricky (macros, generics, async). "Slice usefulness" is separate metric from "extraction success"

4. **Validate against CodeQL/Joern** - Use as reference implementations to check if slices miss key dependencies

### Additional Recommendations from Oracle

1. **Treat SymbolId + unified search as non-negotiable prerequisites** - Identity collisions break all 3 features

2. **Move query planner earlier** - Heuristic planner as "glue layer" that decides lexical vs embedding vs structural, diff-context vs symbol slice, signature-only vs body vs PDG slice

3. **Structural search as first-class retrieval lane** - Semgrep/ast-grep for precise AST patterns (embeddings are weak here)

4. **Security/privacy for VHS** - Add encryption-at-rest option, redaction policies, TTL defaults for sensitive repos

---

## Oracle Review (2026-01-13)

GPT-5.2 Pro reviewed the full codebase (~193k tokens) and identified critical architectural issues that must be fixed before building new features.

### Critical Architecture Issues

#### A) Symbol Identity Not File-Qualified (Highest Risk)

**Problem:** Multiple locations use bare function names instead of file-qualified IDs:
- `api.py:get_relevant_context()` builds a file-qualified call graph but collapses to plain names in traversal
- `analysis.py:impact_analysis()` matches by `name` without file context
- Daemon `impact` handler forwards bare names without disambiguation

**Impact:** Same-named functions across files create phantom edges and wrong context.

**Fix:** Define canonical `SymbolId = (rel_path, qualified_name)` everywhere:
- Call graph adjacency: `dict[SymbolId, set[SymbolId]]`
- Visited sets / BFS queues: store `SymbolId`, not bare names
- Daemon impact: require `file:func` format

#### B) Two Semantic Search Systems Active

**Problem:** CLI uses new `index.py/VectorStore` (`.tldrs/index/`), daemon uses legacy `semantic.py` (`.tldrs/cache/semantic`). Different answers for same queries.

**Fix:** Migrate daemon to `index.py/VectorStore` or mark `semantic.py` as legacy and remove from daemon/MCP.

#### C) Multi-Language Signatures Broken in semantic.py

**Problem:** `api.py` module export mode uses hardcoded Python `def ...` strings instead of `FunctionInfo.signature()`. Produces wrong output for TypeScript/Rust.

**Fix:** Replace all hardcoded signature strings with `func.signature()`.

#### D) File Traversal Inconsistent

**Problem:** `get_relevant_context()` and `get_code_structure()` use ad-hoc `rglob` and only skip hidden dirs, while other paths use `.tldrsignore` and workspace config.

**Fix:** Centralize one "workspace files" iterator used by all: context building, indexing, embeddings, coverage.

#### E) Module Naming Inconsistencies

**Problem:** Mixed `tldr` vs `tldr_swinton` imports:
- Daemon helpers: `from tldr import api`
- MCP server: `python -m tldr.cli`
- CLI daemonization: `python -m tldr.daemon`

**Fix:** Replace all `tldr.*` with `tldr_swinton.*` or add explicit shim package.

#### F) Output Formatting Bugs

**Problem:** `RelevantContext.to_llm_string()` indents by enumeration index, not actual call depth (`api.py`).

---

## Phase 0: Quick Wins (Oracle Review)

**"Fix the foundation before building higher."**

Immediate fixes providing >2x token reduction with minimal effort. **Revised estimate: 2-4 days** (issues are interconnected).

### 0.1 Fix Call Graph Node Identity (Critical)

**Problem:** Call graph uses plain function names (`validate_token`) instead of qualified names (`auth.py:validate_token`). This causes:
- Ambiguous lookups when multiple files have same function name
- Incorrect caller/callee relationships
- Phantom connections between unrelated code

**Fix:** Use canonical `SymbolId = rel_path:qualified_name` everywhere in traversal.

**Files:** `src/tldr_swinton/cross_file_calls.py`, `src/tldr_swinton/api.py`, `src/tldr_swinton/analysis.py`

**Impact:** Correct call graphs = correct context retrieval = massive token savings

### 0.2 Apply SKIP_DIRS Consistently

**Problem:** `get_relevant_context()` in `api.py` doesn't apply `.tldrsignore` or workspace filtering, including `venv/`, `node_modules/`, etc.

**Fix:** Apply same filtering as index.py to all file traversal.

**Files:** `src/tldr_swinton/api.py`, `src/tldr_swinton/index.py`, `src/tldr_swinton/cross_file_calls.py`

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

**Files:** `src/tldr_swinton/api.py`, `src/tldr_swinton/cli.py`

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

**Files:** `src/tldr_swinton/api.py`, `src/tldr_swinton/cli.py`, `src/tldr_swinton/hybrid_extractor.py`

### 0.6 Fix MCP Context Formatting

**Problem:** MCP server returns verbose dict representations instead of formatted output.

**Fix:** Apply same formatters used by CLI to MCP tool responses.

**Files:** `src/tldr_swinton/mcp_server.py`, `src/tldr_swinton/daemon.py`

### 0.7 Fix Language-Aware Signatures in semantic.py (NEW)

**Problem:** `api.py` module export mode uses hardcoded `def ...` strings instead of `FunctionInfo.signature()`. Produces Python-style output for TypeScript/Rust.

**Fix:** Replace hardcoded signature strings with `func.signature()` and ensure synthetic `FunctionInfo` sets `language=...`.

**Files:** `src/tldr_swinton/api.py`

### 0.8 Resolve `tldr` vs `tldr_swinton` Imports (NEW)

**Problem:** Mixed module references can break daemon/MCP startup:
- `from tldr import api` in daemon helpers
- `python -m tldr.cli` in MCP server
- `python -m tldr.daemon` in CLI daemonization

**Fix:** Replace all `tldr.*` with `tldr_swinton.*` (or add explicit shim).

**Files:** `src/tldr_swinton/daemon.py`, `src/tldr_swinton/mcp_server.py`, `src/tldr_swinton/cli.py`, `src/tldr_swinton/install_swift.py`, `src/tldr_swinton/session_warm.py`

### 0.9 Fix Misleading Indentation in to_llm_string() (NEW)

**Problem:** `RelevantContext.to_llm_string()` indents based on enumeration index, not actual BFS depth. Structure displayed can be misleading.

**Fix:** Track actual BFS depth per function rather than `enumerate(i)`.

**Files:** `src/tldr_swinton/api.py`

### Success Metrics

- **Call graph accuracy**: Zero ambiguous node lookups
- **Token reduction**: >50% vs current output
- **Budget compliance**: Output within 5% of requested budget
- **Multi-language correctness**: TS/Rust signatures use correct syntax

---

## Innovation Opportunities (Ranked by Effort/Value)

From Oracle review, ranked for this codebase specifically:

### Research Prototypes to Evaluate (Before Full Implementation)

These are research-backed compression techniques to prototype as **opt-in modes**, evaluate on our core evals, and only then decide whether to fully integrate.

**Prototype candidates (add small spikes + eval gates):**

1. **LongCodeZip-style dual-stage code compression** (ref: https://arxiv.org/abs/2510.00446)  
   Coarse function-level selection + fine block-level pruning under a budget.  
   **Why:** Designed for code; preserves relevance under high compression.  
   **Prototype:** Add a `--compress=two-stage` option to DiffLens/ContextPack that:
   - scores functions by relevance (diff proximity + call graph + embedding similarity)
   - prunes within functions by block-level relevance (CFG/PDG blocks or statement windows)
   **Eval:** DiffLens + agent workflow evals; compare diff+deps baseline.

2. **SCOPE-style chunk summarization compression** (ref: https://arxiv.org/abs/2508.15813)  
   Chunk context into semantically coherent units and rewrite into concise summaries.  
   **Prototype:** `--compress=chunk-summary` for code bodies, with configurable ratio; preserve signatures + key identifiers.  
   **Eval:** Agent workflow eval + manual spot checks for correctness.

3. **FrugalPrompt-style token attribution pruning** (ref: https://arxiv.org/abs/2510.16439)  
   Score tokens for salience and keep top-k% in order.  
   **Prototype:** `--compress=salience` as a last-mile reducer on ultracompact output.  
   **Eval:** Token efficiency + agent workflow evals; guardrails for code tasks.

4. **LLMLingua-style token-level compression** (ref: https://www.microsoft.com/en-us/research/blog/large-language-model-llm-prompt-compression-and-optimization-with-llmlingua/)  
   Use a small LM to drop low-utility tokens while preserving LLM performance.  
   **Prototype:** Optional compression pass on text-only sections (summaries, comments), not code.  
   **Eval:** Semantic search + agent workflow evals.

**Decision gate:** Require ≥10% additional savings vs current diff+deps baseline **without** regression on workflow evals before graduating to full implementation.

### 1. PDG-Guided Minimal Slices (Best Effort/Value)

Program Dependence Graph analysis to include only statements that affect the modification point. Often only 10-30% of a function body is relevant.

**Why it's worth it:** You already have PDG APIs exposed. Instead of compressing *everything*, include *less but more relevant*.

**Pragmatic approach:**
- Start with "slice within the changed function only" (DiffLens integration)
- Gate behind `--slice` flag, measure on eval tasks
- Don't attempt whole-program slicing initially

**Potential:** 30-50% additional savings on function bodies

### 2. Cost-Based Context Query Planner (Good Value)

Like database query optimization - given a task and budget, find the cheapest query plan.

**Start with heuristics:**
- If query is identifier-like → lexical fast-path
- If git diff available → diff-context
- If budget small → signatures-only + callers/callees
- If budget large → include top N bodies + slices

Evolve into learned/cost-based planner once you have metrics.

### 3. Hierarchical Repo Map (Medium)

Graph coarsening: show modules at high level, expand only relevant subtrees.

Relatively straightforward using existing tree/structure handlers.

### 4. Identifier Aliasing / Alpha-Renaming (Low Priority)

Replace verbose identifiers with short aliases:
```python
# Original
def calculate_monthly_subscription_revenue(customer_id: str) -> Decimal

# Alpha-renamed (with legend)
def A(B:str)->C  # A=calculate_monthly_subscription_revenue, B=customer_id, C=Decimal
```

**Potential:** 20-40% additional savings

**Risks:**
- Increases cognitive load
- Can harm LLM understanding if over-applied
- Needs careful legend + stable reversible mapping

Only apply after symbol identity and formatting are correct, and only under tight budgets.

### 5. Near-Duplicate Clustering (Situational)

Use MinHash to detect near-duplicate functions (copy-paste code). Represent cluster with one exemplar + diff annotations.

Only valuable in copy-paste-heavy codebases. Worth a spike later.

### 6. Stateful Delta-Context Protocol (Future)

Track what context the LLM has seen, send only deltas. 5-20x savings over multi-turn sessions.

---

## Phase 1: ContextPack Engine (DiffLens + SymbolKite Merged)

**"Shared infrastructure, multiple query plans."**

Oracle recommends merging DiffLens and SymbolKite since they share core infrastructure: stable symbol IDs, budget allocator, compact/ultracompact formatting, ETag support.

**Revised estimate: 5-8 days total**

### Core Engine Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    ContextPack Engine                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ Symbol ID    │  │ Budget       │  │ Output Formatter     │   │
│  │ Registry     │  │ Allocator    │  │ (compact/ultracompact)│  │
│  │ (file:name)  │  │ (token-aware)│  │                      │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐                             │
│  │ ETag Cache   │  │ Disambiguation│                            │
│  │ (content hash)│ │ (ambiguous →  │                            │
│  │              │  │  candidates)  │                            │
│  └──────────────┘  └──────────────┘                             │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                     Query Plans                                  │
│                                                                  │
│  ┌─────────────────┐        ┌─────────────────┐                 │
│  │ DiffLens        │        │ SymbolKite      │                 │
│  │                 │        │                 │                 │
│  │ • diff-context  │        │ • symbol slice  │                 │
│  │ • hunk→symbol   │        │ • symbol search │                 │
│  │ • caller/callee │        │ • get with etag │                 │
│  └─────────────────┘        └─────────────────┘                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### DiffLens Query Plan

**"The only context that matters is the diff."**

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

**Algorithm:**
1. **Get diff hunks**: Parse `git diff --unified=0` output
2. **Map to symbols**: For each hunk, find enclosing function/class using AST
3. **Expand context**: Add 1-hop callers and callees from call graph
4. **Rank by relevance**:
   - Symbols containing diff hunks (highest)
   - Direct callers/callees
   - Test files referencing changed symbols
5. **Budget constraint**: Include full code for top items, signatures only for rest
6. **Output**: Ordered slices with stable IDs

**Fallback for non-git repos:** Use recently modified files or dirty file set.

### SymbolKite Query Plan

**"Repo map, but queryable."**

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

**Delta Retrieval (ETag Support):**
```python
# First request
result = symbols.get("src/auth.ts:validateToken")
# Returns: { etag: "a1b2c3", content: "...", lines: [45, 72] }

# Subsequent request with etag
result = symbols.get("src/auth.ts:validateToken", etag="a1b2c3")
# Returns: "UNCHANGED" if no changes
# Returns: { etag: "d4e5f6", diff: "...", content: "..." } if changed
```

### Disambiguation Handling

When symbol query is ambiguous:
- Return candidates list with file locations
- Allow selection or "best match" heuristic
- Never silently pick wrong symbol

### Output Format (ContextPack)

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
      "code": null,
      "lines": [12, 45]
    }
  ],
  "signatures_only": [
    "src/routes/api.ts:handleLogin",
    "src/routes/api.ts:handleLogout"
  ]
}
```

### MCP Tools

```python
# DiffLens
difflens.context(base_ref: str, budget: int = 4000) -> ContextPack
difflens.slice(symbol: str, depth: int = 1, budget: int = 1000) -> str
difflens.deps(symbol: str, direction: "callers" | "callees", depth: int = 1) -> list[Symbol]

# SymbolKite
symbols.search(query: str, kind: str = None, limit: int = 20) -> list[SymbolMatch]
symbols.slice(symbol_id: str, depth: int = 1, budget: int = 1000) -> SymbolSlice
symbols.get(symbol_id: str, etag: str = None) -> SymbolContent | "UNCHANGED"
symbols.callers(symbol_id: str, limit: int = 10) -> list[CallSite]
symbols.callees(symbol_id: str, depth: int = 1) -> list[Symbol]
```

### Success Metrics

- **Tokens per PR review**: Target 70% reduction vs full-file reads
- **Relevance hit rate**: >90% of actual changes covered by context pack
- **Latency**: <500ms for typical diffs
- **Cache hit rate**: >60% of repeated symbol reads return UNCHANGED
- **Query latency**: <100ms for symbol lookups

---

## Phase 2: Cassette Integration (Optional)

**"Stop pasting logs. Paste hashes."**

Integration with Cassette content-addressed object store for tool outputs.

**Status:** Optional/parallel. Proceed only after ContextPack Engine proves value.

**Revised estimate: 3-7 days** (depends on Cassette stability)

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

---

## Phase 3: CoverageLens

**"Use execution to choose context."**

Coverage-guided context selection that uses runtime data to rank relevance.

**Revised estimate: 4-8 days** (depends on line→symbol mapping stability)

**Prerequisites:** Symbol ID infrastructure from Phase 0/1 must be stable.

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

### Success Metrics

- **Failure fix rate**: >80% of failures fixed with coverage-guided context
- **Tokens per fix**: 50% reduction vs static analysis only
- **Supported ecosystems**: Python, JS/TS, Go, Rust

---

## Architecture

All features share core infrastructure:

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI / MCP Server                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              ContextPack Engine (Phase 1)                   ││
│  │                                                             ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌───────────────────┐   ││
│  │  │ DiffLens    │  │ SymbolKite  │  │ CoverageLens      │   ││
│  │  │ (query plan)│  │ (query plan)│  │ (query plan)      │   ││
│  │  └──────┬──────┘  └──────┬──────┘  └─────────┬─────────┘   ││
│  │         │                │                   │              ││
│  │         └────────────────┼───────────────────┘              ││
│  │                          │                                  ││
│  │                   ┌──────▼──────┐                           ││
│  │                   │ Context     │                           ││
│  │                   │ Budget      │                           ││
│  │                   │ Allocator   │                           ││
│  │                   └──────┬──────┘                           ││
│  │                          │                                  ││
│  │                   ┌──────▼──────┐                           ││
│  │                   │ Output      │                           ││
│  │                   │ Formatter   │                           ││
│  │                   │ (compact/   │                           ││
│  │                   │ ultracompact)│                          ││
│  │                   └─────────────┘                           ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│                   ┌─────────────────┐                            │
│                   │   Unified Index │                            │
│                   │                 │                            │
│                   │ • Symbols (ID)  │                            │
│                   │ • Call graph    │                            │
│                   │ • Embeddings    │                            │
│                   │ • File hash     │                            │
│                   │ • ETag cache    │                            │
│                   └─────────────────┘                            │
│                                                                  │
│              .tldrs/index/{vectors.faiss, units.json}            │
└──────────────────────────────────────────────────────────────────┘
```

---

## Risk Assessment

### What Could Go Wrong

1. **Wrong context due to identity collisions** → model edits wrong code
   *Mitigation:* Phase 0.1 is top priority

2. **Multi-language output lies** (Python-style signatures for TS/Rust) → confusion and bad patches
   *Mitigation:* Phase 0.7

3. **Performance blowups** from inconsistent excludes scanning vendor trees
   *Mitigation:* Phase 0.2

4. **Entry-point inconsistencies** (daemon vs CLI give different answers)
   *Mitigation:* Consolidate semantic systems

5. **Packaging/import breaks** daemon/MCP startup
   *Mitigation:* Phase 0.8

### Dependencies/Assumptions

- **Git availability**: DiffLens assumes git. Need fallback for non-git repos.
- **Embedding backend**: Ollama might not exist; sentence-transformers is heavy. Ensure graceful fallback.
- **Cassette availability**: Treat as optional until proven.

---

## Open Questions

1. **Budget units**: Tokens (requires tokenizer) or characters/lines (simpler)?
   *Oracle suggests:* Start with character approximation, add tiktoken later

2. **MCP server**: Extend existing daemon or separate server?
   *Oracle suggests:* Migrate daemon to unified index first

3. **Cassette dependency**: Optional or required for some features?
   *Decision:* Optional, proceed only after ContextPack proves value

4. **Coverage persistence**: Store coverage data in .tldrs/ or ephemeral?
   *Deferred to Phase 3*
