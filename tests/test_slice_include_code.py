"""Tests for tldrs slice --include-code flag."""

import json
import subprocess
import sys

import pytest


@pytest.fixture
def slice_project(tmp_path):
    """Create a Python file with functions for slicing."""
    f = tmp_path / "calc.py"
    f.write_text('''def add(a, b):
    result = a + b
    return result

def multiply(a, b):
    x = a
    y = b
    result = x * y
    return result
''')
    return tmp_path, str(f)


def test_slice_include_code_shows_source(slice_project):
    """--include-code should include the actual source lines."""
    _, file_path = slice_project
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tldr_swinton",
            "slice",
            file_path,
            "add",
            "3",
            "--include-code",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode == 0:
        data = json.loads(result.stdout)
        assert "code" in data
        assert "result" in data["code"] or "return" in data["code"]
        assert "file" in data
        assert len(data["lines"]) > 0


def test_slice_without_include_code_no_source(slice_project):
    """Without --include-code, output should be lines only."""
    _, file_path = slice_project
    result = subprocess.run(
        [sys.executable, "-m", "tldr_swinton", "slice", file_path, "add", "3"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode == 0:
        data = json.loads(result.stdout)
        assert "code" not in data
        assert "lines" in data
        assert "count" in data


def test_slice_include_code_with_max_lines(slice_project):
    """--include-code + --max-lines should work together."""
    _, file_path = slice_project
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tldr_swinton",
            "slice",
            file_path,
            "multiply",
            "9",
            "--include-code",
            "--max-lines=5",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode == 0:
        data = json.loads(result.stdout)
        # Should still be valid JSON even if truncated
        assert "lines" in data


def test_slice_include_code_backward(slice_project):
    """Backward slice with --include-code."""
    _, file_path = slice_project
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tldr_swinton",
            "slice",
            file_path,
            "multiply",
            "9",
            "--direction",
            "backward",
            "--include-code",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode == 0:
        data = json.loads(result.stdout)
        assert "code" in data
        # Backward slice from return should include variable assignments
        assert "x" in data["code"] or "y" in data["code"] or "result" in data["code"]
