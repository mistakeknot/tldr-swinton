# Architecture Review: Block-Level Compression Plan

**Reviewer**: Claude Opus 4.6
**Date**: 2026-02-12
**Document**: `/root/projects/tldr-swinton/docs/plans/2026-02-12-longcodezip-block-compression.md`

## Executive Summary

The plan is architecturally sound with the correct layer separation (`--compress blocks` as a flag, not a zoom level). However, it has **critical integration gaps**, **scope ambiguities**, and **missing edge cases** that will cause implementation friction. The core algorithm (AST-based segmentation + knapsack DP) is well-chosen, but the wiring points are underspecified.

**Verdict**: Not ready for implementation. Needs 4-6 hours of spec work to clarify integration points, error paths, and budget allocation semantics.

---

## 1. Architectural Integration

### ✅ Correct: Compression Flag vs Zoom Level

The plan correctly identifies that block compression is **orthogonal** to zoom levels:
- **Zoom**: Controls *what* content to show (L0-L4: signatures → skeletons → full code)
- **Compression**: Controls *how much* of that content fits within budget

The decision to implement as `--compress blocks` (parallel to existing `two-stage`, `chunk-summary`) is **architecturally correct**.

### ⚠️ Critical Gap: Wiring Point is Underspecified

**Issue**: The plan says "replace `_apply_budget()` with block-aware compression" but this function only exists in `output_formats.py` for **text formatting post-processing** (line 328). The actual budget enforcement happens in **two different places**:

1. **`ContextPackEngine.build_context_pack()`** (lines 147-176 in `contextpack_engine.py`)
   - Per-symbol budget decision: include full code, signature-only, or drop entirely
   - Budget accumulator: `used += full_cost` (line 160)
   - **This is where most symbols get budget-truncated**

2. **DiffLens `_two_stage_prune()`** (lines 420-561 in `difflens.py`)
   - Within-function block selection (already does knapsack DP for `--compress two-stage`)
   - Only runs on **diff-context** command with explicit `--compress two-stage` flag
   - **This is the existing block compression implementation**

**Problem**: The plan proposes a new `block_compress.py` module but doesn't specify:
- Does it replace `_two_stage_prune()` or run in parallel?
- Does it hook into `ContextPackEngine.build_context_pack()` or run as post-processing?
- Does it apply to **both** `context` and `diff-context` commands, or just one?

### 🔴 Missing: Budget Allocation Semantics

**Plan says**: "Budget allocation per function: proportional to relevance score from ContextPack"

**Reality**: `ContextPack` doesn't have per-function budget allocation. The current logic is binary:
```python
if budget_tokens is None or used + full_cost <= budget_tokens:
    # Include full code
elif used + sig_cost <= budget_tokens:
    # Signature-only
else:
    break  # Drop entirely
```

To do "proportional budget allocation", you need:
1. Pre-compute total budget and allocate slices (e.g., top 3 symbols get 40%, 30%, 20%)
2. Pass per-symbol budgets to block compression
3. Handle budget exhaustion mid-slice (currently impossible)

**This is a significant architectural change, not a drop-in replacement.**

---

## 2. Integration with Existing Compression Modes

### ⚠️ Collision Risk: `two-stage` Already Does Block Compression

The existing `--compress two-stage` in DiffLens:
- Splits code into blocks by indent (`_split_blocks_by_indent()`, line 398)
- Uses 0/1 knapsack DP to select blocks (lines 508-535)
- Has diff-aware scoring (overlap + adjacency bonuses, lines 450-486)

**Your plan proposes the exact same algorithm** but in a different module (`block_compress.py` vs `difflens.py`).

**Options**:
1. **Refactor**: Extract `_two_stage_prune()` into `block_compress.py`, have DiffLens import it
2. **Replace**: Deprecate `two-stage`, make `blocks` the new standard
3. **Parallel**: Keep both (fragile, will drift)

**Recommendation**: Option 1 (refactor). The DiffLens implementation is battle-tested (in production since v0.6.x). Reusing it reduces risk.

### 🔴 Missing: What Happens to `chunk-summary`?

The plan mentions `--compress` supports `none`, `two-stage`, `chunk-summary`, but **never mentions `chunk-summary` again**. Does `blocks` replace it? Coexist? What's the migration path?

`chunk-summary` (line 741 in difflens.py) builds a text summary instead of selecting blocks:
```python
if compress == "chunk-summary":
    summary = _build_summary(signature, code, diff_line_list, budget_tokens)
    code = None  # Drop full code, replace with summary
```

This is fundamentally different from block selection. **Clarify the relationship.**

---

## 3. Block Boundary Detection

### ✅ Sound: AST-Based Boundaries

Using tree-sitter for block boundaries is **architecturally sound**:
- Reuses existing `_get_parser()` from `zoom.py` (line 139)
- Language-agnostic (Python, TypeScript, Go already supported)
- Semantically meaningful (control-flow nodes are natural boundaries)

### ⚠️ Overlap with Existing `_split_blocks_by_indent()`

**Plan says**: "Tree-sitter AST nodes: function_definition, if_statement, for_statement, ..."

**Reality**: DiffLens already has `_split_blocks_by_indent()` (line 398) which splits on:
- Indent changes (line 410)
- Blank lines (2+ newlines, line 405)

**This is heuristic-based, not AST-based.** The plan's AST approach is **better** (more precise), but you need to decide:
- Do you keep indent-based as a fallback when tree-sitter fails?
- Do you migrate DiffLens to use AST-based blocks too?
- Do you maintain two separate block detection algorithms?

**Risk**: Without a fallback, block compression breaks for languages without tree-sitter support (Bash, SQL, YAML, etc.)

### 🔴 Missing: Nested Block Handling

**Plan lists**:
```
function_definition, class_definition, if_statement, for_statement, ...
```

**Problem**: These nest. Example:
```python
def foo():  # Block A (function)
    if x:   # Block B (if-statement, nested in A)
        for y in z:  # Block C (for-loop, nested in B)
            ...
```

**Questions**:
1. Do you extract **all** AST nodes (flat list) or only **top-level-within-function**?
2. If a `for` loop is inside an `if` block that's dropped, does the `for` loop survive independently?
3. Do you preserve parent-child relationships for indent reconstruction after elision?

**The plan doesn't specify this.** Nested blocks are 80% of real code. You can't ignore this.

### ⚠️ Edge Case: Multi-Statement Lines

AST nodes have **line ranges** (start_line, end_line). But block boundaries in the plan use **line numbers**. What happens with:
```python
if x: return foo()  # Single line, but 2 AST nodes (if_statement, return_statement)
```

Does this count as 1 block or 2? If you split it, the output is syntactically invalid.

**Recommendation**: Merge AST nodes that **share any line** into a single block during segmentation.

---

## 4. Relevance Scoring

### ✅ Pragmatic: Heuristic Scoring as Default

The plan's default scoring (uniform + structural bonuses) is **pragmatic**:
- **Uniform**: Avoids bias when no query context is available
- **Structural bonus**: `return`/`raise`/`yield` are high-signal (line 66)
- **Diff bonus**: Blocks overlapping changed lines (line 67)

This mirrors the existing DiffLens scoring (lines 450-486), which is a good sign (proven in production).

### ⚠️ Missing: Interaction with Existing Relevance Labels

`ContextPack` already has **per-symbol relevance labels**:
```python
@dataclass
class Candidate:
    relevance: int  # Numeric score
    relevance_label: str | None  # "primary", "secondary", "tertiary", "adjacent"
```

**Questions**:
1. Do block relevance scores **override** symbol relevance, or **multiply** with it?
2. If a low-relevance symbol has high-relevance blocks (e.g., changed lines), does it get promoted?
3. How do you handle budget allocation when relevance is at two levels (symbol + block)?

**The plan doesn't address this.** Without clarification, implementers will make arbitrary choices.

### 🔴 Missing: Query-Aware Scoring Fallback

**Plan says**: "Optional scorer callback for query-aware scoring using embeddings"

**Problem**: The plan doesn't specify:
- Where does the query come from? (User doesn't pass a query to `context` or `diff-context` commands)
- How do you get embeddings for code blocks? (Existing `embeddings.py` indexes **symbols**, not blocks)
- When is this "optional" callback actually used?

**This reads like a TODO comment, not a design decision.** Either:
1. Remove it from the plan (YAGNI)
2. Specify the API contract and when it's invoked

---

## 5. Elision Markers

### ✅ Correct: Format Matches DiffLens

**Plan says**: `# ... (N lines elided)`

**Reality**: DiffLens uses `...` (line 556), no line count. Your format is **more informative**, which is good.

**Recommendation**: Also emit **which blocks were elided** (by index or label), not just line count. This helps LLMs understand the gap.

Example:
```python
# ... (15 lines elided: blocks 2-4, error-handling)
```

---

## 6. Missing Edge Cases

### 🔴 Error Handling: Tree-Sitter Parse Failures

**Plan says**: "Reuses `_get_parser()` from zoom.py"

**Reality**: `_get_parser()` can return `None` (lines 150, 156). The plan has **no fallback** when:
- Language not supported (line 206 check in `extract_body_sketch()`)
- Parse error (line 219 try-except)
- Tree-sitter library missing (line 113 exception)

**Without a fallback, block compression silently degrades to truncation.**

**Recommendation**: Add fallback modes:
1. **Indent-based** (reuse DiffLens `_split_blocks_by_indent()`)
2. **Blank-line-based** (simplest, always works)
3. **No-op** (return full code, log warning)

### 🔴 Budget Exhaustion Mid-Symbol

**Current behavior** (line 175 in `contextpack_engine.py`):
```python
else:
    break  # Drop remaining symbols
```

**With block compression**, this changes:
- Some symbols get **partial** content (selected blocks)
- Budget exhaustion can happen **during** a symbol, not just **between** symbols

**Questions**:
1. Do you emit partial symbols in the final output? (Currently impossible)
2. Do you track "budget used by blocks" separately from "budget used by signatures"?
3. What's the UX when a symbol is truncated mid-body?

**The plan assumes infinite per-symbol budget, which is unrealistic.**

### 🔴 Incremental Diff Representation

DiffLens supports **incremental diffs** (line 793 in `output_formats.py`):
```python
if representation == "incremental":
    lines.extend(code.splitlines())  # Not wrapped in ```
```

**Questions**:
1. Does block compression apply to incremental diffs?
2. If yes, how do you segment a unified diff into "blocks"?
3. If no, when is block compression skipped?

**The plan doesn't mention this at all.** Incremental diffs are used in `cache-friendly` format (line 666), which is critical for the `multi-turn` preset.

### ⚠️ Import Compression Interaction

The plan says **"Update compact and minimal presets to default to compress: blocks"**, but:

**`minimal` preset** (line 22 in `presets.py`):
```python
"compress": "two-stage",
"compress_imports": True,
```

**Questions**:
1. Do you set `"compress": "blocks"` **and** keep `"compress_imports": True`?
2. Do block boundaries respect import statements, or can imports get elided mid-block?
3. Does import deduplication (line 75 in `contextpack_engine.py`) run before or after block compression?

**Order of operations matters.** Import compression removes duplicate import lines. Block compression selects which lines to keep. If you compress imports first, block boundaries shift. If you compress blocks first, import deduplication sees fragmented import sections.

**Recommendation**: Run import compression **first** (it's a whole-file transform), then block compression (per-symbol).

---

## 7. Testing Strategy Gaps

### ⚠️ Missing: Language Matrix

**Plan says**: "Test block segmentation on sample Python/TypeScript/Go code"

**Reality**: The tool supports **6+ languages** (Python, JS, TS, Go, Rust, Java). The plan only tests 3. What about:
- Rust (supported by tree-sitter)
- Java (method overloading, different block semantics)
- Languages without tree-sitter (Bash, SQL, YAML)

**Recommendation**: Add a **language support matrix** test:
- ✅ Python, TS, Go: Full AST-based block detection
- ⚠️ Rust, Java: AST-based, needs validation
- ❌ Bash, SQL, YAML: Fallback to indent/blank-line detection

### 🔴 Missing: Budget Boundary Tests

**Plan says**: "Test no-op path when body fits within budget"

**Missing**:
- Symbol that **almost** fits (budget = 100 tokens, symbol = 95 tokens after blocks)
- Budget exhaustion mid-knapsack (DP table W cap at 10K, line 512)
- Multi-symbol budget accumulation (does dropping blocks from symbol A free budget for symbol B?)

**These are the failure modes that will hit in production.**

### 🔴 Missing: Elision Marker Syntax Tests

**Plan doesn't test**:
- Do elision markers break syntax highlighting?
- Do LLMs correctly interpret `# ... (N lines elided)` as "code is missing here"?
- What if a block already contains `...` in the source (e.g., `raise NotImplementedError(...)`)?

**Recommendation**: Add eval integration:
1. Generate compressed output with elision markers
2. Feed to LLM task (e.g., "summarize this function")
3. Verify LLM doesn't hallucinate the elided code

---

## 8. Out-of-Scope Risks

### ⚠️ LM-Based Perplexity Scoring Deferred

**Plan says**: "LM-based perplexity scoring (Phase 2 — requires torch/transformers)"

**Risk**: If heuristic scoring doesn't work well, you'll need to backfill this **and** rewrite the block scoring API. Deferred complexity is fine, but **you're betting the heuristic is good enough**.

**Mitigation**: Add a **pluggable scorer interface** from day 1:
```python
class BlockScorer(Protocol):
    def score_block(self, block: CodeBlock, context: dict) -> float: ...
```

Then heuristic scoring is just one implementation. This makes the Phase 2 upgrade non-breaking.

### ✅ Cross-Block Dependencies Correctly Deferred

**Plan says**: "Cross-block dependency tracking (variable def/use across blocks)"

**This is correctly out-of-scope.** Def-use analysis is a separate feature (would require SSA-like flow analysis). Trying to do it in Phase 1 would blow up the scope.

**However**: Add a **coherence check** as a post-processing step. Example:
```python
if "foo" in block_5 and "foo =" not in any_previous_blocks:
    warn("Possible undefined variable 'foo' in output")
```

This is cheap (regex-based) and catches 80% of def-use issues without full flow analysis.

---

## 9. Timeline Risk

**Plan says**: 4 implementation steps (core module, wire into pipeline, CLI flag, tests)

**Reality**: Based on the gaps above, here's the actual work:

| Task | Plan Est. | Realistic Est. | Reason |
|------|-----------|----------------|--------|
| Core block compression module | 1-2 days | 2-3 days | +Nested block handling +Fallback modes |
| Wire into output_formats pipeline | 0.5 day | 2-3 days | +Per-symbol budget allocation +ContextPackEngine changes |
| CLI flag + preset integration | 0.5 day | 1 day | +Import compression ordering +Incremental diff handling |
| Tests | 1 day | 2-3 days | +Language matrix +Budget boundaries +Elision syntax |
| **Total** | **3-4 days** | **7-10 days** | **2.5x expansion** |

**Root cause**: The plan underestimates integration complexity. Most of the work is in **wiring**, not **algorithm**.

---

## 10. Recommendations

### Must-Fix Before Implementation

1. **Specify the wiring point**: Where does `block_compress.py` hook into the pipeline?
   - Replace `_two_stage_prune()` in DiffLens? (Recommended)
   - Add to `ContextPackEngine.build_context_pack()`? (Complex)
   - Post-processing in `output_formats.py`? (Too late)

2. **Define budget allocation semantics**: Per-symbol proportional budgets or global budget accumulator?

3. **Add fallback for tree-sitter failures**: Indent-based, blank-line-based, or no-op

4. **Clarify nested block handling**: Flat extraction or hierarchical with parent tracking?

5. **Specify import compression order**: Before or after block compression?

### Strongly Recommended

6. **Refactor, don't duplicate**: Extract DiffLens `_two_stage_prune()` into shared `block_compress.py`

7. **Add pluggable scorer interface**: Prepare for Phase 2 LM-based scoring

8. **Test elision marker UX**: Verify LLMs interpret `# ... (N lines)` correctly

9. **Add coherence warnings**: Cheap def-use checks to catch obvious gaps

### Nice-to-Have

10. **Emit block metadata**: Which blocks were kept/dropped, why (helps debugging)

11. **Language support matrix**: Document which languages get AST-based vs fallback

---

## Conclusion

**The core idea is sound**: AST-based block segmentation + knapsack DP is the right algorithm. The decision to implement as `--compress blocks` (not a zoom level) is architecturally correct.

**However, the plan is underspecified**:
- Integration points are vague ("replace `_apply_budget()`" is not actionable)
- Budget allocation semantics are handwavy ("proportional to relevance" is undefined)
- Edge cases are ignored (nested blocks, parse failures, incremental diffs)
- Timeline is optimistic (3-4 days → 7-10 days realistically)

**Recommendation**: **Do not implement yet.** Spend 4-6 hours writing a **detailed integration spec** that answers:
1. Where does the code hook in? (Function call sites, not "the pipeline")
2. What's the data flow? (Input: Candidate list + budget → Output: ContextPack with block metadata)
3. What are the error paths? (Tree-sitter fails, budget exhausted mid-symbol, no blocks found)
4. How does it compose with existing features? (Import compression, incremental diffs, zoom levels)

Once those are answered, the plan is implementable. Without them, you'll hit decision paralysis on day 2 and scope creep by day 4.

---

## Appendix: Suggested Integration Path

**Recommended approach** (refactor DiffLens, don't duplicate):

```python
# Step 1: Extract DiffLens block logic into block_compress.py
def segment_into_blocks(source: str, language: str) -> list[CodeBlock]:
    """AST-based segmentation with indent-based fallback."""
    # Try tree-sitter first
    if ast_blocks := _segment_ast(source, language):
        return ast_blocks
    # Fallback to indent-based (existing DiffLens logic)
    return _segment_indent(source)

def knapsack_select(blocks: list[CodeBlock], budget: int, must_keep: set[int]) -> list[int]:
    """0/1 knapsack DP. Extracted from DiffLens _two_stage_prune."""
    # Lines 508-535 from difflens.py, unchanged

def compress_function_body(
    source: str,
    language: str,
    budget: int,
    diff_lines: list[int] | None = None,
    scorer: BlockScorer | None = None,
) -> tuple[str, dict]:
    """Main entry point. Returns (compressed_code, metadata)."""
    blocks = segment_into_blocks(source, language)
    scores = scorer.score_all(blocks) if scorer else _heuristic_score(blocks, diff_lines)
    must_keep = {i for i, b in enumerate(blocks) if any(ln in diff_lines for ln in range(b.start_line, b.end_line))}
    selected_idx = knapsack_select(blocks, budget, must_keep)
    return _render_with_elision(blocks, selected_idx)

# Step 2: DiffLens calls this
def _two_stage_prune(...):
    # DEPRECATED: Wrapper for backwards compatibility
    code, meta = compress_function_body(code, "python", budget_tokens, diff_lines)
    return code, meta["block_count"], meta["dropped_blocks"]

# Step 3: Add CLI flag
if args.compress == "blocks":
    # Hook into ContextPackEngine or DiffLens, depending on command
```

**This path**:
- Reuses battle-tested DiffLens logic (less risk)
- Adds AST-based improvement (better boundaries)
- Provides fallback (doesn't break on unsupported languages)
- Minimizes duplicate code (DiffLens becomes a thin wrapper)
- Allows phased rollout (DiffLens first, then ContextPackEngine)
