---
name: tldrs-agent-workflow
description: Adaptive code reconnaissance using tldr-swinton. Use for unfamiliar, multi-file, diff-heavy, or delegation-heavy work when compact analysis will narrow the next read.
---

# tldr-swinton Workflow

Use `tldrs` when reconnaissance will reduce uncertainty or isolate noisy exploration. Read directly when the target is already known and small.

## Quick Decision

| Task | Command |
|------|---------|
| Understand recent changes | `tldrs diff-context --project . --budget 2000` |
| Find code by concept | `tldrs find "auth logic"` (run `tldrs index .` first) |
| Get context for a function | `tldrs context func --project . --depth 2 --format ultracompact` |
| See code structure | `tldrs structure src/` |
| Edit a file | Read the full file directly |

## Workflow

1. **Start with diff-context** for non-trivial recent changes:
   ```bash
   tldrs diff-context --project . --budget 2000
   ```

2. **Search by concept** if looking for specific functionality:
   ```bash
   tldrs index .                      # Once per project
   tldrs find "authentication logic"
   ```

3. **Drill into functions** when you need more context:
   ```bash
   tldrs context handle_auth --project . --depth 2 --format ultracompact
   ```

4. **Read full files only when editing** - tldr gives signatures, not full code.

## When NOT to Use

- File < 200 lines (just read it)
- You know exactly what to edit
- You need full implementation code

## Token Budgets

- Small codebase: `--budget 1500`
- Medium codebase: `--budget 2000`
- Large codebase: `--budget 3000`

## Multi-Turn Optimization

Use session IDs to skip unchanged code (~60% additional savings):

```bash
tldrs diff-context --project . --session-id my-session
# Later calls automatically skip unchanged symbols
```

## Common Mistakes

- Running tldrs by ritual when the next file or symbol is already known
- Skipping `--budget` and getting oversized outputs
- Forgetting `--lang` for non-Python repos

## Full Reference

Run `tldrs quickstart` for the complete quick reference guide.

See also: `.codex/skills/tldrs-agent-workflow/SKILL.md` for Codex-specific skill.
