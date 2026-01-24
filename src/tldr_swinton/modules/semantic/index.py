"""
Index management for tldr-swinton semantic search.

Orchestrates:
- Code extraction (via existing TLDR APIs)
- Embedding generation (via embeddings module)
- Vector storage (via vector_store module)
- Optional LLM summaries (via Ollama)
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Literal
from dataclasses import dataclass

logger = logging.getLogger(__name__)

from .embeddings import (
    embed_batch,
    embed_text,
    check_backends,
    BackendType,
)
from .vector_store import (
    VectorStore,
    CodeUnit,
    make_unit_id,
    get_file_hash,
)


# Ollama configuration for summaries
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_SUMMARY_MODEL = os.environ.get("OLLAMA_SUMMARY_MODEL", "llama3.2:3b")


@dataclass
class IndexStats:
    """Statistics from an indexing operation."""
    total_files: int = 0
    total_units: int = 0
    new_units: int = 0
    updated_units: int = 0
    unchanged_units: int = 0
    embed_model: str = ""
    embed_backend: str = ""


def _require_semantic_deps() -> None:
    try:
        import numpy  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Semantic indexing requires NumPy. "
            "Install with: pip install 'tldr-swinton[semantic-ollama]' "
            "or 'tldr-swinton[semantic]'."
        ) from exc
    try:
        import faiss  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Semantic indexing requires FAISS. "
            "Install with: pip install 'tldr-swinton[semantic-ollama]' "
            "or 'tldr-swinton[semantic]'."
        ) from exc


def _extract_code_units(
    project_path: str,
    language: Optional[str] = None,
    respect_ignore: bool = True,
    respect_gitignore: bool = False,
) -> list[CodeUnit]:
    """Extract code units from project using rich extraction API.

    Uses extract_file() to get full signatures, docstrings, and line numbers
    for high-quality semantic embeddings.

    Args:
        project_path: Path to project root
        language: Language to scan for (auto-detect if None)
        respect_ignore: Respect .tldrsignore patterns
        respect_gitignore: If True, also respect .gitignore patterns

    Returns:
        List of CodeUnit objects with rich metadata
    """
    from tldr_swinton.modules.core.api import extract_file
    from tldr_swinton.modules.core.workspace import iter_workspace_files

    project = Path(project_path).resolve()
    units = []

    # Supported extensions by language
    LANG_EXTENSIONS = {
        "python": {".py"},
        "typescript": {".ts", ".tsx"},
        "javascript": {".js", ".jsx"},
        "rust": {".rs"},
        "go": {".go"},
    }

    # Determine which extensions to scan
    if language:
        extensions = LANG_EXTENSIONS.get(language, set())
    else:
        extensions = set()
        for ext_set in LANG_EXTENSIONS.values():
            extensions.update(ext_set)

    source_files = iter_workspace_files(
        project,
        extensions=extensions,
        respect_ignore=respect_ignore,
        respect_gitignore=respect_gitignore,
    )

    for full_path in source_files:

        # Extract rich metadata using extract_file
        try:
            info = extract_file(str(full_path))
        except Exception as e:
            logger.debug("Failed to extract file %s: %s", full_path, e)
            continue

        rel_path = str(full_path.relative_to(project))
        file_hash = get_file_hash(full_path)
        lang = info.get("language", "unknown")

        # Extract functions with full metadata
        for func in info.get("functions", []):
            name = func.get("name", "")
            signature = func.get("signature", f"def {name}(...)")
            line = func.get("line_number", 1)
            docstring = func.get("docstring") or ""

            unit_id = make_unit_id(rel_path, name, line)
            units.append(CodeUnit(
                id=unit_id,
                name=name,
                file=rel_path,
                line=line,
                unit_type="function",
                signature=signature,
                language=lang,
                summary=docstring,  # Use docstring as initial summary
                file_hash=file_hash,
            ))

        # Extract classes with methods
        for class_info in info.get("classes", []):
            class_name = class_info.get("name", "")
            class_sig = class_info.get("signature", f"class {class_name}")
            class_line = class_info.get("line_number", 1)
            class_doc = class_info.get("docstring") or ""
            bases = class_info.get("bases", [])

            # Include bases in signature for context
            if bases:
                class_sig = f"class {class_name}({', '.join(bases)})"

            unit_id = make_unit_id(rel_path, class_name, class_line)
            units.append(CodeUnit(
                id=unit_id,
                name=class_name,
                file=rel_path,
                line=class_line,
                unit_type="class",
                signature=class_sig,
                language=lang,
                summary=class_doc,
                file_hash=file_hash,
            ))

            # Extract methods with full metadata
            for method in class_info.get("methods", []):
                method_name = method.get("name", "")
                method_sig = method.get("signature", f"def {method_name}(self)")
                method_line = method.get("line_number", class_line)
                method_doc = method.get("docstring") or ""

                full_name = f"{class_name}.{method_name}"
                unit_id = make_unit_id(rel_path, full_name, method_line)
                units.append(CodeUnit(
                    id=unit_id,
                    name=full_name,
                    file=rel_path,
                    line=method_line,
                    unit_type="method",
                    signature=method_sig,
                    language=lang,
                    summary=method_doc,
                    file_hash=file_hash,
                ))

    return units


import re

# Embedding text limits
_MAX_DOC_CHARS = 800
_MAX_PATH_PARTS = 3


def _clean_doc(doc: str) -> str:
    """Truncate and clean docstring for embedding.

    Long docstrings with parameter tables and examples can drown out
    the "what it does" signal. Keep first ~800 chars.
    """
    doc = (doc or "").strip()
    # Collapse whitespace so we don't embed indentation noise
    doc = re.sub(r"\s+", " ", doc)
    if len(doc) > _MAX_DOC_CHARS:
        doc = doc[:_MAX_DOC_CHARS] + "…"
    return doc


def _short_path(p: str) -> str:
    """Shorten path to last N segments to reduce noise.

    Paths like 'utils/', 'helpers/', 'common/' can pollute embeddings.
    Keep only the meaningful last segments.
    """
    parts = Path(p).as_posix().split("/")
    return "/".join(parts[-_MAX_PATH_PARTS:]) if parts else p


def _build_embed_text(unit: CodeUnit) -> str:
    """Build text for embedding a code unit.

    Creates a structured representation optimized for embedding models:
    - Field labels help models separate metadata from meaning
    - Truncated docstrings prevent noise from examples/tables
    - Short paths reduce pollution from generic folder names

    Format:
        Language: python
        Kind: function
        Name: verify_token
        Signature: def verify_token(token: str) -> Optional[str]
        Doc: Verify JWT token and return the user_id if valid.
        File: auth/tokens.py
    """
    doc = _clean_doc(unit.summary)
    path = _short_path(unit.file)

    # Labels help embedding models distinguish field types
    parts = [
        f"Language: {unit.language}",
        f"Kind: {unit.unit_type}",
        f"Name: {unit.name}",
        f"Signature: {unit.signature}",
    ]
    if doc:
        parts.append(f"Doc: {doc}")
    parts.append(f"File: {path}")

    return "\n".join(parts)


def _generate_summaries_ollama(
    units: list[CodeUnit],
    project_path: str,
    show_progress: bool = True
) -> dict[str, str]:
    """Generate one-line summaries for units using Ollama.

    Args:
        units: Code units to summarize
        project_path: Project root for reading source
        show_progress: Show progress indicator

    Returns:
        Dict mapping unit ID to summary
    """
    import urllib.request
    import urllib.error

    project = Path(project_path).resolve()
    summaries = {}

    # Check Ollama availability
    try:
        url = f"{OLLAMA_HOST}/api/tags"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2) as response:
            data = json.loads(response.read().decode())
            models = [m["name"].split(":")[0] for m in data.get("models", [])]
            model_base = OLLAMA_SUMMARY_MODEL.split(":")[0]
            if model_base not in models:
                logger.warning("Summary model %s not available, skipping summaries", OLLAMA_SUMMARY_MODEL)
                return {}
    except Exception as e:
        logger.debug("Ollama unavailable for summaries: %s", e)
        return {}

    # Progress handling
    console = None
    if show_progress and sys.stdout.isatty():
        try:
            from rich.progress import Progress, SpinnerColumn, TextColumn
            from rich.console import Console
            console = Console()
        except ImportError:
            pass

    def summarize_one(unit: CodeUnit) -> Optional[str]:
        """Generate summary for a single unit."""
        # Read source code
        full_path = project / unit.file
        if not full_path.exists():
            return None

        try:
            content = full_path.read_text()
            lines = content.split("\n")

            # Extract ~20 lines around the unit
            start = max(0, unit.line - 1)
            end = min(len(lines), start + 20)
            snippet = "\n".join(lines[start:end])

            # Build prompt
            prompt = f"""Summarize this {unit.unit_type} in ONE sentence (max 15 words).
Focus on what it does, not how.

{unit.signature}

Code:
{snippet}

Summary:"""

            # Call Ollama
            url = f"{OLLAMA_HOST}/api/generate"
            payload = json.dumps({
                "model": OLLAMA_SUMMARY_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 50, "temperature": 0.3}
            }).encode()

            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())
                summary = data.get("response", "").strip()
                # Clean up - take first sentence only
                summary = summary.split(".")[0].strip()
                if summary and not summary.endswith("."):
                    summary += "."
                return summary

        except Exception as e:
            logger.debug("Failed to generate summary for %s: %s", unit.name, e)
            return None

    # Generate summaries
    if console:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Generating summaries ({OLLAMA_SUMMARY_MODEL})...", total=len(units))

            for unit in units:
                summary = summarize_one(unit)
                if summary:
                    summaries[unit.id] = summary
                progress.update(task, advance=1)
    else:
        for unit in units:
            summary = summarize_one(unit)
            if summary:
                summaries[unit.id] = summary

    return summaries


def build_index(
    project_path: str,
    language: Optional[str] = None,
    backend: BackendType = "auto",
    embed_model: Optional[str] = None,
    generate_summaries: bool = False,
    rebuild: bool = False,
    show_progress: bool = True,
    respect_ignore: bool = True,
    respect_gitignore: bool = False,
) -> IndexStats:
    """Build or update the semantic index for a project.

    Creates/updates .tldrs/index/ with:
    - vectors.faiss - Vector index
    - units.json - Unit metadata
    - meta.json - Index metadata

    Args:
        project_path: Path to project root
        language: Language to index (auto-detect if None)
        backend: Embedding backend ("ollama", "sentence-transformers", "auto")
        embed_model: Specific model to use
        generate_summaries: Generate one-line summaries with Ollama
        rebuild: Force full rebuild (ignore existing index)
        show_progress: Show progress indicators
        respect_ignore: Respect .tldrsignore patterns
        respect_gitignore: If True, also respect .gitignore patterns

    Returns:
        IndexStats with indexing statistics
    """
    _require_semantic_deps()
    stats = IndexStats()
    project = Path(project_path).resolve()

    # Load or create vector store
    store = VectorStore(str(project))
    existing_units = {}
    existing_vectors = {}  # Map unit ID -> existing vector

    if not rebuild and store.load():
        # Index exists - build lookups for incremental update
        old_units = store.get_all_units()
        old_vectors = store.reconstruct_all_vectors()

        for i, unit in enumerate(old_units):
            existing_units[unit.id] = unit
            if i < len(old_vectors):
                existing_vectors[unit.id] = old_vectors[i]

    # Extract code units
    if show_progress:
        print("Scanning codebase...")
    units = _extract_code_units(
        str(project),
        language,
        respect_ignore=respect_ignore,
        respect_gitignore=respect_gitignore,
    )
    stats.total_files = len(set(u.file for u in units))
    stats.total_units = len(units)

    if not units:
        print("No code units found to index.")
        return stats

    # Determine which units need (re)embedding and which can reuse vectors
    units_to_embed = []
    texts_to_embed = []
    all_units = []  # Final unit list in order
    all_vectors = []  # Corresponding vectors (None for units needing embedding)
    embed_indices = []  # Indices in all_vectors that need embedding

    for unit in units:
        existing = existing_units.get(unit.id)
        existing_vec = existing_vectors.get(unit.id)

        if existing and existing.file_hash == unit.file_hash and existing_vec is not None:
            # Unchanged - reuse existing vector
            all_units.append(unit)
            all_vectors.append(existing_vec)
            stats.unchanged_units += 1
        else:
            # New or changed - needs embedding
            all_units.append(unit)
            all_vectors.append(None)  # Placeholder
            embed_indices.append(len(all_vectors) - 1)
            units_to_embed.append(unit)
            texts_to_embed.append(_build_embed_text(unit))

            if existing:
                stats.updated_units += 1
            else:
                stats.new_units += 1

    # Generate summaries if requested
    if generate_summaries and units_to_embed:
        if show_progress:
            print(f"Generating summaries for {len(units_to_embed)} units...")
        summaries = _generate_summaries_ollama(units_to_embed, str(project), show_progress)
        for unit in units_to_embed:
            if unit.id in summaries:
                unit.summary = summaries[unit.id]

    # Embed only new/changed units
    if units_to_embed:
        if show_progress:
            print(f"Embedding {len(units_to_embed)} code units ({stats.unchanged_units} unchanged, reusing vectors)...")

        results = embed_batch(texts_to_embed, backend=backend, model=embed_model, show_progress=show_progress)

        # Record backend info
        if results:
            stats.embed_model = results[0].model
            stats.embed_backend = results[0].backend

        # Fill in the new embeddings at the right positions
        for i, result in zip(embed_indices, results):
            all_vectors[i] = result.vector

        all_embeddings = all_vectors
    else:
        # No changes
        if show_progress:
            print("Index is up to date.")
        return stats

    # Build and save index
    if show_progress:
        print("Building FAISS index...")

    store.build(
        all_units,
        all_vectors,
        embed_model=stats.embed_model,
        embed_backend=stats.embed_backend
    )
    store.save()

    if show_progress:
        print(f"✓ Indexed {len(all_units)} code units")
        print(f"  Backend: {stats.embed_backend} ({stats.embed_model})")
        print(f"  Location: {store.index_dir}")

    return stats


# Pattern for identifier-like queries (function/method names)
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_\.]*$")


def search_index(
    project_path: str,
    query: str,
    k: int = 10,
    backend: BackendType = "auto",
    model: Optional[str] = None
) -> list[dict]:
    """Search the semantic index.

    Uses a hybrid approach:
    1. If query looks like an identifier, try exact name match first
    2. Fall back to semantic search for natural language queries

    Args:
        project_path: Path to project root
        query: Natural language query or identifier name
        k: Number of results
        backend: Embedding backend (should match index)
        model: Embedding model (should match index)

    Returns:
        List of result dicts with unit info and score
    """
    _require_semantic_deps()
    project = Path(project_path).resolve()
    store = VectorStore(str(project))

    if not store.load():
        raise FileNotFoundError(
            f"No index found at {store.index_dir}. Run `tldrs index` first."
        )

    # Use index's model/backend if not specified
    if model is None:
        model = store.metadata.embed_model
    if backend == "auto" and store.metadata.embed_backend:
        backend = store.metadata.embed_backend  # type: ignore

    query_stripped = query.strip()
    exact_matches = []

    # Lexical fast-path: if query looks like an identifier, try exact match first
    if _IDENT_RE.match(query_stripped):
        exact_matches = store.get_units_by_name(query_stripped)

        # Also try partial match for Class.method style queries
        if not exact_matches and "." in query_stripped:
            # Try matching just the method name
            parts = query_stripped.split(".")
            method_name = parts[-1]
            full_name = query_stripped
            exact_matches = [
                u for u in store.get_all_units()
                if u.name == full_name or u.name.endswith(f".{method_name}")
            ]

    # Format exact matches with synthetic high score (1.0)
    exact_results = [
        {
            "name": u.name,
            "file": u.file,
            "line": u.line,
            "type": u.unit_type,
            "signature": u.signature,
            "summary": u.summary,
            "score": 1.0,  # Perfect match
            "rank": i + 1,
        }
        for i, u in enumerate(exact_matches[:k])
    ]

    # If we got exact matches, fill remaining slots with semantic search
    remaining_k = k - len(exact_results)
    if remaining_k <= 0:
        return exact_results

    # Embed query for semantic search
    result = embed_text(query, backend=backend, model=model)

    # Search
    semantic_results = store.search(result.vector, k=remaining_k + len(exact_matches))

    # Filter out any semantic results that are already in exact matches
    exact_ids = {u.id for u in exact_matches}
    semantic_results = [r for r in semantic_results if r.unit.id not in exact_ids]

    # Format semantic results
    semantic_formatted = [
        {
            "name": r.unit.name,
            "file": r.unit.file,
            "line": r.unit.line,
            "type": r.unit.unit_type,
            "signature": r.unit.signature,
            "summary": r.unit.summary,
            "score": round(r.score, 4),
            "rank": len(exact_results) + i + 1,
        }
        for i, r in enumerate(semantic_results[:remaining_k])
    ]

    return exact_results + semantic_formatted


def get_index_info(project_path: str) -> Optional[dict]:
    """Get information about the project's index.

    Returns:
        Dict with index metadata, or None if no index
    """
    project = Path(project_path).resolve()
    store = VectorStore(str(project))

    if not store.load():
        return None

    return {
        "count": store.count,
        "dimension": store.metadata.dimension,
        "embed_model": store.metadata.embed_model,
        "embed_backend": store.metadata.embed_backend,
        "index_path": str(store.index_dir),
    }
