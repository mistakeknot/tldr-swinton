# Bead 3ia: Compact Extract Format for PostToolUse:Read Hook

## Problem

The PostToolUse:Read hook runs `tldrs extract` on every code file >300 lines that Claude reads, injecting full JSON output per file. The full extract includes `call_graph`, `params` arrays, `is_async` booleans, empty `decorators`, full `docstrings`, and `imports` -- most of which is redundant for LLM context injection. This wastes tokens on every large file read.

## Solution

Added a `compact_extract()` function and `--compact` CLI flag that returns only signatures and line numbers, omitting verbose fields.

### Changes Made

**1. `src/tldr_swinton/modules/core/api.py` -- new `compact_extract()` function**

Added after `extract_file()` (around line 713). The function:
- Calls `extract_file()` for the full parse, then filters to essential fields
- For functions: keeps `name`, `signature`, `line`, optionally `decorators` and first-line `doc`
- For classes: keeps `name`, `line`, `bases`, and compact method list
- Omits: `call_graph`, `imports`, `params`, `is_async`, empty `decorators`, empty `docstrings`

**2. `src/tldr_swinton/cli.py` -- `--compact` flag on `extract` subcommand**

- Added `--compact` argparse argument to `extract_p` (after `--method`)
- Added conditional branch in the `extract` command handler: if `--compact` is set, calls `compact_extract()` instead of `extract_file()`
- All existing filters (`--class`, `--function`, `--method`) still work for full extract; compact mode bypasses them (returns all symbols in compact form)

**3. `.claude-plugin/hooks/post-read-extract.sh` -- uses compact mode**

- Updated header comment to describe compact mode
- Changed line 46 from `tldrs extract "$FILE"` to `tldrs extract --compact "$FILE"`
- No other hook logic changed (timeout, flagging, JSON encoding all preserved)

**4. `src/tldr_swinton/modules/core/mcp_server.py` -- `compact` param on MCP `extract` tool**

- Added `compact: bool = False` parameter to the `extract()` MCP tool
- When `compact=True`, imports and calls `compact_extract()` directly (bypasses daemon)
- When `compact=False` (default), behavior unchanged (sends to daemon)

## Measured Results

Test file: `src/tldr_swinton/cli.py` (2066 lines, 19 functions, no classes)

| Mode | Output size | Keys |
|------|------------|------|
| Full | 7,362 chars | file_path, language, docstring, imports, classes, functions, call_graph |
| Compact | 2,508 chars | file_path, language, functions |

**Reduction: 66% on this file.** Files with classes, call_graph edges, and many imports will see larger savings (up to ~87% as estimated).

## Compact Output Schema

```json
{
  "file_path": "string",
  "language": "string",
  "functions": [
    {
      "name": "string",
      "signature": "string",
      "line": "int",
      "decorators": ["string"],   // only if non-empty
      "doc": "string"             // only first line, only if non-empty
    }
  ],
  "classes": [
    {
      "name": "string",
      "line": "int",
      "bases": ["string"],        // only if non-empty
      "methods": [
        {
          "name": "string",
          "signature": "string",
          "line": "int",
          "decorators": ["string"]  // only if non-empty
        }
      ]
    }
  ]
}
```

Fields omitted vs full extract:
- `docstring` (module-level)
- `imports` (available from the file itself when Claude reads it)
- `call_graph` (calls/called_by -- rarely needed for navigation)
- `params` arrays on functions/methods
- `is_async` booleans
- Empty `decorators` arrays
- Full multi-line docstrings (replaced with first-line summary)

## Files Modified

- `/root/projects/tldr-swinton/src/tldr_swinton/modules/core/api.py` -- added `compact_extract()`
- `/root/projects/tldr-swinton/src/tldr_swinton/cli.py` -- added `--compact` flag + handler branch
- `/root/projects/tldr-swinton/.claude-plugin/hooks/post-read-extract.sh` -- switched to `--compact`
- `/root/projects/tldr-swinton/src/tldr_swinton/modules/core/mcp_server.py` -- added `compact` param to MCP tool
