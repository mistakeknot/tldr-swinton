from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
import subprocess

from ..ast_extractor import FunctionInfo
from ..cross_file_calls import build_project_call_graph
from ..hybrid_extractor import HybridExtractor
from ..workspace import iter_workspace_files

DIFF_CONTEXT_LINES = 6


def parse_unified_diff(diff_text: str) -> list[tuple[str, int, int]]:
    """Parse unified diff output into (file_path, start_line, end_line) tuples."""
    hunks: list[tuple[str, int, int]] = []
    current_file: str | None = None
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                path = parts[3]
                if path.startswith("a/") or path.startswith("b/"):
                    path = path[2:]
                current_file = path
            continue
        if line.startswith("+++ "):
            path = line[4:].strip()
            if path == "/dev/null":
                current_file = None
                continue
            if path.startswith("a/") or path.startswith("b/"):
                path = path[2:]
            current_file = path
            continue

        if line.startswith("@@ ") and current_file:
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if not match:
                continue
            start = int(match.group(1))
            count = int(match.group(2) or "1")
            if count <= 0:
                end = max(start, 1)
            else:
                end = max(start, 1) + count - 1
            hunks.append((current_file, max(start, 1), end))
    return hunks


def map_hunks_to_symbols(
    project: str | Path,
    hunks: list[tuple[str, int, int]],
    language: str = "python",
) -> dict[str, set[int]]:
    """Map diff hunks to enclosing symbols. Returns {symbol_id: {diff_lines}}."""
    project = Path(project).resolve()
    extractor = HybridExtractor()
    results: dict[str, set[int]] = defaultdict(set)
    hunks_by_file: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for path, start, end in hunks:
        hunks_by_file[path].append((start, end))

    for rel_path, ranges in hunks_by_file.items():
        file_path = project / rel_path
        if not file_path.exists():
            continue

        try:
            source = file_path.read_text()
        except OSError:
            continue

        total_lines = max(1, len(source.splitlines()))
        try:
            info = extractor.extract(str(file_path))
        except Exception:
            continue

        symbol_ranges: list[tuple[str, int, int]] = []
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
                symbol_ranges.append((symbol_id, start_line, end_line))
                continue

            class_symbol = f"{rel_path}:{obj.name}"
            symbol_ranges.append((class_symbol, start_line, end_line))

            methods = sorted(obj.methods, key=lambda m: m.line_number)
            for midx, method in enumerate(methods):
                mend = end_line
                if midx + 1 < len(methods):
                    mend = max(method.line_number, methods[midx + 1].line_number - 1)
                method_symbol = f"{rel_path}:{obj.name}.{method.name}"
                symbol_ranges.append((method_symbol, method.line_number, mend))

        for start, end in ranges:
            best_symbol: str | None = None
            best_span: int | None = None
            for symbol_id, s_start, s_end in symbol_ranges:
                if s_start <= end and s_end >= start:
                    span = s_end - s_start
                    if best_span is None or span < best_span:
                        best_span = span
                        best_symbol = symbol_id
            if best_symbol:
                results[best_symbol].update(range(start, end + 1))

    return results


def _compute_symbol_ranges(info, rel_path: str, total_lines: int) -> dict[str, tuple[int, int]]:
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


def _merge_windows(diff_lines: list[int], context: int = DIFF_CONTEXT_LINES) -> list[tuple[int, int]]:
    if not diff_lines:
        return []
    windows: list[tuple[int, int]] = []
    sorted_lines = sorted(diff_lines)
    start = sorted_lines[0] - context
    end = sorted_lines[0] + context
    for line in sorted_lines[1:]:
        window_start = line - context
        window_end = line + context
        if window_start <= end + 1:
            end = max(end, window_end)
        else:
            windows.append((start, end))
            start = window_start
            end = window_end
    windows.append((start, end))
    return windows


def _extract_windowed_code(
    src_lines: list[str],
    diff_lines: list[int],
    symbol_start: int,
    symbol_end: int,
    context: int = DIFF_CONTEXT_LINES,
) -> str | None:
    windows = _merge_windows(diff_lines, context)

    clamped: list[tuple[int, int]] = []
    for win_start, win_end in windows:
        clamped_start = max(symbol_start, win_start)
        clamped_end = min(symbol_end, win_end)
        if clamped_start <= clamped_end:
            clamped.append((clamped_start, clamped_end))

    if not clamped:
        return None

    parts: list[str] = []
    for idx, (win_start, win_end) in enumerate(clamped):
        if idx > 0:
            parts.append("...")
        parts.extend(src_lines[win_start - 1:win_end])

    return "\n".join(parts)


def _split_blocks_by_blank(lines: list[str]) -> list[tuple[int, int]]:
    blocks: list[tuple[int, int]] = []
    start = 0
    idx = 0
    while idx < len(lines):
        if lines[idx].strip() == "" or lines[idx].strip() == "...":
            if start < idx:
                blocks.append((start, idx - 1))
            start = idx + 1
        idx += 1
    if start < len(lines):
        blocks.append((start, len(lines) - 1))
    return blocks or [(0, len(lines) - 1)]


def _two_stage_prune(
    code: str,
    code_start: int,
    diff_lines: list[int],
    budget_tokens: int | None,
) -> tuple[str, int, int]:
    lines = code.splitlines()
    blocks = _split_blocks_by_blank(lines)
    block_count = len(blocks)
    if block_count == 0:
        return code, 0, 0

    def _line_in_block(block: tuple[int, int], line_no: int) -> bool:
        idx = line_no - code_start
        return block[0] <= idx <= block[1]

    keep_indexes: list[int] = []
    for b_idx, block in enumerate(blocks):
        if any(_line_in_block(block, line_no) for line_no in diff_lines):
            keep_indexes.append(b_idx)

    if not keep_indexes:
        keep_indexes = [0]

    expanded: set[int] = set()
    for idx in keep_indexes:
        expanded.add(idx)
        if idx - 1 >= 0:
            expanded.add(idx - 1)
        if idx + 1 < block_count:
            expanded.add(idx + 1)

    keep = sorted(expanded)

    max_blocks = None
    if budget_tokens is not None:
        if budget_tokens <= 800:
            max_blocks = 1
        elif budget_tokens <= 1600:
            max_blocks = 2
        else:
            max_blocks = 3
    if max_blocks is not None and len(keep) > max_blocks:
        keep = keep[:max_blocks]

    kept_lines: list[str] = []
    for idx, block_idx in enumerate(keep):
        if idx > 0:
            kept_lines.append("...")
        start, end = blocks[block_idx]
        kept_lines.extend(lines[start:end + 1])

    dropped_blocks = max(0, block_count - len(keep))
    return "\n".join(kept_lines), block_count, dropped_blocks


def build_diff_context_from_hunks(
    project: str | Path,
    hunks: list[tuple[str, int, int]],
    language: str = "python",
    budget_tokens: int | None = None,
    compress: str | None = None,
) -> dict:
    project = Path(project).resolve()
    symbol_diff_lines = map_hunks_to_symbols(project, hunks, language=language)

    extractor = HybridExtractor()
    symbol_index: dict[str, FunctionInfo] = {}
    symbol_files: dict[str, str] = {}
    symbol_raw_names: dict[str, str] = {}
    signature_overrides: dict[str, str] = {}
    name_index: dict[str, list[str]] = defaultdict(list)
    qualified_index: dict[str, list[str]] = defaultdict(list)
    file_name_index: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    symbol_ranges: dict[str, tuple[int, int]] = {}
    file_sources: dict[str, str] = {}

    ext_map = {
        "python": {".py"},
        "typescript": {".ts", ".tsx"},
        "go": {".go"},
        "rust": {".rs"},
    }
    extensions = ext_map.get(language, {".py"})

    for file_path in iter_workspace_files(project, extensions=extensions):
        try:
            source = file_path.read_text()
            file_sources[str(file_path)] = source
            total_lines = max(1, len(source.splitlines()))
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
                if qualified_name != raw:
                    file_name_index[rel_path][qualified_name].append(symbol_id)

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

            symbol_ranges.update(_compute_symbol_ranges(info, rel_path, total_lines))
        except Exception:
            continue

    call_graph = build_project_call_graph(str(project), language=language)
    adjacency: dict[str, list[str]] = defaultdict(list)
    reverse_adjacency: dict[str, list[str]] = defaultdict(list)

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
        for callee_symbol in callee_symbols:
            reverse_adjacency[callee_symbol].extend(caller_symbols)

    def _dedupe_sorted(values: list[str]) -> list[str]:
        return sorted(set(values))

    for key, values in list(adjacency.items()):
        adjacency[key] = _dedupe_sorted(values)
    for key, values in list(reverse_adjacency.items()):
        reverse_adjacency[key] = _dedupe_sorted(values)

    ordered: list[str] = []
    relevance: dict[str, str] = {}
    for symbol_id in symbol_diff_lines.keys():
        ordered.append(symbol_id)
        relevance[symbol_id] = "contains_diff"

    for symbol_id in list(ordered):
        for callee in adjacency.get(symbol_id, []):
            if callee not in relevance:
                relevance[callee] = "callee"
                ordered.append(callee)
        for caller in reverse_adjacency.get(symbol_id, []):
            if caller not in relevance:
                relevance[caller] = "caller"
                ordered.append(caller)

    def _estimate_tokens(text: str) -> int:
        return max(1, len(text) // 4)

    def _to_ranges(lines: list[int]) -> list[list[int]]:
        if not lines:
            return []
        ranges: list[list[int]] = []
        start = lines[0]
        end = lines[0]
        for line in lines[1:]:
            if line == end + 1:
                end = line
            else:
                ranges.append([start, end])
                start = end = line
        ranges.append([start, end])
        return ranges

    slices: list[dict] = []
    budget_used = 0

    for symbol_id in ordered:
        func_info = symbol_index.get(symbol_id)
        signature = signature_overrides.get(symbol_id)
        if not signature:
            if func_info:
                signature = func_info.signature()
            else:
                signature = f"def {symbol_id.split(':')[-1]}(...)"

        lines_range = symbol_ranges.get(symbol_id)
        if not lines_range and func_info:
            lines_range = (func_info.line_number, func_info.line_number)

        code = None
        code_scope_range = lines_range
        if compress == "two-stage" and symbol_id in symbol_diff_lines and lines_range:
            rel_part, qual_part = symbol_id.split(":", 1)
            if "." in qual_part:
                class_name = qual_part.split(".", 1)[0]
                class_symbol = f"{rel_part}:{class_name}"
                class_range = symbol_ranges.get(class_symbol)
                if class_range:
                    code_scope_range = class_range
        if symbol_id in symbol_diff_lines and lines_range:
            file_path = symbol_files.get(symbol_id)
            if file_path and file_path in file_sources:
                src_lines = file_sources[file_path].splitlines()
                start, end = code_scope_range or lines_range
                start = max(1, start)
                end = min(len(src_lines), end)
                diff_line_list = sorted(symbol_diff_lines.get(symbol_id, []))
                if compress == "two-stage":
                    code = "\n".join(src_lines[start - 1:end])
                else:
                    if diff_line_list:
                        code = _extract_windowed_code(src_lines, diff_line_list, start, end)
                    else:
                        code = "\n".join(src_lines[start - 1:end])
                if code and compress == "two-stage":
                    code, block_count, dropped_blocks = _two_stage_prune(
                        code,
                        start,
                        diff_line_list,
                        budget_tokens,
                    )
                else:
                    block_count = 0
                    dropped_blocks = 0
        else:
            block_count = 0
            dropped_blocks = 0

        sig_cost = _estimate_tokens(signature)
        code_cost = _estimate_tokens(code) if code else 0
        total_cost = sig_cost + code_cost

        if budget_tokens is not None and budget_used + total_cost > budget_tokens:
            if code and budget_used + sig_cost <= budget_tokens:
                code = None
                total_cost = sig_cost
            else:
                break

        budget_used += total_cost

        slice_entry = {
            "id": symbol_id,
            "relevance": relevance.get(symbol_id, "adjacent"),
            "signature": signature,
            "code": code,
            "lines": list(code_scope_range) if code_scope_range else (list(lines_range) if lines_range else []),
            "diff_lines": _to_ranges(sorted(symbol_diff_lines.get(symbol_id, []))),
            "block_count": block_count,
            "dropped_blocks": dropped_blocks,
        }
        slices.append(slice_entry)

    return {
        "base": None,
        "head": None,
        "budget_used": budget_used,
        "slices": slices,
    }


def _fallback_recent_files(project: Path, language: str = "python", limit: int = 5) -> list[tuple[str, int, int]]:
    ext_map = {
        "python": {".py"},
        "typescript": {".ts", ".tsx"},
        "go": {".go"},
        "rust": {".rs"},
    }
    extensions = ext_map.get(language, {".py"})
    files = list(iter_workspace_files(project, extensions=extensions))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    hunks: list[tuple[str, int, int]] = []
    for file_path in files[:limit]:
        try:
            source = file_path.read_text()
        except OSError:
            continue
        total_lines = max(1, len(source.splitlines()))
        rel_path = str(file_path.relative_to(project))
        hunks.append((rel_path, 1, total_lines))
    return hunks


def get_diff_context(
    project: str | Path,
    base: str | None = None,
    head: str | None = None,
    budget_tokens: int | None = None,
    language: str = "python",
    compress: str | None = None,
) -> dict:
    project = Path(project).resolve()
    base_ref = base or "HEAD~1"
    head_ref = head or "HEAD"

    def _run_diff(args: list[str]) -> str:
        result = subprocess.run(
            ["git", "-C", str(project), "diff", "--unified=0"] + args,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            return ""
        return result.stdout

    diff_text = _run_diff([f"{base_ref}..{head_ref}"])
    diff_text += _run_diff(["--staged"])
    diff_text += _run_diff([])

    hunks = parse_unified_diff(diff_text)
    if not hunks:
        hunks = _fallback_recent_files(project, language=language)
    pack = build_diff_context_from_hunks(
        project,
        hunks,
        language=language,
        budget_tokens=budget_tokens,
        compress=compress,
    )
    pack["base"] = base_ref
    pack["head"] = head_ref
    return pack
