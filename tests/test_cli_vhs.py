import os
import subprocess
import sys
from pathlib import Path


def test_cli_vhs_put_uses_repo_local_store(tmp_path):
    project_root = tmp_path
    (project_root / "src").mkdir()
    (project_root / "src" / "a.py").write_text("def a():\n    return 1\n")

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tldr_swinton.cli",
            "context",
            "a",
            "--project",
            str(project_root),
            "--output",
            "vhs",
        ],
        capture_output=True,
        text=True,
        cwd=repo_root,
        env=env,
    )
    assert result.returncode == 0
    assert (project_root / ".tldrs" / "tldrs_state.db").exists()
