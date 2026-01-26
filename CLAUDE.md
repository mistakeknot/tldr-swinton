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
/plugin install tldrs
```

**Available commands:**
- `/tldrs-find <query>` - Semantic code search
- `/tldrs-diff` - Diff-focused context
- `/tldrs-context <symbol>` - Symbol-level context
- `/tldrs-quickstart` - Quick reference guide

## Plugin Publishing Runbook

When releasing a new version of the tldrs plugin:

```bash
# 1. Bump ALL version locations (must stay in sync!)
edit pyproject.toml                   # version = "X.Y.Z"
edit .claude-plugin/plugin.json       # "version": "X.Y.Z"

# 2. Reinstall CLI to update global binary
uv tool install --force .
tldrs --version  # Verify shows new version

# 3. Run tests
uv run pytest tests/ -q --ignore=tests/test_agent_workflow_eval.py

# 4. Commit and push tldr-swinton
git add pyproject.toml .claude-plugin/ uv.lock
git commit -m "chore: bump version to X.Y.Z"
git push

# 5. Update interagency-marketplace
cd ../interagency-marketplace
edit .claude-plugin/marketplace.json  # bump version to match
git add .claude-plugin/marketplace.json
git commit -m "chore: bump tldrs to vX.Y.Z"
git push
```

**Version locations (all must match):**
| File | Field |
|------|-------|
| `pyproject.toml` | `version = "X.Y.Z"` |
| `.claude-plugin/plugin.json` | `"version": "X.Y.Z"` |
| `interagency-marketplace/.claude-plugin/marketplace.json` | `"version": "X.Y.Z"` |

**Plugin structure:**
```
.claude-plugin/
├── plugin.json          # Manifest (version, metadata, references)
├── commands/            # Slash commands (/tldrs-find, etc.)
│   ├── find.md
│   ├── diff-context.md
│   ├── context.md
│   └── quickstart.md
├── hooks/
│   └── hooks.json       # Hook definitions
│   └── setup.sh         # Setup hook script
└── skills/
    └── tldrs-agent-workflow/
        └── SKILL.md     # Workflow skill
```

**Version sync:** All three locations must match: `pyproject.toml`, `.claude-plugin/plugin.json`, and `interagency-marketplace/.claude-plugin/marketplace.json`. Always bump all three together.

**Pre-commit hook:** The hook runs `scripts/check-versions.sh` to verify `pyproject.toml` and `plugin.json` match before allowing commits. To install the hook on a fresh clone, copy `.git/hooks/pre-commit` from an existing setup or run `scripts/check-versions.sh` manually.

## Claude Code-Specific Notes

None currently - all instructions apply to all agents. See AGENTS.md for ContextPack JSON, ETag, and ambiguity notes.
