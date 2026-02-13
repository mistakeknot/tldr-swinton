"""CLI flag presets for token-saving defaults.

Presets expand into multiple flags, reducing cognitive load from 6+ flags to 1.
Names describe output shape (compact/minimal) not intensity (efficient/aggressive).
"""

import hashlib
import os
from pathlib import Path


PRESETS = {
    "compact": {
        "format": "ultracompact",
        "budget": 2000,
        "compress_imports": True,
        "strip_comments": True,
    },
    "minimal": {
        "format": "ultracompact",
        "budget": 1500,
        "compress": "blocks",
        "compress_imports": True,
        "strip_comments": True,
        "type_prune": True,
    },
    "agent": {
        "format": "ultracompact",
        "budget": 4000,
        "compress_imports": True,
        "strip_comments": True,
        "type_prune": True,
    },
    "multi-turn": {
        "format": "cache-friendly",
        "budget": 2000,
        "session_id": "auto",
        "delta": True,
    },
}

PRESET_COMMANDS = {"context", "diff-context", "distill"}


def resolve_auto_session_id(project_root: str = ".") -> str:
    """Generate a stable session ID from CLAUDE_SESSION_ID env var or CWD+HEAD hash."""
    env_id = os.environ.get("CLAUDE_SESSION_ID")
    if env_id:
        return env_id

    import subprocess

    project = Path(project_root).resolve()
    try:
        head = subprocess.run(
            ["git", "-C", str(project), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        head = "no-git"
    raw = f"{project}:{head}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def apply_preset(args, command: str) -> None:
    """Apply preset defaults to parsed args. Explicit flags take precedence. Mutates args in-place."""
    import sys

    preset_name = getattr(args, "preset", None)
    if not preset_name:
        return
    if command not in PRESET_COMMANDS:
        return
    if preset_name not in PRESETS:
        valid = ", ".join(sorted(PRESETS.keys()))
        print(f"Error: Unknown preset '{preset_name}'. Valid presets: {valid}", file=sys.stderr)
        sys.exit(1)

    argv = sys.argv[1:]

    def _is_explicit(key: str) -> bool:
        flag = f"--{key.replace('_', '-')}"
        return any(a == flag or a.startswith(f"{flag}=") for a in argv)

    defaults = PRESETS[preset_name]
    for key, value in defaults.items():
        if _is_explicit(key):
            continue
        if key == "session_id" and value == "auto":
            if getattr(args, "session_id", None) is None:
                args.session_id = resolve_auto_session_id(getattr(args, "project", "."))
            continue
        if command == "distill" and key == "format":
            continue
        setattr(args, key, value)


def emit_preset_hint(command: str, args) -> None:
    """Emit stderr hint when context/diff-context run without --preset."""
    import sys

    if command in ("context", "diff-context") and not getattr(args, "preset", None):
        print("hint: Add --preset compact for 50%+ token savings", file=sys.stderr)
