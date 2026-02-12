"""Shared ProjectIndex — unified symbol scanning for project-scoped engines.

Eliminates duplicated scanning across symbolkite.py and difflens.py by
providing a single build() classmethod that constructs all index dicts,
file_sources, symbol_ranges, and adjacency in one pass.
"""

from __future__ import annotations

import os
import sys
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .ast_cache import ASTCache
from .ast_extractor import FunctionInfo
from .cross_file_calls import build_project_call_graph
from .hybrid_extractor import HybridExtractor
from .workspace import iter_workspace_files


_EXT_MAP = {
    "python": {".py"},
    "typescript": {".ts", ".tsx"},
    "go": {".go"},
    "rust": {".rs"},
}


def _compute_symbol_ranges(info, rel_path: str, total_lines: int) -> dict[str, tuple[int, int]]:
    """Compute line ranges for all symbols in a file.

    Mirrors difflens._compute_symbol_ranges exactly.
    """
    ranges: dict[str, tuple[int, int]] = {}
    top_level: list[tuple[str, int, object]] = []
    for func in info.functions:
        top_level.append(("func", func.line_number, func))
    for cls in info.classes:
        top_level.append(("class", cls.line_number, cls))
    top_level.sort(key=lambda item: item[1])

    for idx, (kind, start_line, obj) in enumerate(top_level):
        end_line = total_lines
        if idx + 1 < len(top_level):
            end_line = max(start_line, top_level[idx + 1][1] - 1)

        if kind == "func":
            symbol_id = f"{rel_path}:{obj.name}"
            ranges[symbol_id] = (start_line, end_line)
            continue

        class_symbol = f"{rel_path}:{obj.name}"
        ranges[class_symbol] = (start_line, end_line)

        methods = sorted(obj.methods, key=lambda m: m.line_number)
        for midx, method in enumerate(methods):
            mend = end_line
            if midx + 1 < len(methods):
                mend = max(method.line_number, methods[midx + 1].line_number - 1)
            method_symbol = f"{rel_path}:{obj.name}.{method.name}"
            ranges[method_symbol] = (method.line_number, mend)

    return ranges


@dataclass
class ProjectIndex:
    """Unified symbol index for a project.

    Consolidates all 7 index dicts plus file_sources, symbol_ranges,
    adjacency, and reverse_adjacency into a single scannable object.
    """

    project: Path
    language: str

    # Core indexes
    symbol_index: dict[str, FunctionInfo] = field(default_factory=dict)
    symbol_files: dict[str, str] = field(default_factory=dict)
    symbol_raw_names: dict[str, str] = field(default_factory=dict)
    signature_overrides: dict[str, str] = field(default_factory=dict)
    name_index: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    qualified_index: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    file_name_index: dict[str, dict[str, list[str]]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(list))
    )

    # Optional data (controlled by build flags)
    file_sources: dict[str, str] = field(default_factory=dict)
    symbol_ranges: dict[str, tuple[int, int]] = field(default_factory=dict)

    # Call graph adjacency
    adjacency: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    reverse_adjacency: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    def _register_symbol(
        self,
        rel_path: str,
        file_path: Path,
        qualified_name: str,
        func_info: FunctionInfo,
        raw_name: str | None = None,
        signature_override: str | None = None,
        include_module_alias: bool = False,
    ) -> str:
        """Register a single symbol in all indexes.

        This is the superset of both symbolkite and difflens registration:
        it always adds file_name_index[rel_path][qualified_name] when
        qualified_name != raw (the difflens-only entry), which is additive
        and harmless for symbolkite paths.
        """
        symbol_id = f"{rel_path}:{qualified_name}"
        self.symbol_index[symbol_id] = func_info
        self.symbol_files[symbol_id] = str(file_path)

        raw = raw_name or func_info.name
        self.symbol_raw_names[symbol_id] = raw
        self.name_index[raw].append(symbol_id)
        self.file_name_index[rel_path][raw].append(symbol_id)

        # Difflens-only entry: qualified name in file_name_index
        if qualified_name != raw:
            self.file_name_index[rel_path][qualified_name].append(symbol_id)

        self.qualified_index[qualified_name].append(symbol_id)
        if include_module_alias:
            module_name = file_path.stem
            self.qualified_index[f"{module_name}.{raw}"].append(symbol_id)

        if signature_override:
            self.signature_overrides[symbol_id] = signature_override

        return symbol_id

    def _to_rel_path(self, path_str: str) -> str:
        """Convert absolute path to project-relative path."""
        path_obj = Path(path_str)
        if path_obj.is_absolute():
            try:
                return str(path_obj.relative_to(self.project))
            except ValueError:
                return str(path_obj)
        return str(path_obj)

    def resolve_entry_symbols(
        self, name: str, allow_ambiguous: bool
    ) -> tuple[list[str], list[str]]:
        """Resolve an entry point name to symbol IDs.

        Returns (resolved_ids, candidate_ids). If ambiguous and not
        allow_ambiguous, resolved_ids is empty and candidate_ids has all matches.
        """
        if ":" in name:
            file_part, sym_part = name.split(":", 1)
            symbol_id = f"{file_part}:{sym_part}"
            if symbol_id in self.symbol_index:
                return [symbol_id], []
            symbol_id = f"{self._to_rel_path(file_part)}:{sym_part}"
            if symbol_id in self.symbol_index:
                return [symbol_id], []
            matches = []
            for rel_path, names in self.file_name_index.items():
                if rel_path == file_part or rel_path.endswith(file_part):
                    matches.extend(names.get(sym_part, []))
            if matches:
                return matches, []

        if "." in name:
            matches = self.qualified_index.get(name, [])
            if matches:
                return matches, []

        matches = self.name_index.get(name, [])
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
                    stacklevel=3,
                )
            return [chosen], matches

        return [name], []

    @classmethod
    def build(
        cls,
        project: str | Path,
        language: str = "python",
        *,
        include_sources: bool = True,
        include_ranges: bool = False,
        include_reverse_adjacency: bool = False,
    ) -> ProjectIndex:
        """Build a complete project index by scanning all workspace files.

        Args:
            project: Path to project root
            language: Programming language
            include_sources: Whether to store file source text (needed for code extraction)
            include_ranges: Whether to compute symbol line ranges (needed for diff context)
            include_reverse_adjacency: Whether to build reverse call graph (needed for caller lookup)

        Returns:
            Fully populated ProjectIndex
        """
        project = Path(project).resolve()
        extensions = _EXT_MAP.get(language, {".py"})

        idx = cls(project=project, language=language)
        extractor = HybridExtractor()
        ast_cache = ASTCache(project)

        for file_path in iter_workspace_files(project, extensions=extensions):
            try:
                source = file_path.read_text()
                if include_sources:
                    idx.file_sources[str(file_path)] = source

                info = ast_cache.get(file_path)
                if info is None:
                    info = extractor.extract(str(file_path))
                    ast_cache.put(file_path, info)
                rel_path = str(file_path.relative_to(project))

                for func in info.functions:
                    idx._register_symbol(
                        rel_path=rel_path,
                        file_path=file_path,
                        qualified_name=func.name,
                        func_info=func,
                        include_module_alias=True,
                    )

                for klass in info.classes:
                    class_as_func = FunctionInfo(
                        name=klass.name,
                        params=[],
                        return_type=klass.name,
                        docstring=klass.docstring,
                        line_number=klass.line_number,
                        language=info.language,
                    )
                    idx._register_symbol(
                        rel_path=rel_path,
                        file_path=file_path,
                        qualified_name=klass.name,
                        func_info=class_as_func,
                        raw_name=klass.name,
                        signature_override=f"class {klass.name}",
                    )

                    for method in klass.methods:
                        idx._register_symbol(
                            rel_path=rel_path,
                            file_path=file_path,
                            qualified_name=f"{klass.name}.{method.name}",
                            func_info=method,
                            raw_name=method.name,
                        )

                if include_ranges:
                    total_lines = max(1, len(source.splitlines()))
                    idx.symbol_ranges.update(
                        _compute_symbol_ranges(info, rel_path, total_lines)
                    )
            except Exception:
                continue

        # Build call graph
        api_module = sys.modules.get("tldr_swinton.api")
        call_graph_builder = getattr(api_module, "build_project_call_graph", None)
        if callable(call_graph_builder):
            call_graph = call_graph_builder(str(project), language=language)
        else:
            call_graph = build_project_call_graph(str(project), language=language)

        for edge in call_graph.edges:
            caller_file, caller_func, callee_file, callee_func = edge
            caller_rel = idx._to_rel_path(caller_file)
            callee_rel = idx._to_rel_path(callee_file)

            caller_symbols = idx.file_name_index.get(caller_rel, {}).get(caller_func, [])
            if not caller_symbols:
                caller_symbols = [f"{caller_rel}:{caller_func}"]

            callee_symbols = idx.file_name_index.get(callee_rel, {}).get(callee_func, [])
            if not callee_symbols:
                callee_symbols = [f"{callee_rel}:{callee_func}"]

            for caller_symbol in caller_symbols:
                idx.adjacency[caller_symbol].extend(callee_symbols)

            if include_reverse_adjacency:
                for callee_symbol in callee_symbols:
                    idx.reverse_adjacency[callee_symbol].extend(caller_symbols)

        # Deduplicate and sort adjacency lists
        for key, values in list(idx.adjacency.items()):
            idx.adjacency[key] = sorted(set(values))

        if include_reverse_adjacency:
            for key, values in list(idx.reverse_adjacency.items()):
                idx.reverse_adjacency[key] = sorted(set(values))

        return idx
