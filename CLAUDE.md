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
# 1. Update version in plugin.json
edit .claude-plugin/plugin.json  # bump version

# 2. Run tests
uv run pytest tests/ -q --ignore=tests/test_agent_workflow_eval.py

# 3. Commit and push tldr-swinton
git add .claude-plugin/
git commit -m "feat: <description>"
git push

# 4. Update interagency-marketplace
cd ../interagency-marketplace
edit .claude-plugin/marketplace.json  # bump version to match
git add .claude-plugin/marketplace.json
git commit -m "chore: bump tldrs to vX.Y.Z"
git push
```

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

**Version sync:** Keep `.claude-plugin/plugin.json` version in sync with `interagency-marketplace/.claude-plugin/marketplace.json`.

## Claude Code-Specific Notes

None currently - all instructions apply to all agents. See AGENTS.md for ContextPack JSON, ETag, and ambiguity notes.
