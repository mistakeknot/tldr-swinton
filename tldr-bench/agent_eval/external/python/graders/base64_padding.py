from __future__ import annotations

import base64
from pathlib import Path
import sys


workspace = Path(sys.argv[1])
sys.path.insert(0, str(workspace / "src"))

from itsdangerous.encoding import base64_decode  # noqa: E402
from itsdangerous.exc import BadData  # noqa: E402


checks = 0
failures: list[str] = []
for value in (b"a", b"ab", b"hello", "無限".encode()):
    encoded = base64.urlsafe_b64encode(value).rstrip(b"=")
    try:
        decoded = base64_decode(encoded)
    except Exception as exc:  # pragma: no cover - failure detail only
        failures.append(f"{encoded!r} raised {type(exc).__name__}: {exc}")
    else:
        if decoded != value:
            failures.append(f"{encoded!r} decoded to {decoded!r}")
    checks += 1

try:
    base64_decode("12345")
except BadData:
    pass
else:
    failures.append("invalid length was accepted")
checks += 1

passed = checks - len(failures)
print(f"EVAL_TESTS passed={passed} total={checks}")
for failure in failures:
    print(failure)
raise SystemExit(0 if not failures else 1)
