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
    source = module._build_fixture_source(300)
    assert source.count("\n") >= 300
