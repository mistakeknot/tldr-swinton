# Claude Code Plugin

## Commands

| Command | Description |
|---------|-------------|
| `/tldrs-find <query>` | Semantic code search |
| `/tldrs-diff` | Diff-focused context for recent changes |
| `/tldrs-context <symbol>` | Symbol-level context |
| `/tldrs-structural <pattern>` | Structural code search (ast-grep patterns) |
| `/tldrs-quickstart` | Show quick reference guide |
| `/tldrs-extract <file>` | Extract file structure |

## Skills (4 autonomous)

| Skill | Trigger |
|-------|---------|
| `tldrs-session-start` | Before reading code for bugs, features, refactoring, tests, reviews, migrations |
| `tldrs-map-codebase` | Understanding architecture, exploring unfamiliar projects, onboarding |
| `tldrs-interbench-sync` | Syncing interbench eval coverage after tldrs capability changes |
| `finding-duplicate-functions` | Auditing codebases for semantic duplication |

## Hooks

| Hook | Matcher | Action |
|------|---------|--------|
| `Setup` | (session start) | Checks tldrs install, semantic index, ast-grep; provides project summary |
| `PreToolUse` | Serena `replace_symbol_body` | Runs `tldrs impact` to show callers before edits |
| `PreToolUse` | Serena `rename_symbol` | Same caller analysis |
| `PostToolUse` | `Read` | Compact `tldrs extract` on large files (>300 lines, once per file per session) |

## Plugin File Layout

```
.claude-plugin/
├── plugin.json          # Manifest (version, MCP server, references)
├── commands/            # 6 slash commands
├── hooks/
│   ├── hooks.json       # Hook definitions
│   ├── setup.sh         # Setup hook
│   ├── pre-serena-edit.sh # Caller analysis before Serena edits
│   └── post-read-extract.sh # Auto-extract on large file reads
└── skills/              # 4 orchestration skills
    ├── tldrs-session-start/
    ├── tldrs-map-codebase/
    ├── tldrs-interbench-sync/
    └── finding-duplicate-functions/
```

## Codex Skill

Repo-scoped at `.codex/skills/tldrs-agent-workflow/`. Mirrors `docs/agent-workflow.md`.
