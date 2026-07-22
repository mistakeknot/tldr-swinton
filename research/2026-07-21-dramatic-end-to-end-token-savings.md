---
title: "Dramatically Improving tldr-swinton: Models, Agent Harnesses, and Context Infrastructure"
date: 2026-07-21
research_type: deep-research
component: agent-workflow
bead: mk-nalf
status: decision-ready
tags: [agents, context-engineering, token-efficiency, retrieval, caching, middleware, evaluation]
---

# Dramatically Improving tldr-swinton

## Executive summary

The strongest opportunity is not another output compressor. It is to turn tldrs
from an optional reconnaissance CLI into a **transparent context gateway inside
the agent harness**.

The current workflow compresses individual tool responses but adds model turns,
tool decisions, and duplicate reads. In the July 2026 paired evaluation, adaptive
tldrs reduced tool-output bytes by 22.1% yet increased uncached agent tokens by
8.4%, raw reads by 31.0%, tool calls by 30.7%, model output tokens by 15.5%, and
elapsed time by 20.3%. Median eligible-task token “savings” were -11.9%. This is
not primarily a retrieval-quality failure. It is an integration failure: the
agent pays to decide whether to use tldrs, pays again to call it, and frequently
reads the source afterward anyway.

The latest model and harness advances point to a different shape:

1. Frontier models can orchestrate and filter multiple tool operations inside
   one inference request. GPT-5.6 explicitly adds programmatic tool calling to
   keep intermediate data out of model context and reduce round trips.
2. OpenAI and Anthropic now support deferred tool loading. tldrs currently
   exposes 26 MCP tools eagerly; the definitions themselves are recurring input
   overhead.
3. Current agent SDKs have native usage accounting, tool-output trimming,
   compaction, and tracing. These make an end-to-end context budget enforceable.
4. Recent code-localization research is converging on graph-aware retrieval,
   role-aware representations, exact line ranking, and fixed context budgets—not
   generic summarization of whole files.
5. Long context has improved dramatically, but retrieval precision still
   deteriorates as contexts become longer and multi-needle. A million-token
   window is capacity, not permission to send a repository.
6. Prompt caching, KV reuse, batch/flex pricing, and model routing can reduce
   cost or latency, but they do not necessarily reduce logical tokens. They must
   be reported as separate optimization layers.

The recommended product is a **tldrs Context Gateway**:

```text
native read/search intent
        |
        v
task gate -> lexical/semantic candidates -> owner/dependency/test expansion
        -> line-level rerank -> hard budget pack -> exact-source packet
        |
        v
same next model turn (no extra reconnaissance turn)
        |
        +--> targeted expansion by stable handle, only if needed
        +--> full source before editing
```

The first target should be **at least 25% median logical-input reduction on
eligible tasks, with a lower confidence bound above 10%, no correctness loss,
no increase in model turns or native reads, and no more than 5% overhead on
negative controls**. That is a hypothesis and promotion gate, not a promised
result.

## Decision

Build and evaluate the Context Gateway before investing further in generic
compression. Preserve the CLI for humans and diagnostics, but make harness
adapters the primary product surface.

The highest-leverage work, in order, is:

| Priority | Intervention | Why now | Expected effect if validated |
|---|---|---|---|
| P0 | Context receipts, health metadata, and fail-open behavior | Current commands can silently return empty results; optimization is unsafe without visibility | Prevent expensive failure loops; foundational measurement |
| P0 | Transparent read/search gateway | Removes the extra model decision and reconnaissance turn that sank the paired eval | Largest logical-token and latency opportunity |
| P0 | Zero-frontier-token utility gate | tldrs should run only when predicted avoided reads exceed packet and invocation cost | Protects localized tasks and prevents negative-value retrieval |
| P0 | One-shot owner-aware bounded packet | Corrects the observed downstream-consumer localization failure | Better correctness at a fixed token/line budget |
| P1 | One MCP namespace/tool with deferred loading | Current server eagerly exposes 26 tools | Lower recurring schema/context overhead |
| P1 | Stable repository atlas plus content-addressed deltas | Aligns current ETags/VHS/delta work with provider caches | Billed-cost and TTFT savings across turns |
| P1 | Server-side composition and result trimming | Keeps candidate lists and graph traversals out of frontier context | Fewer tokens and model turns on multi-stage retrieval |
| P1 | Local router/reranker trained from receipts | The local machine can run Qwen 3.5-class controllers cheaply | Better selection without another remote-model turn |
| P2 | Self-hosted prefix/KV cache integration | Valuable for enterprise/local inference, not API logical tokens | Throughput and TTFT improvement |
| P2 | Prose/log compression only | Evidence for generic compression is workload-sensitive | Selective savings on noisy non-code outputs |

## Key findings

### 1. The unit of optimization must be the whole agent run

tldrs historically reports component compression: signatures versus files,
smaller JSON, compressed diffs, or cached symbols. Those are useful diagnostics,
but the economic unit is the complete successful task:

```text
total value = successful task
            / (logical input + model output + reasoning + tool-loop latency)
```

The paired evaluation is decisive on this point. Both conditions passed 35 of
36 cells, but the adaptive condition used more uncached tokens and time despite
smaller tool responses. A tool can be 90% smaller and still make the agent run
more expensive if it causes one additional model turn or triggers a verify-by-
reading loop.

Current SDK guidance supports run-level accounting. The OpenAI Agents SDK
aggregates input, output, cached, reasoning, and per-request usage across tool
calls and handoffs. Anthropic's agent-eval guidance explicitly tracks turns,
tool calls, total tokens, TTFT, and time-to-last-token alongside task state.

**Implication:** no tldrs feature should ship on output-byte savings alone.
Every experiment needs a paired end-to-end agent arm with hidden correctness.

### 2. New models reward server-side composition, not command chains

[GPT-5.6](https://openai.com/index/gpt-5-6/) can write and execute lightweight
programs that coordinate tools, process intermediate results, and keep only the
final useful result in model context. OpenAI's
[Programmatic Tool Calling](https://developers.openai.com/api/docs/guides/tools-programmatic-tool-calling)
recommends direct tool calls for a single lookup, and programmatic calling when
several results can be filtered, joined, ranked, deduplicated, aggregated, or
validated into a smaller result.

Anthropic reports a 37% token reduction on complex research tasks from
programmatic tool calling, but its own
[programmatic-calling documentation](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling)
is shape-dependent: its sequential one-to-two-call evaluation cost about 8%
more because code generation and execution added overhead. That caveat closely
matches the failed tldrs pattern.

**Implication:** the gateway should internally compose lexical search, semantic
retrieval, graph expansion, test association, line ranking, deduplication, and
budgeting. The frontier model should see one packet—not seven command outputs.

### 3. Tool definitions are now a first-class token budget

The current `mcp_server.py` exposes 26 tools. OpenAI's
[Tool Search](https://developers.openai.com/api/docs/guides/tools-tool-search)
and Anthropic's
[advanced tool-use guidance](https://www.anthropic.com/engineering/advanced-tool-use)
both support `defer_loading`. Anthropic's 50-plus-tool example reduced initial
tool context by 85%; OpenAI says savings are usually most material for namespaces
and MCP servers.

This does not prove that tldrs will save 85%. Its 26 schemas must be tokenized
and measured in each harness. For a modest tool surface, adding a search turn can
be a regression.

**Implication:** expose one always-loaded primitive such as `context_query`, plus
one `expand_context` escape hatch. Put specialist/admin tools behind an MCP
namespace with deferred discovery. Measure schema tokens before and after.

### 4. The best retrieval target is exact source under a fixed line budget

The most actionable recent benchmark is
[SWE-Explore](https://arxiv.org/abs/2606.07297). It evaluates how agents rank
repository regions under a fixed line budget and finds that file localization is
often strong while line ranking and context efficiency remain differentiators.
This isolates the part tldrs should optimize before running a full repair agent.

The retrieval literature adds complementary components:

- [Repoformer](https://arxiv.org/abs/2403.10059) supports selective retrieval
  instead of retrieving on every request.
- [AutoCodeRover](https://arxiv.org/abs/2404.05427) and
  [SWE-agent's agent-computer interface work](https://arxiv.org/abs/2405.15793)
  show that program structure and interface design materially affect outcomes.
- [LocAgent](https://arxiv.org/abs/2503.09089) supports heterogeneous repository
  graphs for localization, though its benchmark-cost claims do not transfer
  directly to end-to-end tldrs use.
- [Retrieval-Oriented Code Representations](https://arxiv.org/abs/2607.11046)
  reports strong Hit@5 gains and 10.4–20.9x smaller index representations using
  role-aware summaries. This is a very recent preprint and should be treated as
  a testable indexing hypothesis, not production proof.
- [RLCoder](https://arxiv.org/abs/2407.19487) supports learning whether retrieval
  is needed at all.

**Implication:** use compact representations to *retrieve*, but generate and
edit from exact excerpts with file, line, symbol, and commit provenance.
Summaries should never be the only evidence for a code mutation.

### 5. Generic prompt compression is not the main bet

[LLMLingua-2](https://arxiv.org/abs/2403.12968) and
[RECOMP](https://arxiv.org/abs/2310.04408) show that learned extractive or
abstractive compression can reduce prompt length on evaluated tasks.

The more decision-relevant result is
[Prompt Compression in the Wild](https://arxiv.org/abs/2604.02985), which
studied more than 30,000 runs. Its maximum end-to-end speedup was 18% inside a
particular model, hardware, and prompt-length window; outside that window,
compression preprocessing erased the gain. Code, diffs, configuration, and
exact error text also have much lower tolerance for lossy token deletion than
generic prose.

**Implication:** do not put generic neural compression in the default code path.
Use deterministic extraction for source. Evaluate compression only for logs,
generated prose, or large tool outputs, and only when a router predicts a net
end-to-end benefit.

### 6. Long context changes the fallback, not the objective

GPT-5.6, Claude Opus 4.8, and Gemini 3.x-class models support very large context
windows and stronger long-horizon tool use. Yet
[RULER](https://arxiv.org/abs/2404.06654),
[NoLiMa](https://arxiv.org/abs/2502.05167), and Google's own
[long-context guidance](https://ai.google.dev/gemini-api/docs/long-context)
all support the same caution: nominal capacity does not imply uniform retrieval
or reasoning quality across a packed context.

**Implication:** full-repository context is the fail-open fallback for tasks that
genuinely require it, not the default. The gateway should target the smallest
high-signal exact packet and expose what it omitted.

### 7. Caching is valuable, but it is not logical-token reduction

OpenAI's current
[prompt-caching documentation](https://developers.openai.com/api/docs/guides/prompt-caching)
requires exact prefix matches. Static content belongs first and dynamic content
last. On GPT-5.6 and later, cache writes are reported separately and billed at
1.25x uncached input; cache reads are reported as cached tokens and receive the
cached-input discount. Cached tokens still count in total input and rate limits.

[Gemini context caching](https://ai.google.dev/gemini-api/docs/caching) similarly
rewards repeated prefixes. OpenAI's
[compaction](https://developers.openai.com/api/docs/guides/compaction) can carry
forward opaque state in fewer tokens for long sessions. Self-hosted stacks such
as [vLLM automatic prefix caching](https://docs.vllm.ai/en/v0.10.1/features/automatic_prefix_caching.html)
and [LMCache](https://docs.lmcache.ai/) target KV reuse and time-to-first-token.

**Implication:** tldrs should produce a deterministic, content-addressed
repository atlas followed by per-turn deltas, but report:

1. logical input tokens,
2. uncached input tokens,
3. cache-write tokens,
4. cache-read tokens,
5. billed dollars,
6. TTFT and total latency.

Otherwise a feature can appear to save tokens while merely moving them into a
different billing or serving category.

### 8. Model routing can improve economics only after context routing works

[RouteLLM](https://arxiv.org/abs/2406.18665) and
[FrugalGPT](https://arxiv.org/abs/2305.05176) show that requests can be routed
across models to trade quality for cost. Current model families also expose
multiple capability and effort tiers. Claude's effort controls and GPT-5.6's
Sol/Terra/Luna tiers make per-task routing increasingly practical.

For tldrs, a local Qwen 3.5-class model can plausibly classify task shape or
rerank candidate regions. The official
[Qwen3.5-9B model card](https://huggingface.co/Qwen/Qwen3.5-9B) supports local
deployment, and the target machine has enough memory for several local tiers.

**Implication:** never add a local generative turn merely because it is cheap.
Use a local model only inside the gateway, where it replaces heuristics or a
frontier round trip. Start with a fast classifier/reranker over trace-derived
features; require a net-positive latency and correctness result.

## Why the current product fails at agent value

### Observed paired-agent mechanism

| Metric on 27 eligible pairs | Baseline | Adaptive | Change |
|---|---:|---:|---:|
| Uncached native tokens | 1,961,420 | 2,125,208 | +8.4% |
| Raw-read commands | 210 | 275 | +31.0% |
| Tool calls | 453 | 592 | +30.7% |
| Tool-output bytes | 5,283,160 | 4,114,726 | -22.1% |
| Model output tokens | 169,743 | 196,099 | +15.5% |
| Elapsed time | 4,738,011 ms | 5,700,993 ms | +20.3% |

The model used tldrs as an additional reconnaissance path rather than a
replacement for native reads. The treatment's routing precision was 100% and
recall was 92.6%, so the dominant issue was not false-positive invocation. It
was the cost of correctly invoking an optional tool and then continuing the
usual loop.

### Correctness failure mode

The only paired correctness disagreement came from a call-graph deduplication
task. The failing agents patched a downstream consumer rather than the class
that owned the invariant. The adaptive run had used semantic search, but the
retrieval path did not privilege ownership or direct hidden-test reachability.

This suggests a packet should explicitly distinguish:

- owner/definition,
- direct callers and callees,
- downstream consumers,
- tests that instantiate the owner,
- changed or suspect lines,
- why each region was included.

### Current integration risks

Live inspection on 2026-07-21 found:

- `mcp_server.py` registers 26 eager MCP tools.
- `tldrs tree src/ --ext .py` finds the populated Python tree.
- `tldrs extract src/tldr_swinton/cli.py --compact` successfully parses the file.
- `tldrs --no-ignore structure src/ --lang python --max 5` returns `files: []`.
- `get_code_structure()` catches every per-file exception and silently skips the
  file, so a total parser/path failure is indistinguishable from an empty tree.

This report does not assert the untraced exception's root cause. It does show a
product-level reliability flaw: silent empty success forces an agent to mistrust
the tool and repeat work with native commands.

## Proposed architecture: the tldrs Context Gateway

### Product contract

The primary surface should be one primitive:

```json
{
  "task": "fix duplicate call-graph insertion",
  "intent": "locate_owner_and_tests",
  "project": ".",
  "budget": {"tokens": 2400, "lines": 180},
  "state": {"commit": "abc123", "session": "s-42"},
  "constraints": {"exact_source": true, "fail_open": true}
}
```

The response should be a context packet:

```json
{
  "health": {"status": "ok", "indexed_commit": "abc123", "coverage": 0.98},
  "receipt": {
    "query_id": "q-...",
    "logical_tokens": 2180,
    "candidate_count": 143,
    "selected_regions": 8,
    "omitted_regions": 135,
    "confidence": 0.87
  },
  "regions": [
    {
      "handle": "sha256:...",
      "path": "src/.../ast_extractor.py",
      "lines": [112, 154],
      "symbol": "CallGraphInfo.add_call",
      "role": "owner",
      "reason": ["defines invariant", "direct test reachability"],
      "source": "exact extractive code"
    }
  ],
  "omissions": ["generated files", "vendor", "low-score callers"],
  "expand": {"tool": "expand_context", "handles": ["sha256:..."]}
}
```

Before modifying a file, the harness should still obtain the full relevant
source range. Reconnaissance can be compressed; surgery must be exact.

### Retrieval pipeline

1. **Task gate.** Skip the gateway for already-scoped, single-file, or exact-line
   tasks. Estimate packet cost and avoided native reads without a frontier-model
   call; route only when predicted utility is positive. Semantic, cross-file,
   diff-heavy, dependency-sensitive, or large-output tasks are candidates, not
   automatic invocations.
2. **Cheap anchors.** Use paths, identifiers, error strings, diff hunks, test
   names, and BM25 first.
3. **Semantic recall.** Add embedding/ColBERT candidates when lexical anchors
   are insufficient.
4. **Structural expansion.** Traverse definitions, imports, calls, inheritance,
   tests, and changed-code edges. Bias toward behavioral owners rather than
   high-fanout consumers.
5. **Role-aware reranking.** Score owner, interface, implementation, consumer,
   test, and configuration roles separately.
6. **Line-level selection.** Rank exact regions under both a line and token
   budget. Prefer cohesive windows over isolated fragments.
7. **Deterministic packing.** Emit provenance, confidence, omissions, and stable
   handles. Sort stable atlas material before dynamic task material.
8. **Hard stop.** Return one packet. A second expansion requires a named missing
   dependency, failed verification, or low confidence.
9. **Fail open.** On stale index, parser failure, or low coverage, return a
   structured degraded status and let the harness perform the exact native read.

### Harness adapters

The integration order should be:

1. **OpenAI Agents SDK / Responses API adapter.** The loop is controllable;
   programmatic tool calling, deferred tool search, usage tracking, compaction,
   and trimming are available now.
2. **Claude Agent SDK / MCP adapter.** Use one always-loaded context tool and
   deferred specialist tools; use programmatic execution only for genuinely
   multi-result workflows.
3. **Codex App Server / SDK adapter.** Wrap read/search requests where the event
   stream permits, or inject the packet before the next model call. Do not require
   a preliminary agent turn.
4. **Claude Code plugin/hook adapter.** Intercept or advise native discovery at
   the harness boundary when hooks expose enough control; otherwise retain the
   one-shot tool policy.
5. **CLI compatibility.** Keep `find`, `structure`, `context`, `impact`, and
   diagnostics for humans and unsupported harnesses, but stop treating the
   command count as product breadth.

### Context state and caching

Reuse existing tldrs machinery rather than starting over:

- `ContextPackEngine` already has token budgets, zoom levels, ETags, relevance,
  comment stripping, type pruning, and import compression.
- `StateStore` and delta paths already track sessions and deliveries.
- VHS already gives content-addressed rehydration handles.
- cache-friendly formats already separate stable and dynamic material.

Reframe these as a stable repository atlas:

```text
stable prefix
  format/version + commit/tree identity
  path/symbol/role atlas
  stable signatures and dependency digest
  cache breakpoint

dynamic suffix
  task query
  changed regions and deltas
  selected exact excerpts
  receipt and omissions
```

Provider caches should be an adapter concern. The core emits prefix hashes,
breakpoint offsets, and content identities; the adapter records actual cache
writes and reads.

### Telemetry: the context receipt

Every packet needs a receipt that joins retrieval behavior to later agent
behavior:

- query/task/harness/model/version,
- index commit and health,
- candidate and selected region IDs,
- role and relevance scores,
- exact output tokens/lines/bytes,
- tool schema tokens loaded,
- retrieval and packing latency,
- regions later reread natively,
- regions actually edited or covered by tests,
- expansion and full-source fallbacks,
- provider logical/cache-write/cache-read/output/reasoning tokens,
- estimated avoided tokens versus realized avoided tokens,
- hidden grader outcome.

The
[OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/)
already distinguish total input, cache creation, cache reads, reasoning output,
tool execution, and retrieval. tldrs should extend those conventions rather
than invent incompatible accounting.

Receipts enable supervised routing without sending repository contents to a
remote trainer. Store hashes, features, and selection outcomes by default; make
source-content tracing opt-in.

## Roadmap

### Phase 0: make the system measurable and trustworthy (1–2 weeks)

1. Add `health`, `coverage`, `errors`, `indexed_commit`, and `fallback` fields to
   every machine/MCP response.
2. Replace broad exception swallowing in multi-file structure extraction with
   counted error categories and degraded status.
3. Tokenize the 26 MCP schemas under GPT, Claude, and Gemini tokenizers; establish
   recurring schema baseline.
4. Add a context receipt and OpenTelemetry-compatible usage fields.
5. Extend the paired eval runner to capture tool-definition tokens, duplicate
   reads, selected-versus-reread regions, cache writes/reads, and owner hits.

Exit gate: cold, warm, stale, missing-index, and parser-failure fixtures all
produce explicit, testable states; no silent empty success.

### Phase 1: prototype the one-turn gateway (2–4 weeks)

1. Implement `context_query` as a deterministic composition of existing engines.
2. Add task gating and a negative-control bypass.
3. Add owner/test/import/call role labels and exact file-line provenance.
4. Enforce one token and line budget with a hard stop.
5. Add the zero-frontier-token utility gate with explicit bypass telemetry.
6. Build an OpenAI Agents/Responses adapter that inserts the packet into the same
   next model turn.
7. Expose only `context_query` and `expand_context` eagerly; defer the remaining
   specialist MCP tools.

Exit gate: versus native baseline, no increase in model calls or native reads;
correctness non-inferior; positive median logical-token savings on the pilot.

### Phase 2: improve selection, not serialization (3–6 weeks)

1. Add line-level ranking tasks from real issue replays.
2. Prototype role-aware retrieval representations for the index.
3. Add lexical-anchor-to-graph expansion similar to LocAgent/LARGER-style
   patterns.
4. Train a small local reranker or contextual bandit on receipts.
5. Add confidence calibration and full-source fail-open thresholds.

Exit gate: improved owner Hit@k and line NDCG at the same context budget, plus
end-to-end token savings with no hidden-test regression.

### Phase 3: optimize repeated and enterprise workloads (3–6 weeks)

1. Stable atlas plus content-addressed deltas and explicit cache breakpoint
   metadata.
2. Provider-specific adapters for OpenAI, Anthropic, and Gemini prompt caching.
3. Long-session compaction integration and older tool-result trimming.
4. Optional vLLM/SGLang/LMCache prefix reuse for local/self-hosted customers.
5. Model/effort routing based on task class and confidence.

Exit gate: report logical, cached, billed, and latency gains separately; prove
cache write/read break-even under realistic reuse distributions.

## Evaluation design

### Experimental arms

| Arm | Condition | Question isolated |
|---|---|---|
| A | Native harness baseline | What does the current model/harness do unaided? |
| B | Guidance only, no tldrs binary | Does routing text itself change behavior? |
| C | Current adaptive CLI | Reproduce the existing treatment |
| D | Current CLI, exactly one permitted tldrs call | Does the stop rule fix loop amplification? |
| E | Transparent gateway, current retrieval | Does removing the extra turn create value? |
| F | E plus owner-aware bounded packet | Does role-aware packing improve correctness/localization? |
| G | F plus role-aware index/local reranker | Does learned selection improve the frontier? |
| H | Best gateway plus stable prefix/delta/cache adapter | What is the additional billed-cost/TTFT benefit? |
| I | Full-source fail-open | What quality ceiling and overhead does safe fallback impose? |

Do not run all arms at full scale initially. Use staged elimination: A/C/D/E on
the existing corpus, then A/E/F/G on the larger corpus, then caching and serving
arms only after a gateway passes logical-token gates.

### Task strata

- exact-path or single-file negative controls,
- unfamiliar semantic localization,
- cross-file owner versus downstream consumer,
- diff regression and change impact,
- configuration/schema propagation,
- large-repository navigation,
- cold/no-index/stale-index/parser-failure cases,
- large logs or generated outputs,
- repeated multi-turn follow-up on the same repository,
- real issue replays created after benchmark/model training cutoffs.

Add a SWE-Explore-style component dataset with line-level relevance labels and a
fixed context budget. Keep hidden repair graders separate so retrieval labels do
not leak the solution.

### Metrics

Correctness and localization:

- hidden tests and task completion,
- changed-line precision/recall,
- owner-symbol Hit@1/Hit@5,
- relevant-line recall at fixed budget,
- NDCG or MRR for ranked regions,
- downstream-consumer false-localization rate.

Context economics:

- total logical input tokens,
- uncached input tokens,
- cache-write and cache-read tokens,
- output and reasoning tokens,
- billed cost using the exact model/date price,
- tool-definition tokens,
- tool-output tokens and bytes.

Agent behavior:

- model requests/turns,
- tool calls,
- native reads/searches,
- duplicate reads,
- tldrs calls and expansions,
- selected regions later reread,
- full-source and low-confidence fallbacks.

Performance:

- retrieval/rerank/pack latency,
- TTFT,
- total time-to-last-token,
- end-to-end wall time,
- warm versus cold cache.

### Promotion gates

The first production candidate should satisfy all of these on paired runs with
fixed model/harness versions, randomized paired order, and at least five repeats
while run-to-run variance remains material:

1. No more than one additional failure, followed by a larger non-inferiority
   confirmation if the pilot passes.
2. At least 25% median logical-input savings on eligible tasks, with the paired
   95% confidence interval lower bound above 10%.
3. No more than 5% median logical-token overhead on negative controls.
4. No increase in model requests or native reads.
5. No more than 10% median latency regression; preferably a reduction.
6. Owner Hit@5 and relevant-line recall must improve or remain non-inferior.
7. Every degraded retrieval state must fail open to exact source.

Cache and self-hosted serving improvements get separate gates. They cannot rescue
a gateway that fails the logical-token or correctness gates.

### Minimal decisive experiment

Before a large implementation, build the thinnest possible adapter:

1. Replay the existing 12 tasks.
2. Precompute exactly one current tldrs packet outside the model loop.
3. Insert it into the adaptive agent's first useful turn without exposing the
   tldrs CLI.
4. Compare A (native), C (current CLI), and E-lite (injected packet).
5. Keep packet contents identical between C and E-lite wherever possible.

This isolates the central causal hypothesis: whether removing the extra
decision/tool loop converts component compression into end-to-end savings. If
E-lite does not beat A, do not build elaborate middleware yet; retrieval content
or the task gate must improve first.

## Rejected or deferred approaches

| Approach | Decision | Reason |
|---|---|---|
| More prompt guidance for the current CLI | Reject as primary fix | The paired eval already had high routing precision and recall but negative savings |
| Mandatory repository map before every task | Reject | Creates overhead on localized negative controls and encourages duplicate reading |
| Chaining specialized tldrs commands | Reject by default | Each chain step can add a model turn and more verification reads |
| Optimize serialized output bytes | Defer | Smaller bytes did not produce smaller agent runs |
| Generic LLMLingua compression for code/diffs/config | Reject by default | Lossy fidelity risk and workload-sensitive preprocessing overhead |
| Put the whole repository in a 1M-token context | Reject | Capacity is not attention quality; cost remains high |
| Eagerly expose more MCP tools | Reject | Tool definitions consume prompt budget; use a small primitive surface |
| Add a subagent for every reconnaissance task | Reject for token savings | Parallel/subagent systems trade more tokens for quality or latency, not less spend |
| Add a local LLM as an extra sequential turn | Reject | Cheap tokens can still amplify latency and complexity without removing frontier work |
| Claim cache savings from deterministic formatting alone | Reject | Actual provider cache writes/reads and reuse distribution must be measured |
| Fully transparent interception without provenance or fail-open | Reject | Retrieval errors could silently hide the source needed for a correct edit |
| Evaluate only on SWE-bench Verified | Reject | Saturation and contamination make it insufficient for current agent decisions |

## Expected impact: hypotheses, not forecasts

| Change | Plausible target to test | Confidence | Important caveat |
|---|---:|---|---|
| Remove extra reconnaissance turn via gateway | 20–35% logical-input reduction on eligible tasks | Medium | Must preserve enough source to avoid fallback reads |
| One-shot owner-aware packet | Fewer duplicate reads and better owner localization | Medium | Role labels and test edges need repo/language coverage |
| Deferred 26-tool MCP surface | Meaningful recurring schema reduction | Medium-low | Must first measure actual schemas per harness; tool search can add a turn |
| Stable prefix + provider caching | Large billed-input/TTFT reduction on repeated repos | Medium | GPT-5.6 cache writes cost 1.25x; one-off calls may lose |
| Role-aware compact retrieval index | Better Hit@k at much smaller index footprint | Low-medium | Based on a new preprint; replication required |
| Local reranker/router | Better packet precision at low marginal cost | Low-medium | Only useful if it stays inside middleware and meets latency budget |
| Generic prompt compression | 0–18% end-to-end speed in favorable windows | Low for code | Outside the window preprocessing can erase gains |
| Self-hosted KV/prefix caching | Better TTFT and throughput | High for repeated prefixes | Does not reduce logical tokens or API bill directly |

## Source assessment

The table favors official product documentation, original papers, official
model cards, protocol specifications, and project documentation. Vendor claims
are useful for capability discovery but are not treated as proof that the same
gain will transfer to tldrs.

| Source | Type / quality | Decision-relevant evidence | Limitation |
|---|---|---|---|
| [tldrs paired-agent evaluation](../docs/research/paired-agent-value-eval-2026-07.md) | Local controlled evaluation, A / 97 | Direct evidence that smaller tool output can lose end to end through extra calls, reads, and turns | 12-task local corpus; needs real-issue replication |
| [GPT-5.6](https://openai.com/index/gpt-5-6/) | Official release, A- | Programmatic orchestration can reduce tokens, turns, and tool calls | Vendor and customer evals; task-specific |
| [Programmatic Tool Calling](https://developers.openai.com/api/docs/guides/tools-programmatic-tool-calling) | Official docs, A | Direct calls for single lookup; programs for filter/join/rank/dedupe workflows | Provider-specific |
| [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) | Official docs, A | Exact prefix, explicit breakpoints, separate cache writes/reads | Economic, not logical-token reduction |
| [Compaction](https://developers.openai.com/api/docs/guides/compaction) | Official docs, A | Long-session state can be carried forward in fewer tokens | Opaque provider state |
| [Tool search](https://developers.openai.com/api/docs/guides/tools-tool-search) | Official docs, A | Deferred loading for functions, namespaces, MCP | Search overhead must be measured |
| [Conversation state](https://developers.openai.com/api/docs/guides/conversation-state) | Official docs, A | Chaining does not make prior input free | Provider-specific |
| [Agents SDK usage](https://openai.github.io/openai-agents-python/usage/) | Official SDK docs, A | Run and per-request token accounting across tools/handoffs | SDK integration required |
| [Tool output trimmer](https://openai.github.io/openai-agents-python/ref/extensions/tool_output_trimmer/) | Official SDK docs, A | Older tool output can be bounded while retaining recent turns | Trimming policy can remove needed evidence |
| [Agents SDK tracing](https://openai.github.io/openai-agents-python/tracing/) | Official SDK docs, A | Trace model/tool/handoff lifecycle | Needs privacy controls |
| [Harness engineering](https://openai.com/index/harness-engineering/) | Official engineering report, A- | Harness/environment design dominates useful agent work | OpenAI internal experience |
| [Unlocking the Codex harness](https://openai.com/index/unlocking-the-codex-harness/) | Official engineering report, A- | App Server exposes harness lifecycle for integrations | Codex-specific |
| [Unrolling the Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/) | Official engineering report, A- | Agent loop and context lifecycle are integration surfaces | Descriptive, not a token eval |
| [SWE-bench Verified retirement](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/) | Official evaluation analysis, A- | Current coding evals need less contaminated, harder tasks | Focused on one benchmark |
| [Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | Official engineering guidance, A- | Seek the smallest high-signal token set | Qualitative synthesis |
| [Advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use) | Official product eval, A- | Deferred tools and programmatic calling reduce large-library context | Vendor internal eval; 50+ tool regime |
| [Anthropic programmatic tool calling](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling) | Official docs/eval, A- / 77 | Intermediate results can stay outside model context; sequential one-to-two-call workflows can regress cost | Provider-specific internal evaluation |
| [Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp) | Official engineering example, B+ | Filter/compose tool results before model context | 150k-to-2k example is not a controlled tldrs eval |
| [Harness design for long-running apps](https://www.anthropic.com/engineering/harness-design-long-running-apps) | Official engineering study, A- | Harness scaffolding can become stale as models improve | Application-development focus |
| [Effective long-running harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) | Official engineering study, A- | Persistent state and staged work aid long horizons | Not primarily token optimization |
| [Managed agents](https://www.anthropic.com/engineering/managed-agents) | Official engineering report, B+ | Separate brain/session/hands; stable execution interface | Architecture-specific latency results |
| [Agent evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) | Official methodology, A | Track outcome, turns, tools, tokens, and latency together | General, not code-localization-specific |
| [Infrastructure noise](https://www.anthropic.com/engineering/infrastructure-noise) | Official experiment, A- | Runtime config can materially shift benchmark scores | Terminal benchmark focus |
| [Claude Opus 4.8](https://www.anthropic.com/news/claude-opus-4-8) | Official release, B+ | Effort controls, long-horizon workflows, mid-task system entries | Vendor benchmark claims |
| [Claude Sonnet 5](https://www.anthropic.com/news/claude-sonnet-5) | Official release, B+ | Cheaper model tier approaches larger-model agent performance | Vendor benchmark claims |
| [Gemini 3.5](https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-5/) | Official release, B+ | Faster agentic tier and harness coupling | Vendor benchmark claims |
| [Gemini tool combinations](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-api-tooling-updates/) | Official product docs, A- | Built-in and custom tools can compose in one request | Gemini-specific |
| [Gemini Docs MCP + Skills eval](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-api-docsmcp-agent-skills/) | Official product eval, B+ | 63% fewer tokens per correct answer for docs MCP + skill | Narrow Gemini API coding task |
| [Gemini caching](https://ai.google.dev/gemini-api/docs/caching) | Official docs, A | Implicit/explicit repeated-prefix caching | Economic/latency layer |
| [Gemini long context](https://ai.google.dev/gemini-api/docs/long-context) | Official docs, A- | Long context enables new patterns but still needs optimization | Provider guidance |
| [Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) | Official model card, A- | Viable local controller/reranker candidate | Capability must be tested on tldrs traces |
| [MCP server specification](https://modelcontextprotocol.io/specification/2025-06-18/server/index) and [tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) | Protocol spec, A | Tools are model-controlled; resource links, output schemas, and pagination can implement lazy context handles | Does not prescribe optimal context policy or measured savings |
| [SWE-Explore](https://arxiv.org/abs/2606.07297) | Original benchmark paper, A- | Fixed-line-budget repository exploration metrics | Very recent; repair success still separate |
| [Retrieval-Oriented Code Representations](https://arxiv.org/abs/2607.11046) | Original preprint, B+ | Role-aware representations improve Hit@5 at smaller footprint | Very recent and unreplicated |
| [Repoformer](https://arxiv.org/abs/2403.10059) | Original paper, A- | Selective retrieval can beat always-retrieve | Repository completion, not repair agents |
| [RepoCoder](https://arxiv.org/abs/2303.12570) | Original paper, A- | Iterative retrieval and generation improve repo completion | Completion task |
| [Agentless](https://github.com/OpenAutoCoder/Agentless) | Original system/repo, A- | Hierarchical localization can be simple and low-cost | Historical prices/models |
| [AutoCodeRover](https://arxiv.org/abs/2404.05427) | Original paper, A- | AST/program structure helps issue localization | Older models and benchmark |
| [SWE-agent ACI](https://arxiv.org/abs/2405.15793) | Original paper, A | Agent-computer interface design affects performance | Not an isolated token study |
| [LocAgent](https://arxiv.org/abs/2503.09089) | Original paper, A- | Heterogeneous graph improves localization and reported cost | Benchmark transfer uncertain |
| [RLCoder](https://arxiv.org/abs/2407.19487) | Original paper, A- | Learned retrieval gate/stop signal | Code completion setting |
| [LARGER](https://arxiv.org/abs/2605.16352) | Original preprint, B+ | Graph expansion can augment lexical retrieval | Very recent; needs replication |
| [RepoMem](https://arxiv.org/abs/2510.01003) | Original preprint, B+ | Repository memory can reduce repeated exploration | Memory staleness and leakage risks |
| [LLMLingua](https://arxiv.org/abs/2310.05736) | Original paper, A- | Aggressive prompt compression can preserve task performance | Mostly non-code workloads |
| [LLMLingua-2](https://arxiv.org/abs/2403.12968) | Original paper, A- | Faster extractive compression with measured latency | Exact code fidelity unproven |
| [RECOMP](https://arxiv.org/abs/2310.04408) | Original paper, A- | Selective extractive/abstractive compression, including empty output | RAG QA focus |
| [Prompt Compression in the Wild](https://arxiv.org/abs/2604.02985) | Large original empirical study, A | E2E gains depend on model/hardware/prompt-length window | Speed focus more than code correctness |
| [Fundamental Limits of Prompt Compression](https://proceedings.neurips.cc/paper_files/paper/2024/file/ac8fbba029dadca99d6b8c3f913d3ed6-Paper-Conference.pdf) | Peer-reviewed paper, A | Compression has information-theoretic limits | Abstract relative to product design |
| [RULER](https://arxiv.org/abs/2404.06654) | Original benchmark paper, A | Claimed long context can overstate usable context | Synthetic task mix |
| [NoLiMa](https://arxiv.org/abs/2502.05167) | Original benchmark paper, A- | Long-context retrieval degrades without lexical overlap | Retrieval focus |
| [LongBench v2](https://arxiv.org/abs/2412.15204) | Original benchmark paper, A- | Realistic long-context reasoning remains difficult | Not code-agent specific |
| [Aider repository map](https://aider.chat/docs/repomap.html) | Primary project docs, A- | Graph-rank symbols under a dynamic token budget | Aider-specific and not a controlled paper |
| [RouteLLM](https://arxiv.org/abs/2406.18665) | Original paper/repo, A- | Learned model routing can trade cost and quality | General prompts, older model set |
| [FrugalGPT](https://arxiv.org/abs/2305.05176) | Original paper, A- | Cascades can reduce inference cost | Pre-agentic workflow era |
| [vLLM automatic prefix caching](https://docs.vllm.ai/en/v0.10.1/features/automatic_prefix_caching.html) | Primary serving docs, A | Reuse KV for shared prefixes | Self-hosted serving only |
| [LMCache](https://docs.lmcache.ai/) | Primary project docs, A- | Cross-request/cache-tier KV reuse | Operational complexity |
| [CacheGen](https://arxiv.org/abs/2310.07240) | Original systems paper, A- | KV-cache compression can reduce transfer delay | Serving, not logical-token reduction |
| [OpenTelemetry GenAI conventions](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/) | Open standard, A | Separate total, cache-create, cache-read, reasoning, tool, retrieval metrics | Semantics evolving |

## Methodology

This was a deep, decision-oriented technical review conducted on 2026-07-21.
It used ten source-routed subqueries covering current models, harness lifecycle,
MCP/tool surfaces, code retrieval, prompt compression, prompt/KV caching, model
routing, observability, evals, and adaptive architecture.

The review prioritized primary sources: official vendor documentation and
engineering reports, original research papers and repositories, protocol
specifications, model cards, and open standards. Marketing examples were kept
only when they identified a capability or testable hypothesis and were explicitly
downweighted for transferability. More than 50 primary sources were reviewed.

Product conclusions were triangulated against:

1. the frozen 72-cell GPT-5.6 Sol paired-agent evaluation,
2. live inspection of tldrs 0.7.19 and the current repository,
3. current model/harness APIs available in July 2026,
4. recent code-localization and context-efficiency research,
5. negative evidence about preprocessing and harness overhead.

The companion automated deep-research servers were not available in this
session, so research used official web sources, the current Codex manual, local
repository evidence, and an independent source-evaluation pass. That evaluator
scored the local paired eval 97/100, SWE-agent 90, Repoformer and NoLiMa 86,
Prompt Compression in the Wild 85, SWE-Explore 84, and LocAgent and OpenAI
prompt-caching documentation 82; lower-transfer vendor examples were explicitly
downweighted. No vendor or paper result is presented as an expected tldrs gain
without a proposed ablation.

## Conclusion

tldrs is not broken because code compression stopped mattering. It is broken
because modern agents optimize across an interaction loop, while tldrs is still
offered as an extra interaction inside that loop.

The dramatic opportunity is to make context selection an invisible harness
service: route once, compose retrieval internally, deliver exact owner-aware
source under a hard budget in the same model turn, expose omissions and stable
handles, and fail open to full source. Then use caching, local routing, and
self-hosted KV reuse as separate economic layers.

The next decisive move is a small causal prototype, not a large rewrite: inject
one existing tldrs packet before the model's first useful turn and test whether
removing the extra tool loop reverses the paired evaluation. If it does, the
Context Gateway is the right product. If it does not, improve retrieval and task
gating before investing in middleware scale.
