---
name: tldrs-understand-symbol
description: "Use BEFORE reading a file to understand a function or class. Gets call graph, signatures, and callers in ~85% fewer tokens than reading the full file."
---

# Understand a Symbol

Run this BEFORE reading a file when you need to understand a function or class.

## Command

```bash
tldrs context <symbol_name> --project . --depth 2 --format ultracompact --budget 2000
```

## Output

Shows signature, call graph, callers, and related types:

```
handle_request(request) -> Response
  calls: validate_input, process_data, format_response
  called_by: main, api_handler
  types: Request, Response
```

## Disambiguation

If ambiguous, tldrs returns candidates:

```
Ambiguous entry 'handle': found in 3 files
  src/api.py:handle_request
  src/ws.py:handle_message
  src/cli.py:handle_command
```

Re-run with qualified name: `tldrs context src/api.py:handle_request --project .`

## Discovering Symbol Names

If you don't know the symbol name:

```bash
tldrs structure src/path/to/dir/
```

## Reverse Call Graph (Who Calls This?)

```bash
tldrs impact authenticate --depth 3
```

## Depth Tuning

- `--depth 1`: direct calls only (minimal tokens)
- `--depth 2`: calls + their calls (default, usually sufficient)
- `--depth 3`: broad context (use for unfamiliar code)

## When to Skip

- You need the full code body to make an edit: just Read the file
- The file is < 200 lines: just Read it
- You need implementation details, not architecture
