# Embedding Model Evaluation

Benchmark results comparing embedding models for code semantic search on a real-world TypeScript/Rust codebase (~12,000 code units).

## Models Tested

| Model | Dimension | Size | MTEB Score* |
|-------|-----------|------|-------------|
| [nomic-embed-text](https://ollama.com/library/nomic-embed-text) | 768 | 274 MB | 53.01 |
| [mxbai-embed-large](https://ollama.com/library/mxbai-embed-large) | 1024 | 669 MB | 64.68 |
| [all-minilm](https://ollama.com/library/all-minilm) | 384 | 45 MB | ~45 |

*MTEB Retrieval average scores from published benchmarks

## Indexing Speed

Time to index ~12,000 code units (functions, classes, type definitions):

| Model | Time | Rate |
|-------|------|------|
| nomic-embed-text | ~130s | ~92 units/sec |
| all-minilm | ~339s | ~35 units/sec |
| mxbai-embed-large | ~460s | ~26 units/sec |

**Winner: nomic-embed-text** (3.5x faster than mxbai-embed-large)

## Query Speed

Average time to embed a single search query (after warmup):

| Model | Avg | Min | Max |
|-------|-----|-----|-----|
| nomic-embed-text | 15.8ms | 13.7ms | 21.8ms |
| all-minilm | 16.4ms | 11.7ms | 32.8ms |
| mxbai-embed-large | 23.6ms | 17.4ms | 41.2ms |

**Winner: nomic-embed-text** (fastest and most consistent)

## Search Quality

Tested against 10 queries ranging from exact function names to natural language descriptions:

| Model | Hit Rate | MRR | Notes |
|-------|----------|-----|-------|
| nomic-embed-text | 80% | 0.725 | Missed 2 harder semantic queries |
| mxbai-embed-large | 100% | 0.817 | All found, some at rank 2-3 |
| all-minilm | 100% | 0.875 | Best MRR despite lower scores |

**Winner: all-minilm** (best MRR) or **mxbai-embed-large** (best hit rate)

### Test Queries

| Query | nomic | mxbai | minilm |
|-------|-------|-------|--------|
| `ComponentName` (exact match) | ✓ r1 (1.00) | ✓ r3 (0.69) | ✓ r4 (0.48) |
| `useHookName` (exact match) | ✓ r1 (1.00) | ✓ r1 (1.00) | ✓ r1 (1.00) |
| `simulation tick loop` | ✓ r1 (0.74) | ✓ r1 (0.71) | ✓ r1 (0.49) |
| `render country borders on map` | ✓ r4 (0.63) | ✓ r1 (0.68) | ✓ r1 (0.54) |
| `economic resource calculation` | ✓ r1 (0.65) | ✓ r1 (0.62) | ✓ r1 (0.50) |
| `React component for agents` | ✓ r1 (0.81) | ✓ r1 (0.73) | ✓ r1 (0.54) |
| `trade route calculation` | ✓ r1 (0.67) | ✓ r1 (0.62) | ✓ r1 (0.49) |
| `diplomatic relations` | ✗ miss | ✓ r2 (0.50) | ✓ r1 (0.28) |
| `historical timeline events` | ✓ r1 (0.64) | ✓ r1 (0.64) | ✓ r1 (0.50) |
| `user authentication login` | ✗ miss | ✓ r3 (0.55) | ✓ r2 (0.26) |

Format: ✓ r*N* (score) = found at rank N with similarity score

### Key Observations

1. **Exact matches work well across all models** - Function/component names that appear in the index get high scores (often 1.0 for exact lexical matches).

2. **nomic-embed-text struggles with abstract queries** - Queries like "diplomatic relations" and "user authentication" that don't have obvious lexical overlap with function names failed.

3. **mxbai-embed-large has best semantic understanding** - Found all queries including abstract ones, though sometimes at rank 2-3.

4. **all-minilm has surprisingly good ranking** - Despite lowest similarity scores, it tends to rank correct results at #1 more often (highest MRR).

5. **Similarity scores vary significantly by model** - mxbai scores range 0.50-1.00, minilm scores range 0.26-1.00. Don't compare scores across models.

## Recommendations

### Default: nomic-embed-text ✓

Best balance of speed and quality for typical code search needs:
- 3.5x faster indexing than alternatives
- 80% hit rate is sufficient when combined with lexical fast-path
- Smallest reasonable model size (274 MB)

### High Quality: mxbai-embed-large

For users who prioritize search quality over speed:
- 100% hit rate on test queries
- Better semantic understanding of abstract concepts
- Trade-off: 2.5x larger, 50% slower indexing

### Minimal Footprint: all-minilm

For resource-constrained environments:
- Only 45 MB (6x smaller than nomic)
- Surprisingly good ranking quality (best MRR)
- Trade-off: Lower similarity scores may affect threshold-based filtering

## Usage

```bash
# Default (nomic-embed-text)
tldrs index /path/to/project

# High quality mode
tldrs index /path/to/project --model mxbai-embed-large

# Minimal footprint
tldrs index /path/to/project --model all-minilm
```

## Methodology

- **Codebase**: Real-world TypeScript/React + Rust monorepo
- **Index size**: ~12,000 code units (functions, classes, types, React components)
- **Query types**: Mix of exact function names and natural language descriptions
- **Metrics**:
  - Hit Rate: % of queries that found a relevant result in top 10
  - MRR (Mean Reciprocal Rank): Average of 1/rank for correct results
- **Hardware**: Apple Silicon (M1/M2), Ollama running locally

## References

- [MTEB Leaderboard](https://huggingface.co/spaces/mteb/leaderboard) - Massive Text Embedding Benchmark
- [Ollama Embedding Models Blog](https://ollama.com/blog/embedding-models)
- [Best Code Embedding Models Compared](https://modal.com/blog/6-best-code-embedding-models-compared)
- [Comparing AI Embedding Models](https://geirfreysson.com/posts/2025-01-25-comparing-embedding-models/)
