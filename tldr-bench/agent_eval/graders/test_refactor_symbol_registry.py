from __future__ import annotations

import tempfile
from pathlib import Path

from _graderlib import prepare, run


prepare()

from tldr_swinton.modules.core.symbol_registry import SymbolRegistry  # noqa: E402


temporary_directory = tempfile.TemporaryDirectory()
sample_root = Path(temporary_directory.name)
sample = sample_root / "agent_eval_registry_sample.py"
sample.write_text("def target(value: int) -> int:\n    return value + 1\n")
registry = SymbolRegistry(sample_root)


def named_lookup() -> None:
    info = registry.get("agent_eval_registry_sample.py:target")
    assert info.file == "agent_eval_registry_sample.py"
    assert info.signature == "def target(value: int) -> int"
    assert info.lines is not None and info.lines[0] > 0
    assert "return value + 1" in (info.code or "")


def missing_lookup() -> None:
    try:
        registry.get("agent_eval_registry_sample.py:missing")
    except KeyError:
        return
    raise AssertionError("missing symbol did not raise KeyError")


run([("named lookup", named_lookup), ("missing lookup", missing_lookup)])
