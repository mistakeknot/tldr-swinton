import os
import shutil
import subprocess
import sys

VARIANT_ID = "cassette"


def _resolve_tldrs_cmd() -> list[str]:
    if shutil.which("tldrs"):
        return ["tldrs"]
    return [sys.executable, "-m", "tldr_swinton.cli"]


def build_context(task: dict) -> str:
    entry = task.get("entry", "")
    if not entry:
        raise ValueError("task.entry is required")

    from . import resolve_project_root

    project = resolve_project_root(task)
    depth = task.get("depth", 2)
    language = task.get("language", "python")
    budget = task.get("budget")
    fmt = task.get("context_format", "text")

    cmd = _resolve_tldrs_cmd() + [
        "context",
        entry,
        "--project",
        str(project),
        "--depth",
        str(depth),
        "--format",
        fmt,
        "--lang",
        language,
        "--output",
        "vhs",
    ]
    if budget is not None:
        cmd += ["--budget", str(budget)]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "tldrs context failed")

    return result.stdout.strip()
