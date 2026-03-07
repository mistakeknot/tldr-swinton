# MCP Server (`tldr-code`)

The MCP server is the primary agent interface. 24 tools organized by category.

**Cost ladder** (cheapest first):
1. `extract(file, compact=True)` ~200 tok -- file map (use instead of Read for overview)
2. `structure(project)` ~500 tok -- directory symbols (use instead of Glob + Reads)
3. `context(entry)` ~400 tok -- call graph around symbol (use instead of reading caller files)
4. `diff_context(project)` ~800 tok -- changed-code context (use instead of git diff + Read)
5. `impact(function)` ~300 tok -- reverse call graph (use before refactoring)
6. `semantic(query)` ~300 tok -- meaning-based search (use instead of Grep for concepts)

## Full Tool Catalog

| Category | Tool | Description |
|----------|------|-------------|
| **Navigation** | `tree` | File tree listing (paths only, no symbols) |
| | `structure` | All symbols across a directory |
| | `search` | Regex search (prefer built-in Grep) |
| | `extract` | Function/class signatures from a file |
| **Context** | `context` | Call graph from a symbol with presets |
| | `diff_context` | Git-aware diff context with symbol mapping |
| | `distill` | Compressed prescriptive context for sub-agent handoff |
| | `delegate` | Prioritized retrieval plan for complex tasks |
| **Flow Analysis** | `cfg` | Control flow graph (basic blocks, cyclomatic complexity) |
| | `dfg` | Data flow graph (variable def-use chains) |
| | `slice` | Program slice (lines affecting/affected by a given line) |
| **Codebase Analysis** | `impact` | Reverse call graph (find all callers) |
| | `dead` | Unreachable code detection (expensive) |
| | `arch` | Architectural layer detection (expensive) |
| | `calls` | Full cross-file call graph (expensive) |
| **Import Analysis** | `imports` | Parse imports from a source file |
| | `importers` | Find files importing a given module |
| **Semantic Search** | `semantic` | Meaning-based code search via embeddings |
| | `semantic_index` | Build/rebuild semantic index |
| | `semantic_info` | Index metadata (backend, model, count) |
| **Quality** | `diagnostics` | Type checker + linter (pyright + ruff) |
| | `change_impact` | Find tests affected by changed files |
| | `verify_coherence` | Cross-file consistency after multi-file edits |
| **Structural** | `structural_search` | AST pattern matching via ast-grep |
| **Admin** | `hotspots` | Most-accessed symbols across sessions |
| | `status` | Daemon uptime and cache statistics |

**Semantic index**: Run `semantic_index()` once before `semantic()`. Use `semantic_info()` to check status. Backends: `faiss` (lighter, Ollama) or `colbert` (better retrieval, heavier).
