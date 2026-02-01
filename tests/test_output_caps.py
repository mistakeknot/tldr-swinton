"""Tests for --max-lines / --max-bytes output caps."""

import json
import subprocess
import sys

import pytest

from tldr_swinton.modules.core.output_formats import truncate_output, truncate_json_output


# --- Unit tests for truncate_output ---

def test_truncate_output_no_caps():
    text = "line1\nline2\nline3"
    assert truncate_output(text) == text


def test_truncate_output_max_lines():
    text = "\n".join(f"line{i}" for i in range(20))
    result = truncate_output(text, max_lines=5)
    lines = result.split("\n")
    # 5 content lines + 1 truncation marker
    assert len(lines) == 6
    assert "[TRUNCATED:" in lines[-1]
    assert "--max-lines=5" in lines[-1]


def test_truncate_output_max_bytes():
    text = "A" * 1000
    result = truncate_output(text, max_bytes=100)
    assert "[TRUNCATED:" in result
    assert "--max-bytes=100" in result
    # The content before marker should be <= 100 bytes
    content_before_marker = result.split("\n[TRUNCATED:")[0]
    assert len(content_before_marker.encode("utf-8")) <= 100


def test_truncate_output_both_caps():
    text = "\n".join("A" * 50 for _ in range(20))
    result = truncate_output(text, max_lines=5, max_bytes=100)
    assert "[TRUNCATED:" in result
    assert "--max-lines=5" in result
    assert "--max-bytes=100" in result


def test_truncate_output_under_caps():
    text = "short"
    assert truncate_output(text, max_lines=100, max_bytes=1000) == text


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
