"""Tests for --max-lines / --max-bytes output caps."""

import json
import subprocess
import sys

import pytest

from tldr_swinton.modules.core.output_formats import truncate_output, truncate_json_output, _trim_to_symbol_boundary


def _content_before_marker(text: str) -> str:
    return text.split("[TRUNCATED:")[0].rstrip("\n")


# --- Unit tests for truncate_output ---

def test_truncate_output_no_caps():
    text = "line1\nline2\nline3"
    assert truncate_output(text) == text


def test_truncate_output_max_lines():
    text = "\n".join(f"line{i}" for i in range(20))
    result = truncate_output(text, max_lines=5)
    assert "[TRUNCATED:" in result
    assert "--max-lines=5" in result
    content_lines = _content_before_marker(result).splitlines()
    assert len(content_lines) <= 5


def test_truncate_output_max_bytes():
    text = "A" * 1000
    result = truncate_output(text, max_bytes=100)
    assert "[TRUNCATED:" in result
    assert "--max-bytes=100" in result
    # The content before marker should be <= 100 bytes
    content_before_marker = _content_before_marker(result)
    assert len(content_before_marker.encode("utf-8")) <= 100


def test_truncate_output_both_caps():
    text = "\n".join("A" * 50 for _ in range(20))
    result = truncate_output(text, max_lines=5, max_bytes=100)
    assert "[TRUNCATED:" in result
    assert "--max-lines=5" in result
    assert "--max-bytes=100" in result


def test_truncate_output_max_bytes_symbol_boundary():
    """max-bytes should truncate at a symbol boundary, not mid-symbol block."""
    blocks = []
    for i in range(10):
        blocks.append(f"P0:func_{i} def func_{i}(x: int) -> int @{i * 10}")
        blocks.append(f"  calls: P0:helper_{i}")
        blocks.append("")
    text = "\n".join(blocks)

    result = truncate_output(text, max_bytes=220)
    assert "[TRUNCATED:" in result
    content = _content_before_marker(result)
    non_empty = [line for line in content.split("\n") if line.strip()]
    assert non_empty
    assert non_empty[-1].startswith("  calls:")


def test_truncate_output_max_lines_symbol_boundary():
    """max-lines should truncate at a symbol boundary."""
    blocks = []
    for i in range(10):
        blocks.append(f"P0:func_{i} def func_{i}() @{i * 10}")
        blocks.append(f"  calls: P0:helper_{i}")
        blocks.append("")
    text = "\n".join(blocks)

    # 7 lines cuts in the middle of the 3rd block without boundary rewind.
    result = truncate_output(text, max_lines=7)
    assert "[TRUNCATED:" in result
    content = _content_before_marker(result)
    assert "func_2" not in content
    non_empty = [line for line in content.split("\n") if line.strip()]
    assert non_empty
    assert non_empty[-1].startswith("  calls:")


def test_truncate_output_under_caps():
    text = "short"
    assert truncate_output(text, max_lines=100, max_bytes=1000) == text


# --- Cache-friendly / markdown header boundary tests ---

def test_truncate_cache_friendly_no_orphaned_header():
    """Truncation in cache-friendly format must not leave orphaned ### headers."""
    blocks = []
    for i in range(5):
        blocks.append(f"### symbol_{i}")
        blocks.append("```python")
        blocks.append(f"def func_{i}(): pass")
        blocks.append("```")
        blocks.append("")
    text = "\n".join(blocks)

    # Truncate mid-way through symbol_3: 14 lines cuts after symbol_2's blank line
    # and into symbol_3's code block.  Without the fix, ### symbol_3 would survive.
    result = truncate_output(text, max_lines=14)
    assert "[TRUNCATED:" in result
    content = _content_before_marker(result)
    for line in content.splitlines():
        if line.strip().startswith("### "):
            # Every ### header must be followed by its code block
            idx = content.splitlines().index(line)
            remaining = content.splitlines()[idx + 1:]
            assert any(l.strip().startswith("```") for l in remaining), (
                f"Orphaned header found: {line!r}"
            )


def test_truncate_cache_friendly_section_header():
    """Orphaned ## section headers (like '## DYNAMIC CONTENT') should be removed."""
    lines_list = [
        "# CACHE-FRIENDLY CONTEXT",
        "",
        "## STATIC SECTION",
        "some static content",
        "",
        "## DYNAMIC CONTENT",
    ]
    # _trim_to_symbol_boundary should strip the orphaned ## header
    trimmed = _trim_to_symbol_boundary(lines_list)
    assert trimmed
    last_nonblank = [l for l in trimmed if l.strip()][-1]
    assert not last_nonblank.strip().startswith("## "), (
        f"Orphaned section header survived: {last_nonblank!r}"
    )


def test_truncate_ultracompact_code_block():
    """Ultracompact with code blocks: truncation inside ``` rewinds to previous symbol."""
    blocks = []
    for i in range(5):
        blocks.append(f"P0:func_{i} def func_{i}(x: int) -> int @{i * 10}")
        blocks.append("```")
        blocks.append(f"  x = {i}")
        blocks.append("```")
        blocks.append("")
    text = "\n".join(blocks)

    # 12 lines: cuts inside func_2's code block.  Rewind should land at func_1's
    # trailing blank line.
    result = truncate_output(text, max_lines=12)
    assert "[TRUNCATED:" in result
    content = _content_before_marker(result)
    # Should contain func_1 completely but not func_2's body
    assert "func_1" in content
    assert "func_2" not in content


def test_truncate_preserves_complete_symbols():
    """Truncation just after a complete symbol's blank line keeps it intact."""
    blocks = []
    for i in range(5):
        blocks.append(f"### symbol_{i}")
        blocks.append("```python")
        blocks.append(f"def func_{i}(): pass")
        blocks.append("```")
        blocks.append("")
    text = "\n".join(blocks)

    # 10 lines = exactly 2 complete symbols (5 lines each).  No truncation needed
    # because the last line is blank.
    result = truncate_output(text, max_lines=10)
    content = result.split("[TRUNCATED:")[0].rstrip("\n") if "[TRUNCATED:" in result else result
    assert "symbol_0" in content
    assert "symbol_1" in content


# --- Unit tests for truncate_json_output ---

def test_truncate_json_slices():
    data = {"slices": list(range(50)), "meta": "keep"}
    result = truncate_json_output(data, max_lines=10, indent=2)
    parsed = json.loads(result)
    assert parsed["truncated"] is True
    assert len(parsed["slices"]) < 50
    assert parsed["meta"] == "keep"


def test_truncate_json_lines():
    data = {"lines": list(range(100)), "count": 100}
    result = truncate_json_output(data, max_lines=10, indent=2)
    parsed = json.loads(result)
    assert parsed["truncated"] is True
    assert len(parsed["lines"]) < 100


def test_truncate_json_no_caps():
    data = {"lines": [1, 2, 3], "count": 3}
    result = truncate_json_output(data)
    assert json.loads(result) == data


def test_truncate_json_max_bytes():
    data = {"slices": list(range(200))}
    result = truncate_json_output(data, max_bytes=100)
    parsed = json.loads(result)
    assert parsed["truncated"] is True
    assert len(result.encode("utf-8")) <= 200  # some margin for truncated key


# --- Integration tests (run CLI) ---

@pytest.fixture
def sample_py_file(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text("def foo():\n" + "\n".join(f"    x{i} = {i}" for i in range(50)) + "\n    return x0\n")
    return str(f)


def test_cli_context_max_lines(sample_py_file, tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "tldr_swinton", "context", "foo", "--project", str(tmp_path), "--max-lines=5"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        lines = result.stdout.strip().split("\n")
        # Should be capped around 5 lines + truncation marker
        assert len(lines) <= 7
        assert "[TRUNCATED:" in result.stdout or len(lines) <= 5


def test_cli_diff_context_max_lines(tmp_path):
    # Set up a git repo for diff-context
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
    f = tmp_path / "a.py"
    f.write_text("def a():\n    pass\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
    f.write_text("def a():\n    return 1\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "change"], cwd=tmp_path, capture_output=True)

    result = subprocess.run(
        [sys.executable, "-m", "tldr_swinton", "diff-context", "--project", str(tmp_path), "--max-lines=5"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        lines = result.stdout.strip().split("\n")
        assert len(lines) <= 7
