import subprocess
import sys
from pathlib import Path


def test_cli_context_output(tmp_path: Path) -> None:
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
            "--format",
            "ultracompact",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "P0=" in result.stdout


def test_cli_diff_context_compress(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "diff-eval@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "DiffEval"], check=True)
    (repo / "app.py").write_text("def foo():\n    return 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "app.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True)
    (repo / "app.py").write_text("def foo():\n    return 2\n")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tldr_swinton.cli",
            "diff-context",
            "--project",
            str(repo),
            "--compress",
            "two-stage",
            "--budget",
            "200",
            "--lang",
            "python",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip()
