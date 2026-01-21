"""Capsule: Replayable command execution records.

A capsule captures everything needed to understand and reproduce a command execution:
- What command was run
- Where it was run (working directory)
- What environment was relevant
- What it output (stdout/stderr)
- Whether it succeeded (exit code)
- How long it took
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Environment variables to capture (allowlist approach for security/noise reduction)
ENV_ALLOWLIST = [
    "PATH",
    "PYTHONPATH",
    "VIRTUAL_ENV",
    "CONDA_PREFIX",
    "NODE_PATH",
    "GOPATH",
    "CARGO_HOME",
    "RUSTUP_HOME",
    "HOME",
    "USER",
    "SHELL",
    "LANG",
    "LC_ALL",
    "TERM",
]


@dataclass
class Capsule:
    """A replayable record of a command execution."""

    id: str
    command: str
    cwd: str
    env_fingerprint: str
    exit_code: int
    stdout: str
    stderr: str
    started_at: datetime
    duration_ms: int
    artifacts: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> Capsule:
        """Create Capsule from database dict."""
        started_at = data["started_at"]
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)

        return cls(
            id=data["id"],
            command=data["command"],
            cwd=data["cwd"],
            env_fingerprint=data["env_fingerprint"],
            exit_code=data["exit_code"],
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            started_at=started_at,
            duration_ms=data["duration_ms"],
            artifacts=data.get("artifacts", []),
        )


def compute_env_fingerprint(env: dict[str, str] | None = None) -> str:
    """Compute a fingerprint of relevant environment variables.

    Args:
        env: Environment dict. Uses os.environ if not specified.

    Returns:
        Short hash of relevant env vars.
    """
    if env is None:
        env = dict(os.environ)

    # Extract relevant vars
    relevant = {k: env.get(k, "") for k in ENV_ALLOWLIST if k in env}

    # Sort for determinism and hash
    content = "\n".join(f"{k}={v}" for k, v in sorted(relevant.items()))
    return hashlib.sha256(content.encode()).hexdigest()[:12]


def compute_capsule_id(
    command: str,
    cwd: str,
    env_fingerprint: str,
    started_at: datetime,
) -> str:
    """Compute content-addressed capsule ID.

    Args:
        command: The command string.
        cwd: Working directory.
        env_fingerprint: Environment fingerprint.
        started_at: When the command started.

    Returns:
        Short content-addressed ID.
    """
    content = f"{command}\n{cwd}\n{env_fingerprint}\n{started_at.isoformat()}"
    return hashlib.sha256(content.encode()).hexdigest()[:12]


def capture(
    command: str,
    cwd: str | Path | None = None,
    shell: bool = True,
    timeout: float | None = None,
) -> Capsule:
    """Capture a command execution.

    Args:
        command: Command string to execute.
        cwd: Working directory. Uses current directory if not specified.
        shell: Whether to run via shell (default True).
        timeout: Optional timeout in seconds.

    Returns:
        Capsule containing the execution record.
    """
    # Resolve working directory
    if cwd is None:
        cwd = Path.cwd()
    elif isinstance(cwd, str):
        cwd = Path(cwd)
    cwd = cwd.resolve()

    # Compute env fingerprint before running
    env_fingerprint = compute_env_fingerprint()

    # Run the command
    started_at = datetime.now(timezone.utc)
    start_time = time.perf_counter()

    try:
        result = subprocess.run(
            command,
            shell=shell,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as e:
        # Capture partial output on timeout
        exit_code = -1
        stdout = e.stdout.decode("utf-8", errors="replace") if e.stdout else ""
        stderr = (
            e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
        ) + f"\n[TIMEOUT after {timeout}s]"
    except Exception as e:
        exit_code = -1
        stdout = ""
        stderr = f"[ERROR: {type(e).__name__}: {e}]"

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    # Compute capsule ID
    capsule_id = compute_capsule_id(command, str(cwd), env_fingerprint, started_at)

    return Capsule(
        id=capsule_id,
        command=command,
        cwd=str(cwd),
        env_fingerprint=env_fingerprint,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        started_at=started_at,
        duration_ms=duration_ms,
    )


def replay_command(capsule: Capsule, dry_run: bool = False) -> Capsule | None:
    """Re-run a captured command.

    Args:
        capsule: The capsule to replay.
        dry_run: If True, just return what would be run without running it.

    Returns:
        New Capsule with the replay results, or None if dry_run.
    """
    if dry_run:
        return None

    return capture(
        command=capsule.command,
        cwd=capsule.cwd,
    )
