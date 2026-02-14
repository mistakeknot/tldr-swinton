"""
Index management for tldr-swinton semantic search.

Orchestrates:
- Code extraction (via existing TLDR APIs)
- Text preparation (shared across all backends)
- Backend-agnostic build/search via SearchBackend protocol
- Optional LLM summaries (via Ollama)
- BM25 identifier fast-path
"""

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from .backend import (
    CodeUnit,
    SearchResult,
    BackendInfo,
    get_backend,
    get_file_hash,
    make_unit_id,
    _colbert_available,
    _read_index_backend,
)

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Code extraction (shared across backends)
# ---------------------------------------------------------------------------


def _extract_code_units(
    project_path: str,
    language: Optional[str] = None,
    respect_ignore: bool = True,
    respect_gitignore: bool = False,
) -> list[CodeUnit]:
    """Extract code units from project using rich extraction API.

    Uses extract_file() to get full signatures, docstrings, and line numbers
    for high-quality semantic embeddings.
    """
    from tldr_swinton.modules.core.api import extract_file
    from tldr_swinton.modules.core.workspace import iter_workspace_files

    project = Path(project_path).resolve()
    units = []

    LANG_EXTENSIONS = {
        "python": {".py"},
        "typescript": {".ts", ".tsx"},
        "javascript": {".js", ".jsx"},
        "rust": {".rs"},
        "go": {".go"},
    }

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
        try:
            info = extract_file(str(full_path))
        except Exception as e:
            logger.debug("Failed to extract file %s: %s", full_path, e)
            continue

        rel_path = str(full_path.relative_to(project))
        file_hash = get_file_hash(full_path)
        lang = info.get("language", "unknown")

        for func in info.get("functions", []):
            name = func.get("name", "")
            signature = func.get("signature", f"def {name}(...)")
            line = func.get("line_number", 1)
            docstring = func.get("docstring") or ""

            unit_id = make_unit_id(rel_path, name, line)
            units.append(CodeUnit(
                id=unit_id, name=name, file=rel_path, line=line,
                unit_type="function", signature=signature,
                language=lang, summary=docstring, file_hash=file_hash,
            ))

        for class_info in info.get("classes", []):
            class_name = class_info.get("name", "")
            class_sig = class_info.get("signature", f"class {class_name}")
            class_line = class_info.get("line_number", 1)
            class_doc = class_info.get("docstring") or ""
            bases = class_info.get("bases", [])

            if bases:
                class_sig = f"class {class_name}({', '.join(bases)})"

            unit_id = make_unit_id(rel_path, class_name, class_line)
            units.append(CodeUnit(
                id=unit_id, name=class_name, file=rel_path, line=class_line,
                unit_type="class", signature=class_sig,
                language=lang, summary=class_doc, file_hash=file_hash,
            ))

            for method in class_info.get("methods", []):
                method_name = method.get("name", "")
                method_sig = method.get("signature", f"def {method_name}(self)")
                method_line = method.get("line_number", class_line)
                method_doc = method.get("docstring") or ""

                full_name = f"{class_name}.{method_name}"
                unit_id = make_unit_id(rel_path, full_name, method_line)
                units.append(CodeUnit(
                    id=unit_id, name=full_name, file=rel_path, line=method_line,
                    unit_type="method", signature=method_sig,
                    language=lang, summary=method_doc, file_hash=file_hash,
                ))

    return units


# ---------------------------------------------------------------------------
# Text preparation (shared across backends)
# ---------------------------------------------------------------------------

_MAX_DOC_CHARS = 800
_MAX_PATH_PARTS = 3


def _clean_doc(doc: str) -> str:
    """Truncate and clean docstring for embedding."""
    doc = (doc or "").strip()
    doc = re.sub(r"\s+", " ", doc)
    if len(doc) > _MAX_DOC_CHARS:
        doc = doc[:_MAX_DOC_CHARS] + "…"
    return doc


def _short_path(p: str) -> str:
    """Shorten path to last N segments to reduce noise."""
    parts = Path(p).as_posix().split("/")
    return "/".join(parts[-_MAX_PATH_PARTS:]) if parts else p


def _build_embed_text(unit: CodeUnit) -> str:
    """Build text for embedding a code unit.

    Creates a structured representation optimized for embedding models:
    - Field labels help models separate metadata from meaning
    - Truncated docstrings prevent noise from examples/tables
    - Short paths reduce pollution from generic folder names
    """
    doc = _clean_doc(unit.summary)
    path = _short_path(unit.file)

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


# ---------------------------------------------------------------------------
# Ollama summaries (optional pre-processing)
# ---------------------------------------------------------------------------


def _generate_summaries_ollama(
    units: list[CodeUnit],
    project_path: str,
    show_progress: bool = True,
) -> dict[str, str]:
    """Generate one-line summaries for units using Ollama."""
    import urllib.request
    import urllib.error

    project = Path(project_path).resolve()
    summaries = {}

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

    console = None
    if show_progress and sys.stdout.isatty():
        try:
            from rich.progress import Progress, SpinnerColumn, TextColumn
            from rich.console import Console
            console = Console()
        except ImportError:
            pass

    def summarize_one(unit: CodeUnit) -> Optional[str]:
        full_path = project / unit.file
        if not full_path.exists():
            return None
        try:
            content = full_path.read_text()
            lines = content.split("\n")
            start = max(0, unit.line - 1)
            end = min(len(lines), start + 20)
            snippet = "\n".join(lines[start:end])

            prompt = (
                f"Summarize this {unit.unit_type} in ONE sentence (max 15 words).\n"
                f"Focus on what it does, not how.\n\n"
                f"{unit.signature}\n\nCode:\n{snippet}\n\nSummary:"
            )

            url = f"{OLLAMA_HOST}/api/generate"
            payload = json.dumps({
                "model": OLLAMA_SUMMARY_MODEL, "prompt": prompt,
                "stream": False, "options": {"num_predict": 50, "temperature": 0.3},
            }).encode()
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())
                summary = data.get("response", "").strip()
                summary = summary.split(".")[0].strip()
                if summary and not summary.endswith("."):
                    summary += "."
                return summary
        except Exception as e:
            logger.debug("Failed to generate summary for %s: %s", unit.name, e)
            return None

    if console:
        from rich.progress import Progress, SpinnerColumn, TextColumn
        with Progress(
            SpinnerColumn(), TextColumn("[bold]{task.description}"), console=console,
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


# ---------------------------------------------------------------------------
# Build / Search / Info — delegate to backend
# ---------------------------------------------------------------------------


def build_index(
    project_path: str,
    language: Optional[str] = None,
    backend: str = "auto",
    embed_model: Optional[str] = None,
    generate_summaries: bool = False,
    rebuild: bool = False,
    show_progress: bool = True,
    respect_ignore: bool = True,
    respect_gitignore: bool = False,
) -> IndexStats:
    """Build or update the semantic index for a project.

    Args:
        project_path: Path to project root
        language: Language to index (auto-detect if None)
        backend: Search backend: "auto" | "faiss" | "colbert"
        embed_model: Specific model to use (FAISS backend only)
        generate_summaries: Generate one-line summaries with Ollama
        rebuild: Force full rebuild (ignore existing index)
        show_progress: Show progress indicators
        respect_ignore: Respect .tldrsignore patterns
        respect_gitignore: If True, also respect .gitignore patterns

    Returns:
        IndexStats with indexing statistics
    """
    stats = IndexStats()
    project = Path(project_path).resolve()

    # Extract code units
    if show_progress:
        print("Scanning codebase...")
    units = _extract_code_units(
        str(project), language,
        respect_ignore=respect_ignore,
        respect_gitignore=respect_gitignore,
    )
    stats.total_files = len(set(u.file for u in units))
    stats.total_units = len(units)

    if not units:
        if show_progress:
            print("No code units found to index.")
        return stats

    # Build embedding texts
    texts = [_build_embed_text(u) for u in units]

    # Generate summaries if requested (before embedding)
    if generate_summaries:
        if show_progress:
            print(f"Generating summaries for {len(units)} units...")
        summaries = _generate_summaries_ollama(units, str(project), show_progress)
        for unit in units:
            if unit.id in summaries:
                unit.summary = summaries[unit.id]
        # Rebuild texts with updated summaries
        texts = [_build_embed_text(u) for u in units]

    # Get backend and build
    search_backend = get_backend(str(project), backend=backend)

    if show_progress:
        backend_info = search_backend.info()
        print(f"Building index with {backend_info.backend_name} backend...")

    backend_stats = search_backend.build(units, texts, rebuild=rebuild)
    search_backend.save()

    # Update stats from backend
    stats.new_units = backend_stats.new_units
    stats.updated_units = backend_stats.updated_units
    stats.unchanged_units = backend_stats.unchanged_units
    stats.embed_model = backend_stats.embed_model
    stats.embed_backend = backend_stats.backend_name

    # Build BM25 index for identifier fast-path (all backends)
    _build_bm25(search_backend, units, texts, show_progress)

    if show_progress:
        print(f"✓ Indexed {stats.total_units} code units")
        print(f"  Backend: {stats.embed_backend} ({stats.embed_model})")
        bi = search_backend.info()
        print(f"  Location: {bi.index_path}")

    return stats


def _build_bm25(search_backend, units, texts, show_progress=False):
    """Build BM25 index for identifier fast-path (used by all backends)."""
    try:
        from .bm25_store import BM25Store

        # BM25 is stored alongside the main index
        bi = search_backend.info()
        bm25_dir = Path(bi.index_path)
        # For ColBERT, store BM25 in the parent index dir (not plaid subdir)
        if bi.backend_name == "colbert":
            bm25_dir = bm25_dir.parent

        bm25 = BM25Store(bm25_dir)
        all_ids = [u.id for u in units]
        bm25.build(all_ids, texts)
        bm25.save()
        if show_progress:
            print("  BM25 lexical index: built")
    except ImportError:
        if show_progress:
            print("  BM25 lexical index: skipped (rank-bm25 not installed)")
    except Exception as e:
        logger.debug("Failed to build BM25 index: %s", e)


# Pattern for identifier-like queries (function/method names)
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_\.]*$")


def search_index(
    project_path: str,
    query: str,
    k: int = 10,
    **kwargs,
) -> list[dict]:
    """Search the semantic index.

    Uses a hybrid approach:
    1. If query looks like an identifier, try exact name match first (BM25)
    2. Delegate semantic search to the active backend

    Args:
        project_path: Path to project root
        query: Natural language query or identifier name
        k: Number of results

    Returns:
        List of result dicts with unit info and score
    """
    project = Path(project_path).resolve()

    # Get the backend (auto-detects from meta.json)
    search_backend = get_backend(str(project), backend="auto")

    if not search_backend.load():
        index_dir = project / ".tldrs" / "index"
        raise FileNotFoundError(
            f"No index found at {index_dir}. Run `tldrs index` first."
        )

    # Migration nudge: if FAISS index but pylate available
    bi = search_backend.info()
    if bi.backend_name == "faiss" and _colbert_available():
        logger.info(
            "ColBERT backend available. Rebuild for better search quality: "
            "tldrs semantic index --backend=colbert"
        )

    query_stripped = query.strip()
    exact_results = []

    # Identifier fast-path: exact name match via loaded backend
    if _IDENT_RE.match(query_stripped):
        exact_matches = _identifier_search(search_backend, query_stripped)
        exact_results = [
            {
                "name": u.name, "file": u.file, "line": u.line,
                "type": u.unit_type, "signature": u.signature,
                "summary": u.summary, "score": 1.0, "rank": i + 1,
                "backend": bi.backend_name,
            }
            for i, u in enumerate(exact_matches[:k])
        ]

    remaining_k = k - len(exact_results)
    if remaining_k <= 0:
        return exact_results

    # Semantic search via backend
    results = search_backend.search(query, k=remaining_k + len(exact_results))

    # Filter out exact matches
    exact_ids = {r["name"] for r in exact_results}
    semantic_formatted = []
    for i, r in enumerate(results):
        if r.unit.name in exact_ids:
            continue
        semantic_formatted.append({
            "name": r.unit.name, "file": r.unit.file, "line": r.unit.line,
            "type": r.unit.unit_type, "signature": r.unit.signature,
            "summary": r.unit.summary, "score": round(r.score, 4),
            "rank": len(exact_results) + len(semantic_formatted) + 1,
            "backend": bi.backend_name,
        })
        if len(semantic_formatted) >= remaining_k:
            break

    return exact_results + semantic_formatted


def _identifier_search(search_backend, query: str) -> list[CodeUnit]:
    """Fast-path: exact name match for identifier-like queries."""
    # FAISSBackend has get_units_by_name; ColBERTBackend uses dict lookup
    if hasattr(search_backend, "get_units_by_name"):
        matches = search_backend.get_units_by_name(query)
    elif hasattr(search_backend, "_units"):
        # ColBERTBackend stores units as dict
        matches = [u for u in search_backend._units.values() if u.name == query]
    else:
        matches = []

    # Also try Class.method partial match
    if not matches and "." in query:
        parts = query.split(".")
        method_name = parts[-1]
        if hasattr(search_backend, "get_all_units"):
            all_units = search_backend.get_all_units()
        elif hasattr(search_backend, "_units"):
            all_units = list(search_backend._units.values())
        else:
            all_units = []
        matches = [
            u for u in all_units
            if u.name == query or u.name.endswith(f".{method_name}")
        ]

    return matches


def get_index_info(project_path: str) -> Optional[dict]:
    """Get information about the project's index.

    Returns:
        Dict with index metadata, or None if no index
    """
    try:
        search_backend = get_backend(project_path, backend="auto")
        if not search_backend.load():
            return None
        bi = search_backend.info()
        return {
            "backend": bi.backend_name,
            "count": bi.count,
            "dimension": bi.dimension,
            "embed_model": bi.model,
            "index_path": bi.index_path,
            "extra": bi.extra,
        }
    except RuntimeError:
        return None
