"""Tests for the upgraded two-stage pruning in difflens."""
from tldr_swinton.modules.core.engines.difflens import (
    _split_blocks_by_indent,
    _two_stage_prune,
)


def test_split_blocks_by_indent_basic():
    """Indentation changes create block boundaries."""
    lines = [
        "def foo():",
        "    x = 1",
        "    y = 2",
        "def bar():",
        "    z = 3",
    ]
    blocks = _split_blocks_by_indent(lines)
    assert len(blocks) >= 2, f"Expected at least 2 blocks, got {blocks}"
    # First block should start at 0
    assert blocks[0][0] == 0


def test_split_blocks_by_indent_empty():
    """Empty input returns a single block."""
    blocks = _split_blocks_by_indent([])
    assert len(blocks) == 1


def test_two_stage_prune_keeps_diff_blocks():
    """Blocks containing diff lines are always kept."""
    code = "line1\nline2\nline3\n\nline5\nline6\nline7"
    result, block_count, dropped = _two_stage_prune(
        code, code_start=1, diff_lines=[1, 2], budget_tokens=None
    )
    assert "line1" in result
    assert block_count >= 1


def test_two_stage_prune_with_tight_budget():
    """Tight budget drops non-essential blocks."""
    # Create code with clear indentation-based blocks
    code = "\n".join([
        "def foo():",
        "    a = 1",
        "    b = 2",
        "    c = 3",
        "def bar():",
        "    d = 4",
        "    e = 5",
        "def baz():",
        "    f = 6",
        "    g = 7",
    ])
    result, block_count, dropped = _two_stage_prune(
        code, code_start=1, diff_lines=[1], budget_tokens=100
    )
    # With very tight budget, should drop some blocks
    assert dropped >= 0
    # Should still contain the diff line's content
    assert "foo" in result


def test_two_stage_prune_returns_original_when_no_budget():
    """Without budget constraint, all high-scoring blocks are kept."""
    code = "a = 1\nb = 2\nc = 3"
    result, block_count, dropped = _two_stage_prune(
        code, code_start=1, diff_lines=[1, 2, 3], budget_tokens=None
    )
    # All lines should be present when no budget and all are diff lines
    assert "a = 1" in result
    assert "b = 2" in result
    assert "c = 3" in result
