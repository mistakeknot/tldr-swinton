"""Tests for --machine flag across all commands.

Verifies that --machine flag returns consistent JSON schema:
- Success: {"success": true, "result": <data>}
- Error: {"error": true, "code": "...", "message": "..."}
"""

import json
import subprocess
from pathlib import Path

import pytest


def run_tldrs(*args: str, cwd: Path | None = None, machine: bool = False) -> tuple[int, str, str]:
    """Run tldrs command and return (returncode, stdout, stderr).

    If machine=True, --machine flag is inserted before the command.
    """
    cmd = ["uv", "run", "tldrs"]
    if machine:
        cmd.append("--machine")
    cmd.extend(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result.returncode, result.stdout, result.stderr


def test_tree_machine_flag(tmp_path: Path):
    """Test tree command with --machine flag."""
    (tmp_path / "test.py").write_text("# test")

    code, stdout, stderr = run_tldrs("tree", str(tmp_path), machine=True)

    assert code == 0
    data = json.loads(stdout)
    assert data.get("success") is True
    assert "result" in data


def test_structure_machine_flag(tmp_path: Path):
    """Test structure command with --machine flag."""
    (tmp_path / "test.py").write_text("def foo(): pass")

    code, stdout, stderr = run_tldrs("structure", str(tmp_path), "--lang", "python", machine=True)

    assert code == 0
    data = json.loads(stdout)
    assert data.get("success") is True
    assert "result" in data


def test_search_machine_flag(tmp_path: Path):
    """Test search command with --machine flag."""
    (tmp_path / "test.py").write_text("def hello(): pass")

    code, stdout, stderr = run_tldrs("search", "hello", str(tmp_path), machine=True)

    assert code == 0
    data = json.loads(stdout)
    assert data.get("success") is True
    assert "result" in data


def test_extract_machine_flag(tmp_path: Path):
    """Test extract command with --machine flag."""
    (tmp_path / "test.py").write_text("def foo(): pass")

    code, stdout, stderr = run_tldrs("extract", str(tmp_path / "test.py"), machine=True)

    assert code == 0
    data = json.loads(stdout)
    assert data.get("success") is True
    assert "result" in data


def test_calls_machine_flag(tmp_path: Path):
    """Test calls command with --machine flag."""
    (tmp_path / "test.py").write_text("def a(): b()\ndef b(): pass")

    code, stdout, stderr = run_tldrs("calls", str(tmp_path), "--lang", "python", machine=True)

    assert code == 0
    data = json.loads(stdout)
    assert data.get("success") is True
    assert "result" in data


def test_machine_flag_error_format(tmp_path: Path):
    """Test that errors return proper machine format."""
    # Try to extract a non-existent file
    code, stdout, stderr = run_tldrs("extract", str(tmp_path / "nonexistent.py"), machine=True)

    assert code == 1
    data = json.loads(stdout)
    assert data.get("error") is True
    assert "code" in data
    assert "message" in data


def test_context_machine_flag_ambiguous(tmp_path: Path):
    """Test that ambiguous entry returns error format."""
    (tmp_path / "a.py").write_text("def dup(): pass")
    (tmp_path / "b.py").write_text("def dup(): pass")

    code, stdout, stderr = run_tldrs(
        "context", "dup",
        "--project", str(tmp_path),
        "--lang", "python",
        machine=True,
    )

    assert code == 0
    data = json.loads(stdout)
    # Ambiguous is returned as error format
    assert data.get("error") is True
    assert data.get("code") == "TLDRS_ERR_AMBIGUOUS"
    assert "candidates" in data


def test_slice_machine_flag(tmp_path: Path):
    """Test slice command with --machine flag."""
    (tmp_path / "test.py").write_text("def foo():\n    x = 1\n    return x")

    code, stdout, stderr = run_tldrs(
        "slice", str(tmp_path / "test.py"), "foo", "3", machine=True
    )

    assert code == 0
    data = json.loads(stdout)
    assert data.get("success") is True
    assert "result" in data
    assert "lines" in data["result"]


def test_imports_machine_flag(tmp_path: Path):
    """Test imports command with --machine flag."""
    (tmp_path / "test.py").write_text("import os\nfrom pathlib import Path")

    code, stdout, stderr = run_tldrs(
        "imports", str(tmp_path / "test.py"), machine=True
    )

    assert code == 0
    data = json.loads(stdout)
    assert data.get("success") is True
    assert "result" in data
