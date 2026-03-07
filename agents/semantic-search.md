# Semantic Search Backends

| Backend | Model | Dimensions | Install | Quality |
|---------|-------|-----------|---------|---------|
| **FAISS** | `nomic-embed-text-v2-moe` (475M) | 768d single-vector | `[semantic-ollama]` | Good |
| **ColBERT** | `LateOn-Code-edge` (17M) | 48d per-token | `[semantic-colbert]` | Best |

```bash
tldrs index . --backend faiss    # or colbert, or auto
tldrs index . --rebuild           # Force full rebuild
tldrs index --info                # Check status
```

Both backends use `threading.RLock` with snapshot pattern for concurrent build/search.

## Operational Notes

### Embedding Model
- Current: `nomic-embed-text-v2-moe` (475M, 768d, MoE)
- **NOT** `nomic-embed-code` (7.1B, 3584d) -- different model
- Jina-code-0.5b evaluated but not adopted (not on Ollama)

### Do NOT Adopt
- Stack Graphs: archived Sept 2025
- LSP: conflicts with offline/static analysis approach
- pylate-rs for LateOn-Code-edge: projection head missing, dimension mismatch

### Gotchas
- Ollama naming: community models use `user/model` format. Always `ollama pull` to verify.
- ThreadPoolExecutor + local GPU Ollama: no speedup (GPU serializes internally).
