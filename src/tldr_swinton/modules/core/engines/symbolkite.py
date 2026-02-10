from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sys

from ..ast_extractor import FunctionInfo
from ..cfg_extractor import (
    extract_c_cfg,
    extract_csharp_cfg,
    extract_elixir_cfg,
    extract_go_cfg,
    extract_java_cfg,
    extract_kotlin_cfg,
    extract_lua_cfg,
    extract_php_cfg,
    extract_python_cfg,
    extract_rust_cfg,
    extract_scala_cfg,
    extract_swift_cfg,
    extract_typescript_cfg,
)
from ..contextpack_engine import Candidate, ContextPackEngine
from ..hybrid_extractor import HybridExtractor
from ..project_index import ProjectIndex
from ..type_pruner import prune_expansion
from ..workspace import iter_workspace_files
from ..zoom import ZoomLevel


@dataclass
class FunctionContext:
    """Context for a single function."""

    name: str
    file: str
    line: int
    signature: str
    docstring: str | None = None
    calls: list[str] = field(default_factory=list)
    depth: int = 0
    blocks: int | None = None
    cyclomatic: int | None = None


@dataclass
class RelevantContext:
    """The full context returned by get_relevant_context."""

    entry_point: str
    depth: int
    functions: list[FunctionContext] = field(default_factory=list)
    ambiguous: bool = False
    candidates: list[str] = field(default_factory=list)

    def to_llm_string(self) -> str:
        """Format for LLM injection."""
        lines = [
            f"## Code Context: {self.entry_point} (depth={self.depth})",
            "",
        ]
        if self.ambiguous and self.candidates:
            lines.append("Ambiguous entry point. Candidates:")
            for cand in self.candidates:
                lines.append(f"- {cand}")
            return "\n".join(lines)

        for func in self.functions:
            indent = "  " * min(func.depth, self.depth)

            short_file = Path(func.file).name if func.file else "?"
            lines.append(f"{indent}📍 {func.name} ({short_file}:{func.line})")
            lines.append(f"{indent}   {func.signature}")

            if func.docstring:
                doc = func.docstring.split("\n")[0][:80]
                lines.append(f"{indent}   # {doc}")

            if func.blocks is not None:
                complexity_marker = "🔥" if func.cyclomatic and func.cyclomatic > 10 else ""
                lines.append(
                    f"{indent}   ⚡ complexity: {func.cyclomatic or '?'} ({func.blocks} blocks) {complexity_marker}"
                )

            if func.calls:
                calls_str = ", ".join(func.calls[:5])
                if len(func.calls) > 5:
                    calls_str += f" (+{len(func.calls) - 5} more)"
                lines.append(f"{indent}   → calls: {calls_str}")

            lines.append("")

        result = "\n".join(lines)
        token_estimate = len(result) // 4
        return result + f"\n---\n📊 {len(self.functions)} functions | ~{token_estimate} tokens"


def _get_module_exports(
    project: Path,
    module_path: str,
    language: str = "python",
    include_docstrings: bool = False,
) -> "RelevantContext":
    """Get all exports from a module path."""
    ext_map = {
        "python": ".py",
        "typescript": ".ts",
        "go": ".go",
        "rust": ".rs",
    }
    ext = ext_map.get(language, ".py")

    module_file = project / f"{module_path}{ext}"

    if not module_file.exists():
        init_file = project / module_path / "__init__.py"
        if init_file.exists():
            module_file = init_file
        else:
            raise ValueError(
                f"Module not found: {module_path} (tried {module_file} and {init_file})"
            )

    extractor = HybridExtractor()
    try:
        module_info = extractor.extract(str(module_file))
    except Exception as e:
        raise ValueError(f"Failed to parse module {module_path}: {e}")

    functions: list[FunctionContext] = []

    for func in module_info.functions:
        ctx = FunctionContext(
            name=func.name,
            signature=func.signature(),
            file=str(module_file),
            line=func.line_number,
            docstring=func.docstring if include_docstrings else None,
            calls=[],
        )
        functions.append(ctx)

    for cls in module_info.classes:
        ctx = FunctionContext(
            name=cls.name,
            signature=f"class {cls.name}",
            file=str(module_file),
            line=cls.line_number,
            docstring=cls.docstring if include_docstrings else None,
            calls=[m.name for m in cls.methods],
        )
        functions.append(ctx)

        for method in cls.methods:
            method_ctx = FunctionContext(
                name=f"{cls.name}.{method.name}",
                signature=method.signature(),
                file=str(module_file),
                line=method.line_number,
                docstring=method.docstring if include_docstrings else None,
                calls=[],
            )
            functions.append(method_ctx)

    return RelevantContext(
        entry_point=module_path,
        depth=0,
        functions=functions,
    )


def get_relevant_context(
    project: str | Path,
    entry_point: str,
    depth: int = 2,
    language: str = "python",
    include_docstrings: bool = False,
    disambiguate: bool = True,
    type_prune: bool = False,
) -> RelevantContext:
    """
    Get token-efficient context for an LLM starting from an entry point.
    """
    project = Path(project).resolve()

    if "/" in entry_point and "." not in entry_point:
        return _get_module_exports(project, entry_point, language, include_docstrings)

    ext_for_lang = {
        "python": ".py",
        "typescript": ".ts",
        "go": ".go",
        "rust": ".rs",
    }.get(language, ".py")

    if "." not in entry_point and "/" not in entry_point:
        module_file = None
        for f in iter_workspace_files(project, extensions={ext_for_lang}):
            if f.name == f"{entry_point}{ext_for_lang}":
                module_file = f
                break

        if module_file:
            rel_path = module_file.relative_to(project)
            module_path = str(rel_path.with_suffix(""))
            return _get_module_exports(project, module_path, language, include_docstrings)

    idx = ProjectIndex.build(project, language, include_sources=True)

    cfg_extractors = {
        "python": extract_python_cfg,
        "typescript": extract_typescript_cfg,
        "go": extract_go_cfg,
        "rust": extract_rust_cfg,
        "java": extract_java_cfg,
        "c": extract_c_cfg,
        "php": extract_php_cfg,
        "kotlin": extract_kotlin_cfg,
        "swift": extract_swift_cfg,
        "csharp": extract_csharp_cfg,
        "scala": extract_scala_cfg,
        "lua": extract_lua_cfg,
        "elixir": extract_elixir_cfg,
    }
    cfg_extractor_fn = cfg_extractors.get(language, extract_python_cfg)

    visited: set[str] = set()
    resolved, candidates = idx.resolve_entry_symbols(entry_point, disambiguate)
    if candidates and not resolved:
        return RelevantContext(
            entry_point=entry_point,
            depth=depth,
            functions=[],
            ambiguous=True,
            candidates=candidates,
        )
    queue = [(symbol_id, 0) for symbol_id in resolved]
    result_functions: list[FunctionContext] = []

    while queue:
        symbol_id, current_depth = queue.pop(0)

        if symbol_id in visited or current_depth > depth:
            continue
        visited.add(symbol_id)

        func_info = idx.symbol_index.get(symbol_id)
        if func_info:
            file_path = idx.symbol_files[symbol_id]
            raw_name = idx.symbol_raw_names.get(symbol_id, func_info.name)

            blocks = None
            cyclomatic = None
            if file_path in idx.file_sources:
                try:
                    cfg = cfg_extractor_fn(idx.file_sources[file_path], raw_name)
                    if cfg and cfg.blocks:
                        blocks = len(cfg.blocks)
                        cyclomatic = cfg.cyclomatic_complexity
                except Exception:
                    pass

            signature = idx.signature_overrides.get(symbol_id, func_info.signature())

            ctx = FunctionContext(
                name=symbol_id,
                file=file_path,
                line=func_info.line_number,
                signature=signature,
                docstring=func_info.docstring if include_docstrings else None,
                calls=idx.adjacency.get(symbol_id, []),
                depth=current_depth,
                blocks=blocks,
                cyclomatic=cyclomatic,
            )
            result_functions.append(ctx)

            for callee in idx.adjacency.get(symbol_id, []):
                if callee not in visited and current_depth < depth:
                    queue.append((callee, current_depth + 1))
        else:
            fallback_name = symbol_id.split(":")[-1]
            ctx = FunctionContext(
                name=symbol_id,
                file="?",
                line=0,
                signature=f"def {fallback_name}(...)",
                calls=idx.adjacency.get(symbol_id, []),
                depth=current_depth,
            )
            result_functions.append(ctx)

            for callee in idx.adjacency.get(symbol_id, []):
                if callee not in visited and current_depth < depth:
                    queue.append((callee, current_depth + 1))

    if type_prune and result_functions:
        callee_signature = ""
        if resolved:
            entry_symbol = resolved[0]
            entry_info = idx.symbol_index.get(entry_symbol)
            if entry_info:
                callee_signature = idx.signature_overrides.get(entry_symbol, entry_info.signature())

        expanded_candidates = [
            Candidate(
                symbol_id=func.name,
                relevance=max(1, (depth - func.depth) + 1),
                relevance_label=f"depth_{func.depth}",
                order=i,
                signature=func.signature,
                code=None,
                lines=(func.line, func.line) if func.line else None,
                meta={"calls": func.calls},
            )
            for i, func in enumerate(result_functions)
        ]
        before_count = len(expanded_candidates)
        pruned_candidates = prune_expansion(
            expanded_candidates,
            callee_signature=callee_signature,
            callee_code=None,
        )
        after_count = len(pruned_candidates)
        print(f"Type pruning: {before_count} → {after_count} candidates", file=sys.stderr)
        by_symbol = {func.name: func for func in result_functions}
        result_functions = [
            by_symbol[candidate.symbol_id]
            for candidate in pruned_candidates
            if candidate.symbol_id in by_symbol
        ]

    return RelevantContext(
        entry_point=entry_point,
        depth=depth,
        functions=result_functions,
    )


def get_context_pack(
    project: str | Path,
    entry_point: str,
    depth: int = 2,
    language: str = "python",
    budget_tokens: int | None = None,
    include_docstrings: bool = False,
    disambiguate: bool = False,
    etag: str | None = None,
    zoom_level: ZoomLevel = ZoomLevel.L4,
    strip_comments: bool = False,
    compress_imports: bool = False,
    type_prune: bool = False,
) -> dict:
    project_root = Path(project).resolve()
    ctx = get_relevant_context(
        project,
        entry_point,
        depth=depth,
        language=language,
        include_docstrings=include_docstrings,
        disambiguate=disambiguate,
        type_prune=type_prune,
    )
    if ctx.ambiguous:
        from ..errors import ERR_AMBIGUOUS
        return {
            "error": True,
            "code": ERR_AMBIGUOUS,
            "message": "Ambiguous entry point. Please specify one of the candidates.",
            "candidates": ctx.candidates,
            "slices": [],
        }

    extractor = HybridExtractor()
    file_imports: dict[str, list[str]] = {}

    def _imports_for_symbol(symbol_id: str) -> list[str]:
        if ":" not in symbol_id:
            return []
        rel_path = symbol_id.split(":", 1)[0]
        if rel_path in file_imports:
            return file_imports[rel_path]
        file_path = project_root / rel_path
        if not file_path.is_file():
            file_imports[rel_path] = []
            return []
        try:
            info = extractor.extract(str(file_path))
            file_imports[rel_path] = [imp.statement() for imp in info.imports]
        except Exception:
            file_imports[rel_path] = []
        return file_imports[rel_path]

    candidates: list[Candidate] = []
    for order_idx, func in enumerate(ctx.functions):
        score = max(1, (depth - func.depth) + 1)
        meta: dict[str, object] = {"calls": func.calls}
        imports = _imports_for_symbol(func.name)
        if imports:
            meta["imports"] = imports
        candidates.append(
            Candidate(
                symbol_id=func.name,
                relevance=score,
                relevance_label=f"depth_{func.depth}",
                order=order_idx,
                signature=func.signature,
                lines=(func.line, func.line) if func.line else None,
                meta=meta,
            )
        )

    # Build post-processors (attention reranking when available)
    processors = _get_attention_processors(project_root)

    pack = ContextPackEngine(registry=None).build_context_pack(
        candidates,
        budget_tokens=budget_tokens,
        post_processors=processors or None,
        zoom_level=zoom_level,
        strip_comments=strip_comments,
        compress_imports=compress_imports,
    )

    # Record delivery for attention tracking
    _record_attention_delivery(project_root, pack)

    slices: list[dict] = []
    for item in pack.slices:
        if etag and item.etag == etag:
            # Return structured dict instead of bare string for consistency
            return {
                "unchanged": True,
                "etag": etag,
                "budget_used": 0,
                "slices": [],
            }
        entry = {
            "id": item.id,
            "relevance": item.relevance,
            "signature": item.signature,
            "code": item.code,
            "lines": list(item.lines) if item.lines else [],
            "etag": item.etag,
        }
        if item.meta:
            entry.update(item.meta)
        slices.append(entry)

    result = {
        "unchanged": False,
        "budget_used": pack.budget_used,
        "slices": slices,
    }
    if pack.import_compression:
        result["import_compression"] = pack.import_compression
    return result


@dataclass
class SymbolSignature:
    """Lightweight symbol signature for delta-first extraction."""
    symbol_id: str
    signature: str
    line: int
    depth: int
    file_path: str
    calls: list[str] = field(default_factory=list)


def get_signatures_for_entry(
    project: str | Path,
    entry_point: str,
    depth: int = 2,
    language: str = "python",
    disambiguate: bool = True,
    type_prune: bool = False,
) -> list[SymbolSignature] | dict:
    """Get symbol signatures without extracting code bodies.

    This is the foundation of delta-first extraction. By getting only signatures,
    we can compute ETags and check delta BEFORE extracting code, avoiding wasted
    work for unchanged symbols.

    Args:
        project: Path to project root
        entry_point: Function or method name to start from
        depth: Call graph traversal depth (default 2)
        language: Programming language (default "python")
        disambiguate: If True, auto-select best match for ambiguous entries

    Returns:
        List of SymbolSignature objects, or error dict if ambiguous and not disambiguate

    Example:
        >>> sigs = get_signatures_for_entry("/project", "main", depth=2)
        >>> for sig in sigs:
        ...     print(f"{sig.symbol_id}: {sig.signature}")
    """
    project = Path(project).resolve()

    # Handle module path lookups
    if "/" in entry_point and "." not in entry_point:
        # This is a module path, delegate to regular context for now
        ctx = get_relevant_context(
            project, entry_point, depth=depth, language=language,
            include_docstrings=False, disambiguate=disambiguate, type_prune=type_prune
        )
        if ctx.ambiguous:
            from ..errors import ERR_AMBIGUOUS
            return {
                "error": True,
                "code": ERR_AMBIGUOUS,
                "message": "Ambiguous entry point. Please specify one of the candidates.",
                "candidates": ctx.candidates,
            }
        return [
            SymbolSignature(
                symbol_id=func.name,
                signature=func.signature,
                line=func.line,
                depth=func.depth,
                file_path=func.file,
                calls=func.calls,
            )
            for func in ctx.functions
        ]

    ext_for_lang = {
        "python": ".py",
        "typescript": ".ts",
        "go": ".go",
        "rust": ".rs",
    }.get(language, ".py")

    # Check if entry_point is a module name
    if "." not in entry_point and "/" not in entry_point:
        module_file = None
        for f in iter_workspace_files(project, extensions={ext_for_lang}):
            if f.name == f"{entry_point}{ext_for_lang}":
                module_file = f
                break

        if module_file:
            ctx = get_relevant_context(
                project, entry_point, depth=depth, language=language,
                include_docstrings=False, disambiguate=disambiguate, type_prune=type_prune
            )
            return [
                SymbolSignature(
                    symbol_id=func.name,
                    signature=func.signature,
                    line=func.line,
                    depth=func.depth,
                    file_path=func.file,
                    calls=func.calls,
                )
                for func in ctx.functions
            ]

    idx = ProjectIndex.build(project, language, include_sources=False)

    resolved, candidates = idx.resolve_entry_symbols(entry_point, disambiguate)
    if candidates and not resolved:
        from ..errors import ERR_AMBIGUOUS
        return {
            "error": True,
            "code": ERR_AMBIGUOUS,
            "message": "Ambiguous entry point. Please specify one of the candidates.",
            "candidates": candidates,
        }

    # BFS to collect signatures (no code extraction)
    visited: set[str] = set()
    queue = [(symbol_id, 0) for symbol_id in resolved]
    result_signatures: list[SymbolSignature] = []

    while queue:
        symbol_id, current_depth = queue.pop(0)

        if symbol_id in visited or current_depth > depth:
            continue
        visited.add(symbol_id)

        func_info = idx.symbol_index.get(symbol_id)
        if func_info:
            file_path = idx.symbol_files[symbol_id]
            signature = idx.signature_overrides.get(symbol_id, func_info.signature())

            result_signatures.append(
                SymbolSignature(
                    symbol_id=symbol_id,
                    signature=signature,
                    line=func_info.line_number,
                    depth=current_depth,
                    file_path=file_path,
                    calls=idx.adjacency.get(symbol_id, []),
                )
            )

            for callee in idx.adjacency.get(symbol_id, []):
                if callee not in visited and current_depth < depth:
                    queue.append((callee, current_depth + 1))
        else:
            # Fallback for unindexed symbols
            fallback_name = symbol_id.split(":")[-1]
            result_signatures.append(
                SymbolSignature(
                    symbol_id=symbol_id,
                    signature=f"def {fallback_name}(...)",
                    line=0,
                    depth=current_depth,
                    file_path="?",
                    calls=idx.adjacency.get(symbol_id, []),
                )
            )

            for callee in idx.adjacency.get(symbol_id, []):
                if callee not in visited and current_depth < depth:
                    queue.append((callee, current_depth + 1))

    if type_prune and result_signatures:
        expanded_candidates = [
            Candidate(
                symbol_id=sig.symbol_id,
                relevance=max(1, (depth - sig.depth) + 1),
                relevance_label=f"depth_{sig.depth}",
                order=i,
                signature=sig.signature,
                code=None,
                lines=(sig.line, sig.line) if sig.line else None,
                meta={"calls": sig.calls},
            )
            for i, sig in enumerate(result_signatures)
        ]
        before_count = len(expanded_candidates)
        pruned_candidates = prune_expansion(
            expanded_candidates,
            callee_signature=result_signatures[0].signature,
            callee_code=None,
        )
        after_count = len(pruned_candidates)
        print(f"Type pruning: {before_count} → {after_count} candidates", file=sys.stderr)
        by_symbol = {sig.symbol_id: sig for sig in result_signatures}
        result_signatures = [
            by_symbol[candidate.symbol_id]
            for candidate in pruned_candidates
            if candidate.symbol_id in by_symbol
        ]

    return result_signatures


def _get_attention_processors(project: Path) -> list:
    """Build attention-based post-processors if attention DB exists."""
    db_path = project / ".tldrs" / "attention.db"
    if not db_path.exists():
        return []
    try:
        from ..attention_pruning import AttentionTracker, create_candidate_reranker
        tracker = AttentionTracker(project)
        return [create_candidate_reranker(tracker)]
    except Exception:
        return []


def _record_attention_delivery(project: Path, pack) -> None:
    """Record delivered symbol IDs for attention tracking."""
    db_path = project / ".tldrs" / "attention.db"
    if not db_path.exists():
        return
    try:
        import os
        from ..attention_pruning import AttentionTracker
        tracker = AttentionTracker(project)
        session_id = os.environ.get("TLDRS_SESSION_ID", "default")
        tracker.record_delivery(session_id, [s.id for s in pack.slices])
    except Exception:
        pass


__all__ = [
    "FunctionContext",
    "RelevantContext",
    "SymbolSignature",
    "get_relevant_context",
    "get_context_pack",
    "get_signatures_for_entry",
]
