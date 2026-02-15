---
module: Beads
date: 2026-02-13
problem_type: workflow_issue
component: cli
symptoms:
  - "bd commands (ready, list, show, etc.) hang indefinitely with no output"
  - "bd.sock.startlock file contains PID of a dead process"
root_cause: config_error
resolution_type: workflow_improvement
severity: high
tags: [beads, daemon, stale-lock, hang, bd-cli, unix-socket, ipc]
---

# Troubleshooting: Beads `bd` Commands Hang Indefinitely Due to Stale Startlock

## Problem
All `bd` commands (`bd ready`, `bd list`, `bd show`, etc.) hang indefinitely with no output. The beads daemon appears to be running but the CLI client cannot connect to it.

## Environment
- Module: Beads (bd CLI v0.49.6)
- Affected Component: bd daemon IPC (Unix socket + startlock)
- Date: 2026-02-13

## Symptoms
- `bd ready` hangs with no output (no error, no timeout)
- `.beads/bd.sock.startlock` file exists and contains a PID
- The PID in `bd.sock.startlock` belongs to a dead process (`kill -0 <pid>` returns "No such process")
- `.beads/daemon.pid` may reference a live but unresponsive daemon process
- `.beads/bd.sock` Unix socket file exists but connections to it stall

## What Didn't Work

**Attempted Solution 1:** Removing only the startlock file
- **Why it failed:** The daemon process itself was also stale/unresponsive. Even with the startlock removed, the existing daemon couldn't handle connections through the old socket.

## Solution

Full daemon reset: kill the daemon, remove all socket and lock files, then let `bd` spawn a fresh daemon on next invocation.

**Commands run:**
```bash
# 1. Check if startlock PID is alive
cat .beads/bd.sock.startlock
# Output: 3222713
kill -0 3222713  # "No such process" = stale lock confirmed

# 2. Get daemon PID
cat .beads/daemon.pid
# Output: 2482903

# 3. Kill daemon and clean all socket/lock files
kill 2482903; sleep 1; kill -9 2482903 2>/dev/null
rm -f .beads/bd.sock .beads/bd.sock.startlock .beads/daemon.pid .beads/daemon.lock

# 4. Verify — next bd command spawns fresh daemon
bd ready  # Works immediately
```

**One-liner for quick recovery:**
```bash
cat .beads/daemon.pid 2>/dev/null | xargs -r kill 2>/dev/null; sleep 1; rm -f .beads/bd.sock .beads/bd.sock.startlock .beads/daemon.pid .beads/daemon.lock && echo "Beads daemon reset — next bd command will spawn fresh"
```

## Why This Works

1. **Root cause:** Beads uses a daemon architecture for performance. The `bd` CLI connects to a persistent daemon via a Unix socket (`.beads/bd.sock`). A `bd.sock.startlock` file acts as a mutex during daemon startup — it contains the PID of the process currently starting the daemon. If that process crashes or is killed before releasing the lock (e.g., a Claude Code session ends abruptly), the lockfile persists with a dead PID. Subsequent `bd` invocations see the lockfile and wait indefinitely for the "starting" process to finish — but it never will.

2. **Why full cleanup is needed:** Three files form the daemon's IPC state: `bd.sock` (the Unix socket), `bd.sock.startlock` (startup mutex), `daemon.pid` (running daemon PID), and `daemon.lock` (daemon metadata). If the daemon itself became unresponsive (accepting connections on the socket but not processing them), just removing the startlock isn't enough — the stale socket must also go. Removing all four files and killing the daemon process ensures a completely clean state.

3. **Why `bd` recovers:** The `bd` CLI auto-spawns a new daemon when it finds no socket file. By removing all state files, the next `bd` command starts fresh with a new daemon, new socket, and no stale locks.

## Prevention

- **After killing Claude Code sessions:** If a session is force-killed (rather than cleanly exited), check `bd ready` in the next session. If it hangs for >5 seconds, run the one-liner above.
- **Diagnostic check:** `kill -0 $(cat .beads/bd.sock.startlock 2>/dev/null) 2>/dev/null || echo "STALE LOCK"` — add this to session startup hooks if the problem recurs frequently.
- **Upstream fix consideration:** The beads daemon could implement lock expiration (e.g., check if startlock PID is alive before waiting) or use `flock` with timeout instead of PID-based locking.

## Related Issues
No related issues documented yet.
