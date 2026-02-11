---
name: tldrs-understand-symbol
description: "Use when asked about how a function or class works, what calls it, what it depends on, or before modifying/extending a symbol. Gets call graph, signatures, and callers in ~85% fewer tokens than reading the full file."
allowed-tools:
  - Bash
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

## Next Step

After reading the output:
1. If you need to edit the symbol, now Read the file (you know exactly where to look)
2. If you need broader context, increase `--depth 3`
3. For reverse impact analysis: `tldrs impact <symbol> --depth 3`

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

## Output Caps

If output is too large:
```bash
tldrs context <symbol> --project . --depth 2 --max-lines 50
```

## Depth Tuning

- `--depth 1`: direct calls only (minimal tokens)
- `--depth 2`: calls + their calls (default, usually sufficient)
- `--depth 3`: broad context (use for unfamiliar code)

## Common Errors

- **"Ambiguous entry"**: Multiple symbols match. Use `file.py:symbol` format.
- **"No symbols found"**: Symbol name doesn't match. Try `tldrs structure` to discover names.
- **Very large output**: Add `--max-lines 50` or reduce `--depth`.

## When to Skip

- You are editing a single file under 200 lines AND you already know which file it is
- You need the full implementation body, not architecture
