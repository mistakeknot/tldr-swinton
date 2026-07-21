from __future__ import annotations

from _graderlib import prepare, run


workspace = prepare()

from tldr_swinton.modules.core.change_impact import get_module_name  # noqa: E402


def package_initializer() -> None:
    path = workspace / "src/example/__init__.py"
    assert get_module_name(str(path), str(workspace)) == "src.example"


def ordinary_module() -> None:
    path = workspace / "src/example/service.py"
    assert get_module_name(str(path), str(workspace)) == "src.example.service"


def root_initializer() -> None:
    path = workspace / "__init__.py"
    assert get_module_name(str(path), str(workspace)) is None


run(
    [
        ("package initializer", package_initializer),
        ("ordinary module", ordinary_module),
        ("root initializer", root_initializer),
    ]
)
