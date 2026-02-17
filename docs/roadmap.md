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

- [TSW-N1] **Default low-cost code context source** — wire tldr-swinton into code-reading-heavy Clavain stages.
- [TSW-N2] **Clavain stage integration map** — add explicit entrypoint guidance for diff review and edits.
- [TSW-N3] **Context handoff metadata** — capture and expose retrieval mode and rationale.
- [TSW-N4] **Integration validation** — validate Clavain workflows against P2.1 success criteria.

## P2.2 — Closer parity with Clavain roadmap beads

- [TSW-N5] **Symbol-boundary truncation safety** — make truncation defaults preserve symbol boundaries.
- [TSW-N6] **`ultracompact` body depth control** — add `--depth=body` option for edit-focused summaries.
- [TSW-N7] **Source-aware slice mode** — include optional source snippets and better range summaries.
- [TSW-N8] **Cache-friendly run format** — add serialized outputs for repeated session reuse.

## P2.3 — Reliability and adoption polish

- [TSW-N9] **Adoption friction reduction** — clarify escalation ladders and cost hints in tool text.
- [TSW-N10] **MCP usage telemetry** — expand usage checks for first-party agent loops.
- [TSW-N11] **Bug-class mitigation loop** — keep solutions docs feedback in sync with releases.

## P2 — Scale and hardening

- [TSW-P1] **Long-context persistence** — persist + rehydrate context across iterative sessions.
- [TSW-P2] **Mixed-mode planner** — improve query routing between semantic and structural paths.
- [TSW-P3] **Architecture-risk benchmarks** — expand multi-file benchmarks beyond refactor workflows.
- [TSW-P4] **Latency-control envelopes** — guard against regressions under high-frequency loops.

## Progress gates

- **Gate 1 (P2.1):** measurable increase in Clavain task throughput with stable
  context quality.
- **Gate 2 (P2.2):** all referenced beads have implementation PRs and eval
  validations.
- **Gate 3 (P2.3):** selection-quality metrics show fewer raw-read fallbacks in
  real sessions.
- **Gate 4 (P2):** no regression in token savings and no drop in semantic retrieval
  quality.

## From Interverse Roadmap

Items from the [Interverse roadmap](../../../docs/roadmap.json) that involve this module:

No monorepo-level items currently reference this module.
