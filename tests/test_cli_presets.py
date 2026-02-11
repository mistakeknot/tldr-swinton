import subprocess
import sys
from pathlib import Path


def test_preset_compact_expands_on_context(tmp_path: Path) -> None:
    """--preset compact should set format=ultracompact, budget=2000, compress-imports, strip-comments."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def foo():\n    return 1\n")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tldr_swinton.cli",
            "context",
            "foo",
            "--project",
            str(tmp_path),
            "--depth",
            "0",
            "--preset",
            "compact",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "P0=" in result.stdout


def test_preset_minimal_expands_on_diff_context(tmp_path: Path) -> None:
    """--preset minimal should set budget=1500, compress=two-stage, etc."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True, capture_output=True)
    (repo / "app.py").write_text("def foo():\n    return 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)
    (repo / "app.py").write_text("def foo():\n    return 2\n")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tldr_swinton.cli",
            "diff-context",
            "--project",
            str(repo),
            "--preset",
            "minimal",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0


def test_preset_invalid_errors() -> None:
    """Invalid preset should exit with error listing valid presets."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tldr_swinton.cli",
            "context",
            "foo",
            "--project",
            ".",
            "--preset",
            "bogus",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    # argparse will reject "bogus" as not in choices
    assert "invalid choice" in result.stderr.lower() or "bogus" in result.stderr.lower()


def test_preset_not_valid_on_extract(tmp_path: Path) -> None:
    """--preset should not be accepted on extract command."""
    (tmp_path / "app.py").write_text("def foo():\n    return 1\n")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tldr_swinton.cli",
            "extract",
            str(tmp_path / "app.py"),
            "--preset",
            "compact",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0


def test_preset_explicit_override(tmp_path: Path) -> None:
    """Explicit --budget overrides preset's budget."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def foo():\n    return 1\n")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tldr_swinton.cli",
            "context",
            "foo",
            "--project",
            str(tmp_path),
            "--depth",
            "0",
            "--preset",
            "compact",
            "--budget",
            "500",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0


def test_presets_subcommand() -> None:
    """tldrs presets should list available presets."""
    result = subprocess.run(
        [sys.executable, "-m", "tldr_swinton.cli", "presets"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "compact" in result.stdout
    assert "minimal" in result.stdout
    assert "multi-turn" in result.stdout


def test_presets_subcommand_machine() -> None:
    """tldrs presets --machine should output JSON."""
    import json

    result = subprocess.run(
        [sys.executable, "-m", "tldr_swinton.cli", "presets", "--machine"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "compact" in data
    assert "minimal" in data
    assert "multi-turn" in data
