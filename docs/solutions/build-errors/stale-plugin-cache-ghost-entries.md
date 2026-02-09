---
title: "Stale Plugin Cache Creates Ghost Entries and Load Failures"
category: build-errors
tags: [plugin, cache, claude-code, ghost, cleanup, installation]
module: ~/.claude/plugins/cache/
symptoms:
  - "duplicate plugin names in plugin list"
  - "plugin shows enabled but commands don't work"
  - "old plugin name appears alongside new name"
  - "temp_git_* directories accumulate in cache"
  - "plugin cache contains full repo instead of .claude-plugin/ contents"
severity: medium
date_solved: 2026-02-08
---

## Problem

After multiple install/uninstall cycles or plugin renames, the plugin cache accumulates stale entries:

1. **Ghost plugins** — Old entries (e.g., `tldrs`) remain in the cache even after the plugin was renamed to `tldr-swinton`. They have no `plugin.json` at the expected location and never load, but cause confusion.

2. **`temp_git_*` directories** — Failed installs leave behind temporary git clone directories that are never cleaned up. Over time these accumulate (16+ directories observed).

3. **Full repo in cache** — Instead of just the `.claude-plugin/` directory contents, the entire repository gets cached (pyproject.toml, src/, tests/, etc.), wasting disk space.

## Root Cause Analysis

### Ghost Entries

When a plugin is renamed (e.g., `tldrs` → `tldr-swinton`):
- The old cache directory remains at `~/.claude/plugins/cache/interagency-marketplace/tldrs/`
- `claude plugin uninstall tldrs` fails because the name doesn't match any entry in `installed_plugins.json`
- The cache directory persists indefinitely
- **Worst case:** The old name persists in `~/.claude/settings.json` under `enabledPlugins` as `"tldrs@interagency-marketplace": true`. This causes a "failed to load" error on every session start, even after the cache directory is deleted. `claude plugin uninstall` does NOT clean `enabledPlugins` — you must manually edit `settings.json` to remove the stale key.

### temp_git Accumulation

Claude Code's plugin installer creates temporary git clone directories:
```
~/.claude/plugins/cache/temp_git_<timestamp>_<random>/
```

When installation fails (network error, LFS budget exceeded, etc.), these directories are not cleaned up. Each failed attempt adds another ~50-100MB directory.

### Full Repo Caching

The plugin installer clones the entire repository into the cache. The `.claude-plugin/` directory is used for loading, but everything else (src/, tests/, docs/, benchmarks/) is also stored. For tldr-swinton, this means ~50MB of Python source, test fixtures, and documentation cached alongside the ~50KB of actual plugin files.

## Working Solution

### Manual Cleanup

```bash
# 1. Remove ghost from enabledPlugins in settings.json
# Edit ~/.claude/settings.json, delete the line: "tldrs@interagency-marketplace": true
# This is the MOST IMPORTANT step — the "failed to load" error comes from here

# 2. Remove ghost cache directories (old plugin names)
rm -rf ~/.claude/plugins/cache/interagency-marketplace/tldrs

# 3. Remove stale temp directories
rm -rf ~/.claude/plugins/cache/temp_git_*

# 3. Remove broken version directories
rm -rf ~/.claude/plugins/cache/interagency-marketplace/tldr-swinton

# 4. Reinstall cleanly
claude plugin install tldr-swinton

# 5. Verify
claude plugin list | grep -A3 tldr-swinton
```

### Diagnostic Commands

```bash
# List all cache entries and their sizes
du -sh ~/.claude/plugins/cache/*/

# Find ghost entries (directories with no plugin.json)
for d in ~/.claude/plugins/cache/*/*/*/; do
  [ ! -f "$d/.claude-plugin/plugin.json" ] && [ ! -f "$d/plugin.json" ] && echo "GHOST: $d"
done

# Count temp directories
ls -d ~/.claude/plugins/cache/temp_git_* 2>/dev/null | wc -l

# Check installed vs cached
claude plugin list 2>&1 | grep "❯" | awk '{print $2}'
ls ~/.claude/plugins/cache/interagency-marketplace/
```

## Prevention Strategy

### For Plugin Developers
- **Never rename a plugin** without documenting the old name for cache cleanup
- **If renaming is necessary**, add a note to the README about cleaning old cache entries
- **Test installation on a clean machine** after any structural changes

### For Plugin Users
- **Periodically clean the cache**: `rm -rf ~/.claude/plugins/cache/temp_git_*`
- **After "failed to load" errors**: check for version mismatches or ghost entries
- **After upgrading Claude Code**: reinstall plugins that stopped working

### For Claude Code (Upstream Improvement Opportunities)
- Auto-clean `temp_git_*` directories after failed installs
- Garbage-collect cache entries not referenced by `installed_plugins.json`
- Only cache `.claude-plugin/` contents, not the full repository
- Handle plugin renames gracefully (remove old cache on install of renamed plugin)

## Related Issues

- Version drift between repo and marketplace (see: `plugin-version-drift-breaks-loading.md`)
- LFS submodule blocking install (see: `lfs-submodule-blocks-plugin-install.md`)

## See Also

- `~/.claude/plugins/installed_plugins.json` — Source of truth for installed plugins
- `~/.claude/plugins/cache/` — Cache directory structure
- `CLAUDE.md` — Publishing runbook
