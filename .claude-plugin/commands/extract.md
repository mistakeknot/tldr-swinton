---
name: tldrs-extract
description: Extract file analysis (functions, classes, imports) as structured output
arguments:
  - name: file
    description: File path to analyze
    required: true
---

Extract structured metadata from a file — functions, classes, imports, and line ranges — without reading the full source.

```bash
tldrs extract "$ARGUMENTS.file"
```

**When to use:**
- Understanding what's in a file before reading it
- Getting function signatures and line numbers
- Quick file overview for large files (500+ lines)

**Tips:**
- Output includes line ranges so you can Read only the lines you need
- Combine with `tldrs cfg <file> <function>` for control flow of a specific function
