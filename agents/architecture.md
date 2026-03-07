# Architecture

## Source Layout

```
src/tldr_swinton/
├── cli.py                     # CLI entry point, argument parsing
├── manifest.py                # Machine-readable capability manifest
├── presets.py                 # Output presets (compact, minimal, multi-turn)
└── modules/
    ├── core/
    │   ├── api.py             # High-level API functions
    │   ├── ast_extractor.py   # Data structures (FunctionInfo, ModuleInfo), Python extraction
    │   ├── hybrid_extractor.py # Multi-language extraction via tree-sitter
    │   ├── mcp_server.py      # MCP server (24 tools, FastMCP)
    │   ├── daemon.py          # Background daemon (socket-based)
    │   ├── cfg_extractor.py   # Control flow graph extraction
    │   ├── dfg_extractor.py   # Data flow graph extraction
    │   ├── pdg_extractor.py   # Program dependency graph
    │   ├── cross_file_calls.py # Cross-file call graph
    │   ├── output_formats.py  # Format rendering (ultracompact, json, text, etc.)
    │   ├── context_delegation.py # Retrieval plan generation
    │   ├── contextpack_engine.py # ContextPack builder
    │   ├── coherence_verify.py # Cross-file consistency checks
    │   ├── change_impact.py   # Test impact analysis
    │   ├── distill_formatter.py # Compressed context for sub-agents
    │   ├── attention_pruning.py # Symbol access tracking
    │   ├── block_compress.py  # Two-stage compression (knapsack DP)
    │   ├── signature_extractor_pygments.py # Fallback signature extraction
    │   └── engines/
    │       ├── astgrep.py     # Structural code search via ast-grep
    │       ├── delta.py       # Delta-mode orchestration (session tracking, etag)
    │       └── difflens.py    # Git-aware diff context
    ├── semantic/
    │   ├── backend.py         # SearchBackend protocol, CodeUnit, get_backend() factory
    │   ├── faiss_backend.py   # FAISSBackend (Ollama/sentence-transformers + FAISS)
    │   ├── colbert_backend.py # ColBERTBackend (PyLate + PLAID indexing)
    │   ├── index.py           # Thin orchestrator: build_index(), search_index()
    │   ├── bm25_store.py      # BM25 keyword index for hybrid search (RRF fusion)
    │   ├── embeddings.py      # Backward-compat shim (re-exports from faiss_backend)
    │   ├── vector_store.py    # Backward-compat shim (aliases FAISSBackend)
    │   └── semantic.py        # Original 5-layer semantic search (legacy)
    ├── bench/                 # Benchmark harness
    ├── vhs/                   # VHS ref storage
    └── workbench/             # Debugging workbench
```

## Core Extraction Pipeline

```
CLI (cli.py) → API (api.py) → extract_file() → HybridExtractor.extract()
  → Language-specific: Python (native AST), TS/Rust/Go/etc (tree-sitter), fallback (Pygments)
  → ModuleInfo with FunctionInfo objects → .to_dict() for JSON
```

## Semantic Search Pipeline

```
tldrs index . → backend.get_backend("auto"|"faiss"|"colbert")
  ├── FAISSBackend: 768d single-vector (Ollama nomic-embed-text-v2-moe)
  └── ColBERTBackend: 48d per-token (PyLate LateOn-Code-edge, PLAID)

tldrs find "query" → Lexical fast-path (BM25 exact match) → Backend.search() → RRF fusion
```

`SearchBackend` protocol (`backend.py`): `build()`, `search()`, `load()`, `save()`, `info()`.
