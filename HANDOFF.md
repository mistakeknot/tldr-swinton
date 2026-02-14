# Session Handoff — 2026-02-14

## Done
- Rewrote all 24 MCP tool descriptions with "INSTEAD OF"/"BEFORE" framing (commit b8fd278)
- Added FastMCP `instructions` parameter with cost ladder
- Moved param docs from docstrings to `Annotated[type, Field(description=...)]`
- Net token reduction: ~1855 → ~989 tokens (-47%)
- Bumped to v0.7.4, pushed both repos (tldr-swinton + marketplace)

## Pending
- `tldr-swinton-wp7`: ColBERT backend still in progress (unstaged files in `semantic/`)
- Other dirty files: `cli.py`, `daemon.py`, `semantic/__init__.py`, `index.py` — from prior ColBERT work

## Next
- Continue ColBERT backend integration (wp7)
- Test new descriptions in a real Claude Code session to measure adoption
- Consider fixing `bump-version.sh` to use regex instead of literal old-version match

## Context
- Bump script failed because pyproject.toml was 0.7.2 but plugin.json was already 0.7.3 — had to fix manually
- All 401 tests pass (ignore `test_agent_workflow_eval.py` — pre-existing `evals` import error)
