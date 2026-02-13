---
name: tldrs-context
description: Get LLM-ready context for a specific function or class
arguments:
  - name: symbol
    description: Function or class name to get context for
    required: true
  - name: depth
    description: Call graph depth (default 2)
    required: false
  - name: budget
    description: Token budget (default 2000)
    required: false
  - name: delegate
    description: Task description for smart context retrieval planning
    required: false
---

Get focused context for a specific symbol including its dependencies and callers.

```bash
tldrs context "$ARGUMENTS.symbol" --project . --depth ${ARGUMENTS.depth:-2} --budget ${ARGUMENTS.budget:-2000} --format ultracompact ${ARGUMENTS.delegate:+--delegate "$ARGUMENTS.delegate"}
```

**When to use:**
- Deep-diving into a specific function
- Understanding a function's dependencies
- Preparing to modify a specific piece of code

**Tips:**
- Use `--format ultracompact` for maximum token savings
- Increase `--depth` for broader context (more callers/callees)
- If symbol is ambiguous, use `file.py:function_name` format
- Use `--delegate "task description"` for smart retrieval planning — tldrs will decide which engines and depth to use based on the task
