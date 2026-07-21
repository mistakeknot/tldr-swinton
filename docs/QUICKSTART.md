# tldrs Quick Reference

Use tldrs when it will narrow the next read, edit, test, or delegation: large or unfamiliar codebases, non-trivial diffs, cross-file relationships, semantic discovery, and noisy exploration.

Skip it when the exact target is already known, the file is small, the task is docs/config only, or the agent harness already supplied a sufficient context packet.

Historical repository benchmarks show substantial token reductions for selected workflows; they are not a promise that every extra tool call saves time or tokens. See [Harness and Model Capabilities](harness-capabilities.md) for the current routing rationale.

## Quick decision

| Need | Command | Next |
|------|---------|------|
| Review a non-trivial diff | `tldrs diff-context --project . --preset compact` | Inspect changed symbols |
| Find code by concept | `tldrs find "auth logic"` | Read the best matches |
| Find code by structure | `tldrs structural 'pattern' --lang python` | Inspect exact matches |
| Understand a symbol | `tldrs context func --project . --preset compact` | Read only the edit target |
| Map an unfamiliar area | `tldrs structure src/` | Drill into one directory |
| Prepare agent handoff | `tldrs distill --task "task" --budget 1500` | Send the compact packet |

## Core commands

### Diff context

```bash
tldrs diff-context --project . --preset compact
```

Use `--preset minimal` for a large diff or a small worker context. Add `--session-id <task-id>` when repeated calls should omit unchanged symbols.

### Semantic search

```bash
tldrs index .
tldrs find "authentication logic"
```

Build the index once, then update it when the codebase changes materially.

### Symbol context

```bash
tldrs context src/app.py:handle_request --project . --depth 2 --preset compact
```

If the entry is ambiguous, tldrs returns candidates. Re-run with `file.py:symbol`.

### Structural search

```bash
tldrs structural 'def $FUNC($$$ARGS): return None' --lang python
```

Always single-quote structural patterns. `$VAR` and `$$$ARGS` are ast-grep meta-variables that a shell would otherwise expand.

### Impact and test selection

```bash
tldrs impact authenticate --depth 3 --lang python
tldrs change-impact --git
```

Use these when callers or affected tests could change the implementation plan.

### Delegation packets

```bash
tldrs distill --task "review authorization changes" --budget 1500 --session-id auth-review
```

Modern harnesses can isolate explorers in their own context windows. Use `distill` when a worker still needs a stable, bounded handoff instead of raw search output.

## Budgets and output caps

| Scope | Starting budget |
|-------|-----------------|
| Small (<50 files) | 1500 |
| Medium (50-200 files) | 2000 |
| Large (200+ files) | 3000 |

Hard caps:

```bash
tldrs context main --project . --max-lines 50
tldrs diff-context --project . --max-bytes 4096
```

## Prompt caching

`--format cache-friendly` separates a stable signature prefix from changing content:

```bash
tldrs diff-context --project . --delta --format cache-friendly
```

Use it only when the consuming API or harness actually reuses that prefix. Provider caching semantics and prices change; measure cache reads, cache writes, total tokens, latency, and task quality on the target harness instead of assuming a fixed percentage.

## Language support

```bash
tldrs structure src/ --lang typescript
tldrs context main --project . --lang rust
```

Base install: Python, TypeScript, JavaScript, Rust, Go, Java, C, C++, and Ruby.

Optional grammars: Kotlin, Swift, C#, Scala, Lua, and Elixir.

## Common errors

| Error | Fix |
|-------|-----|
| `ModuleNotFoundError: tldr_swinton` | Re-run `scripts/install.sh`; it replaces stale editable launchers |
| `No git repository` | Use `tldrs structure <dir>` instead of diff-context |
| `No semantic index found` | Run `tldrs index .` |
| `Ambiguous entry` | Use `file.py:symbol` syntax |
| Garbled structural pattern | Single-quote the ast-grep pattern |

## Full documentation

- `tldrs --help` — command reference
- [Agent Workflow](agent-workflow.md) — harness integration and advanced flow
- [Harness and Model Capabilities](harness-capabilities.md) — current capability baseline
- [Token Savings](token-savings-summary.md) — benchmark methodology
