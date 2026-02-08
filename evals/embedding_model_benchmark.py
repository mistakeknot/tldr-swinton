#!/usr/bin/env python3
"""Benchmark embedding models for code search quality.

Tests different embedding models on real code search queries
against the shadow-work codebase.
"""

import json
import time
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tldr_swinton.embeddings import (
    get_embedder,
    embed_text,
    EMBEDDING_DIMS,
)
from tldr_swinton.vector_store import VectorStore
from tldr_swinton.index import CodeIndex

# Test queries with expected relevant functions
# Format: (query, expected_function_substrings)
TEST_QUERIES = [
    # Direct function name lookups (should get perfect scores)
    ("RelationshipDetailsModal", ["RelationshipDetailsModal"]),
    ("useSimulationState", ["useSimulationState"]),
    ("TradeRouteCalculator", ["TradeRoute", "trade"]),

    # Semantic queries (natural language -> code)
    ("simulation tick loop", ["tick", "simulation", "loop", "update"]),
    ("render country borders on map", ["country", "border", "map", "render"]),
    ("agent relationship visualization", ["relationship", "agent", "visual"]),
    ("economic resource calculation", ["economic", "resource", "calc"]),
    ("React component for displaying agents", ["Agent", "component", "view"]),
    ("handle user authentication", ["auth", "login", "user"]),
    ("database query for countries", ["country", "query", "database", "db"]),
    ("WebSocket connection handler", ["websocket", "socket", "connect"]),

    # Complex multi-concept queries
    ("trade route between countries with tariffs", ["trade", "route", "tariff"]),
    ("historical simulation events timeline", ["history", "event", "timeline"]),
    ("diplomatic relations scoring algorithm", ["diplomatic", "relation", "score"]),
]

OLLAMA_MODELS = [
    "nomic-embed-text-v2-moe",
    "nomic-embed-text",
    "mxbai-embed-large",
    "all-minilm",
]

# Also test sentence-transformers if available
SENTENCE_TRANSFORMER_MODELS = [
    "BAAI/bge-large-en-v1.5",
    "sentence-transformers/all-MiniLM-L6-v2",
]


def check_model_available(model: str, backend: str = "ollama") -> bool:
    """Check if a model is available."""
    try:
        embedder = get_embedder(backend=backend, model=model)
        return embedder.is_available()
    except Exception:
        return False


def benchmark_model(
    index_path: Path,
    model: str,
    backend: str = "ollama",
    k: int = 10,
) -> dict:
    """Benchmark a single model on test queries.

    Returns metrics including:
    - Average query time
    - Hit rate (% of queries finding relevant results)
    - MRR (Mean Reciprocal Rank)
    - Relevance scores
    """
    print(f"\n{'='*60}")
    print(f"Testing: {model} (backend: {backend})")
    print(f"{'='*60}")

    # Check if model is available
    if not check_model_available(model, backend):
        print(f"  SKIPPED: Model not available")
        return {"model": model, "backend": backend, "skipped": True}

    # Load or rebuild index with this model
    # For fair comparison, we need to re-embed with each model
    # But that's expensive, so we'll just test query embedding time

    results = {
        "model": model,
        "backend": backend,
        "skipped": False,
        "queries": [],
        "total_time": 0,
        "avg_query_time": 0,
        "hit_rate": 0,
        "mrr": 0,
    }

    # Get embedding dimension
    dim = EMBEDDING_DIMS.get(model, 768)
    print(f"  Embedding dimension: {dim}")

    # Test embedding generation speed
    warmup_text = "test embedding generation speed"
    try:
        start = time.time()
        _ = embed_text(warmup_text, backend=backend, model=model)
        warmup_time = time.time() - start
        print(f"  Warmup embedding time: {warmup_time:.3f}s")
    except Exception as e:
        print(f"  ERROR during warmup: {e}")
        results["error"] = str(e)
        return results

    # Benchmark query embeddings
    query_times = []
    for query, expected in TEST_QUERIES:
        start = time.time()
        try:
            embedding = embed_text(query, backend=backend, model=model)
            elapsed = time.time() - start
            query_times.append(elapsed)

            results["queries"].append({
                "query": query,
                "time": elapsed,
                "embedding_dim": len(embedding),
            })
        except Exception as e:
            print(f"  ERROR on query '{query}': {e}")
            results["queries"].append({
                "query": query,
                "error": str(e),
            })

    if query_times:
        results["avg_query_time"] = sum(query_times) / len(query_times)
        results["total_time"] = sum(query_times)
        results["min_query_time"] = min(query_times)
        results["max_query_time"] = max(query_times)

    print(f"  Avg query embedding time: {results['avg_query_time']:.3f}s")
    print(f"  Min/Max: {results.get('min_query_time', 0):.3f}s / {results.get('max_query_time', 0):.3f}s")

    return results


def test_search_quality(
    index_path: Path,
    model: str,
    backend: str = "ollama",
    k: int = 10,
) -> dict:
    """Test actual search quality against an existing index.

    This uses the existing index (built with nomic-embed-text-v2-moe) to
    compare how well different query embeddings work.

    NOTE: For a true comparison, we'd need to rebuild the index
    with each model. This test shows how well the query embeddings
    from different models work with the existing document embeddings.
    """
    print(f"\n{'='*60}")
    print(f"Search Quality Test: {model} (backend: {backend})")
    print(f"{'='*60}")

    if not check_model_available(model, backend):
        print(f"  SKIPPED: Model not available")
        return {"model": model, "backend": backend, "skipped": True}

    # Load the existing index
    try:
        index = CodeIndex.load(index_path)
    except Exception as e:
        print(f"  ERROR loading index: {e}")
        return {"model": model, "error": str(e)}

    # Get the index's embedding backend info
    index_backend = index.vector_store.metadata.get("embed_backend", "unknown")
    index_model = index.vector_store.metadata.get("embed_model", "unknown")
    print(f"  Index built with: {index_model} ({index_backend})")

    results = {
        "model": model,
        "backend": backend,
        "index_model": index_model,
        "queries": [],
        "hit_rate": 0,
        "mrr": 0,
    }

    hits = 0
    reciprocal_ranks = []

    for query, expected_substrings in TEST_QUERIES:
        # Embed query with the test model
        try:
            query_embedding = embed_text(query, backend=backend, model=model)
        except Exception as e:
            print(f"  ERROR embedding query '{query}': {e}")
            continue

        # Search using the existing index's vector store
        # NOTE: This is mixing query embeddings from different models!
        # Results may be poor unless models produce compatible embeddings
        search_results = index.vector_store.search(query_embedding, k=k)

        # Check if any expected substring appears in results
        found_rank = None
        for rank, (unit_id, score) in enumerate(search_results, 1):
            func_name = unit_id.split(":")[-1] if ":" in unit_id else unit_id
            for expected in expected_substrings:
                if expected.lower() in func_name.lower() or expected.lower() in unit_id.lower():
                    if found_rank is None:
                        found_rank = rank
                    break
            if found_rank:
                break

        query_result = {
            "query": query,
            "expected": expected_substrings,
            "found_rank": found_rank,
            "top_results": [(uid, f"{score:.3f}") for uid, score in search_results[:5]],
        }
        results["queries"].append(query_result)

        if found_rank:
            hits += 1
            reciprocal_ranks.append(1.0 / found_rank)
        else:
            reciprocal_ranks.append(0)

        status = f"✓ rank {found_rank}" if found_rank else "✗ not found"
        print(f"  [{status}] {query[:40]}...")

    results["hit_rate"] = hits / len(TEST_QUERIES) if TEST_QUERIES else 0
    results["mrr"] = sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0

    print(f"\n  Hit Rate: {results['hit_rate']:.1%} ({hits}/{len(TEST_QUERIES)})")
    print(f"  MRR: {results['mrr']:.3f}")

    return results


def main():
    """Run the benchmark."""
    import argparse

    parser = argparse.ArgumentParser(description="Benchmark embedding models")
    parser.add_argument(
        "--index", "-i",
        type=Path,
        default=Path.home() / "shadow-work" / ".tldr",
        help="Path to existing index (for search quality tests)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path(__file__).parent / "embedding_benchmark_results.json",
        help="Output file for results",
    )
    parser.add_argument(
        "--speed-only",
        action="store_true",
        help="Only run speed benchmarks (no search quality)",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("EMBEDDING MODEL BENCHMARK")
    print("=" * 70)

    all_results = {
        "speed_benchmarks": [],
        "search_quality": [],
    }

    # Test Ollama models
    print("\n" + "=" * 70)
    print("OLLAMA MODELS - Speed Benchmarks")
    print("=" * 70)

    for model in OLLAMA_MODELS:
        result = benchmark_model(args.index, model, backend="ollama")
        all_results["speed_benchmarks"].append(result)

    # Test sentence-transformers models
    print("\n" + "=" * 70)
    print("SENTENCE-TRANSFORMERS MODELS - Speed Benchmarks")
    print("=" * 70)

    for model in SENTENCE_TRANSFORMER_MODELS:
        result = benchmark_model(args.index, model, backend="sentence-transformers")
        all_results["speed_benchmarks"].append(result)

    # Search quality tests (only with matching model)
    if not args.speed_only and args.index.exists():
        print("\n" + "=" * 70)
        print("SEARCH QUALITY TESTS")
        print("=" * 70)
        print(f"Using index at: {args.index}")

        # Only test the model that matches the index
        # Testing other models against a differently-embedded index is unfair
        result = test_search_quality(args.index, "nomic-embed-text-v2-moe", backend="ollama")
        all_results["search_quality"].append(result)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print("\nSpeed Comparison (avg query embedding time):")
    print("-" * 50)

    speed_results = [r for r in all_results["speed_benchmarks"] if not r.get("skipped")]
    speed_results.sort(key=lambda x: x.get("avg_query_time", float("inf")))

    for r in speed_results:
        model = r["model"]
        backend = r["backend"]
        avg_time = r.get("avg_query_time", 0)
        dim = r["queries"][0].get("embedding_dim", "?") if r.get("queries") else "?"
        print(f"  {model:35} ({backend:20}): {avg_time:.3f}s  (dim: {dim})")

    # Save results
    with open(args.output, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
