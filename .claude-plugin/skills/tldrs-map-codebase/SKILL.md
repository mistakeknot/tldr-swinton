---
name: tldrs-map-codebase
description: "Use when asked to understand a codebase's architecture, explore an unfamiliar project, onboard to a new repo, or identify which modules exist. Provides structural overview without reading individual files."
allowed-tools:
  - Bash
---

# Map Codebase Architecture

Run this when you need a bird's-eye view of a project before diving into code.

## Architecture Overview

See how modules connect and what layers exist:

```bash
tldrs arch --lang python .
```

Output shows module relationships:

```
LAYERS:
  api/        → routes, middleware, auth
  core/       → business logic, models
  infra/      → database, cache, external APIs
  utils/      → helpers, constants

DEPENDENCIES:
  api/ → core/ → infra/
  api/ → utils/
  core/ → utils/
```

For non-Python projects, specify the language:

```bash
tldrs arch --lang typescript src/
tldrs arch --lang rust .
```

## Code Structure

See what's in each file within a directory:

```bash
tldrs structure src/
```

Shows files with their key symbols (classes, functions, exports):

```
src/auth.py: AuthManager, login(), verify(), refresh()
src/models.py: User, Token, Session
src/routes.py: app, /login, /logout, /refresh
```

## File Tree

See the file layout without content:

```bash
tldrs tree src/
```

Lighter than `structure` — just file paths organized by directory.

## Workflow

1. Start with `tldrs arch --lang <lang> .` for the big picture
2. Use `tldrs structure <dir>` to explore interesting directories
3. Use `tldrs tree <dir>` for a quick file listing of large directories
4. Drill in with `tldrs context <entry_point>` or `tldrs extract <file>`

## When to Skip

- You already know where to look (go straight to `tldrs context` or Read)
- Project is tiny (<10 files) — just use `tldrs structure .`
- User specified the exact file to work on
- You're resuming work from a previous turn (context already established)

## Next Step

After mapping the codebase:
- Use `tldrs context <entry_point> --project . --depth 2` to drill into key modules
- Use `tldrs extract <file>` for file-level detail on interesting files
- Use `tldrs find "query"` to locate specific functionality

## Common Errors

- **"No files found"**: Check the path. Use `.` for project root.
- **"Language not detected"**: Specify `--lang` explicitly.
- **Very large output**: Target a subdirectory instead of the project root.
