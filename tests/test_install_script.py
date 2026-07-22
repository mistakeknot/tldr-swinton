import os
from pathlib import Path
import subprocess


def _write_version_checker(path: Path, marker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'#!/bin/bash\nprintf \'%s\\n\' "{marker}:$*"\n')
    path.chmod(0o755)


def _copy_version_wrapper(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(Path("scripts/check-versions.sh").read_text())
    path.chmod(0o755)


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


def test_check_versions_uses_explicit_shared_checker_override(tmp_path: Path) -> None:
    wrapper = tmp_path / "standalone" / "scripts" / "check-versions.sh"
    checker = tmp_path / "custom" / "intercheck-versions.sh"
    _copy_version_wrapper(wrapper)
    _write_version_checker(checker, "override")
    environment = dict(os.environ)
    environment["TLDRS_INTERCHECK_VERSIONS"] = str(checker)

    result = subprocess.run(
        [str(wrapper), "--strict", "argument with spaces"],
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "override:--strict argument with spaces"


def test_check_versions_discovers_sibling_sylveste_checkout(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    wrapper = projects / "tldr-swinton" / "scripts" / "check-versions.sh"
    checker = projects / "Sylveste" / "scripts" / "intercheck-versions.sh"
    _copy_version_wrapper(wrapper)
    _write_version_checker(checker, "sibling")

    result = subprocess.run(
        [str(wrapper), "--strict"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "sibling:--strict"


def test_check_versions_preserves_historical_monorepo_layout(tmp_path: Path) -> None:
    sylveste = tmp_path / "Sylveste"
    wrapper = sylveste / "os" / "tldr-swinton" / "scripts" / "check-versions.sh"
    checker = sylveste / "scripts" / "intercheck-versions.sh"
    _copy_version_wrapper(wrapper)
    _write_version_checker(checker, "monorepo")

    result = subprocess.run(
        [str(wrapper)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "monorepo:"


def test_tracked_plugin_tree_contains_no_gitlinks() -> None:
    result = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        check=True,
        capture_output=True,
    )
    gitlinks: list[str] = []
    for raw_entry in result.stdout.split(b"\0"):
        if not raw_entry:
            continue
        metadata, raw_path = raw_entry.split(b"\t", 1)
        if metadata.split()[0] == b"160000":
            gitlinks.append(raw_path.decode())

    assert gitlinks == [], (
        "Claude's tracked-tree plugin cache cannot package gitlinks: "
        + ", ".join(gitlinks)
    )


def test_post_bump_applies_target_version_before_reinstalling_cli() -> None:
    script = Path("scripts/post-bump.sh").read_text()

    version_update = script.index('uv version "$TARGET_VERSION" --no-sync')
    cli_install = script.index("uv tool install --force .")

    assert 'TARGET_VERSION="${1:?target version is required}"' in script
    assert version_update < cli_install
