from __future__ import annotations

import sys
import traceback
from collections.abc import Callable
from pathlib import Path


Case = tuple[str, Callable[[], None]]


def prepare() -> Path:
    if len(sys.argv) != 2:
        raise SystemExit("usage: grader.py WORKSPACE")
    workspace = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(workspace / "src"))
    return workspace


def run(cases: list[Case]) -> None:
    passed = 0
    for name, case in cases:
        try:
            case()
        except Exception:
            print(f"FAIL {name}")
            traceback.print_exc()
        else:
            passed += 1
            print(f"PASS {name}")
    print(f"EVAL_TESTS passed={passed} total={len(cases)}")
    raise SystemExit(0 if passed == len(cases) else 1)
