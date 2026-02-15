# Product Requirements Document — tldr-swinton

**Version:** 0.7.6  
**Last updated:** 2026-02-15  
**Vision:** [`docs/vision.md`](vision.md)

---

## 1) Product Definition

tldr-swinton is a token-efficient code context system for AI coding workflows.
It combines extraction, navigation, static analysis, and retrieval into a single
interface exposed by CLI commands and MCP tools.

Its role is to make exploration cheap, repeatable, and action-oriented for:

- `Claude Code` and other AI agents
- plugin/agent orchestration runtimes (for example Clavain)
- human engineers doing high-volume review or triage

The product is intentionally small in interface shape but wide in analysis depth.

## 2) Product Surface (MVP + current state)

### 2.1 CLI (`tldrs`)

- Structural: `extract`, `structure`, `tree`
- Exploration: `find`, `structural`, `search` (regex helper)
- Context: `context`, `diff-context`, `distill`
- Retrieval: `context-delegation` (`delegate`) and `semantic` stack commands
- Analysis: `cfg`, `dfg`, `slice`, `impact`, `dead`, `arch`, `calls`
- Semantic: `find` and `semantic` (index-driven)

### 2.2 MCP (`tldr-mcp`, server name `tldr-code`)

The MCP surface is split by function and intentionally returns compact,
LLM-friendly payloads.

#### Navigation

- `tree`
- `structure`
- `search`
- `extract`

#### Context

- `context`
- `diff_context`
- `delegate`
- `distill`

#### Flow / Dataflow

- `cfg`
- `dfg`
- `slice`

#### Codebase analysis

- `impact`
- `dead`
- `arch`
- `calls`
- `imports`
- `importers`

#### Semantic

- `semantic`
- `semantic_index`
- `semantic_info`

#### Quality / Utility

- `diagnostics`
- `change_impact`
- `verify_coherence`
- `structural_search`
- `status`
- `hotspots`

Total MCP tools in current surface: **24**.

## 3) Key Capabilities

### 3.1 Structural analysis

Symbol extraction and navigation are first-class. tldr-swinton supports:

- Multi-language symbol extraction (Python, TypeScript, JavaScript, Rust, Go, Java,
  C/C++, Ruby, plus optional grammars)
- Fast file orientation (`structure`, `tree`)
- Signature-first views and compact extracts for large files

### 3.2 Semantic search

- Hybrid retrieval: lexical fast-path plus embedding backend.
- FAISS backend (`faiss`) and ColBERT backend (`colbert`) via protocol.
- Backend info and rebuild controls via MCP (`semantic_info`, `semantic_index`).

### 3.3 Call-graph and cross-file reasoning

- Forward and reverse traversal through symbols (`context`, `impact`).
- Whole-graph views where necessary (`calls`, `arch`, `dead`).
- Diff-aware context for changed code (`diff-context`), mapped to affected symbols.

### 3.4 Slicing and flow analysis

- CFG/DFG for control/data path reasoning (`cfg`, `dfg`).
- Program slicing for line-level dependency tracing (`slice`).
- Import chain tracing (`imports`, `importers`).

## 4) Evaluation and Embedding Research Harness

### 4.1 Internal eval stack

tldr-swinton ships with `evals/` scripts for repeatable measurement:

- `evals/token_efficiency_eval.py`
- `evals/semantic_search_eval.py`
- `evals/agent_workflow_eval.py`
- `evals/difflens_eval.py`
- `evals/vhs_eval.py`

### 4.2 Ashpool / interbench integration

The project integrates with the Ashpool/interbench workflow:

- `tldrs manifest` outputs machine-readable commands, formats, flags, and scoring
  hints.
- `interbench/scripts/check_tldrs_sync.py` verifies parity against:
  - `infra/interbench/scripts/regression_suite.json`
  - `infra/interbench/scripts/ab_formats.py`
  - `infra/interbench/demo-tldrs.sh`
  - `infra/interbench/scripts/score_tokens.py`

### 4.3 Benchmarks and research evidence

- `tldr-bench` tracks token savings and context quality on SWE-style and
  official dataset tasks.
- Historical results are published in `docs/token-savings-summary.md` and
  `evals/EVALS.md`.

## 5) Deliverables and Non-goals

### In scope

- LLM-ready context retrieval and token-optimized analysis surfaces.
- Stable MCP/CLI contracts backed by automated sync tools.
- Continuing empirical loop on feature impact and tool adoption.

### Out of scope

- Replacing editing agents.
- Architectural decisions outside code-understanding surfaces.
- One-time benchmark dashboards and marketing artifacts.

## 6) Success Indicators

- Reduction in raw file read volume during agent sessions.
- Adoption of token-efficient paths (`context`, `diff-context`, `extract`) over raw
  Read/Grep workflows.
- Stable or improved agent workflow quality in `agent_workflow_eval`.
- Positive diff-context and token savings trend in interbench + tldr-bench tracks.
