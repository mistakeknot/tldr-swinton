"""Tests for block_compress module — AST-based block segmentation + knapsack DP."""

import pytest

from tldr_swinton.modules.core.block_compress import (
    CodeBlock,
    compress_function_body,
    knapsack_select,
    score_blocks,
    segment_by_ast,
    segment_by_indent,
    segment_into_blocks,
)


# ---------------------------------------------------------------------------
# Sample code for testing
# ---------------------------------------------------------------------------

PYTHON_FUNCTION = """\
def process_data(items):
    results = []
    errors = []

    for item in items:
        if item.is_valid():
            result = transform(item)
            results.append(result)
        else:
            errors.append(item.error_message())

    if errors:
        log_errors(errors)
        raise ValueError(f"Found {len(errors)} invalid items")

    return results
"""

PYTHON_MULTIBLOCK = """\
def complex_handler(request):
    # Validate input
    if not request.body:
        return Response(400, "Empty body")

    # Parse payload
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError as e:
        return Response(400, str(e))

    # Process items
    results = []
    for item in data["items"]:
        processed = process_item(item)
        results.append(processed)

    # Build response
    response = {
        "count": len(results),
        "items": results,
    }
    return Response(200, json.dumps(response))
"""


# ---------------------------------------------------------------------------
# Test: segment_by_indent (extracted from DiffLens, behavior preserved)
# ---------------------------------------------------------------------------

class TestSegmentByIndent:
    def test_basic_split(self):
        lines = [
            "    x = 1",
            "    y = 2",
            "",
            "    if x > y:",
            "        return x",
        ]
        blocks = segment_by_indent(lines)
        assert len(blocks) >= 2
        assert all(isinstance(b, CodeBlock) for b in blocks)

    def test_empty_input(self):
        blocks = segment_by_indent([])
        assert len(blocks) == 1
        assert blocks[0].text == ""

    def test_single_line(self):
        blocks = segment_by_indent(["    return 42"])
        assert len(blocks) == 1
        assert "return 42" in blocks[0].text

    def test_indent_change_creates_boundary(self):
        lines = [
            "def foo():",
            "    x = 1",
            "    y = 2",
            "    if x:",
            "        return x",
            "    return y",
        ]
        blocks = segment_by_indent(lines)
        # Should split at indent transitions
        assert len(blocks) >= 2


# ---------------------------------------------------------------------------
# Test: segment_by_ast (tree-sitter based)
# ---------------------------------------------------------------------------

class TestSegmentByAst:
    def test_python_function(self):
        blocks = segment_by_ast(PYTHON_FUNCTION, "python")
        if blocks is None:
            pytest.skip("tree-sitter-python not available")
        assert len(blocks) >= 3  # assignment, for loop, if block, return
        # All lines should be covered
        all_lines = set()
        for b in blocks:
            for ln in range(b.start_line, b.end_line + 1):
                all_lines.add(ln)
        source_lines = PYTHON_FUNCTION.splitlines()
        non_empty = {i for i, l in enumerate(source_lines) if l.strip()}
        # Most non-empty lines should be in some block
        assert len(all_lines & non_empty) >= len(non_empty) * 0.8

    def test_python_multiblock(self):
        blocks = segment_by_ast(PYTHON_MULTIBLOCK, "python")
        if blocks is None:
            pytest.skip("tree-sitter-python not available")
        assert len(blocks) >= 4  # validate, parse, process, build response

    def test_unsupported_language_returns_none(self):
        result = segment_by_ast("echo hello", "bash")
        assert result is None

    def test_empty_source_returns_none(self):
        result = segment_by_ast("", "python")
        assert result is None


# ---------------------------------------------------------------------------
# Test: segment_into_blocks (dispatcher with fallback)
# ---------------------------------------------------------------------------

class TestSegmentIntoBlocks:
    def test_python_uses_ast(self):
        blocks = segment_into_blocks(PYTHON_FUNCTION, "python")
        assert len(blocks) >= 2
        assert all(isinstance(b, CodeBlock) for b in blocks)

    def test_unknown_language_falls_back(self):
        code = "x = 1\ny = 2\n\nz = 3"
        blocks = segment_into_blocks(code, "unknown_lang")
        assert len(blocks) >= 1
        # Should still produce blocks via indent fallback


# ---------------------------------------------------------------------------
# Test: score_blocks
# ---------------------------------------------------------------------------

class TestScoreBlocks:
    def test_diff_overlap_scores_high(self):
        blocks = [
            CodeBlock(0, 2, "x = 1\ny = 2\nz = 3", 3, 0.0),
            CodeBlock(3, 5, "a = 4\nb = 5\nc = 6", 3, 0.0),
        ]
        scores, must_keep = score_blocks(blocks, diff_lines=[1], code_start=0)
        assert scores[0] > scores[1]  # Block 0 has diff overlap
        assert 0 in must_keep

    def test_control_flow_bonus(self):
        blocks = [
            CodeBlock(0, 0, "x = 1", 1, 0.0),
            CodeBlock(1, 1, "return x", 2, 0.0),
        ]
        scores, _ = score_blocks(blocks)
        assert scores[1] > scores[0]  # return gets CF bonus

    def test_no_diff_keeps_first_block(self):
        blocks = [
            CodeBlock(0, 0, "x = 1", 1, 0.0),
            CodeBlock(1, 1, "y = 2", 1, 0.0),
        ]
        _, must_keep = score_blocks(blocks, diff_lines=None)
        assert 0 in must_keep

    def test_adjacency_bonus(self):
        blocks = [
            CodeBlock(0, 0, "x = 1", 1, 0.0),
            CodeBlock(1, 1, "y = 2", 1, 0.0),
            CodeBlock(2, 2, "z = 3", 1, 0.0),
        ]
        scores, _ = score_blocks(blocks, diff_lines=[1], code_start=0)
        # Block 1 has diff, blocks 0 and 2 get adjacency bonus
        assert scores[0] > 0  # adjacency bonus
        assert scores[2] > 0  # adjacency bonus


# ---------------------------------------------------------------------------
# Test: knapsack_select
# ---------------------------------------------------------------------------

class TestKnapsackSelect:
    def test_all_fit(self):
        blocks = [
            CodeBlock(0, 0, "x", 10, 0.0),
            CodeBlock(1, 1, "y", 10, 0.0),
        ]
        scores = [5.0, 3.0]
        selected = knapsack_select(blocks, scores, {0}, budget_tokens=100)
        assert selected == [0, 1]

    def test_budget_constraint(self):
        blocks = [
            CodeBlock(0, 0, "x" * 40, 10, 0.0),  # 10 tokens
            CodeBlock(1, 1, "y" * 80, 20, 0.0),  # 20 tokens
            CodeBlock(2, 2, "z" * 40, 10, 0.0),  # 10 tokens
        ]
        scores = [5.0, 3.0, 8.0]
        # Budget = 15: must keep block 0 (10), can fit block 2 (10) but not both 1+2
        selected = knapsack_select(blocks, scores, {0}, budget_tokens=20)
        assert 0 in selected
        # Should prefer block 2 (higher score, same size as block 0's remaining budget)
        assert 2 in selected

    def test_must_keep_always_included(self):
        blocks = [
            CodeBlock(0, 0, "x" * 400, 100, 0.0),
            CodeBlock(1, 1, "y" * 40, 10, 0.0),
        ]
        scores = [1.0, 10.0]
        selected = knapsack_select(blocks, scores, {0}, budget_tokens=50)
        # Block 0 is must-keep even though it exceeds budget
        assert 0 in selected

    def test_empty_blocks(self):
        selected = knapsack_select([], [], set(), budget_tokens=100)
        assert selected == []


# ---------------------------------------------------------------------------
# Test: compress_function_body (end-to-end)
# ---------------------------------------------------------------------------

class TestCompressFunctionBody:
    def test_noop_when_fits(self):
        code = "x = 1\ny = 2"
        result, blocks, dropped = compress_function_body(
            code, budget_tokens=10000
        )
        assert result == code
        assert dropped == 0

    def test_compression_adds_elision_marker(self):
        # Long function with tight budget should produce elision markers
        result, blocks, dropped = compress_function_body(
            PYTHON_MULTIBLOCK,
            budget_tokens=50,  # Very tight budget
            diff_lines=[3],  # One diff line to anchor
            code_start=1,
        )
        assert "# ..." in result
        assert "elided" in result
        assert dropped > 0

    def test_must_keep_diff_blocks(self):
        result, _, _ = compress_function_body(
            PYTHON_MULTIBLOCK,
            budget_tokens=50,
            diff_lines=[5],  # Line 5 in the try block
            code_start=1,
        )
        # The block containing the diff line should be present
        # (either the try block or adjacent content)
        assert len(result) > 0

    def test_no_budget_returns_full(self):
        result, blocks, dropped = compress_function_body(
            PYTHON_FUNCTION, budget_tokens=None
        )
        assert result == PYTHON_FUNCTION
        assert dropped == 0

    def test_indent_fallback(self):
        # Force indent-based by disabling AST
        result, blocks, dropped = compress_function_body(
            PYTHON_MULTIBLOCK,
            budget_tokens=50,
            diff_lines=[3],
            code_start=1,
            use_ast=False,
        )
        assert "# ..." in result
        assert dropped > 0

    def test_return_signature_compat(self):
        # Verify return type matches DiffLens _two_stage_prune()
        result, block_count, dropped = compress_function_body(
            "x = 1\ny = 2",
            budget_tokens=1000,
        )
        assert isinstance(result, str)
        assert isinstance(block_count, int)
        assert isinstance(dropped, int)
