from __future__ import annotations

import argparse

from _graderlib import prepare, run


prepare()

from tldr_swinton.manifest import _classify_flags  # noqa: E402


def boolean_flags() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--enable-cache", action="store_true")
    parser.add_argument("--disable-cache", action="store_false")
    flags = _classify_flags(parser)
    assert flags["boolean"] == ["--disable-cache", "--enable-cache"]
    assert "--disable-cache" not in flags["valued"]


def typed_value() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--count", type=int)
    assert _classify_flags(parser)["valued"]["--count"] == "int"


run([("symmetric boolean flags", boolean_flags), ("typed value", typed_value)])
