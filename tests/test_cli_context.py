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
