---
name: tldrs-interbench-sync
description: "Sync interbench eval coverage with tldrs capabilities. Run when tldrs gains new formats, flags, or commands. Reads the tldrs manifest as ground truth and generates minimal targeted edits to 4 interbench files."
allowed-tools:
  - Bash
  - Read
  - Edit
---

# interbench Sync Protocol

Sync interbench's eval coverage with the current tldrs capabilities.

## Step 1: Get ground truth

```bash
tldrs manifest --pretty
```

Save this output — it is the single source of truth for all tldrs capabilities.

## Step 2: Run gap detection

```bash
tldrs manifest | python3 /root/projects/Interverse/infra/interbench/scripts/check_tldrs_sync.py
```

If exit 0: report "interbench is in sync" and stop.
If exit 1: continue with the gaps listed.

## Step 3: Read target files

Read ALL 4 files to understand existing patterns before editing:

- `/root/projects/Interverse/infra/interbench/scripts/regression_suite.json`
- `/root/projects/Interverse/infra/interbench/scripts/ab_formats.py`
- `/root/projects/Interverse/infra/interbench/demo-tldrs.sh`
- `/root/projects/Interverse/infra/interbench/scripts/score_tokens.py`

## Step 4: Generate edits for each gap

### regression_suite.json patterns

Each query entry follows this pattern:
```json
{
    "name": "{command}_{qualifier}",
    "description": "Human-readable description",
    "command": ["command", "entry_or_flags...", "--format", "fmt"],
    "metadata": {"tool": "tldrs", "command": "cmd", ...}
}
```

- For (command, format) gaps: add a query using `truncate_output` as the default entry
- For boolean flag gaps: add a query combining the flag with `--format ultracompact`
- For zoom level gaps: add a query with `--zoom Lx --format ultracompact`
- `command_raw` (with `{project}` placeholder) is only for `slice` since it needs absolute paths

### ab_formats.py patterns

The `DEFAULT_FORMATS` list should contain all formats from the `context` command. Add missing formats to the list in the existing style:
```python
DEFAULT_FORMATS = ["ultracompact", "text", "cache-friendly", "packed-json", "columnar-json"]
```

### demo-tldrs.sh patterns

Each demo run block follows this pattern:
```bash
# -- Run N: Description --
echo "-- Run N: description --"
"$ASHPOOL" run \
  -m tool=tldrs \
  -m command=context \
  -m entry=truncate_output \
  -m format=FORMAT_NAME \
  -- $TLDRS context truncate_output \
       --project "$TLDRS_PROJECT" \
       --format FORMAT_NAME
echo
```

Add new run blocks before the `# -- Summary --` section. Increment the run number.

### score_tokens.py patterns

For scoring hints with metrics, add a `parse_*` function following the existing pattern:
```python
def parse_FORMAT_NAME(context: str) -> dict | None:
    """Extract SIGNAL from tldrs FORMAT output."""
    # Parse the signal from context
    ...
```

Only add parsers for formats listed in `scoring_hints` that have non-empty `metrics`.

## Step 5: Verify

After all edits, re-run the sync check:

```bash
tldrs manifest | python3 /root/projects/Interverse/infra/interbench/scripts/check_tldrs_sync.py
```

Report the result. Exit 0 means all gaps are covered.

## Common Errors

- Do NOT add entries for non-eval commands (tree, search, imports, etc.)
- Do NOT modify manifest.py — it is the source of truth, not a target
- Do NOT remove existing entries — only add missing ones
- For diff-context formats, note it has `json` and `json-pretty` which context does not
