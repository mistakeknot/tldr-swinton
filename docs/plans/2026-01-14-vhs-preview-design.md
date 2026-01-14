# VHS Preview Output Design

**Goal:** When `tldrs context --output vhs` is used, emit a compact inline preview alongside the `vhs://` ref to preserve token savings while keeping immediate relevance.

## Design Summary

We keep the existing behavior of generating full context output, but when the user chooses `--output vhs`, we now write that full output into the local VHS store and also print a short inline preview to stdout. The preview consists of two parts: (1) a deterministic one‑line summary derived from the `RelevantContext` object (entry point, depth, function count, file count) and (2) a mixed‑cap snippet of the output (max 30 lines, max 2048 bytes). The snippet is built from complete lines only and stops before the first line that would exceed the byte cap, preventing mid‑line truncation.

To preserve script compatibility, the first line of stdout remains the raw `vhs://` ref. Subsequent lines are prefixed with clear markers (`# Summary:` and `# Preview:`) so humans and agents can quickly parse the result, while automated tooling can still reliably read the ref from line 1. The preview logic lives in the CLI module to avoid changing the core formatting pipeline, and defaults are fixed (30 lines / 2 KB) to keep the interface minimal.

Testing uses pure helper functions to validate line and byte caps, as well as summary formatting. CLI behavior is exercised in a small subprocess test to ensure the ref is still the first line and preview markers appear when `--output vhs` is selected.
