---
name: tldrs-session-start
description: "Use when asked to fix bugs, implement features, review code, or explore a codebase. Run BEFORE reading code files. Provides diff-focused context that saves 48-73% tokens."
allowed-tools:
  - Bash
---

# Session Start Reconnaissance

Run this BEFORE opening any code files at the start of a task.

## Command

```bash
tldrs diff-context --project . --budget 2000
```

For large diffs, add compression (35-73% additional savings):
```bash
tldrs diff-context --project . --budget 1500 --compress two-stage
```

For multi-turn conversations, add a session ID (~60% savings on subsequent turns):
```bash
tldrs diff-context --project . --budget 2000 --session-id task-name
```

## Reading the Output

Output lists changed symbols by priority file (P0 = most changed):

```
P0=src/auth.py P1=src/users.py

P0:login def login(user, password)  [contains_diff]
P0:verify def verify(token)  [caller_of_diff]
P1:create_user def create_user(data)  [contains_diff]
```

- `[contains_diff]` — symbol was directly modified
- `[caller_of_diff]` — symbol calls something that changed
- `[dep_of_diff]` — symbol is called by something that changed

## Next Step

After reading the output:
1. Read P0 files first (most changed)
2. Focus on `[contains_diff]` symbols
3. Use `tldrs context <symbol> --project .` to understand specific functions before reading full files

## Budget by Codebase Size

| Size | Budget |
|------|--------|
| Small (<50 files) | 1500 |
| Medium (50-200) | 2000 |
| Large (200+) | 3000 |

## Output Caps

If output is still too large after budgeting:
```bash
tldrs diff-context --project . --budget 2000 --max-lines 50
tldrs diff-context --project . --budget 2000 --max-bytes 4096
```

## Clean Repo (No Changes)

If working tree is clean and no branch divergence:

```bash
tldrs structure src/
```

## Non-Python Repos

Add `--lang` flag:

```bash
tldrs diff-context --project . --budget 2000 --lang typescript
```

Supported: python, typescript, javascript, rust, go, java, c, cpp, ruby, php, kotlin, swift, csharp, scala, lua, elixir

## Common Errors

- **"No git repository"**: diff-context requires a git repo. Use `tldrs structure` instead.
- **Empty output**: Working tree is clean with no uncommitted changes. Use `tldrs structure` to explore.
- **Very large output**: Add `--compress two-stage` or lower `--budget`.

## When to Skip

- You are editing a single file under 200 lines AND you already know which file it is
- Simple config file changes (.json, .yaml, .toml)
