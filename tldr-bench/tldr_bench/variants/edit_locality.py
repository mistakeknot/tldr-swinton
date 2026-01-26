"""Edit-locality context variant for benchmarking.

This variant provides context optimized for generating correct patches,
including edit boundaries, invariants, and patch templates.
"""

VARIANT_ID = "edit_locality"


def build_context(task: dict) -> str:
    """Build edit-locality context for a task.

    Returns context optimized for code editing with:
    - Target function code
    - Edit boundaries
    - Adjacent invariants
    - Patch template
    """
    from tldr_swinton.modules.core.edit_locality import (
        format_edit_context_for_agent,
        get_edit_context,
    )

    from . import resolve_project_root

    project = resolve_project_root(task)
    entry = task.get("entry", "")
    if not entry:
        raise ValueError("task.entry is required")

    # The entry format is "path/to/file.py:SymbolName" which is already
    # the symbol_id format expected by get_edit_context
    symbol_id = entry

    # Validate we have the expected format
    if ":" not in symbol_id:
        raise ValueError(
            f"task.entry must be in format 'path/to/file.py:SymbolName', got: {entry}"
        )

    # Optional: diff_lines from expected_lines if present
    diff_lines = task.get("expected_lines")

    # Optional: call_graph could be passed if available
    call_graph = task.get("call_graph")

    try:
        ctx = get_edit_context(
            project=project,
            symbol_id=symbol_id,
            diff_lines=diff_lines,
            call_graph=call_graph,
        )
        if ctx is None:
            file_path, symbol = symbol_id.rsplit(":", 1)
            return f"# Edit-locality: Symbol not found\n# Target: {symbol} in {file_path}"
        return format_edit_context_for_agent(ctx)
    except Exception as e:
        file_path, symbol = symbol_id.rsplit(":", 1) if ":" in symbol_id else ("", symbol_id)
        # Fall back to basic context if edit-locality fails
        return f"# Edit-locality context failed: {e}\n# Target: {symbol} in {file_path}"
