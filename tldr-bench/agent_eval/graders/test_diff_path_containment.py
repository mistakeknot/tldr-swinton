from __future__ import annotations

import tempfile
from pathlib import Path

from _graderlib import prepare, run


prepare()

from tldr_swinton.modules.core.path_utils import (  # noqa: E402
    PathTraversalError,
    _validate_path_containment,
)


def safe_normalization() -> None:
    with tempfile.TemporaryDirectory() as raw:
        base = Path(raw)
        safe = base / "nested/../inside.py"
        assert _validate_path_containment(str(safe), str(base)) == (base / "inside.py").resolve()


def outside_traversal() -> None:
    with tempfile.TemporaryDirectory() as raw:
        base = Path(raw) / "base"
        base.mkdir()
        unsafe = base / "nested/../../escape.py"
        try:
            _validate_path_containment(str(unsafe), str(base))
        except PathTraversalError:
            return
        raise AssertionError("outside traversal was accepted")


run([("safe normalization", safe_normalization), ("outside traversal", outside_traversal)])
