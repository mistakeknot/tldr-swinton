# Agent Checklist Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** `tldr-swinton-gfb` (Implement tldrs benchmark tracks) — mandatory line tying the plan to the active bead/Task Master item.

**Goal:** Add a short agent workflow checklist to `AGENTS.md` immediately before “Module Selection (Agents)”.

**Architecture:** Docs-only change. Insert a concise checklist that points to `docs/agent-workflow.md` and reminds agents to start with DiffLens, use budgets, and only open full files for edits.

**Tech Stack:** Markdown only.

### Task 1: Add checklist section

**Files:**
- Modify: `AGENTS.md`

**Step 1: Edit AGENTS.md**

Insert a checklist section just before “## Module Selection (Agents)”, e.g.:

```
## Agent Workflow Checklist

- Read `docs/agent-workflow.md` first.
- Start with `tldrs diff-context --project . --budget 2000`.
- Use `tldrs context <entry>` with `--format ultracompact` and a budget.
- Use `tldrs structure` or `tldrs extract` to discover symbols before context.
- Only open full files when making edits.
```

**Step 2: Commit**

```bash
git add AGENTS.md
git commit -m "docs: add agent workflow checklist"
```

---

Plan complete and saved to `docs/plans/2026-01-16-agent-checklist-plan.md`.
Two execution options:
1. Subagent-Driven (this session)
2. Parallel Session (separate)

Which approach?
