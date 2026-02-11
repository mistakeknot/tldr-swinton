date: 2026-01-28
topic: candidate-cap-rerank

# Candidate Cap + Rerank Pipeline

## What We're Building
Introduce an explicit candidate cap after retrieval/fusion (e.g., top 30) and
an optional rerank stage before emitting context. This keeps outputs tight while
preserving relevance quality.

## Why This Approach
QMD uses RRF fusion, caps to a fixed top‑K, then reranks with an LLM. Even without
LLM reranking, a hard top‑K cap prevents token blowups and forces selectivity.

## Key Decisions
- **Cap**: fixed default cap (e.g., 30) with `--top-k` override.
- **Rerank**: optional rerank stage, off by default; add later if needed.
- **Scope**: apply to `find` and any command that expands context from search results.
- **Diagnostics**: show cap and final count in output headers.

## Open Questions
- Should the cap be global or per file/symbol group?
- If rerank is added, do we cache rerank results per query?
- How does the cap interact with `--min-score` and `--max-bytes`?

## Next Steps
→ If approved, draft an implementation plan and identify affected commands/files.
