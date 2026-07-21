from __future__ import annotations

from _graderlib import prepare, run


prepare()

from tldr_swinton.modules.core.tldrsignore import (  # noqa: E402
    _translate_gitignore_pattern,
)


def recursive_basename() -> None:
    assert _translate_gitignore_pattern("*.log", "services/api") == "services/api/**/*.log"


def anchored_pattern() -> None:
    assert _translate_gitignore_pattern("/generated.py", "services/api") == "services/api/generated.py"


def negated_pattern() -> None:
    assert _translate_gitignore_pattern("!keep.log", "services/api") == "!services/api/**/keep.log"


run(
    [
        ("recursive basename", recursive_basename),
        ("anchored pattern", anchored_pattern),
        ("negated pattern", negated_pattern),
    ]
)
