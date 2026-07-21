import os
from pathlib import Path
import subprocess


def test_install_script_uses_semantic_ollama_extra() -> None:
    script = Path("scripts/install.sh").read_text()

    assert 'SEMANTIC_EXTRA="semantic-ollama"' in script
    assert "command -v ollama" in script
    assert 'uv sync --extra "$SEMANTIC_EXTRA"' in script
    assert 'uv pip install -e ".[${SEMANTIC_EXTRA}]"' in script


def test_generated_launchers_preserve_caller_cwd_and_arguments(tmp_path: Path) -> None:
    install_dir = tmp_path / "install root"
    venv_bin = install_dir / ".venv" / "bin"
    launcher_dir = tmp_path / "user bin"
    caller_dir = tmp_path / "caller repo"
    venv_bin.mkdir(parents=True)
    caller_dir.mkdir()

    fake_entrypoint = "#!/usr/bin/env bash\nprintf '%s\\n' \"$PWD\"\nprintf '<%s>\\n' \"$@\"\n"
    for command in ("tldrs", "tldr-swinton", "tldr-mcp"):
        entrypoint = venv_bin / command
        entrypoint.write_text(fake_entrypoint)
        entrypoint.chmod(0o755)

    subprocess.run(
        ["bash", "scripts/install-launchers.sh", str(install_dir), str(launcher_dir)],
        check=True,
        cwd=Path.cwd(),
    )

    result = subprocess.run(
        [str(launcher_dir / "tldrs"), "context", "symbol with spaces"],
        check=True,
        cwd=caller_dir,
        text=True,
        capture_output=True,
    )

    assert result.stdout.splitlines() == [
        str(caller_dir),
        "<context>",
        "<symbol with spaces>",
    ]
    assert os.access(launcher_dir / "tldrs", os.X_OK)


def test_installer_uses_launchers_without_swallowing_sync_failures() -> None:
    script = Path("scripts/install.sh").read_text()

    assert "set -euo pipefail" in script
    assert 'scripts/install-launchers.sh "$INSTALL_DIR" "$HOME/.local/bin"' in script
    assert "alias tldrs='cd" not in script
    assert 'uv sync --extra "$SEMANTIC_EXTRA" 2>&1 | grep -v "^  " || true' not in script


def test_uninstaller_removes_managed_launchers() -> None:
    script = Path("scripts/uninstall.sh").read_text()

    assert "for command in tldrs tldr-swinton tldr-mcp" in script
    assert 'launcher="$HOME/.local/bin/$command"' in script
