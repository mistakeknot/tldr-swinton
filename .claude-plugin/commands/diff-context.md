---
name: tldrs-diff
description: Get token-efficient context for recent changes (diff-first workflow)
arguments:
  - name: budget
    description: Token budget (default 2000)
    required: false
  - name: session
    description: Session ID for delta mode (skip unchanged symbols)
    required: false
---

Generate diff-focused context pack for recent changes. This is the recommended starting point for most coding tasks.

```bash
tldrs diff-context --project . --budget ${ARGUMENTS.budget:-2000} ${ARGUMENTS.session:+--session-id $ARGUMENTS.session}
```

**When to use:**
- Starting work on a codebase
- Understanding recent changes
- Code review context

**Tips:**
- Default range: merge-base(main/master) to HEAD
- Use `--session-id` for multi-turn conversations (60% token savings on unchanged symbols)
- Add `--format json` for structured output
