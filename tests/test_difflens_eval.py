from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_eval_module():
    path = Path("evals/difflens_eval.py")
    spec = spec_from_file_location("difflens_eval", path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_difflens_eval_exists() -> None:
    assert Path("evals/difflens_eval.py").exists()


def test_fixture_source_size() -> None:
    module = _load_eval_module()
    sources = module._build_multifile_fixture_sources()
    assert isinstance(sources, dict)
    assert len(sources) >= 25
    total_lines = sum(source.count("\n") for source in sources.values())
    assert total_lines >= 5000


def test_multifile_fixture_written(tmp_path: Path) -> None:
    module = _load_eval_module()
    module._write_multifile_repo(tmp_path)
    files = sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".py")
    assert len(files) >= 25


def test_ts_fixture_sources() -> None:
    module = _load_eval_module()
    sources = module._build_ts_fixture_sources()
    assert isinstance(sources, dict)
    assert len(sources) >= 10
    total_lines = sum(source.count("\n") for source in sources.values())
    assert total_lines >= 1500


def test_ts_fixture_written(tmp_path: Path) -> None:
    module = _load_eval_module()
    module._write_ts_repo(tmp_path)
    files = sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".ts")
    assert len(files) >= 10


def test_resolve_py_deps(tmp_path: Path) -> None:
    module = _load_eval_module()
    (tmp_path / "a.py").write_text("import b\n")
    (tmp_path / "b.py").write_text("x = 1\n")
    deps = module._resolve_py_deps(tmp_path, {"a.py"})
    assert "b.py" in deps


def test_resolve_ts_deps(tmp_path: Path) -> None:
    module = _load_eval_module()
    (tmp_path / "a.ts").write_text("import { b } from './b';\n")
    (tmp_path / "b.ts").write_text("export const b = 1;\n")
    deps = module._resolve_ts_deps(tmp_path, {"a.ts"})
    assert "b.ts" in deps


def test_resolve_rs_deps(tmp_path: Path) -> None:
    module = _load_eval_module()
    (tmp_path / "a.rs").write_text("use crate::b::b_helper;\n")
    (tmp_path / "b.rs").write_text("pub fn b_helper() -> i32 { 1 }\n")
    deps = module._resolve_rs_deps(tmp_path, {"a.rs"})
    assert "b.rs" in deps


def test_baseline_includes_deps(tmp_path: Path) -> None:
    module = _load_eval_module()
    (tmp_path / "a.py").write_text("import b\n")
    (tmp_path / "b.py").write_text("x = 1\n")
    tokens_full = module._sum_tokens(tmp_path, {"a.py"})
    tokens_with_deps = module._sum_tokens(tmp_path, {"a.py"}, include_deps=True)
    assert tokens_with_deps > tokens_full


def test_rust_fixture_sources() -> None:
    module = _load_eval_module()
    sources = module._build_rust_fixture_sources()
    assert isinstance(sources, dict)
    assert len(sources) >= 25
    total_lines = sum(source.count("\n") for source in sources.values())
    assert total_lines >= 5000


def test_rust_fixture_written(tmp_path: Path) -> None:
    module = _load_eval_module()
    module._write_rust_repo(tmp_path)
    files = sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".rs")
    assert len(files) >= 25


def test_two_stage_compress_prunes_blocks(tmp_path: Path) -> None:
    from tldr_swinton.api import get_diff_context
    repo = tmp_path / "repo"
    repo.mkdir()
    import subprocess
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "diff-eval@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "DiffEval"], check=True)

    file_path = repo / "app.py"
    file_path.write_text(
        "def foo():\n"
        "    a = 1\n"
        "\n"
        "    b = 2\n"
        "\n"
        "    c = 3\n"
    )
    subprocess.run(["git", "-C", str(repo), "add", "app.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True)

    file_path.write_text(
        "def foo():\n"
        "    a = 1\n"
        "\n"
        "    b = 99\n"
        "\n"
        "    c = 3\n"
    )

    pack = get_diff_context(
        repo,
        base="HEAD",
        head="HEAD",
        budget_tokens=500,
        language="python",
        compress="two-stage",
    )
    slices = pack.get("slices", [])
    assert any(slice_.get("dropped_blocks", 0) > 0 for slice_ in slices)


def test_two_stage_keeps_method_scope_on_single_method_diff(tmp_path: Path) -> None:
    from tldr_swinton.api import get_diff_context
    repo = tmp_path / "repo-scope"
    repo.mkdir()
    import subprocess
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "diff-eval@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "DiffEval"], check=True)

    file_path = repo / "app.py"
    file_path.write_text(
        "class A:\n"
        "    def method_0(self):\n"
        "        value = 1\n"
        "        return value\n"
        "\n"
        "    def method_1(self):\n"
        "        value = 2\n"
        "        return value\n"
    )
    subprocess.run(["git", "-C", str(repo), "add", "app.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True)

    file_path.write_text(
        "class A:\n"
        "    def method_0(self):\n"
        "        value = 1\n"
        "        return value + 1\n"
        "\n"
        "    def method_1(self):\n"
        "        value = 2\n"
        "        return value\n"
    )

    pack = get_diff_context(
        repo,
        base="HEAD",
        head="HEAD",
        budget_tokens=1200,
        language="python",
        compress="two-stage",
    )
    slice_map = {s["id"]: s for s in pack.get("slices", [])}
    method_slice = slice_map.get("app.py:A.method_0")
    assert method_slice and method_slice.get("code")
    assert "method_1" not in method_slice["code"]


def test_two_stage_does_not_pull_neighbor_blocks_under_tight_budget(tmp_path: Path) -> None:
    from tldr_swinton.api import get_diff_context
    repo = tmp_path / "repo-blocks"
    repo.mkdir()
    import subprocess
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "diff-eval@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "DiffEval"], check=True)

    file_path = repo / "app.py"
    file_path.write_text(
        "def foo():\n"
        "    alpha = 1\n"
        "\n"
        "    beta = 2\n"
        "\n"
        "    gamma = 3\n"
    )
    subprocess.run(["git", "-C", str(repo), "add", "app.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True)

    file_path.write_text(
        "def foo():\n"
        "    alpha = 1\n"
        "\n"
        "    beta = 99\n"
        "\n"
        "    gamma = 3\n"
    )

    pack = get_diff_context(
        repo,
        base="HEAD",
        head="HEAD",
        budget_tokens=1000,
        language="python",
        compress="two-stage",
    )
    slice_map = {s["id"]: s for s in pack.get("slices", [])}
    foo_slice = slice_map.get("app.py:foo")
    assert foo_slice and foo_slice.get("code")
    assert "alpha" not in foo_slice["code"]
