from pathlib import Path

import warnings

from tldr_swinton.api import get_relevant_context


def test_entry_point_disambiguates_to_single_symbol(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def run():\n    return 1\n")
    (tmp_path / "b.py").write_text("def run():\n    return 2\n")

    ctx = get_relevant_context(tmp_path, "run", depth=0)
    assert len(ctx.functions) == 1
    func = ctx.functions[0]
    assert func.file.endswith("a.py")


def test_entry_point_disambiguation_emits_warning(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def run():\n    return 1\n")
    (tmp_path / "b.py").write_text("def run():\n    return 2\n")

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        get_relevant_context(tmp_path, "run", depth=0)

    assert any("Ambiguous entry point 'run'" in str(w.message) for w in captured)


def test_entry_point_disambiguation_can_be_suppressed(tmp_path, monkeypatch) -> None:
    (tmp_path / "a.py").write_text("def run():\n    return 1\n")
    (tmp_path / "b.py").write_text("def run():\n    return 2\n")

    monkeypatch.setenv("TLDRS_NO_WARNINGS", "1")

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        get_relevant_context(tmp_path, "run", depth=0)

    assert not captured
