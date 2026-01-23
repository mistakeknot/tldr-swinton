---
name: tldrs-find
description: Semantic code search - find code by meaning, not just text patterns
arguments:
  - name: query
    description: Natural language query (e.g., "authentication logic", "database connection")
    required: true
---

Search the codebase semantically using tldr-swinton embeddings.

**Prerequisites:** Run `tldrs index .` once per project to build the semantic index.

```bash
tldrs find "$ARGUMENTS.query" --project .
```

**Tips:**
- Use natural language: "error handling patterns", "user authentication flow"
- Results are ranked by semantic similarity, not just text matching
- If no results, try rephrasing or check that index is built (`tldrs index --info`)
