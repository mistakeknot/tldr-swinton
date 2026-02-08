---
name: tldrs-structural
description: Structural code search using ast-grep tree-sitter patterns
arguments:
  - name: pattern
    description: "ast-grep pattern (use $VAR for single node, $$$ARGS for varargs)"
    required: true
  - name: lang
    description: Language filter (auto-detected if omitted)
    required: false
---

Search code structurally using ast-grep tree-sitter patterns.

IMPORTANT: The pattern contains `$` characters. Always single-quote the pattern to prevent shell expansion.

```bash
tldrs structural '$ARGUMENTS.pattern' ${ARGUMENTS.lang:+--lang $ARGUMENTS.lang}
```

**Pattern syntax:**
- `$VAR` matches any single AST node
- `$$$ARGS` matches zero or more nodes
- Patterns are language-aware (Python `def`, JS `function`, Go `func`, etc.)

**Examples:**
- Functions returning None: `'def $FUNC($$$ARGS): $$$BODY return None'`
- All method calls: `'$OBJ.$METHOD($$$ARGS)'`
- Go error handling: `'if err != nil { $$$BODY }'`

Included in base install (ast-grep-py).
