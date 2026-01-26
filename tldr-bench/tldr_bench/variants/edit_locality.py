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

    # Parse entry to get file and symbol
    if ":" in entry:
        file_path, symbol = entry.rsplit(":", 1)
    else:
        # Try to find file containing entry
        file_path = ""
        symbol = entry

    file_path = file_path or task.get("expected_files", [""])[0]
    if not file_path:
        raise ValueError("Could not determine file path for edit-locality context")

    language = task.get("language", "python")

    try:
        ctx = get_edit_context(
            project_root=project,
            file_path=file_path,
            target_symbol=symbol,
            language=language,
        )
        return format_edit_context_for_agent(ctx)
    except Exception as e:
        # Fall back to basic context if edit-locality fails
        return f"# Edit-locality context failed: {e}\n# Target: {symbol} in {file_path}"
