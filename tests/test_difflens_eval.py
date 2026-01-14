from pathlib import Path


def test_difflens_eval_exists() -> None:
    assert Path("evals/difflens_eval.py").exists()
