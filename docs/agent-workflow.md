# Agent Workflow

tldr-swinton is a context-selection tool, not a mandatory pre-read gate. Use it when compact static or semantic analysis will reduce uncertainty, isolate noisy exploration, or produce a better handoff than raw file reads.

## Install and verify

```bash
curl -fsSL https://raw.githubusercontent.com/mistakeknot/tldr-swinton/main/scripts/install.sh | bash
tldrs --version
```

The installer creates launchers in `~/.local/bin` that preserve the caller's working directory. If `command -v tldrs` succeeds but `tldrs --version` fails, the executable is stale or import-broken; re-run the installer.

## Harness integration

### Claude Code

- The plugin exposes six slash commands, four skills, and the `tldr-code` MCP server.
- Large/unfamiliar reconnaissance and codebase mapping run with `context: fork` on the built-in Explore agent, keeping search output out of the main conversation.
- The Setup hook checks executable health and quietly prebuilds cache state. It does not inject a project map into every session.
- There is no PostToolUse Read hook: adding a second structural dump after a raw read duplicates context.

### Codex

- The repo-scoped skill is `./.codex/skills/tldrs-agent-workflow/SKILL.md`.
- The skill recommends tldrs for unfamiliar, multi-file, diff-heavy, and delegation-heavy work, with an explicit bypass for already-scoped edits.
- Use `tldrs distill` when a Codex subagent needs a bounded packet; otherwise let the explorer keep raw reconnaissance in its own thread.

### Other harnesses

- Use the CLI from any shell-capable agent.
- Use `tldr-mcp --project /path/to/project` when the harness supports MCP.
- Treat the Agent Skills files as portable core guidance; harness-specific frontmatter such as Claude's `context: fork` is an extension.

See [Harness and Model Capabilities](harness-capabilities.md) for the dated primary-source baseline.

## Decision boundary

Use tldrs when at least one is true:

- The target area is unfamiliar or too large to inspect directly.
- Recent changes span multiple files or require caller/callee context.
- Semantic or structural discovery will narrow the file set.
- Search results, logs, or file contents would pollute the main conversation.
- Another agent needs a stable handoff with an explicit token budget.

Read or edit directly when all are true:

- The exact target is known.
- The file or region is small enough to inspect safely.
- No cross-file relationship needs analysis.
- The harness has already provided sufficient context.

## One-shot stop rule

Choose one reconnaissance command that can answer the current navigation
question. Inspect its result, then stop and read the exact implementation and
tests it identified. Run a second tldrs command only when the first output
reveals a specific unresolved ambiguity or dependency edge.

Do not chain `find`, `structure`, `context`, and `impact` by ritual. Command-level
compression does not create end-to-end savings when the agent then performs the
same broad raw reads, adds extra tool loops, or tests the wrong abstraction
layer.

## Command ladder

1. Recent changes:
   `tldrs diff-context --project . --preset compact`
2. Unknown concept:
   `tldrs find "authentication logic"`
3. Known symbol:
   `tldrs context <entry> --project . --depth 2 --preset compact`
4. Architecture or directory shape:
   `tldrs arch --lang <lang> .` or `tldrs structure <dir>`
5. Exact syntax pattern:
   `tldrs structural 'if $COND: $$$BODY' --lang python`
6. Deep dependency question:
   `tldrs impact`, `cfg`, `dfg`, or `slice`
7. Delegation:
   `tldrs distill --task "..." --budget 1500`

## Output discipline

- Start with `--preset compact`; use `minimal` for large diffs or smaller worker contexts.
- Set `--max-lines` or `--max-bytes` when a hard transport cap matters.
- Use JSON only for programmatic consumers; models usually need `ultracompact`.
- Reuse `--session-id` during multi-turn work so unchanged symbols can be omitted.
- Use `cache-friendly` only when the consuming API or harness reuses the stable prefix, and measure actual cache usage.

## Entry syntax

- `file.py:func`
- `Class.method`
- `module:func`

If unsure, use `tldrs structure <dir>` first. If tldrs reports ambiguity, select one of its qualified candidates.

## Typical flows

### Non-trivial bug fix

```bash
# Choose the one command that matches the unknown.
tldrs find "error handling"
# Or, for a change-induced regression:
# tldrs diff-context --project . --preset compact
```

Then stop reconnaissance and read the exact implementation and tests it
identified. Use `context` or `impact` only if the first result leaves a concrete
symbol or dependency question unresolved.

### Large codebase exploration

```bash
tldrs arch --lang typescript .
tldrs structure packages/auth/
tldrs context packages/auth/src/index.ts:initialize --project . --preset compact
```

In Claude Code, the plugin runs this class of work in a forked Explore context. In Codex or another multi-agent harness, keep the raw exploration in an explorer thread and return a short file/symbol summary.

### Agent handoff

```bash
tldrs distill --task "review authorization changes for regressions" --budget 1500 --session-id auth-review
```

The receiving agent should still verify source and tests before editing.

## Troubleshooting

- `command -v tldrs` succeeds but `tldrs --version` fails: stale launcher or deleted editable target; re-run `scripts/install.sh`.
- `No semantic index found`: run `tldrs index .`.
- `No git repository`: use `structure`, `tree`, or `extract` instead of diff-context.
- Structural search is garbled: single-quote `$` patterns.
- Entry is ambiguous: qualify it as `file.py:symbol`.
- Repo-local artifact storage needs relocation: set `TLDRS_VHS_HOME`.
