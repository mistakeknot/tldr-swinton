# tldr-swinton Roadmap

**Version:** 0.7.6  
**Last updated:** 2026-02-15  
**Vision:** [`docs/vision.md`](vision.md)  
**PRD:** [`docs/PRD.md`](PRD.md)

---

## Where We Are

tldr-swinton is the token-efficiency context layer for AI code workflows.
The product has:

- production-ready CLI + MCP surfaces,
- multi-language extraction,
- semantic search with backend selection (`faiss`, `colbert`),
- diff-aware context workflows,
- active eval wiring through `interbench` + `tldr-bench`.

Recent work (2026-01 to 2026-02) focused on:

- MCP capability hardening (`semantic_index`, `semantic_info`),
- hook/skill workflow hardening and adoption experiments,
- performance improvements through index reuse and extraction de-duplication,
- persistent compression options (`cache-friendly`, presets, and multi-turn support).

## What's Working

- **Structural extraction and orientation:** `structure`, `tree`, `extract` for fast
  symbol mapping.
- **Diff and symbol context:** `context`/`diff_context` with budget-aware packing.
- **Call/path understanding:** `impact`, `cfg`, `dfg`, `slice`, `calls`, `arch`, `dead`.
- **Semantic stack:** `semantic` + dual backends via `semantic_index` and
  `semantic_info`.
- **MCP-first usage:** 24 tools behind `tldr-code` with instruction text and
  command presets.
- **Evaluation automation:** `tldrs manifest`, interbench sync skill, and scripts.

## Ashpool eval status

### Status (current)

- **Harness:** integrated via interbench and repo-level manifest contract.
- **Track coverage:** command-format-flag combinations are mapped; sync checks detect
  gaps before release.
- **Signal quality:** token-efficiency, semantic retrieval, and agent workflow
  baselines are reproducible from `evals/`.
- **Operational note:** continued work is needed on agent selection-quality signals
  (tool usage quality, not just output quality).

### Known risks to close

- Tool selection quality can drift when new high-leverage features are added.
- Some workflows still rely on user or agent judgment for escalation (`ultracompact`
  vs deeper analysis modes).
- Cross-stack metrics are not yet a single dashboarded score.

## 2026 Roadmap

## P2.1 — Deep integration with Clavain (`iv-spad`)  
**Status:** planning / active alignment

This is the highest-impact next step and aligns with the Clavain P2.1 thread.

What to ship:

- Make tldr-swinton the default low-cost context source for Clavain stages that
  touch code.
- Add explicit "start here" integration in Clavain workflows:
  diff review, symbol edits, and research tasks.
- Track context handoff metadata so Clavain can reason about which retrieval mode was
  used and why.

### Deliverables

- Dedicated integration map between Clavain work stages and tldr-swinton entrypoints.
- End-to-end handoff contract for `diff-context` + `context` + `delegate`.
- Validation against P2.1 success criteria in Clavain workflows.

## P2.2 — Closer parity with Clavain roadmap beads

### `iv-ca5` — truncation should respect symbol boundaries

Improve truncation defaults and preview behavior so symbol-centric contexts preserve
boundary integrity.

### `iv-dsk` — ultracompact needs `--depth=body` variant

Add and validate deeper control over `ultracompact` body extraction depth to match
editing context needs.

### `iv-19m` — `slice` with source code option

Extend slice payloads with optional source inclusion and better line-range summaries
for agents needing exact edit surfaces.

### `iv-72c` — cache-friendly format in demo and docs

Add `cache-friendly` formatting and demo coverage so `tldr` runs can be reused across
repetitive sessions with predictable cost curves.

## P2.3 — Reliability and adoption polish

- Simplify the largest agent adoption gaps:
  clearer escalation ladder, stronger cost hints in tool descriptions,
  fewer false starts for retrieval mode selection.
- Expand `tldrs-interbench-sync` checks for new MCP-first usage signals.
- Continue bug-class mitigation from solutions docs (`workflow-issues/` and
  `performance-issues/`).

## P3 — Scale and hardening

- Expand long-context persistence and rehydration patterns.
- Improve query planning for mixed modes (`semantic` vs `structural_search`).
- Expand benchmark surfaces for multi-file refactor and architecture-risk tasks.
- Reduce latency regressions under large workspaces and high-frequency agent loops.

## Progress gates

- **Gate 1 (P2.1):** measurable increase in Clavain task throughput with stable
  context quality.
- **Gate 2 (P2.2):** all referenced beads have implementation PRs and eval
  validations.
- **Gate 3 (P2.3):** selection-quality metrics show fewer raw-read fallbacks in
  real sessions.
- **Gate 4 (P3):** no regression in token savings and no drop in semantic retrieval
  quality.
