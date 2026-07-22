# Ideas Backlog

## Promising

- [~] External issue replays: Python and Go pinned corpus built; TypeScript and
  Rust remain future expansion.
- [~] Cross-model confirmation: Codex and Claude Code harnesses ready; paid
  matrix pending.
- [~] `max_chars` ablation below the current 3 × 6000 default: 3000 and 1500
  trials queued after the 6000 smoke gate.
- [~] Isolate packet versus validated-runtime effects on the external corpus.
- [x] Native Codex and Claude Code pre-invocation adapters; MCP remains future
  middleware work.
- [ ] Negative-control utility gate only if a larger sample shows packet cost.
- [ ] Stable handles + read deduplication if packet/native replay reappears.
- [ ] Local reranker only after deterministic ranking plateaus.

## Tried

- [x] Current adaptive CLI guidance — -11.9% median eligible savings; discard as default.
- [x] Current `distill` as injected packet — no concrete targets on known owner failure.
- [x] Current semantic `find` — unavailable backend in installed runtime.
- [x] Current broad routing guidance — rejected: -35.8% eligible median savings
  and a refactor correctness loss.
- [x] Tool exposure without workspace routing — rejected: no adoption on two
  eligible tasks, spontaneous failed adoption on the hard refactor, -37.0%
  eligible median savings.
- [x] Strict one-shot routing — correctness retained and owner recall restored,
  but rejected for savings at -11.8% eligible median.
- [x] Automatic bounded context packet — retain: 4/4 correct, 12/12 offline
  top-three owner recall, +24.2% eligible median savings, and +45.2% on the
  owner-sensitive refactor.
- [x] Validated test runtime — corrected screen passed 4/4 with +45.0% eligible
  median savings; virtualenv symlinks must not be dereferenced.
- [x] Full packet + runtime confirmation — retain: 36/36 vs 35/36 baseline,
  +32.1% eligible median savings (95% interval +25.2% to +41.1%), 100% owner
  recall, and 34.7% lower median latency.

## Rejected

- [-] More mandatory pre-read guidance — already failed at run level.
- [-] Let the model invoke semantic `find` without checking backend readiness —
  repeatedly caused duplicate search and wrong-owner edits.
- [-] Generic lossy compression of code — fidelity and preprocessing risk.
- [-] Multi-agent exploration as a savings strategy — normally increases tokens.
- [-] Prompt caching counted as logical-token savings — different economic layer.
