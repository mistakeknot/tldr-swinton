from __future__ import annotations

from pathlib import Path
import sys


workspace = Path(sys.argv[1])
sys.path.insert(0, str(workspace / "src"))

from itsdangerous.signer import Signer  # noqa: E402


rotated = Signer(["old-secret", "new-secret"])
old_only = Signer("old-secret")
new_only = Signer("new-secret")

new_signature = rotated.sign("payload")
old_signature = old_only.sign("legacy")
checks = [
    (new_only.validate(new_signature), "new key does not validate new signature"),
    (not old_only.validate(new_signature), "old key validates new signature"),
    (rotated.validate(old_signature), "rotated signer rejected legacy signature"),
    (rotated.unsign(old_signature) == b"legacy", "legacy payload changed"),
]
failures = [message for passed, message in checks if not passed]
print(f"EVAL_TESTS passed={len(checks) - len(failures)} total={len(checks)}")
for failure in failures:
    print(failure)
raise SystemExit(0 if not failures else 1)
