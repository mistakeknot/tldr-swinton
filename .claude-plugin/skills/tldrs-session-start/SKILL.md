---
name: tldrs-session-start
description: "Use when starting any coding task: fix bugs, debug, implement features, refactor, write tests, review code, migrate, port, or explore a codebase. Also use when resuming a previous session, onboarding to a repo, or before reading code files in a new conversation. Provides diff-focused context that saves 48-73% tokens."
allowed-tools:
  - Bash
---

# Session Start Reconnaissance

BEFORE reading any code files, determine your starting point.

## Decision Tree

### 1. Are there recent changes?

Check: `git status` or `git diff --stat HEAD`

**YES — changes exist:**
```bash
tldrs diff-context --project . --preset compact
```

**YES + large diff (>500 lines changed):**
```bash
tldrs diff-context --project . --preset minimal
```

**NO — clean working tree:**
```bash
tldrs structure src/
```

### 2. Is this a multi-turn task?

If you expect multiple rounds of queries on the same codebase:
```bash
# Add --session-id auto to ALL tldrs calls this session
tldrs diff-context --project . --preset compact --session-id auto
```

### 3. After diff-context, identify targets

- `[contains_diff]` symbols → `tldrs context <symbol> --project . --preset compact`
- `[caller_of_diff]` symbols → check for breakage with `tldrs impact <symbol> --depth 3`
- Unknown area? → `tldrs find "query"` before Reading files

### 4. Spawning a subagent for code work?

Compress context for sub-agent consumption:
```bash
tldrs distill --task "description of the subtask" --budget 1500 --session-id auto
```

### 5. Test impact

After reviewing diff context, check which tests are affected:
```bash
tldrs change-impact --git
```

Returns `affected_tests` and a suggested `test_command`. Run only affected tests.

## Rules

- Always use `--preset compact` unless you have a reason not to
- Use `--preset minimal` for large diffs (>500 lines) or budget-constrained sessions

## When to Skip

- Editing a single file under 200 lines that you already know
- Simple config file changes (.json, .yaml, .toml)

## Non-Python Repos

Add `--lang` flag: `tldrs diff-context --project . --preset compact --lang typescript`
