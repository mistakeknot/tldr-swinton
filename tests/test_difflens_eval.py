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
