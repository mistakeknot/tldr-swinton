"""Block-level compression for function bodies.

Inspired by LongCodeZip (ASE 2025, arXiv 2510.00446): segments function bodies
into semantic blocks and uses 0/1 knapsack DP to select the highest-value blocks
that fit within a token budget. Elided blocks are replaced with markers.

Two segmentation strategies:
  1. AST-based (tree-sitter): splits at top-level control-flow nodes within functions
  2. Indent-based (fallback): splits at indentation-level transitions and blank lines

The knapsack logic is extracted from DiffLens `_two_stage_prune()` (v0.6.x).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CodeBlock:
    """A semantically coherent block within a function body."""

    start_line: int  # 0-based index within the source lines
    end_line: int  # 0-based, inclusive
    text: str
    token_count: int  # estimated tokens (chars // 4)
    relevance: float = 0.0  # 0.0-1.0 normalized score


# ---------------------------------------------------------------------------
# Block segmentation: AST-based (primary) and indent-based (fallback)
# ---------------------------------------------------------------------------

# AST node types that represent top-level block boundaries within a function body.
_BLOCK_BOUNDARY_NODES: dict[str, set[str]] = {
    "python": {
        "if_statement", "for_statement", "while_statement", "try_statement",
        "with_statement", "match_statement", "return_statement", "raise_statement",
        "assert_statement", "expression_statement", "assignment",
        "augmented_assignment", "function_definition", "async_function_definition",
        "class_definition", "decorated_definition", "for_in_clause",
    },
    "javascript": {
        "if_statement", "for_statement", "for_in_statement", "while_statement",
        "try_statement", "switch_statement", "return_statement", "throw_statement",
        "expression_statement", "variable_declaration", "lexical_declaration",
        "function_declaration", "class_declaration",
    },
    "typescript": {
        "if_statement", "for_statement", "for_in_statement", "while_statement",
        "try_statement", "switch_statement", "return_statement", "throw_statement",
        "expression_statement", "variable_declaration", "lexical_declaration",
        "function_declaration", "class_declaration", "type_alias_declaration",
        "interface_declaration",
    },
    "go": {
        "if_statement", "for_statement", "switch_statement", "type_switch_statement",
        "select_statement", "return_statement", "go_statement", "defer_statement",
        "short_var_declaration", "assignment_statement", "expression_statement",
        "var_declaration", "type_declaration",
    },
}


def segment_by_ast(source: str, language: str) -> list[CodeBlock] | None:
    """Segment source into blocks using tree-sitter AST.

    Returns None if tree-sitter is unavailable or parsing fails, signaling
    the caller to fall back to indent-based segmentation.

    Only extracts **top-level children** of the function body (or module root),
    not nested nodes. A ``for`` inside an ``if`` is part of the ``if`` block.
    """
    from .zoom import _get_parser, _normalize_language

    norm = _normalize_language(language)
    boundary_types = _BLOCK_BOUNDARY_NODES.get(norm)
    if boundary_types is None:
        return None

    parser = _get_parser(norm)
    if parser is None:
        return None

    source_bytes = source.encode("utf-8", errors="replace")
    try:
        tree = parser.parse(source_bytes)
    except Exception:
        return None

    lines = source.splitlines()
    if not lines:
        return None

    # Walk top-level children only (not recursing into nested scopes).
    # If the root has a single function/class child, descend into its body.
    root = tree.root_node
    body_nodes = _find_body_children(root)
    if not body_nodes:
        return None

    # Group consecutive lines that belong to the same top-level statement.
    # Each top-level AST child becomes one block.
    blocks: list[CodeBlock] = []
    covered = set()

    for node in body_nodes:
        start = node.start_point[0]
        end = node.end_point[0]
        # Clamp to source bounds
        start = max(0, min(start, len(lines) - 1))
        end = max(start, min(end, len(lines) - 1))

        # Skip if fully overlapping with a previous block (e.g., decorators)
        if all(ln in covered for ln in range(start, end + 1)):
            continue

        for ln in range(start, end + 1):
            covered.add(ln)

        block_lines = lines[start: end + 1]
        text = "\n".join(block_lines)
        blocks.append(CodeBlock(
            start_line=start,
            end_line=end,
            text=text,
            token_count=max(1, len(text) // 4),
        ))

    # Fill gaps — lines not covered by any AST node (comments, blank lines, etc.)
    if blocks:
        blocks = _fill_gaps(blocks, lines)

    return blocks if blocks else None


def _find_body_children(root):
    """Find the top-level statement nodes to use as block boundaries.

    If the root is a module with a single function/class, descend into its body.
    Otherwise, use the root's direct children.
    """
    children = [c for c in root.children if c.type not in ("comment", "newline", "NEWLINE")]
    if not children:
        return list(root.children)

    # If single definition, descend into its body/block
    if len(children) == 1 and children[0].type in (
        "function_definition", "async_function_definition", "class_definition",
        "function_declaration", "method_declaration", "class_declaration",
    ):
        body = None
        for child in children[0].children:
            if child.type in ("block", "statement_block", "class_body",
                              "function_body", "body"):
                body = child
                break
        if body is not None:
            return list(body.children)

    return children


def _fill_gaps(blocks: list[CodeBlock], lines: list[str]) -> list[CodeBlock]:
    """Merge uncovered line ranges into adjacent blocks."""
    if not blocks:
        return blocks

    # Sort by start_line
    blocks.sort(key=lambda b: b.start_line)
    result: list[CodeBlock] = []

    for i, block in enumerate(blocks):
        # Check for gap before this block
        prev_end = blocks[i - 1].end_line if i > 0 else -1
        if block.start_line > prev_end + 1:
            gap_start = prev_end + 1
            gap_end = block.start_line - 1
            gap_lines = lines[gap_start: gap_end + 1]
            gap_text = "\n".join(gap_lines)
            if gap_text.strip():  # Don't create blocks for blank-only gaps
                result.append(CodeBlock(
                    start_line=gap_start,
                    end_line=gap_end,
                    text=gap_text,
                    token_count=max(1, len(gap_text) // 4),
                ))
        result.append(block)

    # Trailing gap
    last_end = blocks[-1].end_line
    if last_end < len(lines) - 1:
        gap_start = last_end + 1
        gap_lines = lines[gap_start:]
        gap_text = "\n".join(gap_lines)
        if gap_text.strip():
            result.append(CodeBlock(
                start_line=gap_start,
                end_line=len(lines) - 1,
                text=gap_text,
                token_count=max(1, len(gap_text) // 4),
            ))

    return result


def segment_by_indent(lines: list[str]) -> list[CodeBlock]:
    """Segment code into blocks at indentation-level transitions.

    Extracted from DiffLens ``_split_blocks_by_indent()`` for reuse.
    Detects block boundaries where indentation level changes, which captures
    structural boundaries (function bodies, if/else branches, loops) better
    than blank-line splitting.
    """
    if not lines:
        return [CodeBlock(start_line=0, end_line=0, text="", token_count=0)]

    ranges: list[tuple[int, int]] = []
    start = 0

    def _indent_level(line: str) -> int | None:
        stripped = line.lstrip()
        if not stripped:
            return None
        return len(line) - len(stripped)

    prev_indent = _indent_level(lines[0])

    for idx in range(len(lines)):
        stripped = lines[idx].strip()
        if stripped == "" or stripped == "...":
            if start < idx:
                ranges.append((start, idx - 1))
            start = idx + 1
            prev_indent = None
            continue

        cur_indent = _indent_level(lines[idx])
        if cur_indent is None:
            continue

        if prev_indent is not None and cur_indent != prev_indent:
            if cur_indent < prev_indent or abs(cur_indent - prev_indent) >= 4:
                if start < idx:
                    ranges.append((start, idx - 1))
                start = idx

        prev_indent = cur_indent

    if start < len(lines):
        ranges.append((start, len(lines) - 1))

    if not ranges:
        ranges = [(0, len(lines) - 1)]

    blocks = []
    for s, e in ranges:
        block_lines = lines[s: e + 1]
        text = "\n".join(block_lines)
        blocks.append(CodeBlock(
            start_line=s,
            end_line=e,
            text=text,
            token_count=max(1, len(text) // 4),
        ))
    return blocks


def segment_into_blocks(source: str, language: str = "python") -> list[CodeBlock]:
    """Segment source into blocks with AST-based → indent-based fallback."""
    ast_blocks = segment_by_ast(source, language)
    if ast_blocks:
        return ast_blocks
    return segment_by_indent(source.splitlines())


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

_CF_KEYWORDS = (
    "if ", "else", "elif ", "for ", "while ", "return ", "raise ",
    "try:", "except ", "finally:", "with ", "yield ", "async ",
    "switch", "case ", "defer ", "go ",
)


def score_blocks(
    blocks: list[CodeBlock],
    diff_lines: list[int] | None = None,
    code_start: int = 0,
) -> tuple[list[float], set[int]]:
    """Score blocks for knapsack selection. Returns (scores, must_keep_indices).

    Scoring mirrors DiffLens ``_two_stage_prune()`` logic:
      - +10.0 per diff line overlap
      - +3.0 for adjacency to diff blocks
      - +0.5 per control-flow keyword line
    """
    diff_set = set(diff_lines) if diff_lines else set()
    scores: list[float] = []
    diff_block_indices: set[int] = set()

    for b_idx, block in enumerate(blocks):
        score = 0.0

        # Diff overlap
        if diff_set:
            for ln in range(block.start_line, block.end_line + 1):
                abs_ln = ln + code_start
                if abs_ln in diff_set:
                    score += 10.0
                    diff_block_indices.add(b_idx)

        # Control-flow keywords
        for line in block.text.splitlines():
            stripped = line.strip()
            if any(stripped.startswith(kw) for kw in _CF_KEYWORDS):
                score += 0.5

        scores.append(score)

    # Adjacency bonus (second pass)
    for b_idx in list(diff_block_indices):
        if b_idx - 1 >= 0 and b_idx - 1 not in diff_block_indices:
            scores[b_idx - 1] += 3.0
        if b_idx + 1 < len(blocks) and b_idx + 1 not in diff_block_indices:
            scores[b_idx + 1] += 3.0

    must_keep = diff_block_indices or {0}  # Always keep at least the first block
    return scores, must_keep


# ---------------------------------------------------------------------------
# Knapsack selection
# ---------------------------------------------------------------------------


def knapsack_select(
    blocks: list[CodeBlock],
    scores: list[float],
    must_keep: set[int],
    budget_tokens: int,
) -> list[int]:
    """Select optimal subset of blocks via 0/1 knapsack DP.

    Extracted from DiffLens ``_two_stage_prune()`` knapsack logic.
    Returns sorted list of selected block indices.
    """
    n = len(blocks)
    sizes = [b.token_count for b in blocks]

    # Reserve budget for must-keep blocks
    must_keep_cost = sum(sizes[i] for i in must_keep)
    remaining_budget = max(0, budget_tokens - must_keep_cost)

    # Optional blocks (scored > 0, not must-keep)
    optional = [
        (i, scores[i], sizes[i])
        for i in range(n)
        if i not in must_keep and scores[i] > 0
    ]

    keep = set(must_keep)

    if optional and remaining_budget > 0:
        W = min(remaining_budget, 10000)
        scale = 1
        if W > 5000:
            scale = max(1, W // 5000)
            W = W // scale

        dp = [0.0] * (W + 1)
        choice = [[False] * (W + 1) for _ in range(len(optional))]

        for i in range(len(optional)):
            _, val, raw_sz = optional[i]
            sz = max(1, raw_sz // scale)
            for w in range(W, sz - 1, -1):
                if dp[w - sz] + val > dp[w]:
                    dp[w] = dp[w - sz] + val
                    choice[i][w] = True

        # Traceback
        w = W
        for i in range(len(optional) - 1, -1, -1):
            if choice[i][w]:
                keep.add(optional[i][0])
                w -= max(1, optional[i][2] // scale)

    return sorted(keep)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def compress_function_body(
    code: str,
    code_start: int = 0,
    diff_lines: list[int] | None = None,
    budget_tokens: int | None = None,
    language: str = "python",
    *,
    use_ast: bool = True,
) -> tuple[str, int, int]:
    """Compress a function body to fit within token budget.

    Uses block segmentation (AST or indent-based) + knapsack optimization.
    Elided blocks are replaced with ``# ... (N lines elided)`` markers.

    Returns:
        (compressed_code, block_count, dropped_blocks)
        Same return signature as DiffLens ``_two_stage_prune()`` for compatibility.
    """
    lines = code.splitlines()
    if not lines:
        return code, 0, 0

    # Segment
    if use_ast:
        blocks = segment_into_blocks(code, language)
    else:
        blocks = segment_by_indent(lines)

    block_count = len(blocks)
    if block_count == 0:
        return code, 0, 0

    total_tokens = sum(b.token_count for b in blocks)
    if budget_tokens is None or total_tokens <= budget_tokens:
        return code, block_count, 0  # Fits within budget

    # Score
    scores, must_keep = score_blocks(blocks, diff_lines, code_start)

    # Select
    selected = knapsack_select(blocks, scores, must_keep, budget_tokens)

    # Render with elision markers
    kept_lines: list[str] = []
    selected_set = set(selected)
    i = 0
    while i < block_count:
        if i in selected_set:
            if kept_lines and kept_lines[-1].startswith("# ..."):
                pass  # Don't add blank line between elision and content
            kept_lines.extend(blocks[i].text.splitlines())
            i += 1
        else:
            # Count consecutive elided blocks
            elided_start = i
            elided_lines = 0
            while i < block_count and i not in selected_set:
                elided_lines += blocks[i].end_line - blocks[i].start_line + 1
                i += 1
            kept_lines.append(f"# ... ({elided_lines} lines elided)")

    dropped = max(0, block_count - len(selected))
    return "\n".join(kept_lines), block_count, dropped
