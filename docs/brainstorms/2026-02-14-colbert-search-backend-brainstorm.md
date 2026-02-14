# ColBERT Late-Interaction Search Backend

**Bead:** tldr-swinton-wp7
**Phase:** strategized (as of 2026-02-14T19:05:21Z)
**Date:** 2026-02-14
**Status:** Ready for planning

## What We're Building

Replace the semantic search layer in `modules/semantic/` with a **dual-backend architecture** supporting both the current FAISS single-vector search and a new ColBERT late-interaction search via PyLate + LateOn-Code-edge.

ColBERT preserves per-token embeddings instead of compressing everything into a single vector. This gives fundamentally better retrieval quality for code search — a 17M parameter late-interaction model (LateOn-Code-edge) outperforms our 475M general-purpose dense model on code benchmarks.

**What changes:** The `modules/semantic/` package gains a `SearchBackend` protocol and two implementations (FAISS, PLAID). The embedding and vector store modules are refactored to be backend-agnostic. A new `colbert` backend is added alongside the existing `ollama`/`sentence-transformers` backends.

**What stays the same:** All 5-layer analysis (AST, CG, CFG, DFG, PDG), ContextPack pipeline, delta caching, diff context, all MCP tools, all engines.

## Why This Approach

### The Retrieval Quality Gap

| Model | Params | MTEB Code v1 |
|-------|--------|--------------|
| BM25 baseline | — | 44.41 |
| LateOn-Code-edge | 17M | **66.64** |
| nomic-embed-text-v2-moe (ours) | 475M | ~62-65 est. |
| LateOn-Code (larger variant) | 130M | 74.12 |

Late interaction (MaxSim over per-token vectors) preserves fine-grained lexical signal that single-vector compression loses. A query like "authentication token validation" can match strongly against individual tokens ("verify", "JWT", "valid") independently, then aggregate those signals.

### Empirical Verification (2026-02-13)

Tested PyLate v1.3.4 + LateOn-Code-edge end-to-end:

| Metric | Value |
|--------|-------|
| Model load | 16.9s cold, ~2s warm |
| Doc encoding | 11ms/doc (CPU, batch=32) |
| Query encoding | 6.3ms/query (CPU) |
| Output dimensions | (N_tokens, 48) per doc |
| Avg embedding size | 5.5 KB/unit (pool_factor=2) vs 3 KB/unit (FAISS 768d) |
| Process RSS | ~900 MB |

Search quality on 8-doc test corpus: correct top-1 result on 4/4 test queries.

### Why Backend Abstraction (Not Thin Wrapper)

A `SearchBackend` protocol makes the system extensible without touching orchestration code. If we ever add jina, Cohere, or a future embedding model, we add a new backend class — not more if/else branches in `index.py`. The refactor cost is moderate (existing code is clean and well-separated) and the payoff is a single code path for indexing and search regardless of backend.

## Key Decisions

1. **Dual backend, ColBERT preferred**: Auto-detect at search time. If pylate installed → ColBERT. Else → FAISS+Ollama. Both backends coexist.

2. **Daemon-resident model**: Load the PyLate model once on first search, keep in memory (~900MB RSS). Avoids 2-16s reload per query. Matches Ollama's always-on pattern.

3. **Rebuild threshold for deletions**: PLAID can't delete documents. Track deletion count; auto-rebuild when deletions exceed 20% of index. Between rebuilds, stale entries may appear in results (acceptable — they're filtered by file existence check).

4. **BM25 for identifier fast-path only**: ColBERT's per-token matching subsumes BM25's lexical advantage for natural language queries. Keep BM25 only for exact identifier lookups (`verify_token`, `ClassName.method`), which bypass semantic search entirely.

5. **Backend Abstraction pattern**: Extract `SearchBackend` protocol. Both FAISS and PLAID implement it. `index.py` orchestration is backend-agnostic. Backend selection recorded in `meta.json`.

6. **Pool factor = 2**: Halves token count per document, reducing storage from 11 KB to 5.5 KB per unit (1.8x FAISS) with minimal quality loss. Tunable via config.

## Open Questions

1. **pylate-rs projection head bug**: pylate-rs v1.0.4 outputs 512d for LateOn-Code-edge (missing the 256→512→48 projection layers). Need to monitor for fix. Until then, PyLate (PyTorch) is the only viable encoder.

2. **Cold start in daemon**: First query after daemon start will take ~17s (model download + load). Should we pre-warm on daemon start, or accept the one-time hit?

3. **Index migration UX**: Users with existing FAISS indexes need a clear path. `tldrs index --backend=colbert` rebuilds with the new backend. Auto-migration on version upgrade? Or manual opt-in?

4. **torch CPU-only wheel**: Can we pin `torch` to CPU-only in the extras to avoid pulling 4GB of CUDA libs? Needs `--extra-index-url https://download.pytorch.org/whl/cpu`.

## Technology References

- [PyLate](https://github.com/lightonai/pylate) v1.3.4 (MIT) — ColBERT training + retrieval
- [LateOn-Code-edge](https://huggingface.co/lightonai/LateOn-Code-edge) — 17M code-specialized ColBERT model
- [ColGrep](https://github.com/lightonai/next-plaid/tree/main/colgrep) — Rust CLI using same tech (reference, not forking)
- [pylate-rs](https://github.com/lightonai/pylate-rs) v1.0.4 — Rust inference (broken for this model, monitoring)
