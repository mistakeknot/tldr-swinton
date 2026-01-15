from pathlib import Path

from tldr_swinton.workspace import iter_workspace_files


def test_workspace_iter_respects_tldrsignore(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("def a():\n    return 1\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignore.js").write_text("console.log('x')\n")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "ignore.py").write_text("def b():\n    return 2\n")
    (tmp_path / ".tldrsignore").write_text("node_modules/\nbuild/\n")

    files = list(iter_workspace_files(tmp_path, extensions={".py"}))
    rels = {str(p.relative_to(tmp_path)) for p in files}

    assert "src/a.py" in rels
    assert "build/ignore.py" not in rels


def test_workspace_iter_respects_legacy_tldrignore(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("def a():\n    return 1\n")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "ignore.py").write_text("def b():\n    return 2\n")
    (tmp_path / ".tldrignore").write_text("vendor/\n")

    files = list(iter_workspace_files(tmp_path, extensions={".py"}))
    rels = {str(p.relative_to(tmp_path)) for p in files}

    assert "src/a.py" in rels
    assert "vendor/ignore.py" not in rels


def test_workspace_iter_respects_nested_gitignore(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / ".gitignore").write_text("*.log\n")
    (tmp_path / "pkg" / "keep.py").write_text("print('ok')\n")
    (tmp_path / "pkg" / "skip.log").write_text("nope\n")
    (tmp_path / "pkg" / "nested").mkdir()
    (tmp_path / "pkg" / "nested" / "skip2.log").write_text("nope\n")

    files = list(
        iter_workspace_files(
            tmp_path,
            extensions={".py", ".log"},
            respect_gitignore=True,
        )
    )
    rels = {str(p.relative_to(tmp_path)) for p in files}

    assert "pkg/keep.py" in rels
    assert "pkg/skip.log" not in rels
    assert "pkg/nested/skip2.log" not in rels
