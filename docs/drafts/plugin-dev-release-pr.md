# PR Draft: Add `/plugin-dev:release` command to plugin-dev

## PR Title

feat(plugin-dev): add `/release` command for marketplace plugin publishing

## PR Body

---

### The pain point

If you've ever published a Claude Code plugin through a marketplace, you know the specific heartache of the version drift bug: you bump your version in `plugin.json`, push, feel good about yourself, and then spend 20 minutes debugging why nobody can install the new version. Turns out `marketplace.json` still says `0.5.1`.

The failure mode is particularly cruel because it's silent. There's no error message that says "your marketplace version doesn't match your plugin version." Instead, Claude Code creates a cache directory named after the marketplace version, then tries to load paths from the plugin.json version, and every command/skill/hook just... doesn't exist. The user sees a clean install, the plugin shows as installed, but nothing works.

I've been building Claude Code plugins for a few months now (6 plugins across a dedicated marketplace), and I've hit this bug enough times that I started documenting the failure mode and eventually built tooling to prevent it. Jesse Vincent's [superpowers](https://github.com/obra/superpowers) — probably the most widely-used plugin ecosystem — faces the same problem with the same manual workflow: bump version in the plugin repo, commit, then remember to go update the marketplace repo too.

### Who this helps

Any plugin author who distributes through a separate marketplace repository. This is the standard architecture for anyone with more than one plugin (the official Anthropic marketplace, obra/superpowers-marketplace, and numerous community marketplaces all use this pattern). Based on the [awesome-claude-plugins](https://github.com/Chat2AnyLLM/awesome-claude-plugins) catalog, there are 43 marketplaces serving 834 plugins. Not all of them have the 2-repo split, but anyone scaling past a couple of plugins inevitably ends up here.

### What this adds

A new `/plugin-dev:release` command that guides plugin authors through a safe publishing workflow:

**Phase 1: Discover version locations**
- Finds `plugin.json` in the current plugin repo
- Scans for `marketplace.json` in common locations (sibling directories, `../` patterns, configurable path)
- Reports what it found and the current versions

**Phase 2: Validate before bumping**
- Checks that all current versions are in sync (catches existing drift)
- Runs the plugin-validator agent to ensure the plugin is healthy
- Optionally runs tests if a test script exists

**Phase 3: Bump and publish**
- Updates all version locations atomically
- Commits the plugin repo
- Commits the marketplace repo (if found and confirmed)
- Pushes both

**Phase 4: Verify**
- Confirms the push succeeded
- Reminds the author to restart Claude Code sessions

The command handles the common case automatically while asking for confirmation on anything destructive (pushes, marketplace edits in a different repo). It works with the existing `plugin-validator` agent already in plugin-dev.

### Why a command, not a skill

Skills are for things Claude should invoke autonomously. Publishing a new version is a deliberate, user-initiated action — you don't want Claude deciding it's time to bump your version mid-conversation. A slash command is the right affordance: explicit invocation, clear intent.

### What I learned building this

The interesting constraint is that `plugin.json` can't be templated — there's no `${VERSION}` variable support in metadata fields, and setup hooks run after the cache directory is already named. So the only real solution is tooling that writes all the files, not tooling that derives them. This is a fundamental property of the plugin system, not a bug, and it means every marketplace operator needs something like this.

I also found that a pre-commit hook checking version sync is a valuable safety net alongside the command. I'm including a reference implementation in the skill's `references/` directory.

### Implementation

- `plugins/plugin-dev/commands/release.md` — the command definition
- `plugins/plugin-dev/skills/plugin-structure/references/version-management.md` — reference doc on version sync, failure modes, prevention patterns

Happy to adjust scope or approach based on feedback. This is my first contribution to the repo — I wanted to start with something concrete that solves a specific problem I've lived with.

---

## Files to create

### `plugins/plugin-dev/commands/release.md`

```markdown
---
description: Publish a new plugin version across all version locations (plugin.json, marketplace.json) with validation
argument-hint: <version> e.g., 1.2.0
allowed-tools: ["Read", "Write", "Grep", "Glob", "Bash", "AskUserQuestion", "Task"]
---

# Plugin Release Workflow

Guide the plugin author through publishing a new version safely. This command prevents the most common plugin publishing failure: version drift between plugin.json and marketplace.json.

**Requested version:** $ARGUMENTS

---

## Phase 1: Discover Version Locations

**Goal**: Find all files that contain version strings for this plugin.

**Actions**:
1. Read `.claude-plugin/plugin.json` in the current directory to get the plugin name and current version
2. Search for marketplace.json files that reference this plugin:
   - Check `../*/.claude-plugin/marketplace.json` (sibling marketplace repos)
   - Check `../*-marketplace/.claude-plugin/marketplace.json`
   - Check `.claude-plugin/marketplace.json` (in-repo dev marketplace)
3. Check for language-specific version files:
   - `pyproject.toml` (Python: `version = "X.Y.Z"`)
   - `package.json` (Node: `"version": "X.Y.Z"`)
   - `Cargo.toml` (Rust: `version = "X.Y.Z"`)
4. Present all discovered locations and their current versions to the user

**If no version argument was provided**: Ask the user what the new version should be, showing the current version for reference.

**Output**: Table of all version locations, current versions, and new target version.

---

## Phase 2: Validate

**Goal**: Ensure the plugin is healthy before publishing.

**Actions**:
1. Verify all current versions match (if they don't, warn about existing drift and ask whether to continue)
2. Run the plugin-validator agent on the current plugin to catch structural issues
3. If a test script exists (`tests/`, `scripts/test.sh`, or similar), ask if the user wants to run tests first

**Output**: Validation summary. Stop if critical issues found.

---

## Phase 3: Update Versions

**Goal**: Write the new version to all discovered locations.

**Actions**:
1. Update each file, showing the diff for each change
2. For files in the current repo: stage and commit with message `chore: bump version to <version>`
3. For files in other repos (marketplace): ask the user for confirmation before modifying, then stage and commit with message `chore: bump <plugin-name> to v<version>`
4. Push each repo (ask for confirmation before each push)

**Important**: Always ask before pushing. Never push without explicit user confirmation.

**Output**: Summary of what was committed and pushed.

---

## Phase 4: Verify and Remind

**Goal**: Confirm the release succeeded.

**Actions**:
1. Verify git push succeeded for each repo
2. If the plugin has a CLI tool (detected from pyproject.toml or package.json), remind the user to reinstall it
3. Remind the user: "Restart Claude Code sessions to pick up the new plugin version"

**Output**: Release summary with version number and any remaining manual steps.
```

### `plugins/plugin-dev/skills/plugin-structure/references/version-management.md`

```markdown
# Plugin Version Management

## The Version Sync Problem

Plugins distributed through marketplace repositories have version strings in multiple locations that must stay in sync:

| Location | Purpose | Example |
|----------|---------|---------|
| `.claude-plugin/plugin.json` | Plugin identity (takes priority at runtime) | `"version": "1.2.0"` |
| Marketplace `marketplace.json` | Cache directory naming during install | `"version": "1.2.0"` |
| `pyproject.toml` / `package.json` | Language package version | `version = "1.2.0"` |

### Why drift breaks installs

When a user runs `claude plugin install`, Claude Code:
1. Reads the version from `marketplace.json` → creates cache at `~/.claude/plugins/cache/<marketplace>/<plugin>/<marketplace-version>/`
2. Copies the plugin repo into that cache directory
3. Reads `plugin.json` from the cached copy

If `marketplace.json` says `1.1.0` but `plugin.json` says `1.2.0`, the cache directory is named `1.1.0/` but the plugin's internal paths may reference the wrong version. More commonly, the user simply never gets the new version because the marketplace still advertises the old one.

**This failure is silent** — the plugin appears installed, but commands, skills, and hooks may not load.

## Prevention Patterns

### Single-command release

Use `/plugin-dev:release <version>` to update all version locations atomically.

### Pre-commit validation

Add a pre-commit hook that checks version sync:

```bash
#!/bin/bash
# .git/hooks/pre-commit (or via pre-commit framework)
PLUGIN_V=$(grep '"version"' .claude-plugin/plugin.json | sed 's/.*"\([0-9][^"]*\)".*/\1/')
# Check against pyproject.toml, package.json, etc.
PYPROJECT_V=$(grep -E '^version\s*=' pyproject.toml 2>/dev/null | sed 's/.*"\([^"]*\)".*/\1/')
if [ -n "$PYPROJECT_V" ] && [ "$PYPROJECT_V" != "$PLUGIN_V" ]; then
    echo "Version mismatch: pyproject.toml=$PYPROJECT_V, plugin.json=$PLUGIN_V" >&2
    exit 1
fi
```

### In-repo dev marketplace

For local development, include a dev marketplace inside the plugin repo:

```json
// .claude-plugin/marketplace.json
{
  "name": "my-plugin-dev",
  "plugins": [{
    "name": "my-plugin",
    "source": "./",
    "version": "1.2.0"
  }]
}
```

This lets you `plugin marketplace add ./` during development without needing the production marketplace.

## Recovery

If versions have drifted and users report broken installs:

```bash
# User fix:
claude plugin uninstall <plugin>@<marketplace>
# Clear stale cache
rm -rf ~/.claude/plugins/cache/<marketplace>/<plugin>/
# Reinstall
claude plugin install <plugin>@<marketplace>
```

## See Also

- [Plugin Marketplaces Documentation](https://code.claude.com/docs/en/plugin-marketplaces)
- [Plugin Discovery Documentation](https://code.claude.com/docs/en/discover-plugins)
```
