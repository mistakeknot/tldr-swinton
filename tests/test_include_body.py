"""Tests for --include-body in ultracompact context output."""

import subprocess
import sys

import pytest


@pytest.fixture
def project_with_functions(tmp_path):
    """Create a small project with function bodies."""
    f = tmp_path / "main.py"
    f.write_text(
        '''
def greet(name: str) -> str:
    """Say hello."""
    message = f"Hello, {name}!"
    return message


def farewell(name: str) -> str:
    """Say goodbye."""
    return f"Goodbye, {name}!"
'''.lstrip()
    )
    return tmp_path


def test_context_include_body_shows_code(project_with_functions):
    """--include-body should include function source code in ultracompact output."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tldr_swinton.cli",
            "context",
            "greet",
            "--project",
            str(project_with_functions),
            "--format",
            "ultracompact",
            "--include-body",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "```" in result.stdout
    assert "message = f\"Hello, {name}!\"" in result.stdout


def test_context_without_include_body_no_code(project_with_functions):
    """Without --include-body, ultracompact output should remain signature-only."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tldr_swinton.cli",
            "context",
            "greet",
            "--project",
            str(project_with_functions),
            "--format",
            "ultracompact",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "greet" in result.stdout
    assert "```" not in result.stdout
    assert "Hello" not in result.stdout
