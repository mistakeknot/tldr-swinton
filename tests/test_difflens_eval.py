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
