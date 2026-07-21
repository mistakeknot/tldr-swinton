---
name: tldrs-session-start
description: "Use for large or unfamiliar codebases, multi-file or diff-heavy changes, call-graph investigation, or reconnaissance that would flood the main context. Skip known small edits and simple docs/config changes."
context: fork
agent: Explore
allowed-tools:
  - Bash
---

# Adaptive Repository Reconnaissance

Inspect the current repository with tldrs and return a concise summary with specific files and symbols. Keep raw search results in this Explore context.

## Use tldrs when

- The repository or target area is unfamiliar.
- The change crosses multiple files or has a large diff.
- Callers, callees, data flow, or affected tests matter.
- The main conversation would otherwise accumulate search output or file contents.

## Skip tldrs when

- The exact target is already known and is a small file.
- The task is a simple docs, config, or one-line change.
- The parent harness already supplied a narrow, sufficient context packet.

## Decision tree

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

If the repository has no `src/`, choose the smallest relevant source directory instead of scanning the entire tree.

### 2. Is this a multi-turn task?

If you expect multiple rounds of queries on the same codebase:
```bash
# Add --session-id auto to ALL tldrs calls this session
tldrs diff-context --project . --preset compact --session-id auto
```

### 3. Identify targets

- `[contains_diff]` symbols → `tldrs context <symbol> --project . --preset compact`
- `[caller_of_diff]` symbols → check for breakage with `tldrs impact <symbol> --depth 3`
- Unknown area? → `tldrs find "query"`

### 4. Preparing a packet for another agent?

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

## Output

- Summarize the smallest useful file/symbol set; do not paste raw command output.
- Note unresolved ambiguity or a failed index explicitly.
- Recommend the next direct read or test command.
- Use `--preset minimal` for large diffs (>500 lines) or budget-constrained workers.

## Non-Python Repos

Add `--lang` flag: `tldrs diff-context --project . --preset compact --lang typescript`
