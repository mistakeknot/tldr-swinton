from __future__ import annotations

from _graderlib import prepare, run


prepare()

from tldr_swinton.modules.core.ast_extractor import ImportInfo  # noqa: E402


def from_import() -> None:
    info = ImportInfo(module="collections", names=["Counter", "defaultdict"], is_from=True)
    assert info.statement() == "from collections import Counter, defaultdict"


def plain_import() -> None:
    info = ImportInfo(module="pathlib", names=[], is_from=False)
    assert info.statement() == "import pathlib"


run([("from import commas", from_import), ("plain import", plain_import)])
