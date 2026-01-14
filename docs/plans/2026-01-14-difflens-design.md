# DiffLens Design

**Goal:** Provide diff‑first context packs that prioritize changed symbols and minimal surrounding dependencies, with ultracompact CLI output by default.

## Architecture

DiffLens is implemented as a new API entry point `get_diff_context(...)` in `tldr_swinton.api` and a CLI command `tldrs diff-context`. The CLI default base is the merge‑base with `main`/`master` (fallback `HEAD~1`) and default output is ultracompact text; `--format json` returns a structured ContextPack.

The flow is:
1. Resolve project root and detect git availability.
2. Resolve `base` and `head` refs, prefer merge‑base with `main` or `master`.
3. Run `git diff --unified=0 base..head` and include working tree changes.
4. Parse hunks into file + line ranges.
5. Map each hunk to an enclosing symbol using AST ranges (HybridExtractor) and build symbol IDs (`relpath:qualified_name`).
6. Expand context one hop in the call graph (callers/callees) for dependency awareness.
7. Rank: contains diff > caller/callee > file fallback.
8. Budget: include full code slices for top symbols, signatures only for overflow.
9. Output: ultracompact pack or JSON ContextPack.

Non‑git repos fall back to recently modified files or current working set.

## CLI

```
# Default (ultracompact)
tldrs diff-context --base main

# JSON pack
 tldrs diff-context --format json
```

## Output (ContextPack JSON)

```json
{
  "base": "main",
  "head": "HEAD",
  "budget_used": 1847,
  "slices": [
    {
      "id": "src/auth.ts:validateToken",
      "relevance": "contains_diff",
      "signature": "async function validateToken(token: string): Promise<boolean>",
      "code": "...",
      "lines": [45, 72],
      "diff_lines": [52, 53, 58]
    }
  ],
  "signatures_only": ["src/routes/api.ts:handleLogin"]
}
```
