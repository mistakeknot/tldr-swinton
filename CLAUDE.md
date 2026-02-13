# tldr-swinton Claude Code Instructions

> CLAUDE.md: This file provides Claude Code-specific instructions. For shared agent documentation, see **AGENTS.md**.

## See AGENTS.md

All architecture, commands, critical rules, debugging, and testing instructions are in **AGENTS.md** (shared across all AI agents).

Full workflow guide: see `docs/agent-workflow.md`.
Claude skill template: `docs/claude-skill.md`.

## Claude Code Plugin

This project is available as a Claude Code plugin from the [interagency-marketplace](https://github.com/mistakeknot/interagency-marketplace):

```bash
/plugin marketplace add mistakeknot/interagency-marketplace
/plugin install tldr-swinton
```

**Available commands:**
- `/tldrs-find <query>` - Semantic code search
- `/tldrs-diff` - Diff-focused context
- `/tldrs-context <symbol>` - Symbol-level context
- `/tldrs-structural <pattern>` - Structural code search (ast-grep)
- `/tldrs-quickstart` - Quick reference guide
- `/tldrs-extract <file>` - Extract file structure (functions, classes, imports)

**Autonomous skills** (Claude invokes these automatically):
- `tldrs-session-start` - Runs diff-context before reading files (any coding task)
- `tldrs-map-codebase` - Understand architecture, explore unfamiliar projects
- `tldrs-ashpool-sync` - Sync Ashpool eval coverage with tldrs capabilities

**MCP tools** (direct tool calls, replace retired skills):
- `tldr-code` MCP server provides `find`, `context`, `impact`, `cfg`, `dfg`, `extract`, `structural` etc. as native tools

## Plugin Publishing Runbook

**Interactive (preferred):** Use `/interpub:release <version>` for a guided 4-phase workflow with validation and push confirmation.

**Scripted:** Use the local bump script:

```bash
# One command — updates all 3 version locations, commits, pushes, reinstalls CLI
scripts/bump-version.sh 0.7.0

# Dry-run to preview changes
scripts/bump-version.sh 0.7.0 --dry-run
```

Both methods update `pyproject.toml`, `.claude-plugin/plugin.json`, and `../interagency-marketplace/.claude-plugin/marketplace.json` atomically. The pre-commit hook (`scripts/check-versions.sh`) validates all three are in sync.

**Plugin structure:**
```
.claude-plugin/
├── plugin.json          # Manifest (version, metadata, MCP server, references)
├── commands/            # Slash commands (/tldrs-find, etc.)
│   ├── find.md
│   ├── diff-context.md
│   ├── context.md
│   ├── structural.md
│   ├── quickstart.md
│   └── extract.md
├── hooks/
│   ├── hooks.json       # Hook definitions (Setup, PreToolUse:Serena, PostToolUse:Read)
│   ├── setup.sh         # Setup hook script (+ prebuild cache warming)
│   ├── pre-serena-edit.sh # Caller analysis before Serena edits/renames
│   └── suggest-recon.sh # (legacy, not registered)
└── skills/              # 3 orchestration skills (Claude-invoked)
    ├── tldrs-session-start/
    ├── tldrs-map-codebase/
    └── tldrs-ashpool-sync/
```

**Version sync:** All three locations must match: `pyproject.toml`, `.claude-plugin/plugin.json`, and `interagency-marketplace/.claude-plugin/marketplace.json`. Always bump all three together.

**Pre-commit hook:** The hook runs `scripts/check-versions.sh` to verify `pyproject.toml` and `plugin.json` match before allowing commits. To install the hook on a fresh clone, copy `.git/hooks/pre-commit` from an existing setup or run `scripts/check-versions.sh` manually.

**IMPORTANT: Always update and push the marketplace.** Any change to `.claude-plugin/` (version bumps, renames, new commands, etc.) must be followed by updating `interagency-marketplace` and pushing both repos. The plugin is not published until the marketplace is updated.

## Claude Code-Specific Notes

**After adding formats/flags:** Run `tldrs manifest | python3 ../Ashpool/scripts/check_tldrs_sync.py` to detect gaps, then use `/tldrs-ashpool-sync` to fix them. Also update `../Ashpool` manually if needed. See AGENTS.md "Related Projects".
