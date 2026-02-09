---
title: "Plugin Version Drift Between Repo and Marketplace Breaks Loading"
category: build-errors
tags: [plugin, version, marketplace, cache, claude-code, publishing]
module: .claude-plugin/plugin.json
symptoms:
  - "Path not found: commands/find.md"
  - "Path not found: skills/tldrs-session-start"
  - "Path not found: hooks/hooks.json"
  - "Status: failed to load"
  - "plugin installs but shows 'failed to load' in plugin list"
severity: high
date_solved: 2026-02-08
---

## Problem

After installing `tldr-swinton` via `claude plugin install`, the plugin shows "failed to load" with path-not-found errors for every command, skill, and hook:

```
❯ tldr-swinton@interagency-marketplace
    Version: 0.5.2
    Status: ✘ failed to load
    Error: Path not found: .../0.5.1/commands/find.md (commands)
    Error: Path not found: .../0.5.1/skills/tldrs-session-start (skills)
    Error: Path not found: .../0.5.1/hooks/hooks.json (hooks)
```

The installed version says `0.5.2` but the error paths reference `0.5.1`.

## Root Cause Analysis

### Three Version Locations Must Stay Synced

The plugin has three version declarations that must always match:

| File | Field | What reads it |
|------|-------|---------------|
| `pyproject.toml` | `version = "X.Y.Z"` | Python packaging, `tldrs --version` |
| `.claude-plugin/plugin.json` | `"version": "X.Y.Z"` | Claude Code plugin loader |
| `interagency-marketplace/.claude-plugin/marketplace.json` | `"version": "X.Y.Z"` | `claude plugin install` |

### What Happened

1. `pyproject.toml` and `plugin.json` were bumped to `0.5.2`
2. `marketplace.json` was **not** updated — still at `0.5.1`
3. `claude plugin install` read marketplace.json, cached the repo under a `0.5.1` directory
4. But the repo's `plugin.json` declared `0.5.2`
5. Claude Code tried to resolve paths using the version from `plugin.json` (`0.5.2`) against the cache directory named from the marketplace version (`0.5.1`)
6. Path mismatch caused every command, skill, and hook to fail to load

### Cache Directory Structure

Claude Code caches plugins at:
```
~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/
```

When the marketplace version doesn't match the repo's plugin.json version, the cache directory name and the internal version reference diverge, breaking all relative path resolution.

## Working Solution

### Immediate Fix (Clean Reinstall)

```bash
# 1. Uninstall the broken plugin
claude plugin uninstall tldr-swinton

# 2. Clear stale cache entries
rm -rf ~/.claude/plugins/cache/interagency-marketplace/tldr-swinton

# 3. Also clean any orphaned temp directories
rm -rf ~/.claude/plugins/cache/temp_git_*

# 4. Sync marketplace version to match repo
# Edit interagency-marketplace/.claude-plugin/marketplace.json
# Set version to match pyproject.toml and plugin.json

# 5. Push marketplace update
cd interagency-marketplace && git add . && git commit -m "chore: sync version" && git push

# 6. Reinstall
claude plugin install tldr-swinton

# 7. Verify
claude plugin list | grep -A3 tldr-swinton
# Should show: Status: ✔ enabled
```

### Root Fix (Prevent Drift)

The `scripts/check-versions.sh` pre-commit hook already validates `pyproject.toml` vs `plugin.json`. Extend the publishing runbook to always update all three:

```bash
# Publishing checklist (all three must be bumped together)
edit pyproject.toml                                    # version = "X.Y.Z"
edit .claude-plugin/plugin.json                        # "version": "X.Y.Z"
edit ../interagency-marketplace/.claude-plugin/marketplace.json  # "version": "X.Y.Z"
```

## Prevention Strategy

### For This Project
1. Always bump all three version locations in a single commit or PR
2. The pre-commit hook catches pyproject.toml ↔ plugin.json drift
3. Add marketplace.json to the mental model — it's the third leg of the stool
4. After pushing the repo, **always** update and push the marketplace

### General Guidelines
- **Treat marketplace.json as part of the release** — not a separate step you might forget
- **Version in plugin.json is authoritative** — Claude Code reads it at load time
- **Version in marketplace.json controls cache directory naming** — must match plugin.json
- **Stale cache directories cause phantom failures** — when debugging, check `~/.claude/plugins/cache/` first
- **`temp_git_*` directories accumulate** — clean them periodically; they're failed install artifacts

### Testing After Version Bump

```bash
# After bumping version:
claude plugin uninstall tldr-swinton
claude plugin install tldr-swinton
claude plugin list | grep -A3 tldr-swinton
# Must show: Status: ✔ enabled (not "failed to load")
```

## Related Issues

- Ghost `tldrs` cache entry (see companion doc: `stale-plugin-cache-ghost-entries.md`)
- LFS submodule blocking install (see: `lfs-submodule-blocks-plugin-install.md`)
- `temp_git_*` cache pollution from repeated failed installs

## See Also

- `.claude-plugin/plugin.json` — Plugin manifest (version source of truth)
- `scripts/check-versions.sh` — Pre-commit version sync check
- `CLAUDE.md` — Publishing runbook with version locations table
