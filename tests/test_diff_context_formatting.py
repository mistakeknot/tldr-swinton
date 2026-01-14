from tldr_swinton.output_formats import format_context_pack


def test_diff_context_pack_uses_fenced_code_blocks() -> None:
    pack = {
        "base": "BASE",
        "head": "HEAD",
        "slices": [
            {
                "id": "mod.py:foo",
                "relevance": "contains_diff",
                "signature": "def foo()",
                "lines": [1, 5],
                "diff_lines": [[2, 2]],
                "code": "line1\nline2",
            }
        ],
    }

    output = format_context_pack(pack, fmt="ultracompact")
    assert "```" in output
    assert "  code:" not in output
    assert "  line1" not in output
    assert "line1" in output
    assert "line2" in output
