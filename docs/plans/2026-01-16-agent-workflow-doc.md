# Agent Workflow Doc Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** `tldr-swinton-gfb` (Implement tldrs benchmark tracks) — mandatory line tying the plan to the active bead/Task Master item.

**Goal:** Create a full agent workflow document and link it from `README.md`, with a pointer in `AGENTS.md`/`CLAUDE.md` for agents to follow.

**Architecture:** Add `docs/agent-workflow.md` as a concise, step-by-step guide: install, tool selection decision tree, example commands, and VHS usage. Update `README.md` to link to the doc. Add a short note in `AGENTS.md` (and `CLAUDE.md` if present) telling agents to follow the workflow doc.

**Tech Stack:** Markdown docs only.

### Task 1: Add agent workflow document

**Files:**
- Create: `docs/agent-workflow.md`

**Step 1: Write the failing test**

Not applicable (docs-only change). Confirm with user if tests are required. Default: no tests.

**Step 2: Draft the workflow doc**

Include sections:
- Purpose + scope
- Install (tldrs + tldrs-vhs)
- Decision tree for tool choice
- Canonical commands (diff-context, context, structure/extract, find/index, slice/cfg/dfg)
- Output handling (vhs refs, budget, ultracompact)
- Troubleshooting (PATH, TLDRS_VHS_CMD, TLDRS_VHS_PYTHONPATH)

**Step 3: Review for clarity + brevity**

Ensure it’s short, agent-friendly, and copy/pasteable.

**Step 4: Commit**

```bash
git add docs/agent-workflow.md
git commit -m "docs: add agent workflow guide"
```

### Task 2: Link from README and reference from AGENTS/CLAUDE

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md` (if present)

**Step 1: Update README**

Add a short link near the Agent Snippets section:

```md
See `docs/agent-workflow.md` for the full step-by-step agent workflow.
```

**Step 2: Update AGENTS.md**

Add a short pointer line near the top (or tool usage section):

```md
For the full step-by-step agent workflow, see docs/agent-workflow.md.
```

**Step 3: Update CLAUDE.md (if present)**

Same line as AGENTS.md.

**Step 4: Commit**

```bash
git add README.md AGENTS.md CLAUDE.md
git commit -m "docs: link agent workflow guide"
```

---

Plan complete and saved to `docs/plans/2026-01-16-agent-workflow-doc.md`.
Two execution options:
1. Subagent-Driven (this session)
2. Parallel Session (separate)

Which approach?
