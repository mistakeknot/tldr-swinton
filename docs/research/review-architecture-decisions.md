# Architectural Review: Prompt Cache Optimization Design

**Date:** 2026-02-10
**Reviewer:** System Architecture Expert
**Document Under Review:** `docs/plans/2026-02-10-prompt-cache-optimization.md`
**Context:** `docs/brainstorms/2026-02-10-prompt-cache-optimization-brainstorm.md`

---

## Executive Summary

This architectural review evaluates five key design decisions in the prompt cache optimization feature for tldr-swinton. Overall assessment: **3 WARNINGS, 2 NOTES**. The design is fundamentally sound but requires refinements to the extension point abstraction and clarification of semantic contracts.

**Critical findings:**
1. The `prefix_sections` extension point needs ordering control and budget awareness
2. Putting changed symbol signatures in the cache prefix creates a subtle semantic inconsistency
3. Two-section layout may need a third tier for semi-stable content
4. JSON cache hints in text output is pragmatic but needs escape hardening
5. Non-delta path creates ceremonial cache prefixes with limited value

---

## 1. Architecture Overview

### System Context

tldr-swinton is a token-efficient code analysis tool for LLMs with a layered architecture:

```
CLI (cli.py)
    ↓
API layer (api.py)
    ↓
ContextPackEngine (contextpack_engine.py)
    ↓
Output Formatters (output_formats.py)
    ↓
LLM Consumer (Anthropic/OpenAI/etc.)
```

The cache-friendly format is a **terminal output formatter** — it receives fully-constructed `ContextPack` objects and serializes them for LLM consumption. It has no control over symbol selection, budget allocation, or delta calculation. These responsibilities belong to upstream layers.

### Relevant Architectural Context

**Current state:**
- `ContextPack` dataclass: `slices`, `budget_used`, `unchanged`, `rehydrate`, `cache_stats`
- `ContextSlice` dataclass: `id`, `signature`, `code`, `lines`, `relevance`, `meta`, `etag`
- Output formatting is **stateless** — receives pack dict, returns string
- Three output modes: `json`, `ultracompact`, `cache-friendly`
- Cache-friendly format already exists (lines 438-578) with basic prefix/dynamic separation

**Planned features that will interact with cache-friendly format:**
- **Zoom levels (0ay)**: L0-L4 progressive disclosure — signatures, sketches, windows, full bodies
- **Import compression (aqm)**: Common imports as a prefix section
- **Precomputed bundles (jji)**: Bundle IS the pre-serialized prefix
- **Type pruning (yw8)**: Type stubs as prefix content
- **Incremental diff (4u5)**: Textual diffs for partially changed symbols
- **JSON optimization (s5v)**: Packed-json format with key aliasing
- **Session memory**: AGENTS.md / POLICY.md as preamble slices

---

## 2. Change Assessment

### Decision 1: `prefix_sections` Extension Point

**Design:**
```python
prefix_sections: list[tuple[str, str]] | None = None  # [(section_name, rendered_text), ...]
```

**Analysis:**
This is a **deliberate simplification** — the plan states "This is deliberately simple — no protocol, no ABC, just a list of named strings." The brainstorm shows awareness that future features (import compression, bundles, type stubs) will need to inject content into the prefix.

**Integration assessment:**
- ✅ Minimal coupling: callers just pass pre-rendered strings
- ✅ Easy to implement: no factory pattern, no registration
- ⚠️ **Missing ordering control**: What if import compression (aqm) needs to appear BEFORE signatures but bundle precomputation (jji) needs to appear AFTER? The simple list provides insertion-order semantics but no priority control.
- ⚠️ **No budget awareness**: If future features need to respect `--memory-budget` for policy content, who enforces the cap? The formatter just concatenates everything.
- ⚠️ **No conditional inclusion**: What if a section should only appear when certain flags are set? Callers must implement this logic themselves.

**Severity:** **WARNING**

**Recommendation:**
Extend the tuple to include ordering hints and optional budget allocation:
```python
@dataclass
class PrefixSection:
    name: str
    content: str
    priority: int = 50  # 0-100, lower = earlier in prefix
    budget_tokens: int | None = None  # Optional separate budget

prefix_sections: list[PrefixSection] | None = None
```

Alternatively, keep the simple `list[tuple[str, str]]` for MVP but document that:
1. Sections are rendered in list order (caller controls order)
2. No per-section budget enforcement (caller must pre-budget)
3. Conditional inclusion is caller responsibility

This makes the contract explicit and prevents future features from assuming capabilities that don't exist.

---

### Decision 2: All Signatures in Prefix (Including Changed Symbols)

**Design:**
> "Even for *changed* symbols, signatures usually stay the same when only the body changes. We should put ALL signatures in the prefix, not just unchanged ones."

**Analysis:**
This is a **pragmatic optimization** based on the insight that function signatures are stable across edits. The plan's prefix maximization strategy correctly identifies that body-only edits shouldn't invalidate the cache.

**Semantic contract assessment:**
- ✅ Improves cache hit rate (80-95% of calls with identical prefixes)
- ✅ Technically correct: signatures ARE stable in most edits
- ⚠️ **Breaks implicit "prefix = unchanged" contract**: Consumers might expect the prefix to contain only unchanged content. The format now has "prefix = signatures" (all) + "dynamic = changed bodies" (subset).
- ⚠️ **Changed signatures still invalidate prefix**: If a function signature changes (param renamed, return type added), the entire prefix invalidates. This is unavoidable but worth documenting.
- ⚠️ **Marker ambiguity**: A symbol marked `[UNCHANGED]` appears in the prefix. But a changed symbol's signature ALSO appears in the prefix (without the marker). The prefix is no longer homogeneous.

**Consumer expectations:**
The brainstorm documents this for users:
> "For Anthropic users: Place tldrs output in a `system` message content block. Add `cache_control: {"type": "ephemeral"}` at the character offset from `breakpoint_char_offset`."

This implies consumers need to:
1. Understand that prefix = "all signatures" not "unchanged symbols"
2. Trust that signatures are stable (usually true, but not guaranteed)
3. Accept that signature changes invalidate the entire prefix

**Severity:** **WARNING**

**Recommendation:**
1. **Document the semantic shift explicitly**: Add a "Contract" section to the output format docstring explaining that prefix contains "all stable structure" not "unchanged symbols only."
2. **Add validation**: If a changed symbol's signature differs from its previous version (tracked via etag), emit a warning or fallback to full-prefix-rebuild mode.
3. **Consider a hybrid marker**: Changed symbols with stable signatures could be marked `[CHANGED_BODY_ONLY]` to make the distinction visible.

Example enhanced output:
```
## CACHE PREFIX (134 symbols)

src/app.py:handle_request def handle_request(req): @42-67 [contains_diff] [CHANGED_BODY_ONLY]
src/db.py:connect def connect(url): @10-15 [caller] [UNCHANGED]
```

This preserves the optimization while making the contract explicit.

---

### Decision 3: Two-Section Layout (Prefix + Dynamic)

**Design:**
```
1. CACHE PREFIX (stable)
2. CACHE_BREAKPOINT marker
3. DYNAMIC CONTENT (volatile)
```

**Analysis:**
This is a **binary partitioning** — content is either stable (prefix) or volatile (dynamic). The brainstorm explicitly considers a three-tier system but rejects it:

> "Is there a need for a third section (e.g., 'semi-stable' for recently changed but not actively edited)?"

**Assessment against future features:**

| Feature | Stability Tier | Fits Two-Section? |
|---------|----------------|-------------------|
| Import graph digest (aqm) | Fully stable | ✅ Prefix |
| File tree summary (jji) | Fully stable | ✅ Prefix |
| Type stubs (yw8) | Fully stable | ✅ Prefix |
| AGENTS.md policy | Semi-stable (updated weekly) | ⚠️ Depends |
| Zoom L2 sketches (0ay) | Semi-stable (control flow changes) | ⚠️ Depends |
| Incremental diff bodies (4u5) | Volatile | ✅ Dynamic |

**Problem case: Semi-stable content**
Consider `AGENTS.md` / `POLICY.md` content (session memory feature). This changes infrequently (weekly/monthly) but not never. Putting it in the prefix causes cache invalidation on every policy update. Putting it in the dynamic section defeats the purpose (policy should be cached).

**Potential third tier:**
```
1. CACHE PREFIX (fully stable: signatures, imports, stubs)
2. SEMI_STABLE (weekly changes: policy, file tree, zoom sketches)
3. CACHE_BREAKPOINT marker
4. DYNAMIC CONTENT (per-request: changed bodies)
```

Anthropic supports **up to 4 cache breakpoints**. OpenAI caches the prefix automatically (no control). A three-tier system would:
- Anthropic: Use 2 breakpoints (after prefix, after semi-stable)
- OpenAI: Treat both prefix and semi-stable as prefix (still benefits)

**Severity:** **NOTE** (acceptable for MVP, revisit later)

**Recommendation:**
1. **Ship two-section layout for MVP** — it handles 90% of cases correctly
2. **Document the limitation** — note that semi-stable content (policy, file tree) will invalidate prefix cache
3. **Add extension point for future tiers** — when session memory ships, evaluate whether a third tier is warranted. The `prefix_sections` design already allows multiple named sections; the formatter could be enhanced to emit multiple breakpoints without changing the calling interface.

Example future output:
```
## CACHE PREFIX (signatures + imports)
...
<!-- CACHE_BREAKPOINT_1: ~1200 tokens -->

## SEMI-STABLE (policy + tree)
...
<!-- CACHE_BREAKPOINT_2: ~300 tokens -->

## DYNAMIC CONTENT (changed bodies)
...
```

---

### Decision 4: Cache Hints as Inline JSON

**Design:**
```json
{"cache_hints": {"prefix_tokens": 1200, "prefix_hash": "abc123...", "breakpoint_char_offset": 4850, "format_version": 1}}
```

**Analysis:**
This embeds a JSON object as a single line in otherwise plain-text output. The plan justifies this:
> "Always present in cache-friendly format (not behind a flag). Provider-agnostic — includes enough info for any SDK to map to its native caching API."

**Parsing risk assessment:**

**Potential issues:**
1. **Newlines in content**: If a symbol signature contains a literal `\n` (unlikely but possible in comments), does the JSON line remain single-line?
2. **JSON injection**: If a symbol ID contains `}` or `"cache_hints"`, could it break extraction?
3. **Format ambiguity**: Is this a JSON document or text document? Tools expecting pure text may choke on the JSON line.
4. **Line-based tools**: Will `grep`, `sed`, `awk` handle this gracefully?

**Reality check:**
- Symbol IDs are controlled by tldr-swinton (file paths + `:` + identifiers). Unlikely to contain JSON metacharacters.
- The JSON line is emitted via `json.dumps(..., ensure_ascii=False)` — properly escaped.
- LLMs consume this as **text context** not structured data. They can read JSON in text.
- The alternative (separate JSON header file) breaks single-output simplicity.

**Consumer perspective:**
```python
# Consumers can extract metadata programmatically
for line in output.split("\n"):
    if "cache_hints" in line:
        hints = json.loads(line)
        prefix_tokens = hints["cache_hints"]["prefix_tokens"]
```

This is **simple and pragmatic**. The risk is low because:
- tldrs controls the content (no user-provided symbol IDs in prefix)
- JSON parsing is robust to whitespace/escaping
- Embedding metadata in output is common (EXIF, frontmatter, etc.)

**Severity:** **NOTE** (acceptable design, minor hardening recommended)

**Recommendation:**
1. **Add escape validation**: Ensure symbol IDs can never contain `"cache_hints"` string (already unlikely, but add assertion).
2. **Document extraction pattern**: Show the `if "cache_hints" in line: json.loads(line)` pattern in the docstring.
3. **Consider comment wrapping**: Wrap the JSON line in HTML comment to make it visually distinct:
   ```
   <!-- {"cache_hints": {...}} -->
   ```
   This signals "metadata" vs "content" more clearly. Still parseable by consumers who know to look for it.

---

### Decision 5: Non-Delta Path Creates Ceremonial Prefix

**Design:**
```python
# Non-delta context: no unchanged info. All signatures go to prefix,
# no code bodies means empty dynamic section.
"unchanged": None,
"cache_stats": {"hit_rate": 0.0, "hits": 0, "misses": len(ctx.functions)},
```

**Analysis:**
The non-delta path (`tldrs context`, not `diff-context`) creates hollow slices with `code: None`. The plan fixes this to put all signatures in the prefix, but there's still no code in the dynamic section.

**Question: Is this a meaningful cache prefix?**

**Non-delta use case:**
```bash
# Call 1: Get context for "handle_request"
tldrs context handle_request --project . --format cache-friendly

# Call 2: Same query, same commit
tldrs context handle_request --project . --format cache-friendly
```

**Cache behavior:**
- ✅ Call 2 has identical prefix (same signatures)
- ✅ Call 2 has identical dynamic section (empty both times)
- ✅ Entire output is byte-identical → cache hit

**But:** Non-delta context **doesn't include code bodies** — it's signatures-only by design. The cache optimization is **orthogonal** here. The output is already minimal (signatures are ~5% of full file size). Caching this saves latency but not tokens.

**Actual value:**
- **For Anthropic/OpenAI billing**: Caching signatures-only output saves 90%/50% of prompt cost, but the prompt was already 95% smaller than reading full files. Net savings: ~47-97% vs reading files (still good).
- **For repeated queries**: Non-delta context is usually a one-shot operation (get context, read files, edit). Multi-turn repetition is rare.
- **Ceremony cost**: The cache-friendly format adds ~10 lines of metadata (cache hints, stats footer). For signatures-only output, this is 5-10% overhead.

**Severity:** **NOTE** (not a problem, just clarify value prop)

**Recommendation:**
1. **Document the use case**: Non-delta cache-friendly format is for "repeated structure queries" (e.g., agent navigating codebase, multiple context calls before editing). Not for "get context once, edit, commit."
2. **Consider making it opt-in**: If `--format cache-friendly` is used on non-delta context, emit a hint:
   ```
   # Note: cache-friendly format is most valuable with diff-context (full code bodies).
   # For signature-only context, cache savings apply to repeated queries.
   ```
3. **Don't block it**: The feature is harmless. Some users may benefit (e.g., notebook environments with persistent LLM sessions).

---

## 3. Compliance Check: Architectural Principles

### SOLID Principles Assessment

**Single Responsibility Principle (SRP):** ✅ PASS
`_format_cache_friendly()` has one job: serialize ContextPack for cache optimization. It doesn't perform symbol selection, budget allocation, or delta calculation.

**Open/Closed Principle (OCP):** ⚠️ PARTIAL
The `prefix_sections` extension point allows new features to add content without modifying the formatter. However, the simple `list[tuple[str, str]]` design may require formatter changes if features need ordering control or budget enforcement. **Recommendation:** Enhance to `list[PrefixSection]` dataclass (see Decision 1).

**Liskov Substitution Principle (LSP):** ✅ PASS
All output formatters (`json`, `ultracompact`, `cache-friendly`) accept the same `ContextPack` dict and return `str`. No behavioral violations.

**Interface Segregation Principle (ISP):** ✅ PASS
The formatter interface is minimal: `format_context_pack(pack, fmt) -> str`. Callers don't depend on internal formatter details.

**Dependency Inversion Principle (DIP):** ✅ PASS
The formatter depends on abstractions (`ContextPack` dataclass) not concrete implementations. Future features can inject content via `prefix_sections` without coupling to the formatter.

### Separation of Concerns

| Concern | Layer | Status |
|---------|-------|--------|
| Symbol selection | `ContextPackEngine` | ✅ Correct |
| Budget allocation | `ContextPackEngine` | ✅ Correct |
| Delta calculation | `engines/delta.py` | ✅ Correct |
| Serialization | `output_formats.py` | ✅ Correct |
| Cache metadata | `output_formats.py` | ✅ Correct |

**No layering violations detected.** The cache-friendly format is a pure presentation concern.

### Dependency Analysis

**Current dependencies:**
```
output_formats.py
├── contextpack_engine.py (ContextPack, ContextSlice dataclasses)
├── tiktoken (optional, for token estimation)
└── hashlib (stdlib, for prefix hash)
```

**Future dependencies (via prefix_sections):**
```
callers (cli.py, engines/*.py)
├── import compression (aqm) → renders import section
├── bundle precomputation (jji) → renders bundle section
├── type pruning (yw8) → renders type stubs section
└── session memory → renders policy section
```

**Risk:** ⚠️ **Indirect coupling via content assumptions**
If the formatter assumes section content is plain text, but a future feature injects Markdown tables or code blocks, formatting may break. **Recommendation:** Document that section content must be plain text or valid Markdown (no nested HTML comments, no JSON unless escaped).

---

## 4. Risk Analysis

### BLOCKER Issues

**None identified.** All issues are addressable via refinement, not redesign.

### WARNING Issues

#### W1: Extension Point Lacks Ordering and Budget Control
**Impact:** Future features (import compression, bundles, policy) may conflict over section order or exceed token budgets.
**Mitigation:** Enhance `prefix_sections` to `list[PrefixSection]` with `priority` and `budget_tokens` fields.
**Timeline:** Address before feature integration (aqm, jji, session memory).

#### W2: "All Signatures in Prefix" Breaks Implicit Contract
**Impact:** Consumers may assume prefix = unchanged content. Changed signatures invalidate prefix unexpectedly.
**Mitigation:** Document semantic contract explicitly. Add `[CHANGED_BODY_ONLY]` marker for changed symbols with stable signatures.
**Timeline:** Address in MVP implementation (docstring + output markers).

#### W3: Two-Section Layout May Need Third Tier
**Impact:** Semi-stable content (policy, file tree) will invalidate prefix cache more often than necessary.
**Mitigation:** Ship two-section MVP, revisit when session memory feature lands. Anthropic supports 4 breakpoints (room for future extension).
**Timeline:** Defer to phase 2 (session memory integration).

### NOTE Issues

#### N1: JSON Metadata in Text Output
**Impact:** Line-based tools may struggle with mixed JSON/text format.
**Mitigation:** Wrap JSON in HTML comment, document extraction pattern.
**Timeline:** MVP cosmetic improvement.

#### N2: Non-Delta Ceremonial Prefix
**Impact:** Cache-friendly format adds overhead for signatures-only output (minimal benefit).
**Mitigation:** Document use case, consider opt-in warning. Don't block.
**Timeline:** Documentation-only (no code change needed).

---

## 5. Feature Composition Matrix: Integration Risks

| Feature | Cache-Friendly Interaction | Risk Level | Notes |
|---------|---------------------------|------------|-------|
| **Zoom L0-L4 (0ay)** | L1/L2 prefixes more stable than L4 | ✅ Low | Sketches (L2) change less often than full bodies (L4). Fits two-section layout. |
| **Import compression (aqm)** | Common imports as prefix section | ⚠️ Medium | Needs ordering control (before signatures). Triggers W1. |
| **Precomputed bundles (jji)** | Bundle IS the prefix | ⚠️ Medium | Replaces entire prefix. May need special handling (skip signature section). |
| **Type pruning (yw8)** | Type stubs as prefix section | ✅ Low | Clean additive section. No conflicts. |
| **Incremental diff (4u5)** | Diffs in dynamic section | ✅ Low | Volatile content, fits dynamic section. |
| **JSON optimization (s5v)** | Key aliasing must be deterministic | ✅ Low | Separate format (`packed-json`). No cache-friendly interaction. |
| **Session memory** | AGENTS.md/POLICY.md in prefix | ⚠️ Medium | Semi-stable content. May need third tier (W3). |
| **Distillation (het)** | Too small to benefit (1-2K total) | ✅ Low | Not used with cache-friendly. |
| **Comment stripping (9us)** | Stripped code more cacheable | ✅ Low | Applied before packing. Transparent to formatter. |
| **Popularity index (e5g)** | Popular symbols prioritized | ✅ Low | Affects candidate selection, not formatting. |

**High-risk interaction: Precomputed bundles (jji)**

The brainstorm states:
> "Bundle IS the pre-serialized prefix"

This implies bundles **replace** the normal prefix (signatures + sections). The formatter needs to detect bundle mode and skip normal prefix construction:

```python
if "bundle_ref" in pack:
    # Bundle mode: use pre-serialized prefix directly
    prefix_text = load_bundle(pack["bundle_ref"])
else:
    # Normal mode: construct prefix from signatures + sections
    prefix_text = _build_prefix(slices, prefix_sections)
```

**Recommendation:** Add bundle detection to the formatter design. Document that bundles are **mutually exclusive** with normal prefix construction.

---

## 6. Recommendations Summary

### Immediate (MVP Implementation)

1. **Enhance extension point (W1):**
   ```python
   @dataclass
   class PrefixSection:
       name: str
       content: str
       priority: int = 50  # 0-100, lower = earlier
       budget_tokens: int | None = None
   ```

2. **Document semantic contract (W2):**
   - Prefix contains "all stable structure" not "unchanged symbols only"
   - Changed symbols with stable signatures marked `[CHANGED_BODY_ONLY]`
   - Signature changes invalidate prefix (unavoidable)

3. **Wrap cache hints in HTML comment (N1):**
   ```
   <!-- {"cache_hints": {"prefix_tokens": 1200, ...}} -->
   ```

4. **Add bundle detection (integration risk):**
   ```python
   if "bundle_ref" in pack:
       prefix_text = load_bundle(pack["bundle_ref"])
   ```

### Phase 2 (Session Memory Integration)

5. **Evaluate three-tier layout (W3):**
   - Fully stable (signatures, imports, stubs)
   - Semi-stable (policy, file tree, sketches)
   - Volatile (changed bodies)
   - Only add if semi-stable content creates measurable cache thrashing

6. **Measure cache hit rates:**
   - Track prefix hash stability across sessions
   - Report % of calls with identical prefix
   - Validate 80-95% hit rate claim

### Future (Feature Integration)

7. **Add ordering validation:**
   - When multiple features provide prefix sections, sort by `priority`
   - Validate no conflicts (two sections with same priority)

8. **Add budget enforcement:**
   - If `prefix_sections` include `budget_tokens`, enforce cap
   - Truncate or reject sections that exceed budget

---

## 7. Conclusion

**Overall architectural assessment: SOUND WITH REFINEMENTS NEEDED**

The prompt cache optimization design demonstrates strong architectural thinking:
- ✅ Clean separation of concerns (formatting is separate from selection/budgeting)
- ✅ Provider-agnostic design (works with Anthropic, OpenAI, and future providers)
- ✅ Pragmatic optimization (all signatures in prefix maximizes cache hits)
- ✅ Extension point for future features (prefix_sections)

**Critical refinements:**
1. Enhance `prefix_sections` abstraction to support ordering and budgeting
2. Document semantic shift (prefix = "stable structure" not "unchanged only")
3. Plan for three-tier layout when semi-stable content becomes common
4. Add bundle detection for precomputed bundle integration

**No blocking issues identified.** The design is production-ready after addressing the WARNING items. All NOTE items are cosmetic improvements or documentation clarifications.

**Promotion recommendation: APPROVE WITH CONDITIONS**
- Implement W1 (extension point enhancement) before merging
- Implement W2 (semantic contract documentation) before merging
- Defer W3 (three-tier layout) to session memory feature
- Implement N1 (JSON comment wrapping) for cleaner output
- Document N2 (non-delta use case) in CLI help text

**Estimated refactoring effort:** 2-3 hours (extension point enhancement + documentation).

---

## Appendix: Alternative Designs Considered

### A1: Separate Metadata File
**Rejected.** Would require consumers to fetch two outputs (content + metadata). Breaks single-output simplicity.

### A2: Binary Cache Format
**Rejected.** LLMs consume text, not binary. Serialization/deserialization overhead outweighs benefits.

### A3: Dynamic Section Includes Signatures
**Rejected.** Current design puts signatures in prefix, bodies in dynamic. Alternative would duplicate signatures in dynamic. Wastes tokens (signatures appear twice).

### A4: Per-Symbol Cache Markers
**Rejected.** Anthropic/OpenAI cache at block level, not per-symbol. Granular markers don't map to provider APIs.

---

**Review completed:** 2026-02-10
**Confidence level:** HIGH (based on full system context, roadmap analysis, and provider caching mechanics)
