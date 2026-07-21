from __future__ import annotations

from _graderlib import prepare, run


prepare()

from tldr_swinton.modules.core.change_impact import is_test_file  # noqa: E402


def tests_directory() -> None:
    assert is_test_file("web/__tests__/helper.ts")


def spec_suffix() -> None:
    assert is_test_file("web/helper.spec.ts")


def regular_source() -> None:
    assert not is_test_file("web/helper.ts")


run(
    [
        ("__tests__ directory", tests_directory),
        ("spec suffix", spec_suffix),
        ("regular source", regular_source),
    ]
)
