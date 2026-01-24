from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import sys
import os
from pathlib import Path
import warnings

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
from ..cross_file_calls import build_project_call_graph
from ..contextpack_engine import Candidate, ContextPackEngine
from ..hybrid_extractor import HybridExtractor
from ..workspace import iter_workspace_files


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

    api_module = sys.modules.get("tldr_swinton.api")
    call_graph_builder = getattr(api_module, "build_project_call_graph", None)
    if callable(call_graph_builder):
        call_graph = call_graph_builder(str(project), language=language)
    else:
        call_graph = build_project_call_graph(str(project), language=language)

    extractor = HybridExtractor()
    symbol_index: dict[str, FunctionInfo] = {}
    symbol_files: dict[str, str] = {}
    symbol_raw_names: dict[str, str] = {}
    signature_overrides: dict[str, str] = {}
    name_index: dict[str, list[str]] = defaultdict(list)
    qualified_index: dict[str, list[str]] = defaultdict(list)
    file_name_index: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    ext_map = {
        "python": {".py"},
        "typescript": {".ts", ".tsx"},
        "go": {".go"},
        "rust": {".rs"},
    }
    extensions = ext_map.get(language, {".py"})

    file_sources: dict[str, str] = {}

    for file_path in iter_workspace_files(project, extensions=extensions):
        try:
            source = file_path.read_text()
            file_sources[str(file_path)] = source

            info = extractor.extract(str(file_path))
            rel_path = str(file_path.relative_to(project))

            def register_symbol(
                qualified_name: str,
                func_info: FunctionInfo,
                raw_name: str | None = None,
                signature_override: str | None = None,
                include_module_alias: bool = False,
            ) -> str:
                symbol_id = f"{rel_path}:{qualified_name}"
                symbol_index[symbol_id] = func_info
                symbol_files[symbol_id] = str(file_path)

                raw = raw_name or func_info.name
                symbol_raw_names[symbol_id] = raw
                name_index[raw].append(symbol_id)
                file_name_index[rel_path][raw].append(symbol_id)

                qualified_index[qualified_name].append(symbol_id)
                if include_module_alias:
                    module_name = file_path.stem
                    qualified_index[f"{module_name}.{raw}"].append(symbol_id)

                if signature_override:
                    signature_overrides[symbol_id] = signature_override

                return symbol_id

            for func in info.functions:
                register_symbol(
                    qualified_name=func.name,
                    func_info=func,
                    include_module_alias=True,
                )

            for cls in info.classes:
                class_as_func = FunctionInfo(
                    name=cls.name,
                    params=[],
                    return_type=cls.name,
                    docstring=cls.docstring,
                    line_number=cls.line_number,
                    language=info.language,
                )
                register_symbol(
                    qualified_name=cls.name,
                    func_info=class_as_func,
                    raw_name=cls.name,
                    signature_override=f"class {cls.name}",
                )

                for method in cls.methods:
                    register_symbol(
                        qualified_name=f"{cls.name}.{method.name}",
                        func_info=method,
                        raw_name=method.name,
                    )
        except Exception:
            pass

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

    adjacency: dict[str, list[str]] = defaultdict(list)

    def _to_rel_path(path_str: str) -> str:
        path_obj = Path(path_str)
        if path_obj.is_absolute():
            try:
                return str(path_obj.relative_to(project))
            except ValueError:
                return str(path_obj)
        return str(path_obj)

    for edge in call_graph.edges:
        caller_file, caller_func, callee_file, callee_func = edge
        caller_rel = _to_rel_path(caller_file)
        callee_rel = _to_rel_path(callee_file)

        caller_symbols = file_name_index.get(caller_rel, {}).get(caller_func, [])
        if not caller_symbols:
            caller_symbols = [f"{caller_rel}:{caller_func}"]

        callee_symbols = file_name_index.get(callee_rel, {}).get(callee_func, [])
        if not callee_symbols:
            callee_symbols = [f"{callee_rel}:{callee_func}"]

        for caller_symbol in caller_symbols:
            adjacency[caller_symbol].extend(callee_symbols)

    def resolve_entry_symbols(name: str, allow_ambiguous: bool) -> tuple[list[str], list[str]]:
        if ":" in name:
            file_part, sym_part = name.split(":", 1)
            symbol_id = f"{file_part}:{sym_part}"
            if symbol_id in symbol_index:
                return [symbol_id], []
            symbol_id = f"{_to_rel_path(file_part)}:{sym_part}"
            if symbol_id in symbol_index:
                return [symbol_id], []
            matches = []
            for rel_path, names in file_name_index.items():
                if rel_path == file_part or rel_path.endswith(file_part):
                    matches.extend(names.get(sym_part, []))
            if matches:
                return matches, []

        if "." in name:
            matches = qualified_index.get(name, [])
            if matches:
                return matches, []

        matches = name_index.get(name, [])
        if matches:
            if len(matches) == 1:
                return matches, []

            def score_match(symbol_id: str) -> tuple[int, int, int, str]:
                rel_path, sym = (
                    symbol_id.rsplit(":", 1) if ":" in symbol_id else ("", symbol_id)
                )
                basename = Path(rel_path).stem if rel_path else ""
                sym_tail = sym.split(".")[-1]
                basename_match = 1 if basename.lower() == sym_tail.lower() else 0
                exact_match = 1 if sym == name else 0
                path_depth = rel_path.count("/") if rel_path else 0
                return (-basename_match, -exact_match, path_depth, rel_path)

            if not allow_ambiguous:
                return [], matches
            chosen = sorted(matches, key=score_match)[0]
            if not os.environ.get("TLDRS_NO_WARNINGS"):
                warnings.warn(
                    f"Ambiguous entry point '{name}' matched {len(matches)} symbols; using {chosen}",
                    stacklevel=2,
                )
            return [chosen], matches

        return [name], []

    def _dedupe_sorted(values: list[str]) -> list[str]:
        return sorted(set(values))

    for key, values in list(adjacency.items()):
        adjacency[key] = _dedupe_sorted(values)

    visited: set[str] = set()
    resolved, candidates = resolve_entry_symbols(entry_point, disambiguate)
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

        func_info = symbol_index.get(symbol_id)
        if func_info:
            file_path = symbol_files[symbol_id]
            raw_name = symbol_raw_names.get(symbol_id, func_info.name)

            blocks = None
            cyclomatic = None
            if file_path in file_sources:
                try:
                    cfg = cfg_extractor_fn(file_sources[file_path], raw_name)
                    if cfg and cfg.blocks:
                        blocks = len(cfg.blocks)
                        cyclomatic = cfg.cyclomatic_complexity
                except Exception:
                    pass

            signature = signature_overrides.get(symbol_id, func_info.signature())

            ctx = FunctionContext(
                name=symbol_id,
                file=file_path,
                line=func_info.line_number,
                signature=signature,
                docstring=func_info.docstring if include_docstrings else None,
                calls=adjacency.get(symbol_id, []),
                depth=current_depth,
                blocks=blocks,
                cyclomatic=cyclomatic,
            )
            result_functions.append(ctx)

            for callee in adjacency.get(symbol_id, []):
                if callee not in visited and current_depth < depth:
                    queue.append((callee, current_depth + 1))
        else:
            fallback_name = symbol_id.split(":")[-1]
            ctx = FunctionContext(
                name=symbol_id,
                file="?",
                line=0,
                signature=f"def {fallback_name}(...)" ,
                calls=adjacency.get(symbol_id, []),
                depth=current_depth,
            )
            result_functions.append(ctx)

            for callee in adjacency.get(symbol_id, []):
                if callee not in visited and current_depth < depth:
                    queue.append((callee, current_depth + 1))

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
) -> dict:
    ctx = get_relevant_context(
        project,
        entry_point,
        depth=depth,
        language=language,
        include_docstrings=include_docstrings,
        disambiguate=disambiguate,
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
    candidates: list[Candidate] = []
    for order_idx, func in enumerate(ctx.functions):
        score = max(1, (depth - func.depth) + 1)
        candidates.append(
            Candidate(
                symbol_id=func.name,
                relevance=score,
                relevance_label=f"depth_{func.depth}",
                order=order_idx,
                signature=func.signature,
                lines=(func.line, func.line) if func.line else None,
                meta={"calls": func.calls},
            )
        )

    pack = ContextPackEngine(registry=None).build_context_pack(
        candidates,
        budget_tokens=budget_tokens,
    )

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

    return {
        "unchanged": False,
        "budget_used": pack.budget_used,
        "slices": slices,
    }


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
            include_docstrings=False, disambiguate=disambiguate
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
                include_docstrings=False, disambiguate=disambiguate
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

    # Build call graph and symbol index (same as get_relevant_context but lighter)
    api_module = sys.modules.get("tldr_swinton.api")
    call_graph_builder = getattr(api_module, "build_project_call_graph", None)
    if callable(call_graph_builder):
        call_graph = call_graph_builder(str(project), language=language)
    else:
        call_graph = build_project_call_graph(str(project), language=language)

    extractor = HybridExtractor()
    symbol_index: dict[str, FunctionInfo] = {}
    symbol_files: dict[str, str] = {}
    symbol_raw_names: dict[str, str] = {}
    signature_overrides: dict[str, str] = {}
    name_index: dict[str, list[str]] = defaultdict(list)
    qualified_index: dict[str, list[str]] = defaultdict(list)
    file_name_index: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    ext_map = {
        "python": {".py"},
        "typescript": {".ts", ".tsx"},
        "go": {".go"},
        "rust": {".rs"},
    }
    extensions = ext_map.get(language, {".py"})

    for file_path in iter_workspace_files(project, extensions=extensions):
        try:
            info = extractor.extract(str(file_path))
            rel_path = str(file_path.relative_to(project))

            def register_symbol(
                qualified_name: str,
                func_info: FunctionInfo,
                raw_name: str | None = None,
                signature_override: str | None = None,
                include_module_alias: bool = False,
            ) -> str:
                symbol_id = f"{rel_path}:{qualified_name}"
                symbol_index[symbol_id] = func_info
                symbol_files[symbol_id] = str(file_path)

                raw = raw_name or func_info.name
                symbol_raw_names[symbol_id] = raw
                name_index[raw].append(symbol_id)
                file_name_index[rel_path][raw].append(symbol_id)

                qualified_index[qualified_name].append(symbol_id)
                if include_module_alias:
                    module_name = file_path.stem
                    qualified_index[f"{module_name}.{raw}"].append(symbol_id)

                if signature_override:
                    signature_overrides[symbol_id] = signature_override

                return symbol_id

            for func in info.functions:
                register_symbol(
                    qualified_name=func.name,
                    func_info=func,
                    include_module_alias=True,
                )

            for cls in info.classes:
                class_as_func = FunctionInfo(
                    name=cls.name,
                    params=[],
                    return_type=cls.name,
                    docstring=cls.docstring,
                    line_number=cls.line_number,
                    language=info.language,
                )
                register_symbol(
                    qualified_name=cls.name,
                    func_info=class_as_func,
                    raw_name=cls.name,
                    signature_override=f"class {cls.name}",
                )

                for method in cls.methods:
                    register_symbol(
                        qualified_name=f"{cls.name}.{method.name}",
                        func_info=method,
                        raw_name=method.name,
                    )
        except Exception:
            pass

    # Build adjacency from call graph
    adjacency: dict[str, list[str]] = defaultdict(list)

    def _to_rel_path(path_str: str) -> str:
        path_obj = Path(path_str)
        if path_obj.is_absolute():
            try:
                return str(path_obj.relative_to(project))
            except ValueError:
                return str(path_obj)
        return str(path_obj)

    for edge in call_graph.edges:
        caller_file, caller_func, callee_file, callee_func = edge
        caller_rel = _to_rel_path(caller_file)
        callee_rel = _to_rel_path(callee_file)

        caller_symbols = file_name_index.get(caller_rel, {}).get(caller_func, [])
        if not caller_symbols:
            caller_symbols = [f"{caller_rel}:{caller_func}"]

        callee_symbols = file_name_index.get(callee_rel, {}).get(callee_func, [])
        if not callee_symbols:
            callee_symbols = [f"{callee_rel}:{callee_func}"]

        for caller_symbol in caller_symbols:
            adjacency[caller_symbol].extend(callee_symbols)

    def _dedupe_sorted(values: list[str]) -> list[str]:
        return sorted(set(values))

    for key, values in list(adjacency.items()):
        adjacency[key] = _dedupe_sorted(values)

    # Resolve entry point
    def resolve_entry_symbols(name: str, allow_ambiguous: bool) -> tuple[list[str], list[str]]:
        if ":" in name:
            file_part, sym_part = name.split(":", 1)
            symbol_id = f"{file_part}:{sym_part}"
            if symbol_id in symbol_index:
                return [symbol_id], []
            symbol_id = f"{_to_rel_path(file_part)}:{sym_part}"
            if symbol_id in symbol_index:
                return [symbol_id], []
            matches = []
            for rel_path, names in file_name_index.items():
                if rel_path == file_part or rel_path.endswith(file_part):
                    matches.extend(names.get(sym_part, []))
            if matches:
                return matches, []

        if "." in name:
            matches = qualified_index.get(name, [])
            if matches:
                return matches, []

        matches = name_index.get(name, [])
        if matches:
            if len(matches) == 1:
                return matches, []

            def score_match(symbol_id: str) -> tuple[int, int, int, str]:
                rel_path, sym = (
                    symbol_id.rsplit(":", 1) if ":" in symbol_id else ("", symbol_id)
                )
                basename = Path(rel_path).stem if rel_path else ""
                sym_tail = sym.split(".")[-1]
                basename_match = 1 if basename.lower() == sym_tail.lower() else 0
                exact_match = 1 if sym == name else 0
                path_depth = rel_path.count("/") if rel_path else 0
                return (-basename_match, -exact_match, path_depth, rel_path)

            if not allow_ambiguous:
                return [], matches
            chosen = sorted(matches, key=score_match)[0]
            if not os.environ.get("TLDRS_NO_WARNINGS"):
                warnings.warn(
                    f"Ambiguous entry point '{name}' matched {len(matches)} symbols; using {chosen}",
                    stacklevel=2,
                )
            return [chosen], matches

        return [name], []

    resolved, candidates = resolve_entry_symbols(entry_point, disambiguate)
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

        func_info = symbol_index.get(symbol_id)
        if func_info:
            file_path = symbol_files[symbol_id]
            signature = signature_overrides.get(symbol_id, func_info.signature())

            result_signatures.append(
                SymbolSignature(
                    symbol_id=symbol_id,
                    signature=signature,
                    line=func_info.line_number,
                    depth=current_depth,
                    file_path=file_path,
                    calls=adjacency.get(symbol_id, []),
                )
            )

            for callee in adjacency.get(symbol_id, []):
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
                    calls=adjacency.get(symbol_id, []),
                )
            )

            for callee in adjacency.get(symbol_id, []):
                if callee not in visited and current_depth < depth:
                    queue.append((callee, current_depth + 1))

    return result_signatures


__all__ = [
    "FunctionContext",
    "RelevantContext",
    "SymbolSignature",
    "get_relevant_context",
    "get_context_pack",
    "get_signatures_for_entry",
]
