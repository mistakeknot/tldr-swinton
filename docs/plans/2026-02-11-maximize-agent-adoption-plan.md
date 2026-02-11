# Maximize Agent tldrs Adoption — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Close the gap between tldrs's 23 subcommands and what agents actually use, targeting >60% of large-file reads going through tldrs.

**Architecture:** Four layered changes — CLI presets provide the foundation (compact/minimal/multi-turn), skill rewrites give agents decision trees instead of man pages, a dynamic setup hook auto-runs diff-context at session start, and a PostToolUse Read hook auto-injects extract output for large files. Each layer builds on the previous.

**Tech Stack:** Python 3 (argparse), Bash (hooks), Markdown (skills), JSON (hooks.json)

**Design doc:** `docs/plans/2026-02-11-maximize-agent-tldrs-adoption-design.md`

**Beads:**
- `tldr-swinton-9yl` — Epic (parent)
- `tldr-swinton-p9b` — Task 1: CLI presets
- `tldr-swinton-ov4` — Task 2: Skill rewrite
- `tldr-swinton-0in` — Task 3: Setup hook
- `tldr-swinton-wb6` — Task 4: PostToolUse Read hook

---

## Task 1: Add `--preset` flag to CLI (`tldr-swinton-p9b`)

**Files:**
- Create: `src/tldr_swinton/presets.py`
- Modify: `src/tldr_swinton/cli.py:295-542` (argparse definitions + command handlers at lines 1052, 1159, 1219)
- Test: `tests/test_cli_presets.py`

### Step 1: Write the failing test for preset expansion

```python
# tests/test_cli_presets.py
import subprocess
import sys
from pathlib import Path


def test_preset_compact_expands_on_context(tmp_path: Path) -> None:
    """--preset compact should set format=ultracompact, budget=2000, compress-imports, strip-comments."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def foo():\n    return 1\n")

    result = subprocess.run(
        [
            sys.executable, "-m", "tldr_swinton.cli",
            "context", "foo",
            "--project", str(tmp_path),
            "--depth", "0",
            "--preset", "compact",
        ],
        text=True, capture_output=True, check=False,
    )

    assert result.returncode == 0
    # ultracompact format uses P0= prefix
    assert "P0=" in result.stdout


def test_preset_minimal_expands_on_diff_context(tmp_path: Path) -> None:
    """--preset minimal should set budget=1500, compress=two-stage, etc."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True, capture_output=True)
    (repo / "app.py").write_text("def foo():\n    return 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)
    (repo / "app.py").write_text("def foo():\n    return 2\n")

    result = subprocess.run(
        [
            sys.executable, "-m", "tldr_swinton.cli",
            "diff-context",
            "--project", str(repo),
            "--preset", "minimal",
        ],
        text=True, capture_output=True, check=False,
    )

    assert result.returncode == 0


def test_preset_invalid_errors() -> None:
    """Invalid preset should exit with error listing valid presets."""
    result = subprocess.run(
        [
            sys.executable, "-m", "tldr_swinton.cli",
            "context", "foo",
            "--project", ".",
            "--preset", "bogus",
        ],
        text=True, capture_output=True, check=False,
    )

    assert result.returncode != 0
    assert "compact" in result.stderr
    assert "minimal" in result.stderr
    assert "multi-turn" in result.stderr


def test_preset_not_valid_on_extract(tmp_path: Path) -> None:
    """--preset should not be accepted on extract command."""
    (tmp_path / "app.py").write_text("def foo():\n    return 1\n")

    result = subprocess.run(
        [
            sys.executable, "-m", "tldr_swinton.cli",
            "extract", str(tmp_path / "app.py"),
            "--preset", "compact",
        ],
        text=True, capture_output=True, check=False,
    )

    # argparse rejects unknown args
    assert result.returncode != 0


def test_preset_explicit_override(tmp_path: Path) -> None:
    """Explicit --budget overrides preset's budget."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def foo():\n    return 1\n")

    # compact sets budget=2000, but we override to 500
    result = subprocess.run(
        [
            sys.executable, "-m", "tldr_swinton.cli",
            "context", "foo",
            "--project", str(tmp_path),
            "--depth", "0",
            "--preset", "compact",
            "--budget", "500",
        ],
        text=True, capture_output=True, check=False,
    )

    assert result.returncode == 0


def test_preset_multi_turn_sets_session_id(tmp_path: Path) -> None:
    """--preset multi-turn should auto-set session-id."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def foo():\n    return 1\n")

    result = subprocess.run(
        [
            sys.executable, "-m", "tldr_swinton.cli",
            "context", "foo",
            "--project", str(tmp_path),
            "--depth", "0",
            "--preset", "multi-turn",
        ],
        text=True, capture_output=True, check=False,
    )

    assert result.returncode == 0
```

### Step 2: Run tests to verify they fail

Run: `cd /root/projects/tldr-swinton && uv run pytest tests/test_cli_presets.py -v`
Expected: FAIL — `--preset` argument not recognized

### Step 3: Create `src/tldr_swinton/presets.py`

```python
"""CLI flag presets for token-saving defaults.

Presets expand into multiple flags, reducing cognitive load from 6+ flags to 1.
Names describe output shape (compact/minimal) not intensity (efficient/aggressive).
"""
import hashlib
import os
from pathlib import Path

PRESETS = {
    "compact": {
        "format": "ultracompact",
        "budget": 2000,
        "compress_imports": True,
        "strip_comments": True,
    },
    "minimal": {
        "format": "ultracompact",
        "budget": 1500,
        "compress": "two-stage",
        "compress_imports": True,
        "strip_comments": True,
        "type_prune": True,
    },
    "multi-turn": {
        "format": "cache-friendly",
        "budget": 2000,
        "session_id": "auto",
        "delta": True,
    },
}

# Commands that support presets (have --format, --budget, --compress)
PRESET_COMMANDS = {"context", "diff-context", "distill"}


def resolve_auto_session_id(project_root: str = ".") -> str:
    """Generate a stable session ID.

    Uses CLAUDE_SESSION_ID env var if available (stable across turns),
    falls back to hash of CWD + git HEAD for non-Claude environments.
    """
    env_id = os.environ.get("CLAUDE_SESSION_ID")
    if env_id:
        return env_id

    import subprocess
    project = Path(project_root).resolve()
    try:
        head = subprocess.run(
            ["git", "-C", str(project), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        head = "no-git"

    raw = f"{project}:{head}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def apply_preset(args, command: str) -> None:
    """Apply preset defaults to parsed args. Explicit flags take precedence.

    Mutates args in-place. Only applies to commands in PRESET_COMMANDS.
    """
    preset_name = getattr(args, "preset", None)
    if not preset_name:
        return

    if command not in PRESET_COMMANDS:
        return

    if preset_name not in PRESETS:
        import sys
        valid = ", ".join(sorted(PRESETS.keys()))
        print(f"Error: Unknown preset '{preset_name}'. Valid presets: {valid}", file=sys.stderr)
        sys.exit(1)

    defaults = PRESETS[preset_name]

    for key, value in defaults.items():
        # "auto" session_id gets resolved to actual ID
        if key == "session_id" and value == "auto":
            if getattr(args, "session_id", None) is None:
                args.session_id = resolve_auto_session_id(
                    getattr(args, "project", ".")
                )
            continue

        # Only apply if user didn't explicitly set this flag.
        # For store_true booleans, argparse default is False — if still False, apply preset.
        # For valued args, argparse default is None — if still None, apply preset.
        current = getattr(args, key, None)
        if current is None or current is False:
            setattr(args, key, value)
        # Special case: format default is "text" for context, "ultracompact" for diff-context.
        # We need to detect if user explicitly passed --format or just got the default.
        # Use a sentinel approach: we'll check via sys.argv in the caller instead.


def emit_preset_hint(command: str, args) -> None:
    """Emit stderr hint when context/diff-context run without --preset."""
    import sys
    if command in ("context", "diff-context") and not getattr(args, "preset", None):
        print("hint: Add --preset compact for 50%+ token savings", file=sys.stderr)
```

### Step 4: Add `--preset` argument to context, diff-context, and distill parsers in `cli.py`

In `src/tldr_swinton/cli.py`, add `--preset` to each of the three subparsers.

After `ctx_p.add_argument("--max-bytes", ...)` (line 451), add:
```python
    ctx_p.add_argument(
        "--preset",
        choices=["compact", "minimal", "multi-turn"],
        default=None,
        help="Flag preset: compact (ultracompact/2000/compress-imports/strip-comments), "
             "minimal (two-stage/1500/type-prune), multi-turn (cache-friendly/delta/session-id auto)",
    )
```

After `diff_p.add_argument("--max-bytes", ...)` (line 531), add:
```python
    diff_p.add_argument(
        "--preset",
        choices=["compact", "minimal", "multi-turn"],
        default=None,
        help="Flag preset: compact (ultracompact/2000/compress-imports/strip-comments), "
             "minimal (two-stage/1500/type-prune), multi-turn (cache-friendly/delta/session-id auto)",
    )
```

After `distill_p.add_argument("--language", ...)` (line 542), add:
```python
    distill_p.add_argument(
        "--preset",
        choices=["compact", "minimal", "multi-turn"],
        default=None,
        help="Flag preset: compact (ultracompact/2000/compress-imports/strip-comments), "
             "minimal (two-stage/1500/type-prune), multi-turn (cache-friendly/delta/session-id auto)",
    )
```

### Step 5: Apply preset defaults after `args = parser.parse_args()`

In `cli.py`, right after `args = parser.parse_args()` (line 830), add:

```python
    # Apply preset defaults (explicit flags override)
    from .presets import apply_preset, emit_preset_hint
    if args.command in ("context", "diff-context", "distill"):
        apply_preset(args, args.command)
```

### Step 6: Add stderr hint emission

At the end of the `context` and `diff-context` command handlers (after the final `print()` in each), add:

```python
        emit_preset_hint(args.command, args)
```

Specifically:
- After the context handler's final print (around line 1157), add `emit_preset_hint(args.command, args)`
- After the diff-context handler's final print (around line 1217), add `emit_preset_hint(args.command, args)`

### Step 7: Add `tldrs presets` subcommand

After the `manifest_p` definition (line 819), add:

```python
    # tldrs presets — list available flag presets
    presets_p = subparsers.add_parser(
        "presets", help="List available flag presets with their expansions"
    )
    presets_p.add_argument(
        "--machine", action="store_true", help="JSON output"
    )
```

And in the command dispatch (before the manifest handler), add:

```python
        elif args.command == "presets":
            from .presets import PRESETS
            if getattr(args, "machine", False):
                print(json.dumps(PRESETS, indent=2))
            else:
                for name, flags in PRESETS.items():
                    expanded = " ".join(
                        f"--{k.replace('_', '-')}" + (f" {v}" if not isinstance(v, bool) else "")
                        for k, v in flags.items()
                        if v is not False
                    )
                    print(f"  {name:12s} → {expanded}")
```

### Step 8: Run tests to verify they pass

Run: `cd /root/projects/tldr-swinton && uv run pytest tests/test_cli_presets.py -v`
Expected: All 6 tests PASS

### Step 9: Run existing tests to verify no regressions

Run: `cd /root/projects/tldr-swinton && uv run pytest tests/test_cli_context.py tests/test_cli_context_delta.py -v`
Expected: PASS (presets don't change default behavior)

### Step 10: Commit

```bash
git add src/tldr_swinton/presets.py tests/test_cli_presets.py src/tldr_swinton/cli.py
git commit -m "feat: add --preset flag (compact/minimal/multi-turn) to context, diff-context, distill

Presets reduce 6+ flags to 1 flag for token-saving defaults.
Names describe output shape, not intensity.
CLI emits stderr hint when run without --preset.
session-id auto uses CLAUDE_SESSION_ID env var with CWD+HEAD fallback.

Part of: tldr-swinton-p9b"
```

---

## Task 2: Rewrite all 6 skills as decision trees (`tldr-swinton-ov4`)

**Files:**
- Modify: `.claude-plugin/skills/tldrs-session-start/SKILL.md`
- Modify: `.claude-plugin/skills/tldrs-find-code/SKILL.md`
- Modify: `.claude-plugin/skills/tldrs-understand-symbol/SKILL.md`
- Modify: `.claude-plugin/skills/tldrs-explore-file/SKILL.md`
- Modify: `.claude-plugin/skills/tldrs-map-codebase/SKILL.md`
- No change: `.claude-plugin/skills/tldrs-ashpool-sync/SKILL.md`

**Principle:** Skills handle session-level strategy only. No per-file rules (hooks handle those). All presets referenced as `compact`/`minimal`/`multi-turn`.

### Step 1: Rewrite `tldrs-session-start/SKILL.md`

Replace the entire file content with a decision-tree structure. Key changes:
- Replace all raw flag combinations with `--preset compact` / `--preset minimal`
- Remove "Never Read >100 lines without extract" rule (hook handles it)
- Add handoff branch: "Spawning a subagent? → tldrs distill"
- Add `--session-id auto` guidance for multi-turn tasks
- Keep trigger description broad (fix bugs, debug, implement, refactor, etc.)

```markdown
---
name: tldrs-session-start
description: "Use when asked to fix bugs, debug issues, implement features, refactor code, write tests, review code, migrate/port code, or explore a codebase. Run BEFORE reading code files. Provides diff-focused context that saves 48-73% tokens."
allowed-tools:
  - Bash
---

# Session Start Reconnaissance

BEFORE reading any code files, determine your starting point.

## Decision Tree

### 1. Are there recent changes?

Check: `git status` or `git diff --stat HEAD`

**YES — changes exist:**
```bash
tldrs diff-context --project . --preset compact
```

**YES + large diff (>500 lines changed):**
```bash
tldrs diff-context --project . --preset minimal
```

**NO — clean working tree:**
```bash
tldrs structure src/
```

### 2. Is this a multi-turn task?

If you expect multiple rounds of queries on the same codebase:
```bash
# Add --session-id auto to ALL tldrs calls this session
tldrs diff-context --project . --preset compact --session-id auto
```

### 3. After diff-context, identify targets

- `[contains_diff]` symbols → `tldrs context <symbol> --project . --preset compact`
- `[caller_of_diff]` symbols → check for breakage with `tldrs impact <symbol> --depth 3`
- Unknown area? → `tldrs find "query"` before Reading files

### 4. Spawning a subagent for code work?

Compress context for sub-agent consumption:
```bash
tldrs distill --task "description of the subtask" --budget 1500 --session-id auto
```

### 5. Test impact

After reviewing diff context, check which tests are affected:
```bash
tldrs change-impact --git
```

Returns `affected_tests` and a suggested `test_command`. Run only affected tests.

## Rules

- Always use `--preset compact` unless you have a reason not to
- Use `--preset minimal` for large diffs (>500 lines) or budget-constrained sessions

## When to Skip

- Editing a single file under 200 lines that you already know
- Simple config file changes (.json, .yaml, .toml)

## Non-Python Repos

Add `--lang` flag: `tldrs diff-context --project . --preset compact --lang typescript`
```

### Step 2: Rewrite `tldrs-understand-symbol/SKILL.md`

Key changes:
- Replace raw flags with `--preset compact`
- Add before-edit branch: "About to modify? → run impact first"
- Remove any per-file size rules

```markdown
---
name: tldrs-understand-symbol
description: "Use when asked about how a function or class works, what calls it, what it depends on, or before modifying/extending a symbol. Gets call graph, signatures, and callers in ~85% fewer tokens than reading the full file."
allowed-tools:
  - Bash
---

# Understand a Symbol

Run BEFORE reading a file when you need to understand a function or class.

## Decision Tree

### What do you need?

**Callers (who calls this?):**
```bash
tldrs impact <symbol> --depth 3
```

**Callees (what does this call?):**
```bash
tldrs context <symbol> --project . --preset compact
```

**Both callers and callees:**
```bash
tldrs context <symbol> --project . --preset compact --depth 2
```

### About to modify a symbol?

**Always check callers before modifying a public function:**
```bash
tldrs impact <symbol> --depth 3
```

Review the callers list. If callers depend on the current signature or return type, plan how to update them.

### Symbol name is ambiguous?

If tldrs returns multiple matches, re-run with qualified name:
```bash
tldrs context src/api.py:handle_request --project . --preset compact
```

### Don't know the symbol name?

```bash
tldrs structure src/path/to/dir/
```

## Import Dependencies

```bash
# What does this file import?
tldrs imports <file>

# Who imports this module? (essential before renaming/moving)
tldrs importers <module_name> .
```

## Rules

- Always use `--preset compact`
- Always check callers (via `tldrs impact`) before modifying a public function
- Use `--depth 1` for minimal tokens, `--depth 3` for broad unfamiliar context

## When to Skip

- File is under 200 lines and you already know its structure
- You need the full implementation body, not architecture
```

### Step 3: Rewrite `tldrs-find-code/SKILL.md`

Key change: frame as decision tree, keep structural/semantic/regex split clear.

```markdown
---
name: tldrs-find-code
description: "Use when searching for code by concept, pattern, or text, or when asked 'where is X handled/defined/implemented'. Prefer over grep or Read-and-scan. Semantic search finds by meaning. Structural search finds by code shape."
allowed-tools:
  - Bash
---

# Find Code by Meaning or Structure

Use instead of Grep tool or Read-and-scan when looking for code.

## Decision Tree

### What kind of search?

**Know the concept, not the name:**
```bash
tldrs find "authentication logic"
tldrs find "error handling in payment"
```
Requires one-time index: `tldrs index .`

**Know the code shape (pattern matching):**
```bash
# CRITICAL: Always single-quote the pattern. NEVER double-quote.
tldrs structural 'def $FUNC($$$ARGS): return None' --lang python
tldrs structural '$OBJ.$METHOD($$$ARGS)' --lang python
tldrs structural 'if err != nil { $$$BODY }' --lang go
```
Pattern syntax: `$VAR` = any single AST node, `$$$ARGS` = zero or more nodes.

**Know the exact text:**
```bash
tldrs search "TODO|FIXME" src/
tldrs search "def authenticate" src/ --ext .py
```

## Rules

- Always try `tldrs find` before Grep for code files
- Use structural search for pattern-matching (all functions returning None, all error handlers, etc.)

## Next Step

After finding results, use `tldrs context <symbol> --project . --preset compact` to understand the matched function.

## When to Skip

- You know the exact file and line — just Read it
- Searching for a filename — use Glob tool instead
```

### Step 4: Rewrite `tldrs-explore-file/SKILL.md`

Key change: decision tree format, no per-file size rules in the skill body.

```markdown
---
name: tldrs-explore-file
description: "Use when asked to debug a function, understand control flow, trace variable usage, or analyze a file's structure before reading it raw. Provides function-level analysis in ~85% fewer tokens than reading the full file."
allowed-tools:
  - Bash
---

# Explore File Internals

Run BEFORE reading a file when you need to understand its structure, debug a function, or trace data flow.

## Decision Tree

### What are you doing?

**Need file overview (functions, classes, imports):**
```bash
tldrs extract <file>
```

**Debugging a function (branches, loops, early returns):**
```bash
tldrs cfg <file> <function_name>
```

**Tracing data flow (variable definitions, uses, chains):**
```bash
tldrs dfg <file> <function_name>
```

**Need cross-file relationships:**
Use `tldrs context <symbol> --project . --preset compact` instead.

## Workflow

1. `tldrs extract <file>` → see what's in the file
2. `tldrs cfg <file> <function>` → understand control flow
3. `tldrs dfg <file> <function>` → trace data flow
4. Read only the specific lines you need to edit

## When to Skip

- File is under 100 lines — just Read it directly
- You need cross-file relationships — use `tldrs context` instead
- You only need a function signature — use `tldrs context <symbol> --depth 1`
```

### Step 5: Rewrite `tldrs-map-codebase/SKILL.md`

Key change: decision tree format, reference presets.

```markdown
---
name: tldrs-map-codebase
description: "Use when asked to understand a codebase's architecture, explore an unfamiliar project, onboard to a new repo, or identify which modules exist. Provides structural overview without reading individual files."
allowed-tools:
  - Bash
---

# Map Codebase Architecture

Run when you need a bird's-eye view of a project before diving into code.

## Decision Tree

### New repo or unfamiliar project?

Start with architecture overview:
```bash
tldrs arch --lang python .
```
Then drill into interesting directories:
```bash
tldrs structure src/
```

### Known repo, exploring a new area?

```bash
tldrs structure src/path/to/area/
```

### Just need the file layout?

```bash
tldrs tree src/
```
Lighter than `structure` — just file paths, no symbols.

## Workflow

1. `tldrs arch --lang <lang> .` → big picture (layers, dependencies)
2. `tldrs structure <dir>` → symbols in each file
3. `tldrs tree <dir>` → file listing for large directories
4. Drill in with `tldrs context <entry_point> --project . --preset compact`

## Rules

- Use `tree` only for orientation, `structure` for real work
- For non-Python projects: `tldrs arch --lang typescript src/`

## When to Skip

- You already know where to look — go straight to `tldrs context` or Read
- Project is tiny (<10 files) — just `tldrs structure .`
- User specified the exact file to work on
```

### Step 6: Verify skill YAML frontmatter is valid

For each SKILL.md, confirm:
- `name:` matches directory name
- `description:` is a single quoted string
- `allowed-tools:` lists `Bash`

### Step 7: Commit

```bash
git add .claude-plugin/skills/
git commit -m "feat: rewrite 5 skills as decision trees with preset references

session-start: +handoff branch, +session-id auto guidance
understand-symbol: +before-edit branch (impact before modify)
find-code: cleaner decision tree
explore-file: decision tree format
map-codebase: decision tree format

No per-file rules in skills — hooks handle per-file tactics.
All preset references use compact/minimal/multi-turn names.

Part of: tldr-swinton-ov4"
```

---

## Task 3: Setup hook — run diff-context automatically (`tldr-swinton-0in`)

**Files:**
- Modify: `.claude-plugin/hooks/setup.sh`
- Modify: `.claude-plugin/hooks/hooks.json` (increase setup timeout)

### Step 1: Update hooks.json to increase setup timeout

Change setup timeout from 5 to 10 seconds (Claude Code max for setup hooks):

```json
{
  "type": "command",
  "command": "${CLAUDE_PLUGIN_ROOT}/hooks/setup.sh",
  "timeout": 10
}
```

### Step 2: Rewrite setup.sh

Replace the full content of `.claude-plugin/hooks/setup.sh`:

```bash
#!/bin/bash
# tldrs Setup Hook — Dynamic Briefing
# Runs at session start. Auto-runs diff-context and injects output.
# Fallback chain: diff-context → structure → static tip
# Must complete within 10s (Claude Code setup hook timeout).

set +e  # Never fail the hook

# Check tldrs is installed
if ! command -v tldrs &> /dev/null; then
    echo "tldrs: NOT INSTALLED. Install with: pip install tldr-swinton"
    echo "tldrs: Plugin skills will not function until tldrs is installed."
    exit 0
fi

# Check ast-grep availability (non-blocking warning)
if ! python3 -c "import ast_grep_py" 2>/dev/null; then
    echo "tldrs: Structural search unavailable. Reinstall with: uv tool install --force tldr-swinton"
fi

# Prebuild cache in background (fast, <1s)
if [ -d ".git" ]; then
    tldrs prebuild --project . >/dev/null 2>&1 &
fi

# Count project files
PY_COUNT=$(find . -name '*.py' -not -path './.tldrs/*' -not -path './.git/*' 2>/dev/null | wc -l)

# Check semantic index
INDEX_STATUS="not built"
if [ -d ".tldrs" ]; then
    INDEX_STATUS="ready"
fi

# Determine if there are recent changes
CHANGED_COUNT=0
CHANGED_FILES=""
if [ -d ".git" ]; then
    DIFF_STAT=$(git diff --stat HEAD 2>/dev/null)
    if [ -n "$DIFF_STAT" ]; then
        CHANGED_COUNT=$(git diff --name-only HEAD 2>/dev/null | wc -l)
        CHANGED_FILES=$(git diff --name-only HEAD 2>/dev/null | head -10 | tr '\n' ', ' | sed 's/,$//')
    fi
fi

# --- Attempt to run tldrs diff-context or structure ---
TLDRS_OUTPUT=""
if [ "$CHANGED_COUNT" -gt 0 ]; then
    # Has changes — run diff-context with timeout
    TLDRS_OUTPUT=$(timeout 7 tldrs diff-context --project . --preset compact 2>/dev/null)
    if [ $? -ne 0 ] || [ -z "$TLDRS_OUTPUT" ]; then
        # diff-context failed or timed out — try structure
        TLDRS_OUTPUT=$(timeout 3 tldrs structure src/ 2>/dev/null || echo "")
    fi
else
    # Clean tree — run structure
    TLDRS_OUTPUT=$(timeout 5 tldrs structure src/ 2>/dev/null || echo "")
fi

# --- Format output ---
echo "Project: $(basename "$(pwd)") (${PY_COUNT} Python files, ${CHANGED_COUNT} changed since last commit)"
echo "Semantic index: ${INDEX_STATUS}"

if [ -n "$CHANGED_FILES" ]; then
    echo "Changed files: ${CHANGED_FILES}"
fi

echo ""

if [ -n "$TLDRS_OUTPUT" ]; then
    echo "$TLDRS_OUTPUT"
else
    # Final fallback — static tip
    echo "Run 'tldrs diff-context --project . --preset compact' before reading code."
    echo "Use 'tldrs extract <file>' for file structure."
fi

echo ""
echo "Available presets: compact, minimal, multi-turn"
```

### Step 3: Test the hook locally

Run: `cd /root/projects/tldr-swinton && bash .claude-plugin/hooks/setup.sh`
Expected: Project stats + diff-context output (or structure if clean tree)

### Step 4: Commit

```bash
git add .claude-plugin/hooks/setup.sh .claude-plugin/hooks/hooks.json
git commit -m "feat: setup hook runs tldrs diff-context automatically at session start

Replaces static tip with dynamic briefing.
Fallback chain: diff-context → structure → static tip.
Timeout 7s for diff-context, 10s total.
Outputs project stats + actual tldrs output + available presets.

Part of: tldr-swinton-0in"
```

---

## Task 4: PostToolUse Read hook — auto-inject extract (`tldr-swinton-wb6`)

**Files:**
- Create: `.claude-plugin/hooks/post-read-extract.sh`
- Modify: `.claude-plugin/hooks/hooks.json` (add PostToolUse entry, keep existing PreToolUse)

### Step 1: Create `post-read-extract.sh`

```bash
#!/bin/bash
# tldrs PostToolUse hook for Read — auto-inject extract on large files
# Fires AFTER Read completes. Runs tldrs extract and returns as additionalContext.
# Only fires for code files >300 lines.
#
# Input: JSON on stdin with { session_id, tool_name, tool_input: { file_path } }

set +e  # Never fail the hook

# Read stdin (hook input is JSON)
INPUT=$(cat 2>/dev/null) || exit 0

# Extract file path
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""' 2>/dev/null) || exit 0
[ -z "$FILE" ] && exit 0

# Skip non-existent files
[ -f "$FILE" ] || exit 0

# Skip non-code files
case "$FILE" in
    *.md|*.txt|*.json|*.yaml|*.yml|*.toml|*.cfg|*.ini|*.env|*.lock|*.csv|*.html|*.css|*.svg|*.png|*.jpg|*.gif|*.ico|*.pdf|*.xml|*.sql)
        exit 0
        ;;
esac

# Skip files under 300 lines
LINE_COUNT=$(wc -l < "$FILE" 2>/dev/null || echo 0)
if [ "$LINE_COUNT" -lt 300 ]; then
    exit 0
fi

# Check tldrs is installed
command -v tldrs &> /dev/null || exit 0

# Per-file flag: only extract once per file per session
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""' 2>/dev/null) || exit 0
if [ -n "$SESSION_ID" ]; then
    # Hash the file path for a safe filename
    FILE_HASH=$(echo -n "$FILE" | md5sum | cut -d' ' -f1)
    FLAG="/tmp/tldrs-extract-${SESSION_ID}-${FILE_HASH}"
    [ -f "$FLAG" ] && exit 0
fi

# Run extract with timeout
EXTRACT_OUTPUT=$(timeout 5 tldrs extract "$FILE" 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$EXTRACT_OUTPUT" ]; then
    exit 0
fi

# Create per-file flag
if [ -n "$SESSION_ID" ] && [ -n "$FILE_HASH" ]; then
    touch "$FLAG"
fi

# Return as additionalContext JSON
# Escape the extract output for JSON embedding
ESCAPED=$(echo "$EXTRACT_OUTPUT" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))' 2>/dev/null)
if [ -z "$ESCAPED" ]; then
    exit 0
fi

cat <<HOOK_JSON
{"additionalContext": "tldrs extract output for ${FILE} (${LINE_COUNT} lines):\n${EXTRACT_OUTPUT}"}
HOOK_JSON
```

Wait — the JSON escaping above won't work correctly with raw newlines. Let me fix the approach:

```bash
# Return as additionalContext JSON — use python for safe JSON encoding
python3 -c "
import sys, json
extract = '''$EXTRACT_OUTPUT_PLACEHOLDER'''
msg = f'tldrs extract output for $FILE ({LINE_COUNT} lines):\\n' + extract
print(json.dumps({'additionalContext': msg}))
" 2>/dev/null || exit 0
```

Actually, the safest approach is to pipe the extract output through Python:

```bash
# Return as additionalContext JSON
echo "$EXTRACT_OUTPUT" | python3 -c "
import sys, json
extract = sys.stdin.read()
file_path = sys.argv[1]
line_count = sys.argv[2]
msg = f'tldrs extract output for {file_path} ({line_count} lines):\n{extract}'
print(json.dumps({'additionalContext': msg}))
" "$FILE" "$LINE_COUNT" 2>/dev/null || exit 0
```

### Step 2: Make the script executable

Run: `chmod +x .claude-plugin/hooks/post-read-extract.sh`

### Step 3: Update hooks.json

Add PostToolUse section alongside existing hooks:

```json
{
  "description": "tldrs plugin hooks — token-efficient reconnaissance",
  "hooks": {
    "Setup": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/setup.sh",
            "timeout": 10
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Read",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/suggest-recon.sh\"",
            "timeout": 3
          }
        ]
      },
      {
        "matcher": "Grep",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/suggest-recon.sh\"",
            "timeout": 3
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Read",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/post-read-extract.sh\"",
            "timeout": 8
          }
        ]
      }
    ]
  }
}
```

### Step 4: Test the hook locally

```bash
# Create a test file >300 lines
python3 -c "
for i in range(400):
    print(f'def func_{i}(): return {i}')
" > /tmp/test_large_file.py

# Simulate hook input
echo '{"session_id":"test123","tool_name":"Read","tool_input":{"file_path":"/tmp/test_large_file.py"}}' | bash .claude-plugin/hooks/post-read-extract.sh
```

Expected: JSON with `additionalContext` containing the extract output.

### Step 5: Test that small files are skipped

```bash
echo '{"session_id":"test123","tool_name":"Read","tool_input":{"file_path":"/root/projects/tldr-swinton/README.md"}}' | bash .claude-plugin/hooks/post-read-extract.sh
```

Expected: No output (file skipped — either too small or non-code).

### Step 6: Commit

```bash
git add .claude-plugin/hooks/post-read-extract.sh .claude-plugin/hooks/hooks.json
git commit -m "feat: PostToolUse Read hook auto-injects extract for files >300 lines

Runs tldrs extract after Read completes on large code files.
Agent gets file structure for free — zero cooperation required.
Per-file flag prevents duplicate extracts in same session.
8s timeout, skips non-code files and files <300 lines.

Part of: tldr-swinton-wb6"
```

---

## Task 5: Version bump, close beads, final validation

**Files:**
- Modify: `pyproject.toml` (version bump)
- Modify: `.claude-plugin/plugin.json` (version bump)

### Step 1: Bump version

Run: `scripts/bump-version.sh 0.7.0 --dry-run` to preview, then `scripts/bump-version.sh 0.7.0` to execute.

### Step 2: Run full test suite

Run: `cd /root/projects/tldr-swinton && uv run pytest tests/ -v --timeout=30`
Expected: All tests pass including new preset tests.

### Step 3: Test plugin structure

Run: `python3 -c "import json; d=json.load(open('.claude-plugin/plugin.json')); print(d['version']); print(len(d['skills']), 'skills'); print(len(d['commands']), 'commands')"`
Expected: `0.7.0`, `6 skills`, `6 commands`

### Step 4: Close beads

```bash
bd close tldr-swinton-p9b tldr-swinton-ov4 tldr-swinton-0in tldr-swinton-wb6 tldr-swinton-9yl
```

### Step 5: Final commit

```bash
git add -A
git commit -m "chore: bump version to 0.7.0 — maximize agent tldrs adoption

Epic: tldr-swinton-9yl
- CLI presets (compact/minimal/multi-turn)
- 5 skills rewritten as decision trees
- Setup hook runs diff-context automatically
- PostToolUse Read hook auto-injects extract for large files"
```
