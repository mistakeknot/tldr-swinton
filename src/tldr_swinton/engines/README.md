# Engines

Discrete context strategies exposed as stable entry points.

## Overview

Each engine module wraps a specific context strategy. Today these are thin
wrappers around `tldr_swinton.api`, but the intent is to migrate logic into
these modules over time while keeping call sites stable.

## Engines

- `symbolkite.py`
  - Call-graph based context via `get_relevant_context`.
  - Best for entry-point expansion with depth control.

- `difflens.py`
  - Diff-centric ContextPack via `get_diff_context`.
  - Best for recent-change views and patch-focused context.

- `cfg.py`
  - Control flow graphs via `get_cfg_context`.
  - Best for branch structure and complexity insights.

- `dfg.py`
  - Data flow graphs via `get_dfg_context`.
  - Best for variable usage/def-use tracing.

- `pdg.py`
  - Program dependence graph via `get_pdg_context`.
  - Best for dependency-aware slicing.

- `slice.py`
  - Program slicing via `get_slice`.
  - Best for minimal line-focused context.

## Migration plan

1) Keep the current API stable (import paths stay the same).
2) Move implementation details from `api.py` into the engine modules.
3) Leave thin wrappers in `api.py` that delegate to engines.
4) Update docs/tests to refer to `tldr_swinton.engines.*`.
