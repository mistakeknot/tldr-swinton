# MCP Server Implementation Analysis

**Date:** 2026-02-14  
**Project:** tldr-swinton v0.7.3  
**Purpose:** Comprehensive analysis of the MCP server architecture for buildInstructions implementation

---

## Executive Summary

The tldrs MCP server (`tldr-code`) is implemented using FastMCP and provides 24 tool functions across 7 capability categories. The server supports **static instructions** via the `FastMCP(instructions=...)` constructor parameter, but does **not** currently have dynamic context injection (like `buildInstructions()`). 

Key architecture:
- **Entry point:** `tldr-mcp` command → `src/tldr_swinton/modules/core/mcp_server.py:main()`
- **Framework:** FastMCP (mcp.server.fastmcp)
- **Transport:** stdio (declared in `.claude-plugin/plugin.json`)
- **Tool registration:** `@mcp.tool()` decorator pattern
- **Daemon integration:** Tools communicate with a background daemon via Unix socket

---

## 1. MCP Server Source Code

**Location:** `/root/projects/tldr-swinton/src/tldr_swinton/modules/core/mcp_server.py` (855 lines)

### 1.1 Server Initialization

```python
# Line 39
mcp = FastMCP("tldr-code") if _MCP_AVAILABLE else _NoMCP("tldr-code")

# Line 838-850 (main function)
def main():
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description="TLDR MCP Server")
    parser.add_argument("--project", default=".", help="Project root directory")
    args = parser.parse_args()
    
    # Set default project for tools that need it
    os.environ["TLDR_PROJECT"] = str(Path(args.project).resolve())
    
    mcp.run(transport="stdio")
```

**Current limitation:** Instructions are NOT set during initialization. The FastMCP instance is created with only a name parameter.

### 1.2 FastMCP Constructor Signature

From `/root/projects/tldr-swinton/.venv/lib/python3.12/site-packages/mcp/server/fastmcp/server.py`:

```python
def __init__(
    self,
    name: str | None = None,
    instructions: str | None = None,  # ← KEY PARAMETER
    website_url: str | None = None,
    icons: list[Icon] | None = None,
    # ... (20+ more parameters)
):
```

**Key properties:**
- `instructions` is passed to the underlying `MCPServer` (line 205-207)
- Exposed as read-only property: `@property def instructions(self) -> str | None`
- Set **once at construction time** — no dynamic update API visible

---

## 2. Tool Registration Surface

All tools use the `@mcp.tool()` decorator pattern. Tools are grouped into 7 functional categories:

### 2.1 Navigation Tools (4 tools)

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `tree()` | File tree structure | `extensions: list[str] \| None` |
| `structure()` | Code structure (codemaps) | `language: str`, `max_results: int` |
| `search()` | Regex pattern search | `pattern: str`, `max_results: int` |
| `extract()` | File structure extraction | `file: str`, `compact: bool` |

**Note:** `extract(compact=True)` bypasses daemon, calls `compact_extract()` directly for 87% size savings.

### 2.2 Context Tools (1 flagship tool)

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `context()` | Token-efficient LLM context | `entry: str`, `preset: str \| None`, `depth: int`, `format: str`, `budget: int \| None`, `with_docs: bool`, `session_id: str \| None`, `delta: bool` |

**Presets:** `compact`, `minimal`, `agent`, `multi-turn` (defined in `src/tldr_swinton/presets.py`)

**Key innovation:** 93% token savings when comparing signatures to full files. For editing workflows, expect 20-35% savings.

### 2.3 Flow Analysis Tools (3 tools)

| Tool | Purpose | Returns |
|------|---------|---------|
| `cfg()` | Control flow graph | Basic blocks, edges, cyclomatic complexity |
| `dfg()` | Data flow graph | Variable references, def-use chains |
| `slice()` | Program slice | Lines affecting/affected by a given line |

### 2.4 Codebase Analysis Tools (4 tools)

| Tool | Purpose | Key Feature |
|------|---------|-------------|
| `impact()` | Reverse call graph (find callers) | Noise stripping via `_strip_impact_noise()` |
| `dead()` | Find unreachable code | Entry point pattern matching |
| `arch()` | Detect architectural layers | Identifies circular dependencies |
| `calls()` | Cross-file call graph | Project-wide function relationships |

### 2.5 Import Analysis (2 tools)

| Tool | Purpose |
|------|---------|
| `imports()` | Parse imports from a file |
| `importers()` | Find files importing a module |

### 2.6 Semantic Search (1 tool)

| Tool | Purpose | Notes |
|------|---------|-------|
| `semantic()` | Vector similarity search | Auto-downloads embedding model, builds index on first use |

### 2.7 Quality Tools (2 tools)

| Tool | Purpose | Language Support |
|------|---------|------------------|
| `diagnostics()` | Type and lint checks | Python: pyright (types) + ruff (lint) |
| `change_impact()` | Find affected tests | Uses call graph + import analysis |

### 2.8 Direct-Call Tools (5 tools, bypass daemon)

These tools call Python APIs directly, avoiding the daemon socket overhead:

| Tool | Purpose | Key Feature |
|------|---------|-------------|
| `diff_context()` | **Flagship:** Git-aware diff context | Presets: `compact`, `minimal`, `multi-turn` |
| `structural_search()` | ast-grep pattern matching | Meta-variables: `$VAR`, `$$$ARGS` |
| `delegate()` | Incremental context retrieval plan | 50%+ reduction in wasted retrieval |
| `verify_coherence()` | Cross-file edit verification | Signature mismatches, import inconsistencies |
| `distill()` | Compressed prescriptive context | Ideal for sub-agent consumption |
| `hotspots()` | Attention tracking analysis | Requires `.tldrs/attention.db` |

### 2.9 Daemon Management (1 tool)

| Tool | Purpose |
|------|---------|
| `status()` | Daemon uptime and cache stats |

**Total:** 24 tools

---

## 3. Daemon Integration Architecture

### 3.1 Socket-Based Communication

```python
def _get_socket_path(project: str) -> Path:
    """Compute socket path matching daemon.py logic."""
    hash_val = hashlib.md5(str(Path(project).resolve()).encode()).hexdigest()[:8]
    return Path(f"/tmp/tldr-{hash_val}.sock")
```

### 3.2 Auto-Start Logic

```python
def _ensure_daemon(project: str, timeout: float = 10.0) -> None:
    """Ensure daemon is running, starting it if needed."""
    socket_path = _get_socket_path(project)
    
    if socket_path.exists():
        # Try to ping existing daemon
        try:
            result = _send_raw(project, {"cmd": "ping"})
            if result.get("status") == "ok":
                return  # Daemon is alive
        except Exception as e:
            # Stale socket — clean up and restart
            socket_path.unlink(missing_ok=True)
    
    # Start daemon in background
    subprocess.Popen([
        sys.executable, "-m", "tldr_swinton.cli", 
        "daemon", "start", "--project", project
    ], ...)
```

### 3.3 Response Unwrapping

All daemon responses follow this pattern:
```python
def _send_command(project: str, command: dict) -> dict:
    """Send command to daemon, auto-starting if needed."""
    _ensure_daemon(project)
    response = _send_raw(project, command)
    if (
        isinstance(response, dict)
        and response.get("status") == "ok"
        and "result" in response
    ):
        return response["result"]  # Unwrap envelope
    return response
```

---

## 4. Plugin Configuration

**Location:** `.claude-plugin/plugin.json`

```json
{
  "name": "tldr-swinton",
  "version": "0.7.3",
  "mcpServers": {
    "tldr-code": {
      "type": "stdio",
      "command": "tldr-mcp",
      "args": ["--project", "."]
    }
  }
}
```

**Entry point:** `pyproject.toml` declares `tldr-mcp` script:
```toml
[project.scripts]
tldr-mcp = "tldr_swinton.modules.core.mcp_server:main"
```

---

## 5. Preset System (Context Configuration)

**Location:** `src/tldr_swinton/presets.py`

### 5.1 Preset Definitions

```python
PRESETS = {
    "compact": {
        "format": "ultracompact",
        "budget": 2000,
        "compress_imports": True,
        "strip_comments": True,
    },
    "minimal": {
        "format": "ultracompact",
        "budget": 1500,
        "compress": "blocks",
        "compress_imports": True,
        "strip_comments": True,
        "type_prune": True,
    },
    "agent": {
        "format": "ultracompact",
        "budget": 4000,
        "compress_imports": True,
        "strip_comments": True,
        "type_prune": True,
    },
    "multi-turn": {
        "format": "cache-friendly",
        "budget": 2000,
        "session_id": "auto",
        "delta": True,
    },
}
```

### 5.2 Session ID Resolution

```python
def resolve_auto_session_id(project_root: str = ".") -> str:
    """Generate stable session ID from CLAUDE_SESSION_ID env or CWD+HEAD hash."""
    env_id = os.environ.get("CLAUDE_SESSION_ID")
    if env_id:
        return env_id
    
    # Fallback: hash of project path + git HEAD
    project = Path(project_root).resolve()
    head = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True
    ).stdout.strip()
    
    raw = f"{project}:{head}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]
```

**Key insight:** `CLAUDE_SESSION_ID` env var is the primary session identifier. This is set by Claude Code and available to MCP tools.

---

## 6. Hooks Integration

**Location:** `.claude-plugin/hooks/hooks.json`

### 6.1 Hook Definitions

```json
{
  "hooks": {
    "Setup": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/setup.sh",
            "timeout": 10
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "mcp__plugin_serena_serena__replace_symbol_body",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/pre-serena-edit.sh\"",
            "timeout": 8
          }
        ]
      },
      {
        "matcher": "mcp__plugin_serena_serena__rename_symbol",
        "hooks": [/* same as above */]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Read",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/post-read-extract.sh\"",
            "timeout": 8
          }
        ]
      }
    ]
  }
}
```

### 6.2 Hook Stdin API

**Critical:** Hooks receive JSON on stdin, NOT env vars.

Example from `post-read-extract.sh`:
```bash
# Read stdin (hook input is JSON)
INPUT=$(cat 2>/dev/null) || exit 0

# Extract file path
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""' 2>/dev/null) || exit 0

# Extract session ID for per-file flagging
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""' 2>/dev/null) || exit 0
```

**Available fields in hook stdin:**
- `.session_id` — Claude Code session identifier
- `.tool_name` — Name of the tool being called
- `.tool_input` — Tool parameters (e.g., `.tool_input.file_path` for Read)

---

## 7. Skills (Orchestration Layer)

**Location:** `.claude-plugin/skills/`

### 7.1 Available Skills

1. **tldrs-session-start** — Diff-focused reconnaissance before reading files
2. **tldrs-map-codebase** — Architecture exploration for unfamiliar projects
3. **tldrs-ashpool-sync** — Sync eval coverage with tldrs capabilities

### 7.2 Session-Start Skill Pattern

**File:** `.claude-plugin/skills/tldrs-session-start/SKILL.md`

```markdown
## Decision Tree

### 1. Are there recent changes?

Check: `git status` or `git diff --stat HEAD`

**YES — changes exist:**
```bash
tldrs diff-context --project . --preset compact
```

**YES + large diff (>500 lines changed):**
```bash
tldrs diff-context --project . --preset minimal
```

**NO — clean working tree:**
```bash
tldrs structure src/
```

### 2. Is this a multi-turn task?

If you expect multiple rounds of queries on the same codebase:
```bash
tldrs diff-context --project . --preset compact --session-id auto
```
```

**Key pattern:** Skills use bash commands, not MCP tool calls. They invoke the `tldrs` CLI directly.

---

## 8. buildInstructions() Gap Analysis

### 8.1 Current State

- **Static instructions:** Supported via `FastMCP(instructions="...")` constructor
- **Dynamic instructions:** NOT supported — no `buildInstructions()` method or callback
- **Context available to tools:**
  - `project` parameter (from CLI args or tool params)
  - `TLDR_PROJECT` env var (set in `main()`)
  - `CLAUDE_SESSION_ID` env var (from Claude Code, accessible via `os.environ`)

### 8.2 What buildInstructions() Could Provide

Hypothetical dynamic context injection:

```python
def buildInstructions() -> str:
    """Generate dynamic instructions based on current project state."""
    project = os.environ.get("TLDR_PROJECT", ".")
    session_id = os.environ.get("CLAUDE_SESSION_ID")
    
    # Detect project type
    has_git = Path(project, ".git").exists()
    has_tldrs = Path(project, ".tldrs").exists()
    
    # Build context-aware guidance
    parts = [
        "# tldr-code MCP Server",
        "",
        f"**Project:** {Path(project).name}",
    ]
    
    if has_git:
        # Check for uncommitted changes
        try:
            diff_stat = subprocess.run(
                ["git", "-C", project, "diff", "--stat", "HEAD"],
                capture_output=True, text=True, check=True
            ).stdout.strip()
            if diff_stat:
                parts.append("**Status:** Uncommitted changes detected")
                parts.append("**Recommended:** Use `diff_context` with preset 'compact'")
        except:
            pass
    
    if has_tldrs:
        parts.append("**Semantic index:** Ready")
    else:
        parts.append("**Semantic index:** Not built (run `tldrs index .` to enable)")
    
    if session_id:
        parts.append(f"**Session:** {session_id[:8]}... (delta mode available)")
    
    return "\n".join(parts)
```

### 8.3 Alternative: Lifespan Hook

FastMCP supports a `lifespan` callback:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def server_lifespan(app: FastMCP):
    # Startup: could inject instructions here if API allowed mutation
    project = os.environ.get("TLDR_PROJECT", ".")
    print(f"tldrs MCP server starting for project: {project}", file=sys.stderr)
    
    yield  # Server runs
    
    # Shutdown
    print("tldrs MCP server shutting down", file=sys.stderr)

mcp = FastMCP(
    "tldr-code",
    instructions="Static instructions here",  # Still static
    lifespan=server_lifespan
)
```

**Limitation:** Lifespan runs once at startup. Instructions are still set once in constructor.

---

## 9. Output Formats

**Location:** `src/tldr_swinton/modules/core/output_formats.py`

### 9.1 Format Types

| Format | Use Case | Features |
|--------|----------|----------|
| `text` | Human-readable output | Full function bodies, imports, calls |
| `ultracompact` | LLM-optimized (default) | Signatures only, token budget enforcement |
| `cache-friendly` | Multi-turn sessions | Delta markers, cache stats, [UNCHANGED] symbols |
| `json` | Programmatic consumption | Full structured data |
| `json-pretty` | Debugging | Pretty-printed JSON |

### 9.2 Token Budget Enforcement

```python
def compute_max_calls(budget_tokens: int | None = None) -> int:
    """Compute token-aware max calls to display."""
    if budget_tokens is None:
        return MAX_CALLS_DEFAULT  # 12
    
    if budget_tokens < 1000:
        return MAX_CALLS_MIN  # 3
    elif budget_tokens < 2000:
        return 5
    elif budget_tokens < 3000:
        return 8
    elif budget_tokens < 5000:
        return MAX_CALLS_DEFAULT  # 12
    else:
        return MAX_CALLS_MAX  # 20
```

**Token estimation:** `len(text) / 4` (rough approximation)

---

## 10. Command Surface (Slash Commands)

**Location:** `.claude-plugin/commands/`

### 10.1 Available Commands

1. **`/tldrs-find`** — Semantic code search
2. **`/tldrs-diff`** — Diff-focused context (maps to `diff_context` tool)
3. **`/tldrs-context`** — Symbol-level context (maps to `context` tool)
4. **`/tldrs-structural`** — Structural search (maps to `structural_search` tool)
5. **`/tldrs-quickstart`** — Quick reference guide
6. **`/tldrs-extract`** — File structure extraction

### 10.2 Command Template Pattern

From `.claude-plugin/commands/diff-context.md`:

```yaml
---
name: tldrs-diff
description: Get token-efficient context for recent changes
arguments:
  - name: budget
    description: Token budget (default 2000)
    required: false
  - name: session
    description: Session ID for delta mode
    required: false
  - name: no-verify
    description: Skip coherence verification
    required: false
---

Generate diff-focused context pack for recent changes.

```bash
tldrs diff-context --project . \
  --budget ${ARGUMENTS.budget:-2000} \
  ${ARGUMENTS.session:+--session-id $ARGUMENTS.session} \
  ${ARGUMENTS.no-verify:+--no-verify}
```
```

**Key insight:** Commands invoke the `tldrs` CLI, NOT the MCP tools directly. This is by design — the CLI has richer flags and error handling.

---

## 11. Recommendations for buildInstructions() Implementation

### 11.1 Static Approach (Immediate)

Add static instructions to the FastMCP constructor:

```python
mcp = FastMCP(
    "tldr-code",
    instructions="""
# tldr-code MCP Server

Token-efficient code reconnaissance for LLMs.

## Quick Start

1. **Diff-focused workflow:** Use `diff_context` with preset 'compact' for 48-73% token savings
2. **Semantic search:** Use `semantic` to find code by meaning (requires index: `tldrs index .`)
3. **Multi-turn sessions:** Add `session_id` to enable delta mode (60% savings on unchanged symbols)

## Recommended Tool Combinations

- **Bug fixing:** `diff_context` → `context` for symbols → `impact` for callers
- **Code review:** `diff_context` with preset 'minimal' → `verify_coherence`
- **Refactoring:** `impact` → `context` → `structural_search` for patterns

## Presets

- `compact`: Default (2000 tokens, import compression, no comments)
- `minimal`: Aggressive (1500 tokens, block pruning, type pruning)
- `multi-turn`: Cache-friendly with delta tracking

See tool descriptions for parameter details.
"""
)
```

### 11.2 Dynamic Approach (Requires Upstream Change)

If FastMCP adds a `buildInstructions()` callback in the future:

```python
def build_dynamic_instructions() -> str:
    """Generate context-aware instructions."""
    project = os.environ.get("TLDR_PROJECT", ".")
    session_id = os.environ.get("CLAUDE_SESSION_ID")
    
    # Detect project state
    git_status = _check_git_status(project)
    index_status = "ready" if Path(project, ".tldrs").exists() else "not built"
    
    # Build adaptive guidance
    parts = [
        "# tldr-code MCP Server",
        "",
        f"**Current project:** {Path(project).name}",
        f"**Semantic index:** {index_status}",
    ]
    
    if git_status["has_changes"]:
        parts.append(f"**Uncommitted changes:** {git_status['changed_files']} files")
        parts.append("**Recommended:** Start with `diff_context --preset compact`")
    else:
        parts.append("**Clean working tree:** Use `structure` or `semantic` to explore")
    
    if session_id:
        parts.append(f"**Session ID:** {session_id[:8]}... (delta mode available)")
    
    return "\n".join(parts)

# Hypothetical API
mcp = FastMCP(
    "tldr-code",
    build_instructions=build_dynamic_instructions  # Not supported yet
)
```

### 11.3 Workaround: Status Tool Enhancement

Add session-aware context to the `status()` tool:

```python
@mcp.tool()
def status(project: str = ".") -> dict:
    """Get daemon status + session guidance."""
    daemon_status = _send_command(project, {"cmd": "status"})
    
    # Add context-aware guidance
    session_id = os.environ.get("CLAUDE_SESSION_ID")
    has_index = Path(project, ".tldrs").exists()
    
    daemon_status["session_guidance"] = {
        "session_id": session_id,
        "semantic_index": "ready" if has_index else "not built",
        "recommended_preset": "compact",
    }
    
    # Check for uncommitted changes
    try:
        diff_stat = subprocess.run(
            ["git", "-C", project, "diff", "--stat", "HEAD"],
            capture_output=True, text=True, timeout=2
        ).stdout.strip()
        daemon_status["session_guidance"]["has_changes"] = bool(diff_stat)
    except:
        pass
    
    return daemon_status
```

Then update tool descriptions to recommend calling `status()` first.

---

## 12. Key Findings Summary

1. **No buildInstructions() API exists** — FastMCP only supports static `instructions` parameter
2. **24 MCP tools** across 7 categories (navigation, context, flow, analysis, imports, semantic, quality)
3. **Daemon architecture** — most tools communicate via Unix socket (`/tmp/tldr-{hash}.sock`)
4. **Direct-call tools** — 5 flagship tools bypass daemon for performance (diff_context, structural_search, delegate, verify_coherence, distill)
5. **Preset system** — 4 presets (compact, minimal, agent, multi-turn) for token optimization
6. **Session awareness** — `CLAUDE_SESSION_ID` env var available to tools and hooks
7. **Hook stdin API** — Hooks receive JSON with `.session_id`, `.tool_name`, `.tool_input`
8. **Skills invoke CLI** — Skills use `tldrs` CLI commands, not MCP tools directly
9. **Commands invoke CLI** — Slash commands also use `tldrs` CLI for richer error handling
10. **Static instructions recommended** — Add context-aware static instructions as immediate improvement

---

## 13. Next Steps

1. **Add static instructions** to `mcp_server.py:main()` (lines 838-850)
2. **Enhance `status()` tool** with session guidance (workaround for dynamic context)
3. **Monitor FastMCP upstream** for `buildInstructions()` callback support
4. **Document preset recommendations** in static instructions
5. **Add tool combination patterns** to help agents choose the right workflow

---

**End of Analysis**
