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
- `tldrs-interbench-sync` - Sync interbench eval coverage with tldrs capabilities

**MCP tools** (direct tool calls, replace retired skills):
- `tldr-code` MCP server provides `find`, `context`, `impact`, `cfg`, `dfg`, `extract`, `structural` etc. as native tools

## Publishing

Use `/interpub:release <version>` or `scripts/bump-version.sh <version>`. See root [agents/plugin-publishing.md](../../agents/plugin-publishing.md) for full runbook. Pre-commit hook validates version sync across `pyproject.toml`, `plugin.json`, and marketplace.

## Tool Overlap with intermap

4 tools overlap functionally with intermap (`structure`/`code_structure`, `impact`/`impact_analysis`, `arch`/`detect_patterns`, `change_impact`/`change_impact`). Intermap provides project-level scope; tldr-swinton provides file-level detail. Both coexist. See intermap CLAUDE.md for the full matrix.

## Claude Code-Specific Notes

**After adding formats/flags:** Run `tldrs manifest | python3 /root/projects/Interverse/infra/interbench/scripts/check_tldrs_sync.py` to detect gaps, then use `/tldrs-interbench-sync` to fix them. Also update `/root/projects/Interverse/infra/interbench` manually if needed. See AGENTS.md "Related Projects".
