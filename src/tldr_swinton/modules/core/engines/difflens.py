from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import re
import subprocess
import sys

from ..ast_extractor import FunctionInfo
from ..hybrid_extractor import HybridExtractor
from ..project_index import ProjectIndex
from ..workspace import iter_workspace_files
from ..contextpack_engine import Candidate, ContextPackEngine
from ..type_pruner import prune_expansion
from ..zoom import ZoomLevel


@dataclass
class DiffSymbolSignature:
    """Lightweight signature for delta-first diff context."""
    symbol_id: str
    signature: str
    line: int
    file_path: str
    diff_lines: list[int] = field(default_factory=list)
    relevance_label: str = "adjacent"

# Default context lines (used for normal-density code)
DIFF_CONTEXT_LINES_DEFAULT = 6
# Minimum context lines (used for very dense code)
DIFF_CONTEXT_LINES_MIN = 2
# Maximum context lines (used for sparse/simple code)
DIFF_CONTEXT_LINES_MAX = 8


def compute_adaptive_context_lines(code_lines: list[str], budget_tokens: int | None = None) -> int:
    """Compute adaptive context window size based on code density.

    Dense code (many non-empty lines, short average length) gets smaller windows.
    Sparse code (lots of whitespace, comments) gets larger windows.

    Args:
        code_lines: Lines of code to analyze
        budget_tokens: Optional token budget (lower budget = smaller windows)

    Returns:
        Number of context lines to use (2-8)
    """
    if not code_lines:
        return DIFF_CONTEXT_LINES_DEFAULT

    # Calculate density metrics
    non_empty = [line for line in code_lines if line.strip()]
    if not non_empty:
        return DIFF_CONTEXT_LINES_MAX

    density_ratio = len(non_empty) / len(code_lines)  # 0-1, higher = denser
    avg_line_length = sum(len(line) for line in non_empty) / len(non_empty)

    # Dense code indicators:
    # - High density ratio (>0.8)
    # - Long average lines (>60 chars)
    # - Many complex lines (with multiple operators/calls)
    complex_indicators = sum(
        1 for line in non_empty
        if line.count('(') > 1 or line.count(',') > 2 or len(line) > 80
    )
    complexity_ratio = complex_indicators / len(non_empty) if non_empty else 0

    # Start with default, adjust based on metrics
    context = DIFF_CONTEXT_LINES_DEFAULT

    # Dense code: reduce context
    if density_ratio > 0.85 or avg_line_length > 70:
        context = DIFF_CONTEXT_LINES_MIN
    elif density_ratio > 0.75 or avg_line_length > 55:
        context = 4
    # Sparse code: increase context
    elif density_ratio < 0.5:
        context = DIFF_CONTEXT_LINES_MAX

    # High complexity: reduce further
    if complexity_ratio > 0.3:
        context = max(DIFF_CONTEXT_LINES_MIN, context - 2)

    # Budget constraint
    if budget_tokens is not None:
        if budget_tokens < 1000:
            context = DIFF_CONTEXT_LINES_MIN
        elif budget_tokens < 2000:
            context = min(context, 4)

    return context


# Backwards compatibility alias
DIFF_CONTEXT_LINES = DIFF_CONTEXT_LINES_DEFAULT


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
    _project_index: "ProjectIndex | None" = None,
) -> dict[str, set[int]]:
    """Map diff hunks to enclosing symbols. Returns {symbol_id: {diff_lines}}."""
    project = Path(project).resolve()
    results: dict[str, set[int]] = defaultdict(set)
    hunks_by_file: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for path, start, end in hunks:
        hunks_by_file[path].append((start, end))

    # Fast path: use pre-built index ranges when available
    if _project_index and _project_index.symbol_ranges:
        # Group symbol_ranges by file for efficient lookup
        ranges_by_file: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
        for symbol_id, (s_start, s_end) in _project_index.symbol_ranges.items():
            if ":" in symbol_id:
                rel_path = symbol_id.split(":", 1)[0]
                ranges_by_file[rel_path].append((symbol_id, s_start, s_end))

        for rel_path, hunk_ranges in hunks_by_file.items():
            file_ranges = ranges_by_file.get(rel_path, [])
            if not file_ranges:
                continue
            for start, end in hunk_ranges:
                best_symbol: str | None = None
                best_span: int | None = None
                for symbol_id, s_start, s_end in file_ranges:
                    if s_start <= end and s_end >= start:
                        span = s_end - s_start
                        if best_span is None or span < best_span:
                            best_span = span
                            best_symbol = symbol_id
                if best_symbol:
                    results[best_symbol].update(range(start, end + 1))
        return results

    # Fallback: scan files with HybridExtractor (no pre-built index)
    extractor = HybridExtractor()

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

        symbol_ranges_list: list[tuple[str, int, int]] = []
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
                symbol_ranges_list.append((symbol_id, start_line, end_line))
                continue

            class_symbol = f"{rel_path}:{obj.name}"
            symbol_ranges_list.append((class_symbol, start_line, end_line))

            methods = sorted(obj.methods, key=lambda m: m.line_number)
            for midx, method in enumerate(methods):
                mend = end_line
                if midx + 1 < len(methods):
                    mend = max(method.line_number, methods[midx + 1].line_number - 1)
                method_symbol = f"{rel_path}:{obj.name}.{method.name}"
                symbol_ranges_list.append((method_symbol, method.line_number, mend))

        for start, end in ranges:
            best_symbol: str | None = None
            best_span: int | None = None
            for symbol_id, s_start, s_end in symbol_ranges_list:
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


def _merge_windows(
    diff_lines: list[int],
    context: int = DIFF_CONTEXT_LINES_DEFAULT,
) -> list[tuple[int, int]]:
    """Merge overlapping diff windows.

    Args:
        diff_lines: List of line numbers with changes
        context: Number of context lines before/after each diff line

    Returns:
        List of (start, end) tuples representing merged windows
    """
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
    context: int | None = None,
    budget_tokens: int | None = None,
) -> str | None:
    """Extract code around diff lines with context.

    Args:
        src_lines: All source code lines
        diff_lines: Line numbers with changes
        symbol_start: Symbol's start line
        symbol_end: Symbol's end line
        context: Context lines (if None, computed adaptively)
        budget_tokens: Token budget (affects adaptive context)

    Returns:
        Windowed code with context, or None if no overlap
    """
    # Compute adaptive context if not specified
    if context is None:
        symbol_lines = src_lines[max(0, symbol_start - 1):symbol_end]
        context = compute_adaptive_context_lines(symbol_lines, budget_tokens)

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


def _split_blocks_by_indent(lines: list[str]) -> list[tuple[int, int]]:
    """Split code into blocks at indentation-level transitions.

    Detects block boundaries where indentation level changes, which captures
    structural boundaries (function bodies, if/else branches, loops) better
    than blank-line splitting. Inspired by LongCodeZip (ASE 2025).
    """
    if not lines:
        return [(0, 0)]

    blocks: list[tuple[int, int]] = []
    start = 0

    def _indent_level(line: str) -> int | None:
        stripped = line.lstrip()
        if not stripped:
            return None  # blank line - no indent signal
        return len(line) - len(stripped)

    prev_indent = _indent_level(lines[0])

    for idx in range(len(lines)):
        stripped = lines[idx].strip()
        if stripped == "" or stripped == "...":
            if start < idx:
                blocks.append((start, idx - 1))
            start = idx + 1
            prev_indent = None
            continue

        cur_indent = _indent_level(lines[idx])
        if cur_indent is None:
            continue

        # Block boundary: indent level changed AND we're at a "top" boundary
        # (dedent back to a lower level, or indent into a new scope)
        if prev_indent is not None and cur_indent != prev_indent:
            # Only split at dedents (end of a block) to avoid splitting
            # every indented line. Also split at significant indents (>=4 change)
            if cur_indent < prev_indent or abs(cur_indent - prev_indent) >= 4:
                if start < idx:
                    blocks.append((start, idx - 1))
                start = idx

        prev_indent = cur_indent

    # Final block
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
    blocks = _split_blocks_by_indent(lines)
    block_count = len(blocks)
    if block_count == 0:
        return code, 0, 0

    def _line_in_block(block: tuple[int, int], line_no: int) -> bool:
        idx = line_no - code_start
        return block[0] <= idx <= block[1]

    # Score each block
    scores: list[float] = []
    sizes: list[int] = []  # token estimate per block (chars / 4)
    diff_block_indices: set[int] = set()

    for b_idx, block in enumerate(blocks):
        start, end = block
        block_lines = lines[start:end + 1]
        block_text = "\n".join(block_lines)
        size = max(1, len(block_text) // 4)  # rough token estimate
        sizes.append(size)

        score = 0.0
        # Primary: diff overlap - blocks containing diff lines get high score
        overlap = sum(1 for ln in diff_lines if _line_in_block(block, ln))
        if overlap > 0:
            score += 10.0 * overlap
            diff_block_indices.add(b_idx)

        # Secondary: adjacency to diff blocks (will be recalculated after first pass)
        # Tertiary: control-flow keywords
        cf_keywords = (
            "if ",
            "else",
            "elif ",
            "for ",
            "while ",
            "return ",
            "raise ",
            "try:",
            "except ",
            "finally:",
            "with ",
            "yield ",
            "async ",
        )
        cf_count = sum(
            1
            for line in block_lines
            if any(line.strip().startswith(kw) for kw in cf_keywords)
        )
        score += 0.5 * cf_count

        scores.append(score)

    # Second pass: adjacency bonus for blocks next to diff blocks
    for b_idx in list(diff_block_indices):
        if b_idx - 1 >= 0 and b_idx - 1 not in diff_block_indices:
            scores[b_idx - 1] += 3.0
        if b_idx + 1 < block_count and b_idx + 1 not in diff_block_indices:
            scores[b_idx + 1] += 3.0

    # Always keep diff blocks
    must_keep = diff_block_indices or {0}

    # Budget: estimate max tokens for block selection
    if budget_tokens is not None:
        max_tokens = budget_tokens
    else:
        max_tokens = sum(sizes)  # no budget = keep everything eligible

    # 0/1 Knapsack DP for optional blocks (not must-keep)
    optional = [
        (i, scores[i], sizes[i])
        for i in range(block_count)
        if i not in must_keep and scores[i] > 0
    ]

    # Reserve budget for must-keep blocks
    must_keep_cost = sum(sizes[i] for i in must_keep)
    remaining_budget = max(0, max_tokens - must_keep_cost)

    # Simple knapsack - small enough for DP (typically <50 blocks)
    keep = set(must_keep)
    if optional and remaining_budget > 0:
        n = len(optional)
        W = min(remaining_budget, 10000)  # cap to prevent huge DP tables
        # Scale sizes down if needed
        scale = 1
        if W > 5000:
            scale = max(1, W // 5000)
            W = W // scale

        dp = [0] * (W + 1)
        choice = [[False] * (W + 1) for _ in range(n)]

        for i in range(n):
            _, val, raw_sz = optional[i]
            sz = max(1, raw_sz // scale)
            for w in range(W, sz - 1, -1):
                if dp[w - sz] + val > dp[w]:
                    dp[w] = dp[w - sz] + val
                    choice[i][w] = True

        # Traceback
        w = W
        for i in range(n - 1, -1, -1):
            if choice[i][w]:
                keep.add(optional[i][0])
                w -= max(1, optional[i][2] // scale)

    # Apply max_blocks cap (same logic as before)
    if budget_tokens is not None:
        allow_neighbors = budget_tokens >= 2500
        if not allow_neighbors:
            max_blocks = 1
        elif budget_tokens <= 1600:
            max_blocks = 2
        else:
            max_blocks = 3
        # If knapsack selected too many, trim by score (keep must_keep first)
        if len(keep) > max_blocks:
            ranked = sorted(keep, key=lambda i: (i in must_keep, scores[i]), reverse=True)
            keep = set(ranked[:max_blocks])

    keep_sorted = sorted(keep)

    kept_lines: list[str] = []
    for idx, block_idx in enumerate(keep_sorted):
        if idx > 0:
            kept_lines.append("...")
        start, end = blocks[block_idx]
        kept_lines.extend(lines[start:end + 1])

    dropped_blocks = max(0, block_count - len(keep_sorted))
    return "\n".join(kept_lines), block_count, dropped_blocks


def _build_summary(
    signature: str,
    code: str | None,
    diff_lines: list[int],
    budget_tokens: int | None,
) -> str:
    if not code:
        return signature
    lines = code.splitlines()
    summary_lines = [signature]
    if diff_lines:
        summary_lines.append(f"# diff lines: {len(diff_lines)}")
    keep_lines: list[str] = []
    for line in lines[:12]:
        stripped = line.strip()
        if stripped.startswith("def ") or stripped.startswith("class "):
            keep_lines.append(line)
            continue
        if "=" in line and stripped and not stripped.startswith("#"):
            keep_lines.append(line)
            continue
        if stripped.startswith("return "):
            keep_lines.append(line)
            continue
    if keep_lines:
        summary_lines.append("...summary...")
        summary_lines.extend(keep_lines[:6])
    summary = "\n".join(summary_lines)
    if budget_tokens is not None and len(summary) > budget_tokens * 4:
        summary = "\n".join(summary_lines[:3])
    return summary


def build_diff_context_from_hunks(
    project: str | Path,
    hunks: list[tuple[str, int, int]],
    language: str = "python",
    budget_tokens: int | None = None,
    compress: str | None = None,
    zoom_level: ZoomLevel = ZoomLevel.L4,
    strip_comments: bool = False,
    compress_imports: bool = False,
    type_prune: bool = False,
    _project_index: "ProjectIndex | None" = None,
) -> dict:
    project = Path(project).resolve()
    symbol_diff_lines = map_hunks_to_symbols(
        project, hunks, language=language, _project_index=_project_index,
    )

    idx = _project_index or ProjectIndex.build(
        project, language,
        include_sources=True,
        include_ranges=True,
        include_reverse_adjacency=True,
    )

    ordered: list[str] = []
    relevance: dict[str, str] = {}
    for symbol_id in symbol_diff_lines.keys():
        ordered.append(symbol_id)
        relevance[symbol_id] = "contains_diff"

    class_diff_counts: dict[str, set[str]] = defaultdict(set)
    for symbol_id in symbol_diff_lines.keys():
        rel_part, qual_part = symbol_id.split(":", 1)
        if "." in qual_part:
            class_name = qual_part.split(".", 1)[0]
            class_symbol = f"{rel_part}:{class_name}"
            class_diff_counts[class_symbol].add(symbol_id)
    class_multi_diff = {
        class_symbol for class_symbol, members in class_diff_counts.items() if len(members) > 1
    }

    for symbol_id in list(ordered):
        for callee in idx.adjacency.get(symbol_id, []):
            if callee not in relevance:
                relevance[callee] = "callee"
                ordered.append(callee)
        for caller in idx.reverse_adjacency.get(symbol_id, []):
            if caller not in relevance:
                relevance[caller] = "caller"
                ordered.append(caller)

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

    candidates: list[Candidate] = []
    import_extractor = HybridExtractor()
    file_imports: dict[str, list[str]] = {}

    def _imports_for_symbol(symbol_id: str) -> list[str]:
        if ":" not in symbol_id:
            return []
        rel_path = symbol_id.split(":", 1)[0]
        if rel_path in file_imports:
            return file_imports[rel_path]
        file_path = project / rel_path
        if not file_path.is_file():
            file_imports[rel_path] = []
            return []
        try:
            info = import_extractor.extract(str(file_path))
            file_imports[rel_path] = [imp.statement() for imp in info.imports]
        except Exception:
            file_imports[rel_path] = []
        return file_imports[rel_path]

    relevance_score = {"contains_diff": 3, "caller": 2, "callee": 2, "adjacent": 1}

    for order_idx, symbol_id in enumerate(ordered):
        func_info = idx.symbol_index.get(symbol_id)
        signature = idx.signature_overrides.get(symbol_id)
        if not signature:
            if func_info:
                signature = func_info.signature()
            else:
                signature = f"def {symbol_id.split(':')[-1]}(...)"

        lines_range = idx.symbol_ranges.get(symbol_id)
        if not lines_range and func_info:
            lines_range = (func_info.line_number, func_info.line_number)

        code = None
        summary = None
        code_scope_range = lines_range
        if compress in ("two-stage", "blocks") and symbol_id in symbol_diff_lines and lines_range:
            rel_part, qual_part = symbol_id.split(":", 1)
            if "." in qual_part:
                class_name = qual_part.split(".", 1)[0]
                class_symbol = f"{rel_part}:{class_name}"
                if class_symbol in class_multi_diff and (budget_tokens is None or budget_tokens >= 4000):
                    class_range = idx.symbol_ranges.get(class_symbol)
                    if class_range:
                        code_scope_range = class_range
        if symbol_id in symbol_diff_lines and lines_range:
            file_path = idx.symbol_files.get(symbol_id)
            if file_path and file_path in idx.file_sources:
                src_lines = idx.file_sources[file_path].splitlines()
                start, end = code_scope_range or lines_range
                start = max(1, start)
                end = min(len(src_lines), end)
                diff_line_list = sorted(symbol_diff_lines.get(symbol_id, []))
                if compress in ("two-stage", "blocks", "chunk-summary"):
                    code = "\n".join(src_lines[start - 1:end])
                else:
                    if diff_line_list:
                        # Use adaptive context based on code density and budget
                        code = _extract_windowed_code(
                            src_lines, diff_line_list, start, end,
                            context=None,  # Compute adaptively
                            budget_tokens=budget_tokens,
                        )
                    else:
                        code = "\n".join(src_lines[start - 1:end])
                if code and compress in ("two-stage", "blocks"):
                    if compress == "blocks":
                        from ..block_compress import compress_function_body
                        code, block_count, dropped_blocks = compress_function_body(
                            code,
                            code_start=start,
                            diff_lines=diff_line_list,
                            budget_tokens=budget_tokens,
                            language=language,
                            use_ast=True,
                        )
                    else:
                        code, block_count, dropped_blocks = _two_stage_prune(
                            code,
                            start,
                            diff_line_list,
                            budget_tokens,
                        )
                else:
                    block_count = 0
                    dropped_blocks = 0
                if compress == "chunk-summary":
                    summary = _build_summary(signature, code, diff_line_list, budget_tokens)
                    code = None
        else:
            block_count = 0
            dropped_blocks = 0

        label = relevance.get(symbol_id, "adjacent")
        meta: dict[str, object] = {
            "diff_lines": _to_ranges(sorted(symbol_diff_lines.get(symbol_id, []))),
            "block_count": block_count,
            "dropped_blocks": dropped_blocks,
            "summary": summary,
        }
        imports = _imports_for_symbol(symbol_id)
        if imports:
            meta["imports"] = imports
        candidates.append(
            Candidate(
                symbol_id=symbol_id,
                relevance=relevance_score.get(label, 1),
                relevance_label=label,
                order=order_idx,
                signature=signature,
                code=code,
                lines=code_scope_range or lines_range,
                meta=meta,
            )
        )

    if type_prune and candidates:
        callee_signature = ""
        callee_code = None
        for candidate in candidates:
            if candidate.relevance_label == "contains_diff":
                callee_signature = candidate.signature or ""
                callee_code = candidate.code
                break
        if not callee_signature:
            callee_signature = candidates[0].signature or ""
            callee_code = candidates[0].code

        before_count = len(candidates)
        candidates = prune_expansion(
            candidates,
            callee_signature=callee_signature,
            callee_code=callee_code,
        )
        after_count = len(candidates)
        print(f"Type pruning: {before_count} → {after_count} candidates", file=sys.stderr)

    # Build post-processors (attention reranking + edit locality)
    processors = _get_diff_processors(project, idx.file_sources)

    pack = ContextPackEngine(registry=None).build_context_pack(
        candidates,
        budget_tokens=budget_tokens,
        post_processors=processors or None,
        zoom_level=zoom_level,
        strip_comments=strip_comments,
        compress_imports=compress_imports,
    )

    # Record delivery for attention tracking
    _record_attention_delivery(project, pack)

    slices: list[dict] = []
    for item in pack.slices:
        entry = {
            "id": item.id,
            "relevance": item.relevance,
            "signature": item.signature,
            "code": item.code,
            "lines": list(item.lines) if item.lines else [],
        }
        if item.meta:
            entry.update(item.meta)
        slices.append(entry)

    result = {
        "base": None,
        "head": None,
        "budget_used": pack.budget_used,
        "slices": slices,
    }
    if pack.import_compression:
        result["import_compression"] = pack.import_compression
    return result


def _get_diff_processors(project: Path, file_sources: dict[str, str]) -> list:
    """Build post-processors for diff context (attention + edit locality)."""
    processors = []

    # Attention reranking
    db_path = project / ".tldrs" / "attention.db"
    if db_path.exists():
        try:
            from ..attention_pruning import AttentionTracker, create_candidate_reranker
            tracker = AttentionTracker(project)
            processors.append(create_candidate_reranker(tracker))
        except Exception:
            pass

    # Edit locality enrichment
    try:
        from ..edit_locality import create_edit_locality_enricher
        processors.append(create_edit_locality_enricher(project, file_sources))
    except Exception:
        pass

    return processors


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


def get_diff_signatures(
    project: str | Path,
    hunks: list[tuple[str, int, int]],
    language: str = "python",
    type_prune: bool = False,
    _project_index: "ProjectIndex | None" = None,
) -> list[DiffSymbolSignature]:
    """Get signatures for symbols affected by diff hunks without extracting code.

    This is the foundation of delta-first diff context. By getting only signatures,
    we can compute ETags and check delta BEFORE extracting code, avoiding wasted
    work for unchanged symbols.

    Args:
        project: Path to project root
        hunks: List of (file_path, start_line, end_line) from parse_unified_diff
        language: Programming language

    Returns:
        List of DiffSymbolSignature objects
    """
    project = Path(project).resolve()
    symbol_diff_lines = map_hunks_to_symbols(
        project, hunks, language=language, _project_index=_project_index,
    )

    idx = _project_index or ProjectIndex.build(
        project, language,
        include_sources=False,
        include_ranges=True,
        include_reverse_adjacency=True,
    )

    # Collect ordered symbols with relevance
    ordered: list[str] = []
    relevance: dict[str, str] = {}

    for symbol_id in symbol_diff_lines.keys():
        ordered.append(symbol_id)
        relevance[symbol_id] = "contains_diff"

    # Expand to callers/callees
    for symbol_id in list(ordered):
        for callee in idx.adjacency.get(symbol_id, []):
            if callee not in relevance:
                relevance[callee] = "callee"
                ordered.append(callee)
        for caller in idx.reverse_adjacency.get(symbol_id, []):
            if caller not in relevance:
                relevance[caller] = "caller"
                ordered.append(caller)

    # Build signature list
    signatures: list[DiffSymbolSignature] = []

    for symbol_id in ordered:
        func_info = idx.symbol_index.get(symbol_id)
        signature = idx.signature_overrides.get(symbol_id)
        if not signature:
            if func_info:
                signature = func_info.signature()
            else:
                signature = f"def {symbol_id.split(':')[-1]}(...)"

        line = func_info.line_number if func_info else 0
        file_path_str = idx.symbol_files.get(symbol_id, "?")

        signatures.append(
            DiffSymbolSignature(
                symbol_id=symbol_id,
                signature=signature,
                line=line,
                file_path=file_path_str,
                diff_lines=sorted(symbol_diff_lines.get(symbol_id, [])),
                relevance_label=relevance.get(symbol_id, "adjacent"),
            )
        )

    if type_prune and signatures:
        expanded_candidates = [
            Candidate(
                symbol_id=sig.symbol_id,
                relevance={"contains_diff": 3, "caller": 2, "callee": 2, "adjacent": 1}.get(
                    sig.relevance_label, 1
                ),
                relevance_label=sig.relevance_label,
                order=i,
                signature=sig.signature,
                code=None,
                lines=(sig.line, sig.line) if sig.line else None,
                meta={"diff_lines": sig.diff_lines},
            )
            for i, sig in enumerate(signatures)
        ]
        callee_signature = next(
            (sig.signature for sig in signatures if sig.relevance_label == "contains_diff"),
            signatures[0].signature,
        )
        before_count = len(expanded_candidates)
        pruned_candidates = prune_expansion(
            expanded_candidates,
            callee_signature=callee_signature,
            callee_code=None,
        )
        after_count = len(pruned_candidates)
        print(f"Type pruning: {before_count} → {after_count} candidates", file=sys.stderr)
        by_symbol = {sig.symbol_id: sig for sig in signatures}
        signatures = [
            by_symbol[candidate.symbol_id]
            for candidate in pruned_candidates
            if candidate.symbol_id in by_symbol
        ]

    return signatures


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
    zoom_level: ZoomLevel = ZoomLevel.L4,
    strip_comments: bool = False,
    compress_imports: bool = False,
    type_prune: bool = False,
    _project_index: "ProjectIndex | None" = None,
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
        zoom_level=zoom_level,
        strip_comments=strip_comments,
        compress_imports=compress_imports,
        type_prune=type_prune,
        _project_index=_project_index,
    )
    pack["base"] = base_ref
    pack["head"] = head_ref
    return pack
