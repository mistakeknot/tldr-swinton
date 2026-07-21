from __future__ import annotations

import sys
from types import SimpleNamespace

from _graderlib import prepare, run


prepare()

from tldr_swinton.presets import apply_preset  # noqa: E402


def equals_form_override() -> None:
    args = SimpleNamespace(
        preset="compact",
        budget=99,
        format="text",
        compress_imports=False,
        strip_comments=False,
        project=".",
    )
    previous = sys.argv
    try:
        sys.argv = ["tldrs", "context", "target", "--budget=99"]
        apply_preset(args, "context")
    finally:
        sys.argv = previous
    assert args.budget == 99
    assert args.format == "ultracompact"
    assert args.compress_imports is True


def separate_form_override() -> None:
    args = SimpleNamespace(
        preset="compact",
        budget=101,
        format="text",
        compress_imports=False,
        strip_comments=False,
        project=".",
    )
    previous = sys.argv
    try:
        sys.argv = ["tldrs", "context", "target", "--budget", "101"]
        apply_preset(args, "context")
    finally:
        sys.argv = previous
    assert args.budget == 101
    assert args.format == "ultracompact"


run(
    [
        ("equals-form override", equals_form_override),
        ("separate-form override", separate_form_override),
    ]
)
