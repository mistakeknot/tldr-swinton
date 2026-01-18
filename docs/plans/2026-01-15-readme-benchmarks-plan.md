# README Benchmarks Additions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Bead:** N/A (Task reference)

**Goal:** Add the most compelling benchmark results (token efficiency, semantic search, agent workflow) to the README with clear methodology and reproduction commands.

**Architecture:** Run the existing eval scripts to capture fresh numbers, then add a compact benchmark section to `README.md` with a per-eval summary table and short methodology notes. Keep the section stable and reproducible, and include commands to rerun.

**Tech Stack:** Python, eval scripts, Markdown

### Task 1: Capture fresh benchmark numbers

**Files:**
- Modify: `README.md`
- (No new code files)

**Step 1: Write the failing test**

N/A (documentation change).

**Step 2: Run evals to gather numbers**

Run:
```bash
.venv/bin/python evals/token_efficiency_eval.py
.venv/bin/python evals/semantic_search_eval.py
.venv/bin/python evals/agent_workflow_eval.py
```
Expected: scripts complete and print summary metrics (capture key numbers).

**Step 3: Record key metrics**

Extract the most representative figures (token savings, recall/quality, latency if reported).

**Step 4: Update README**

Add a “Benchmarks” section with:
- a compact table of the three evals
- a short methodology box defining baselines and scope
- reproduction commands

**Step 5: Commit**

```bash
git add README.md
git commit -m "docs: add benchmark results to README"
```

### Task 2: Verify formatting

**Files:**
- Modify: `README.md`

**Step 1: Review README section**

Confirm numbers are correct and phrasing is concise.

**Step 2: Commit (if needed)**

```bash
git status --porcelain
```
