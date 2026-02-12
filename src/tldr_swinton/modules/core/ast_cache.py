"""File-system AST cache for fast CLI fallback.

Caches HybridExtractor.extract() results (ModuleInfo objects) to disk
so that one-shot CLI calls (hooks, setup scripts) don't pay 500-800ms
for uncached AST extraction. Expected: ~50ms for cached files.

Cache location: .tldrs/cache/ast/
Key: (relative_file_path, mtime_ns, size) — invalidates on file change.
Storage: One JSON file per source file.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from pathlib import Path

from .ast_extractor import (
    CallGraphInfo,
    ClassInfo,
    FunctionInfo,
    ImportInfo,
    ModuleInfo,
)

logger = logging.getLogger(__name__)


def _module_info_to_dict(info: ModuleInfo) -> dict:
    """Lossless serialization of ModuleInfo to JSON-safe dict."""
    return dataclasses.asdict(info)


def _module_info_from_dict(d: dict) -> ModuleInfo:
    """Reconstruct ModuleInfo from a dict produced by _module_info_to_dict."""
    imports = [ImportInfo(**imp) for imp in d.get("imports", [])]

    classes = []
    for cd in d.get("classes", []):
        methods = [FunctionInfo(**md) for md in cd.pop("methods", [])]
        classes.append(ClassInfo(**cd, methods=methods))

    functions = [FunctionInfo(**fd) for fd in d.get("functions", [])]

    cg_data = d.get("call_graph", {})
    call_graph = CallGraphInfo(
        calls=cg_data.get("calls", {}),
        called_by=cg_data.get("called_by", {}),
    )

    return ModuleInfo(
        file_path=d["file_path"],
        language=d["language"],
        docstring=d.get("docstring"),
        imports=imports,
        classes=classes,
        functions=functions,
        call_graph=call_graph,
    )


class ASTCache:
    """File-system cache for ModuleInfo extraction results."""

    def __init__(self, project_root: Path):
        self._project = project_root.resolve()
        self._cache_dir = self._project / ".tldrs" / "cache" / "ast"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._hits = 0
        self._misses = 0

    def _cache_path(self, file_path: Path) -> Path:
        """Derive on-disk cache file from source file path."""
        try:
            rel = str(file_path.resolve().relative_to(self._project))
        except ValueError:
            rel = str(file_path)
        key = hashlib.md5(rel.encode()).hexdigest()
        return self._cache_dir / f"{key}.json"

    def get(self, file_path: Path) -> ModuleInfo | None:
        """Return cached ModuleInfo if file hasn't changed, else None."""
        cp = self._cache_path(file_path)
        if not cp.exists():
            self._misses += 1
            return None

        try:
            stat = file_path.stat()
        except OSError:
            self._misses += 1
            return None

        try:
            with open(cp) as f:
                entry = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("ast_cache: corrupt entry for %s: %s", file_path, exc)
            self._misses += 1
            return None

        # Validate freshness
        if entry.get("mtime_ns") != stat.st_mtime_ns or entry.get("size") != stat.st_size:
            self._misses += 1
            return None

        try:
            info = _module_info_from_dict(entry["module_info"])
            self._hits += 1
            return info
        except Exception as exc:
            logger.debug("ast_cache: deserialization error for %s: %s", file_path, exc)
            self._misses += 1
            return None

    def put(self, file_path: Path, info: ModuleInfo) -> None:
        """Write a ModuleInfo cache entry for the given file."""
        try:
            stat = file_path.stat()
        except OSError:
            return

        entry = {
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
            "module_info": _module_info_to_dict(info),
        }

        cp = self._cache_path(file_path)
        try:
            with open(cp, "w") as f:
                json.dump(entry, f, separators=(",", ":"))
        except OSError as exc:
            logger.debug("ast_cache: write error for %s: %s", file_path, exc)

    def invalidate(self, file_path: Path) -> None:
        """Remove cache entry for a file."""
        cp = self._cache_path(file_path)
        cp.unlink(missing_ok=True)

    def clear(self) -> None:
        """Remove all cached entries."""
        for p in self._cache_dir.glob("*.json"):
            p.unlink(missing_ok=True)

    @property
    def stats(self) -> dict[str, int]:
        return {"hits": self._hits, "misses": self._misses}
