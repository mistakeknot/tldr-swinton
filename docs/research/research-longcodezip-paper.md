# Research: LongCodeZip (ASE 2025)

> Block-level compression within function bodies for LLM code context

**Date**: 2026-02-12
**Status**: Research complete
**Relevance**: High -- candidate for new zoom level or post-processor in tldr-swinton

---

## 1. Paper Identity

| Field | Value |
|-------|-------|
| **Full Title** | LongCodeZip: Compress Long Context for Code Language Models |
| **Authors** | Yuling Shi (Zhejiang University), Yichun Qian (Ant Group), Hongyu Zhang (University of Newcastle), Beijun Shen (Zhejiang University), Xiaodong Gu (Zhejiang University) |
| **Venue** | ASE 2025 (40th IEEE/ACM International Conference on Automated Software Engineering) |
| **arXiv** | [2510.00446](https://arxiv.org/abs/2510.00446) (submitted October 1, 2025) |
| **GitHub** | [YerbaPage/LongCodeZip](https://github.com/YerbaPage/LongCodeZip) |
| **License** | MIT |
| **HuggingFace** | [papers/2510.00446](https://huggingface.co/papers/2510.00446) (107 upvotes) |

---

## 2. The Algorithm: Dual-Stage Hierarchical Compression

LongCodeZip is a **training-free, model-agnostic, plug-and-play** compression framework with two stages:

### Stage 1: Coarse-Grained Compression (Function-Level)

1. **Function-based chunking**: Parse source code with **tree-sitter** to extract function-level chunks (each function becomes a "chunk").

2. **Ranking via Approximated Mutual Information (AMI)**: For each function chunk `c` and query/instruction `q`, compute:

   ```
   AMI(c, q) = PPL(q) - PPL(q | c)
   ```

   Where PPL is perplexity:
   ```
   PPL(q | c) = exp(-1/N * sum(log P(q_i | q_{<i}, c)))
   ```

   AMI measures how much providing a function chunk as context *reduces* the perplexity of generating the target query/instruction. Higher AMI = more relevant function.

3. **Token budget allocation**: Select top-ranked functions under a coarse token budget:
   ```
   B_coarse = B / R_fine
   ```
   where `B` is the total target budget and `R_fine` accounts for the expected further compression in stage 2.

### Stage 2: Fine-Grained Compression (Block-Level)

1. **Perplexity-based block detection**: Within each retained function, compute **line-level perplexity** (perplexity of each line without context). When a line's perplexity exhibits a **sharp local increase** -- exceeding that of its neighbors by at least `alpha` times the standard deviation -- it is marked as a **block boundary**. This naturally groups semantically related lines into blocks.

2. **Adaptive per-function budget**: Each function receives a proportional budget based on its importance:
   ```
   R_biased_i = R_base * (1 + beta * (2 * AMI_norm_i - 1))
   ```
   where `beta` controls sensitivity to importance, and rates are globally rescaled to match the target budget. More important functions get a higher retention rate.

3. **0/1 Knapsack optimization**: Each block within a function becomes an item:
   - **Value** = normalized AMI score (min-max normalized to [0, 1]) -- how much the block reduces perplexity of the target
   - **Weight** = token count of the block
   - **Constraint** = per-function token budget
   - Solved with **dynamic programming** to select the optimal subset of blocks that maximizes cumulative relevance within the allocated budget.

4. **Output**: The selected blocks are concatenated in source order, preserving structural integrity.

### Visual Summary

```
Source File
  |
  v
[tree-sitter parse] --> Function chunks: f1, f2, f3, ..., fN
  |
  v
[Compute AMI(fi, query)] --> Rank functions by relevance
  |
  v
[Select top-K under B_coarse] --> Retained functions
  |
  v  (for each retained function)
[Line-level perplexity] --> Block boundaries where PPL spikes
  |
  v
[Block segmentation] --> Blocks: b1, b2, ..., bM per function
  |
  v
[Compute AMI(bi, query)] --> Block values
  |
  v
[0/1 Knapsack DP] --> Selected blocks per function
  |
  v
[Concatenate in source order] --> Compressed output
```

---

## 3. Compression Results

### Headline Numbers

| Task | Max Compression Ratio | Model |
|------|-----------------------|-------|
| Long Code Completion | **5.6x** | Seed-Coder-8B |
| Long Module Summarization | 2.5x -- 3.5x | Deepseek-6.7B / Seed-8B |
| RepoQA (question answering) | **5.3x** | Various |

### What "5.6x Compression" Means in Practice

- **Input**: A long code context (e.g., a full repository file or multiple related files) with N tokens
- **Output**: N/5.6 tokens (roughly 18% of original), containing only the most relevant function blocks
- **Token cost reduction**: ~77% fewer input tokens sent to the LLM
- **Latency reduction**: Generation time drops from 15.70s to 6.59s (58% faster)
- **Semantic preservation**: Task performance (code completion accuracy, summarization quality, QA accuracy) is maintained or improved compared to full context

### How Semantics Are Preserved

1. **Query-aware selection**: Both stages use AMI computed against the specific query/instruction, ensuring retained content is task-relevant.
2. **Block-level granularity**: Instead of discarding entire functions or random tokens, it selects semantically coherent blocks (groups of related lines).
3. **Structural ordering**: Selected blocks maintain their original source order, preserving code structure.
4. **Perplexity as proxy for information content**: High-perplexity lines (surprising to the model) tend to be informationally rich; low-perplexity lines (predictable boilerplate) can be safely removed.

### Comparison with Baselines

| Method | Approach | LongCodeZip Advantage |
|--------|----------|----------------------|
| Random Token/Line | Remove random content | LCZ is query-aware |
| RAG (Sliding Window) | Retrieve by similarity | LCZ operates at finer block granularity |
| RAG (Function Chunking) | Retrieve whole functions | LCZ compresses within functions |
| LLMLingua/LLMLingua-2 | Token-level perplexity pruning | LCZ uses block-level (more coherent) |
| DietCode | CodeBERT attention heuristics | LCZ is model-agnostic |
| SlimCode | Rule-based token pruning + PDG | LCZ uses query-conditional relevance |
| A3-CodGen, cAST, RepoGenix | RAG-based retrieval | LCZ adds fine-grained compression |

### Compression Overhead

| Metric | Value |
|--------|-------|
| Compression time overhead | 2.58s (vs. baselines < 1s) |
| GPU memory for compression | Depends on compression model size |
| Mitigation | Use 0.5B model (Qwen2.5-Coder-0.5B) with negligible quality loss |
| Net effect | Compression overhead << saved generation time |

---

## 4. Implementation Details

### Repository Structure

```
LongCodeZip/
├── longcodezip/          # Main Python package
│   └── __init__.py       # Exports LongCodeZip class
├── experiments/          # Experimental evaluation code
├── assets/               # Example files
├── demo.py               # Usage demonstration
├── requirements.txt      # Dependencies
├── setup.py              # Package configuration
├── pyproject.toml        # Build config
└── LICENSE               # MIT
```

### Dependencies

```
accelerate
appdirs
datasets
editdistance
fire
loguru
matplotlib
nltk
numpy
openai>=1.0.0
rich
torch
transformers
tqdm
tree-sitter==0.21.3       # Pinned -- older API
tree-sitter-languages     # Pre-built language parsers
tempdir
wget
```

**Key observations:**
- **tree-sitter==0.21.3** is pinned (older version). tldr-swinton uses newer tree-sitter APIs with per-language packages (tree-sitter-python, tree-sitter-javascript, etc.). This is a compatibility concern.
- **torch + transformers** are required for the perplexity computation (running a language model for scoring). This is the heaviest dependency.
- The compression model defaults to **Qwen/Qwen2.5-Coder-7B-Instruct** but can use models as small as **0.5B** with minimal quality loss.
- Also supports **OpenAI API** for the generation step (not the compression step).

### Python API

```python
from longcodezip import LongCodeZip

# Initialize with a compression model
compressor = LongCodeZip(model_name="Qwen/Qwen2.5-Coder-0.5B-Instruct")

# Compute target ratio from token budget
original_tokens = len(compressor.tokenizer.encode(source_code))
target_ratio = min(1.0, max(0.0, target_tokens / original_tokens))

# Coarse-grained only (function ranking)
result = compressor.compress_code_file(
    code=source_code,
    query=query_text,
    instruction="Complete the following code function given the context.",
    rate=target_ratio,
    rank_only=True,    # Only stage 1
)

# Full two-stage compression (function ranking + block selection)
result = compressor.compress_code_file(
    code=source_code,
    query=query_text,
    instruction="Complete the following code function given the context.",
    rate=target_ratio,
    rank_only=False,   # Both stages
)

# Result dict
result["compressed_prompt"]     # The compressed code
result["compression_ratio"]     # Achieved ratio
```

### Models Evaluated

**Open-source (for both compression and generation):**
- Deepseek-Coder-6.7B
- Qwen2.5-Coder-7B-Instruct
- Seed-Coder-8B
- Qwen2.5-Coder-0.5B (lightweight compressor)

**Closed-source (generation only):**
- GPT-4o
- Claude-3.7-Sonnet

### Limitations (From Paper)

1. **Ambiguous instructions**: When the context lacks task-relevant information or when the instruction is too ambiguous to align with any code segment, the method struggles.
2. **Compression overhead**: 2.58s overhead per compression call (mitigated by using smaller compression models).
3. **GPU requirement**: Needs a GPU to run the compression model for perplexity computation.
4. **Language coverage**: Uses tree-sitter for function chunking, so coverage depends on tree-sitter grammar availability (broad but not universal).

---

## 5. Integration Feasibility with tldr-swinton

### Current Zoom Level Architecture

tldr-swinton has a 5-level zoom system in `src/tldr_swinton/modules/core/zoom.py`:

| Level | Name | Content |
|-------|------|---------|
| L0 | Module map | File list + 1-line descriptions |
| L1 | Signatures | Symbol signatures + docstring first line |
| L2 | Body sketch | Control-flow skeleton via tree-sitter |
| L3 | Windowed | Diff-relevant code windows |
| L4 | Full | Complete source code |

The zoom system is used by `format_at_zoom()` which takes a symbol ID, signature, code, zoom level, and language.

### Integration Options

#### Option A: New Zoom Level L2.5 ("Compressed Body")

**Concept**: Insert between L2 (body sketch) and L3 (windowed), offering a query-aware compressed view that retains more detail than a skeleton but much less than full code.

**Pros:**
- Fits naturally in the progressive disclosure hierarchy
- L2 = structural skeleton, L2.5 = semantically-relevant blocks, L3 = windowed, L4 = full
- Query-awareness means compression adapts to what the LLM needs

**Cons:**
- Requires an LM for perplexity scoring (heavy dependency)
- Not purely structural like other zoom levels
- Breaks the clean L0-L4 numbering

#### Option B: Post-Processor on L4 Output

**Concept**: Apply LongCodeZip as a post-processing step on the full L4 context pack output, compressing it before sending to the LLM. This would be a "budget-aware" final stage.

**Pros:**
- No changes to existing zoom architecture
- Works on any output format
- Natural fit: ContextPack already has a budget/token concept
- Can be toggled on/off independently

**Cons:**
- Requires running an LM for compression (latency + GPU)
- Post-processing the whole context pack is a different granularity than per-function compression

#### Option C: Hybrid -- Lightweight Block Detection Without LM (Recommended)

**Concept**: Extract the *block detection algorithm* from LongCodeZip (perplexity-based boundary detection) but replace the LM-based perplexity scoring with a **heuristic proxy**:

1. Use tree-sitter AST to identify **semantic block boundaries** (similar to L2 body sketch, but producing blocks instead of a skeleton):
   - Function/class definitions
   - Control flow boundaries (if/for/while/try)
   - Blank-line separated blocks
   - Decorator groups
   - Comment/docstring boundaries

2. Score blocks using **existing relevance signals** from tldr-swinton:
   - Candidate relevance scores (already computed)
   - Semantic similarity to query (already have embedding infrastructure)
   - Diff proximity (for diff-aware contexts)
   - Call graph distance from focal function

3. Apply the **knapsack optimization** to select blocks within a token budget.

**Pros:**
- No LM dependency for compression -- uses existing infrastructure
- Reuses tree-sitter parsers already in zoom.py
- Knapsack optimization is trivial to implement (pure Python, no deps)
- Can work as a new zoom level (L2.5) or post-processor
- Preserves the key insight: block-level granularity + budget-aware selection

**Cons:**
- Without LM perplexity, block boundaries may be less semantically precise
- Relevance scoring is approximate (but so is LongCodeZip's -- it uses a 0.5B model)

#### Option D: Full LongCodeZip Integration (GPU-Required Mode)

**Concept**: Add LongCodeZip as an optional dependency, activated via `--compress` flag or when a GPU is available.

**Pros:**
- Gets the full paper's quality
- MIT license, pip-installable

**Cons:**
- tree-sitter version conflict (LCZ pins 0.21.3, tldrs uses newer per-language packages)
- Torch/transformers heavyweight deps
- GPU required
- LCZ's `compress_code_file()` API expects single-file input, not multi-file context packs

### Recommended Integration Path

**Phase 1 (immediate value, no new deps):**
- Implement Option C: AST-based block detection + knapsack selection
- New zoom level L2.5 or a `--budget` flag that activates block-level compression
- Use tree-sitter to segment functions into blocks at control-flow boundaries
- Score blocks with existing relevance/similarity scores
- Select blocks via 0/1 knapsack DP

**Phase 2 (optional, for users with GPU):**
- Add `longcodezip` as an optional dependency
- Fork or vendor the compression logic to handle the tree-sitter version mismatch
- Expose as `--compress longcodezip` mode
- Use it to validate Phase 1's heuristic quality against the LM-based approach

### Implementation Sketch for Phase 1

```python
# New file: src/tldr_swinton/modules/core/block_compress.py

from dataclasses import dataclass
from typing import Sequence

@dataclass
class CodeBlock:
    """A semantically coherent block within a function body."""
    start_line: int
    end_line: int
    text: str
    token_count: int
    relevance: float  # 0.0-1.0 normalized score

def segment_into_blocks(
    source: str,
    language: str,
) -> list[CodeBlock]:
    """Segment source code into semantic blocks using tree-sitter.

    Block boundaries are detected at:
    - Function/class definition starts
    - Control flow statement starts (if/for/while/try)
    - Blank line separations
    - Decorator groups
    """
    # Use existing tree-sitter infrastructure from zoom.py
    ...

def knapsack_select(
    blocks: Sequence[CodeBlock],
    budget_tokens: int,
) -> list[CodeBlock]:
    """Select optimal subset of blocks via 0/1 knapsack DP.

    Each block: value=relevance, weight=token_count.
    Returns selected blocks in source order.
    """
    n = len(blocks)
    # Standard DP knapsack
    dp = [[0.0] * (budget_tokens + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        w = blocks[i-1].token_count
        v = blocks[i-1].relevance
        for j in range(budget_tokens + 1):
            dp[i][j] = dp[i-1][j]
            if j >= w:
                dp[i][j] = max(dp[i][j], dp[i-1][j-w] + v)

    # Backtrack to find selected blocks
    selected = []
    j = budget_tokens
    for i in range(n, 0, -1):
        if dp[i][j] != dp[i-1][j]:
            selected.append(blocks[i-1])
            j -= blocks[i-1].token_count

    return sorted(selected, key=lambda b: b.start_line)

def compress_function_body(
    source: str,
    language: str,
    budget_tokens: int,
    relevance_scorer: callable = None,
) -> str:
    """Compress a function body to fit within token budget.

    Uses block segmentation + knapsack optimization.
    Omitted blocks are replaced with '# ... (N lines)' markers.
    """
    blocks = segment_into_blocks(source, language)
    if not blocks:
        return source

    total_tokens = sum(b.token_count for b in blocks)
    if total_tokens <= budget_tokens:
        return source  # Already fits

    # Score blocks (use provided scorer or uniform)
    if relevance_scorer:
        for block in blocks:
            block.relevance = relevance_scorer(block.text)

    selected = knapsack_select(blocks, budget_tokens)
    # Reconstruct with elision markers
    ...
```

### Key Technical Considerations

1. **tree-sitter version**: LongCodeZip pins `tree-sitter==0.21.3` with `tree-sitter-languages` (bundled grammars). tldr-swinton uses newer tree-sitter with individual language packages. These are **incompatible** -- cannot coexist in the same virtualenv. A vendored/forked approach would be needed for full LCZ integration.

2. **Token counting**: LongCodeZip uses the compression model's tokenizer for token counting. For the heuristic approach, use a fast tokenizer (tiktoken) or character-based approximation (4 chars/token).

3. **Knapsack complexity**: O(n * B) where n = number of blocks and B = token budget. For typical function bodies (< 100 blocks, budget < 10K tokens), this is near-instant.

4. **Block boundary quality**: The paper's perplexity-based boundaries are empirically better than pure AST boundaries, but AST boundaries are free (no LM inference) and still produce semantically coherent blocks.

5. **Multi-file context**: LongCodeZip's API is single-file. tldr-swinton's ContextPack is multi-file. The integration should apply block compression per-function within the existing candidate pipeline.

---

## 6. Related Work and Context

### Compared Methods (from the paper)

- **LLMLingua / LLMLingua-2**: Token-level perplexity-based pruning (not code-specific)
- **DietCode**: CodeBERT attention + frequency-based filtering
- **SlimCode**: Rule-based token pruning using program dependency graphs
- **RAG approaches**: A3-CodGen, cAST, RepoGenix, RLCoder (retrieve, don't compress)
- **Repomix**: Code compression for repo-level context (different approach)

### Key Insight for tldr-swinton

The paper validates that **block-level granularity** (groups of 3-15 lines) is the sweet spot for code compression -- more coherent than token-level, more precise than function-level. This aligns with tldr-swinton's philosophy of progressive disclosure (L0 through L4). A block-compressed view fills the gap between L2 (skeleton) and L3/L4 (full/windowed code) where useful detail is preserved but boilerplate is elided.

---

## 7. Raw Links and References

- **Paper (arXiv)**: https://arxiv.org/abs/2510.00446
- **Paper (HTML)**: https://arxiv.org/html/2510.00446v1
- **Paper (PDF)**: https://arxiv.org/pdf/2510.00446
- **GitHub Repo**: https://github.com/YerbaPage/LongCodeZip
- **HuggingFace Discussion**: https://huggingface.co/papers/2510.00446
- **ResearchGate**: https://www.researchgate.net/publication/396094482
- **Related -- DietCode**: Token-level code compression
- **Related -- SlimCode**: https://github.com/gksajy/SlimCode
- **Related -- LLMLingua**: General-purpose prompt compression
- **Related -- Repomix**: https://repomix.com/guide/code-compress
