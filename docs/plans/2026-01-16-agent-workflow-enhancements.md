# Agent Workflow Enhancements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** `tldr-swinton-gfb` (Implement tldrs benchmark tracks) — mandatory line tying the plan to the active bead/Task Master item.

**Goal:** Expand `docs/agent-workflow.md` with missing instructions and one-line examples to help Codex/Claude use tldr-swinton effectively.

**Architecture:** Update the workflow doc only (Markdown). Add concise bullets with one-line example commands for: entry syntax, language flags, adjusting depth/budget, DiffLens compression, test impact helpers, call graph/import helpers, and VHS behavior notes.

**Tech Stack:** Markdown docs only.

### Task 1: Update workflow doc

**Files:**
- Modify: `docs/agent-workflow.md`

**Step 1: Edit doc content**

Add these sections/bullets with one-line examples:

- **Entry syntax & discovery**
  - Use `file.py:func`, `Class.method`, or `module:func` entries.
  - Example: `tldrs context src/app.py:handle_request --project .`
  - If unsure, run `tldrs structure src/` first to discover names.

- **Language flags**
  - Example: `tldrs structure src/ --lang typescript`
  - Example: `tldrs context src/main.rs:run --lang rust`

- **Budget/Depth tuning**
  - If context is thin: increase `--depth` (e.g., `--depth 3`).
  - If too large: reduce `--budget` or use `--format ultracompact`.
  - Example: `tldrs context <entry> --depth 3 --budget 1500 --format ultracompact`

- **DiffLens compression**
  - Example: `tldrs diff-context --project . --budget 1500 --compress two-stage`
  - Example: `tldrs diff-context --project . --budget 1500 --compress chunk-summary`

- **Impact/test selection**
  - Example: `tldrs change-impact --git --git-base HEAD~1`
  - Example: `tldrs change-impact --session --run`

- **Call graph/import helpers**
  - Example: `tldrs calls . --lang python`
  - Example: `tldrs impact authenticate --depth 3 --lang python`
  - Example: `tldrs importers tldr_swinton.api --lang python`

- **VHS behavior**
  - Note: `--output vhs` prints a ref + short summary/preview; the ref is what saves tokens.
  - Example: `tldrs context main --project . --output vhs`

Keep the doc concise and copy/pasteable.

**Step 2: Review for clarity**

Check for brevity and consistent formatting.

**Step 3: Commit**

```bash
git add docs/agent-workflow.md
git commit -m "docs: expand agent workflow guidance"
```

---

Plan complete and saved to `docs/plans/2026-01-16-agent-workflow-enhancements.md`.
Two execution options:
1. Subagent-Driven (this session)
2. Parallel Session (separate)

Which approach?
