# Ideas Backlog

## Promising

- [x] External issue replays: pinned Python and Go corpora confirmed; TypeScript
  and Rust remain future expansion.
- [x] Cross-model confirmation: balanced Codex and Claude matrix completed
  32/32 correct cells.
- [x] `max_chars` ablation: 1500 retained as general default; 750 promoted for
  Codex when an explicit test-file path supplies an owner hint.
- [x] Packet versus validated-runtime isolation: validated runtime retained in
  three of four smoke arms.
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
- [x] External 1500-character balanced matrix — retain as general default:
  32/32 correct, 14.0% aggregate cross-model savings, lower median latency in
  every repository/harness arm.
- [x] Codex/Python 750-character owner-hint profile — retain: 8/8 correct,
  22.5% median paired savings, 26.9% aggregate savings, 46.4% lower latency.

## Rejected

- [-] More mandatory pre-read guidance — already failed at run level.
- [-] Let the model invoke semantic `find` without checking backend readiness —
  repeatedly caused duplicate search and wrong-owner edits.
- [-] Generic lossy compression of code — fidelity and preprocessing risk.
- [-] Multi-agent exploration as a savings strategy — normally increases tokens.
- [-] Prompt caching counted as logical-token savings — different economic layer.
- [-] Bounded task-tracker/Git ceremony guidance — fewer tool calls but 20.3%
  higher median Codex/Go adaptive tokens.
- [-] Universal 750-character budget — Claude/Python aggregate regressed 3.7%.
