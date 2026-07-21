from __future__ import annotations

from _graderlib import prepare, run


prepare()

from tldr_swinton.modules.core.ast_extractor import FunctionInfo  # noqa: E402


def signature(language: str) -> str:
    return FunctionInfo(
        name="target",
        params=["value int"],
        return_type="int",
        docstring=None,
        language=language,
    ).signature()


def go_signature() -> None:
    assert signature("go") == "func target(value int) int"


def python_signature() -> None:
    assert signature("python") == "def target(value int) -> int"


def rust_signature() -> None:
    assert signature("rust") == "fn target(value int) -> int"


run(
    [
        ("Go signature", go_signature),
        ("Python signature", python_signature),
        ("Rust signature", rust_signature),
    ]
)
