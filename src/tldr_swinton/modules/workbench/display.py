"""Output formatting for tldrs-workbench CLI."""

from __future__ import annotations

from datetime import datetime

# ANSI color codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"


def supports_color() -> bool:
    """Check if terminal supports color."""
    import os
    import sys

    if not sys.stdout.isatty():
        return False
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return True


def color(text: str, code: str) -> str:
    """Apply color if supported."""
    if supports_color():
        return f"{code}{text}{RESET}"
    return text


def format_duration(ms: int) -> str:
    """Format duration in human-readable form."""
    if ms < 1000:
        return f"{ms}ms"
    elif ms < 60000:
        return f"{ms / 1000:.1f}s"
    else:
        minutes = ms // 60000
        seconds = (ms % 60000) // 1000
        return f"{minutes}m{seconds}s"


def format_timestamp(ts: datetime | str) -> str:
    """Format timestamp for display."""
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)

    # Show relative time if recent
    from datetime import timezone

    now = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    delta = now - ts
    seconds = delta.total_seconds()

    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes}m ago"
    elif seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours}h ago"
    else:
        return ts.strftime("%Y-%m-%d %H:%M")


def format_exit_code(code: int) -> str:
    """Format exit code with color."""
    if code == 0:
        return color("0", GREEN)
    else:
        return color(str(code), RED)


def truncate(text: str, max_len: int = 60) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def format_capsule_row(capsule: dict) -> str:
    """Format a capsule for list display (single row)."""
    cap_id = color(f"capsule:{capsule['id']}", CYAN)
    exit_code = format_exit_code(capsule["exit_code"])
    duration = color(format_duration(capsule["duration_ms"]), DIM)
    timestamp = color(format_timestamp(capsule["started_at"]), DIM)
    command = truncate(capsule["command"], 50)

    return f"{cap_id}  {exit_code}  {duration:>8}  {timestamp:>12}  {command}"


def format_capsule_detail(
    capsule: dict, show_stdout: bool = False, show_stderr: bool = False
) -> str:
    """Format a capsule for detailed display."""
    lines = []

    # Header
    lines.append(color(f"Capsule: {capsule['id']}", BOLD + CYAN))
    lines.append("")

    # Metadata
    lines.append(f"  {color('Command:', BOLD)} {capsule['command']}")
    lines.append(f"  {color('CWD:', BOLD)} {capsule['cwd']}")
    lines.append(f"  {color('Exit:', BOLD)} {format_exit_code(capsule['exit_code'])}")
    lines.append(f"  {color('Duration:', BOLD)} {format_duration(capsule['duration_ms'])}")
    lines.append(f"  {color('Started:', BOLD)} {format_timestamp(capsule['started_at'])}")
    lines.append(f"  {color('Env:', BOLD)} {capsule['env_fingerprint']}")

    # Output sizes
    stdout = capsule.get("stdout", "")
    stderr = capsule.get("stderr", "")
    stdout_size = len(stdout.encode("utf-8")) if stdout else 0
    stderr_size = len(stderr.encode("utf-8")) if stderr else 0

    lines.append("")
    lines.append(f"  {color('stdout:', BOLD)} {stdout_size} bytes")
    lines.append(f"  {color('stderr:', BOLD)} {stderr_size} bytes")

    # Show output if requested
    if show_stdout and stdout:
        lines.append("")
        lines.append(color("─── stdout ───", DIM))
        lines.append(stdout.rstrip())
        lines.append(color("──────────────", DIM))

    if show_stderr and stderr:
        lines.append("")
        lines.append(color("─── stderr ───", DIM))
        lines.append(stderr.rstrip())
        lines.append(color("──────────────", DIM))

    # If neither flag specified, show a preview
    if not show_stdout and not show_stderr:
        if stdout:
            lines.append("")
            lines.append(color("─── stdout (preview) ───", DIM))
            preview_lines = stdout.split("\n")[:5]
            for line in preview_lines:
                lines.append(truncate(line, 80))
            if len(stdout.split("\n")) > 5:
                lines.append(color(f"  ... ({len(stdout.split(chr(10)))} lines total)", DIM))

        if stderr:
            lines.append("")
            lines.append(color("─── stderr (preview) ───", DIM))
            preview_lines = stderr.split("\n")[:3]
            for line in preview_lines:
                lines.append(truncate(line, 80))
            if len(stderr.split("\n")) > 3:
                lines.append(color(f"  ... ({len(stderr.split(chr(10)))} lines total)", DIM))

    return "\n".join(lines)


def format_replay_preview(capsule: dict) -> str:
    """Format a replay dry-run preview."""
    lines = []
    lines.append(color("Would replay:", BOLD))
    lines.append(f"  {color('Command:', BOLD)} {capsule['command']}")
    lines.append(f"  {color('CWD:', BOLD)} {capsule['cwd']}")
    lines.append("")
    lines.append(color("Original result:", DIM))
    lines.append(f"  Exit: {format_exit_code(capsule['exit_code'])}")
    lines.append(f"  Duration: {format_duration(capsule['duration_ms'])}")
    return "\n".join(lines)


def format_capture_result(capsule_id: str, exit_code: int, duration_ms: int) -> str:
    """Format the result of a capture command."""
    status = color("captured", GREEN) if exit_code == 0 else color("captured (failed)", YELLOW)
    return (
        f"{status} as {color(f'capsule:{capsule_id}', CYAN)} "
        f"[exit {format_exit_code(exit_code)}, {format_duration(duration_ms)}]"
    )


# Decision formatting (Phase 2)

MAGENTA = "\033[35m"


def format_decision_row(decision: dict) -> str:
    """Format a decision for list display (single row)."""
    dec_id = color(decision["id"], MAGENTA)
    timestamp = color(format_timestamp(decision["created_at"]), DIM)
    statement = truncate(decision["statement"], 55)

    # Show superseded status
    if decision.get("superseded_by"):
        status = color(" [superseded]", DIM)
    else:
        status = ""

    return f"{dec_id}  {timestamp:>12}  {statement}{status}"


def format_decision_detail(decision: dict) -> str:
    """Format a decision for detailed display."""
    lines = []

    # Header with status
    status = ""
    if decision.get("superseded_by"):
        status = color(" [superseded]", YELLOW)
    lines.append(color(f"Decision: {decision['id']}", BOLD + MAGENTA) + status)
    lines.append("")

    # Statement
    lines.append(f"  {color('Statement:', BOLD)} {decision['statement']}")

    # Reason
    if decision.get("reason"):
        lines.append(f"  {color('Reason:', BOLD)} {decision['reason']}")

    # Refs
    refs = decision.get("refs", [])
    if refs:
        lines.append(f"  {color('Refs:', BOLD)} {', '.join(refs)}")

    # Timestamps
    lines.append(f"  {color('Created:', BOLD)} {format_timestamp(decision['created_at'])}")

    # Superseded info
    if decision.get("superseded_by"):
        lines.append("")
        lines.append(
            color(f"  Superseded by: {decision['superseded_by']}", YELLOW)
        )

    return "\n".join(lines)


def format_decision_created(decision_id: str) -> str:
    """Format the result of creating a decision."""
    return f"{color('recorded', GREEN)} as {color(decision_id, MAGENTA)}"


def format_decision_superseded(old_id: str, new_id: str) -> str:
    """Format the result of superseding a decision."""
    return (
        f"{color('superseded', YELLOW)} {color(old_id, MAGENTA)} "
        f"with {color(new_id, MAGENTA)}"
    )


# Hypothesis formatting (Phase 3)

ORANGE = "\033[38;5;208m"  # 256-color orange for hypotheses


def format_hypothesis_status(status: str) -> str:
    """Format hypothesis status with color."""
    if status == "active":
        return color("active", BLUE)
    elif status == "confirmed":
        return color("confirmed", GREEN)
    elif status == "falsified":
        return color("falsified", RED)
    return status


def format_hypothesis_row(hypothesis: dict) -> str:
    """Format a hypothesis for list display (single row)."""
    hyp_id = color(hypothesis["id"], ORANGE)
    status = format_hypothesis_status(hypothesis["status"])
    timestamp = color(format_timestamp(hypothesis["created_at"]), DIM)
    statement = truncate(hypothesis["statement"], 50)

    return f"{hyp_id}  {status:>12}  {timestamp:>12}  {statement}"


def format_hypothesis_detail(hypothesis: dict) -> str:
    """Format a hypothesis for detailed display."""
    lines = []

    # Header with status
    status_str = format_hypothesis_status(hypothesis["status"])
    lines.append(f"{color('Hypothesis:', BOLD)} {color(hypothesis['id'], ORANGE)}")
    lines.append(f"  {color('Status:', BOLD)} {status_str}")
    lines.append("")

    # Statement
    lines.append(f"  {color('Statement:', BOLD)} {hypothesis['statement']}")

    # Test method
    if hypothesis.get("test"):
        lines.append(f"  {color('Test:', BOLD)} {hypothesis['test']}")

    # Disconfirmer
    if hypothesis.get("disconfirmer"):
        lines.append(f"  {color('Disconfirmer:', BOLD)} {hypothesis['disconfirmer']}")

    # Timestamps
    lines.append(f"  {color('Created:', BOLD)} {format_timestamp(hypothesis['created_at'])}")

    if hypothesis.get("resolved_at"):
        lines.append(
            f"  {color('Resolved:', BOLD)} {format_timestamp(hypothesis['resolved_at'])}"
        )

    # Resolution note
    if hypothesis.get("resolution_note"):
        lines.append("")
        lines.append(f"  {color('Note:', BOLD)} {hypothesis['resolution_note']}")

    # Evidence
    evidence = hypothesis.get("evidence", [])
    if evidence:
        lines.append("")
        lines.append(f"  {color('Evidence:', BOLD)}")
        for e in evidence:
            rel = color(e["relation"], GREEN if e["relation"] == "supports" else RED)
            lines.append(f"    - {e['artifact_type']}:{e['artifact_id']} ({rel})")

    return "\n".join(lines)


def format_hypothesis_created(hypothesis_id: str) -> str:
    """Format the result of creating a hypothesis."""
    return f"{color('created', GREEN)} as {color(hypothesis_id, ORANGE)}"


def format_hypothesis_confirmed(hypothesis_id: str) -> str:
    """Format the result of confirming a hypothesis."""
    return f"{color('confirmed', GREEN)} {color(hypothesis_id, ORANGE)}"


def format_hypothesis_falsified(hypothesis_id: str) -> str:
    """Format the result of falsifying a hypothesis."""
    return f"{color('falsified', RED)} {color(hypothesis_id, ORANGE)}"


def format_evidence_added(hypothesis_id: str, artifact_id: str, relation: str) -> str:
    """Format the result of adding evidence."""
    rel_color = GREEN if relation == "supports" else RED
    return (
        f"{color('linked', BLUE)} {artifact_id} to {color(hypothesis_id, ORANGE)} "
        f"({color(relation, rel_color)})"
    )


# Link formatting (Phase 4)

WHITE = "\033[37m"


def format_link_row(link: dict) -> str:
    """Format a link for list display (single row)."""
    src = f"{link['src_type']}:{link['src_id'][:8]}"
    dst = f"{link['dst_type']}:{link['dst_id'][:8]}"
    relation = link["relation"]
    timestamp = color(format_timestamp(link["created_at"]), DIM)

    # Color-code relation
    rel_colors = {
        "evidence": GREEN,
        "falsifies": RED,
        "implements": BLUE,
        "refs": CYAN,
        "supersedes": YELLOW,
        "related": WHITE,
    }
    rel_color = rel_colors.get(relation, WHITE)

    return (
        f"{color(src, CYAN)} --{color(relation, rel_color)}--> "
        f"{color(dst, MAGENTA)}  {timestamp}"
    )


def format_link_created(src: str, dst: str, relation: str) -> str:
    """Format the result of creating a link."""
    return f"{color('linked', GREEN)} {src} --{relation}--> {dst}"


def format_link_deleted(src: str, dst: str, relation: str) -> str:
    """Format the result of deleting a link."""
    return f"{color('unlinked', YELLOW)} {src} --{relation}--> {dst}"


# Timeline formatting (Phase 4)


def format_timeline_row(item: dict) -> str:
    """Format a timeline item for list display."""
    artifact_type = item["type"]
    artifact_id = item["id"]
    summary = truncate(item["summary"], 50)
    timestamp = color(format_timestamp(item["created_at"]), DIM)

    # Color by type
    type_colors = {
        "capsule": CYAN,
        "decision": MAGENTA,
        "hypothesis": ORANGE,
    }
    type_color = type_colors.get(artifact_type, WHITE)

    # Type indicator
    type_indicator = {
        "capsule": "CAP",
        "decision": "DEC",
        "hypothesis": "HYP",
    }.get(artifact_type, "???")

    # For hypotheses/decisions, show status
    status = ""
    if artifact_type == "hypothesis":
        hyp_status = item["data"].get("status", "active")
        if hyp_status == "confirmed":
            status = color(" [confirmed]", GREEN)
        elif hyp_status == "falsified":
            status = color(" [falsified]", RED)
    elif artifact_type == "decision":
        if item["data"].get("superseded_by"):
            status = color(" [superseded]", DIM)
    elif artifact_type == "capsule":
        exit_code = item["data"].get("exit_code", 0)
        if exit_code != 0:
            status = color(f" [exit {exit_code}]", RED)

    id_display = artifact_id[:12] if len(artifact_id) > 12 else artifact_id

    return (
        f"{color(type_indicator, type_color)}  {color(id_display, type_color)}  "
        f"{timestamp}  {summary}{status}"
    )


def format_graph_node(node: dict) -> str:
    """Format a graph node for display."""
    node_type = node["type"]
    node_id = node["id"]

    type_colors = {
        "capsule": CYAN,
        "decision": MAGENTA,
        "hypothesis": ORANGE,
        "symbol": WHITE,
        "patch": GREEN,
        "task": BLUE,
    }
    type_color = type_colors.get(node_type, WHITE)

    return f"{color(f'{node_type}:{node_id}', type_color)}"


def format_graph(graph: dict) -> str:
    """Format a graph for text display."""
    lines = []

    lines.append(color("Nodes:", BOLD))
    for node in graph["nodes"]:
        lines.append(f"  {format_graph_node(node)}")

    lines.append("")
    lines.append(color("Edges:", BOLD))
    for edge in graph["edges"]:
        src = f"{edge['src_type']}:{edge['src_id'][:8]}"
        dst = f"{edge['dst_type']}:{edge['dst_id'][:8]}"
        lines.append(f"  {src} --{edge['relation']}--> {dst}")

    return "\n".join(lines)
