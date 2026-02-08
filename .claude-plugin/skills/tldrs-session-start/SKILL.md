---
name: tldrs-session-start
description: "Use when starting a coding session or task. Run BEFORE reading any code files. Provides diff-focused context that saves 48-73% tokens."
---

# Session Start Reconnaissance

Run this BEFORE opening any code files at the start of a task.

## Command

```bash
tldrs diff-context --project . --budget 2000
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

## Budget by Codebase Size

| Size | Budget |
|------|--------|
| Small (<50 files) | 1500 |
| Medium (50-200) | 2000 |
| Large (200+) | 3000 |

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

## When to Skip

- File < 200 lines: just Read it
- You already know exactly what file to edit
- Simple config file changes
