# 7kb: MCP context() Default Changes

## Summary

Changed the `context()` MCP tool defaults in `mcp_server.py` to optimize for the primary consumer: AI agents calling via MCP.

## Changes Made

**File:** `src/tldr_swinton/modules/core/mcp_server.py`

### 1. Default format: `"text"` -> `"ultracompact"`

```python
# Before
format: str = "text",
# After
format: str = "ultracompact",
```

### 2. Default budget: `None` (unlimited) -> `4000`

```python
# Before
budget: int | None = None,
# After
budget: int | None = 4000,
```

### 3. Docstring updates

- `format` description changed from `Output format (text, ultracompact, json)` to `Output format (default: ultracompact for LLMs; also: text, json)`
- `budget` description changed from `Optional token budget` to `Token budget (default: 4000; set to None for unlimited)`

## Rationale

The MCP server's primary consumers are AI tools (Claude Code, OpenCode, etc.) where token efficiency matters. The `ultracompact` format saves 30-50% tokens compared to `text` format. The plugin's slash commands (`/tldrs-context`) already hardcoded `--format ultracompact`, but direct MCP tool calls -- which are now the primary interface since skills were retired in favor of MCP tools -- still defaulted to verbose text format.

A 4000-token budget prevents runaway context retrieval. Callers can override to `None` for unlimited if needed.

## Scope

Only the `context()` function signature and its docstring were modified. No other functions in `mcp_server.py` were touched.
