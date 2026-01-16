import subprocess


def test_cli_contextpack_command(tmp_path) -> None:
    (tmp_path / "m.py").write_text("def foo():\n    return 1\n")
    result = subprocess.run(
        ["tldrs", "context", "foo", "--project", str(tmp_path), "--format", "ultracompact"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
