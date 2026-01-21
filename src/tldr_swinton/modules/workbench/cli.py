"""Workbench CLI - subcommand handler for tldrs wb."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .capsule import Capsule, capture, replay_command
from .decision import Decision, parse_refs
from .display import (
    BOLD,
    DIM,
    YELLOW,
    color,
    format_capsule_detail,
    format_capsule_row,
    format_capture_result,
    format_decision_created,
    format_decision_detail,
    format_decision_row,
    format_decision_superseded,
    format_evidence_added,
    format_graph,
    format_hypothesis_confirmed,
    format_hypothesis_created,
    format_hypothesis_detail,
    format_hypothesis_falsified,
    format_hypothesis_row,
    format_link_created,
    format_link_deleted,
    format_link_row,
    format_replay_preview,
    format_timeline_row,
)
from .export import (
    export_artifact_json,
    export_artifact_markdown,
    export_json,
    export_markdown,
    export_vhs,
)
from .hypothesis import Hypothesis
from .link import parse_artifact_id
from .store import WorkbenchStore


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Add the 'wb' subcommand to the main CLI parser."""
    wb_parser = subparsers.add_parser(
        "wb",
        help="Agent reasoning artifact persistence",
        description="Track capsules, decisions, hypotheses, and their relationships.",
    )
    wb_sub = wb_parser.add_subparsers(dest="wb_command", required=True)

    # capture command
    capture_p = wb_sub.add_parser("capture", help="Capture a command execution")
    capture_p.add_argument("command", nargs="*", help="Command to run")
    capture_p.add_argument("--cwd", "-C", metavar="DIR", help="Run command in this directory")
    capture_p.add_argument("--timeout", "-t", type=float, metavar="SECS", help="Timeout in seconds")
    capture_p.add_argument("--verbose", "-v", action="store_true", help="Show command output")

    # show command
    show_p = wb_sub.add_parser("show", help="Show capsule details")
    show_p.add_argument("id", help="Capsule ID")
    show_p.add_argument("--stdout", action="store_true", help="Print only stdout (raw)")
    show_p.add_argument("--stderr", action="store_true", help="Print only stderr (raw)")
    show_p.add_argument("--full", "-f", action="store_true", help="Show full stdout and stderr")

    # capsules command
    capsules_p = wb_sub.add_parser("capsules", help="List capsules")
    capsules_p.add_argument("--limit", "-n", type=int, default=20, help="Max capsules to show")
    capsules_p.add_argument("--failed", "-F", action="store_true", help="Only show failed commands")
    capsules_p.add_argument("--command", "-c", metavar="PATTERN", help="Filter by command substring")

    # replay command
    replay_p = wb_sub.add_parser("replay", help="Re-run a captured command")
    replay_p.add_argument("id", help="Capsule ID to replay")
    replay_p.add_argument("--dry-run", "-n", action="store_true", help="Show what would run")
    replay_p.add_argument("--force", "-f", action="store_true", help="Run even if destructive")

    # decide command
    decide_p = wb_sub.add_parser("decide", help="Record a decision")
    decide_p.add_argument("statement", nargs="*", help="Decision statement")
    decide_p.add_argument("--reason", "-r", metavar="TEXT", help="Rationale for the decision")
    decide_p.add_argument("--refs", metavar="SYMBOLS", help="Comma-separated symbol refs")

    # decisions command
    decisions_p = wb_sub.add_parser("decisions", help="List decisions")
    decisions_p.add_argument("--limit", "-n", type=int, default=20, help="Max decisions to show")
    decisions_p.add_argument("--all", "-a", action="store_true", help="Include superseded")
    decisions_p.add_argument("--refs", metavar="PATTERN", help="Filter by symbol ref pattern")

    # show-decision command
    show_dec_p = wb_sub.add_parser("show-decision", help="Show decision details")
    show_dec_p.add_argument("id", help="Decision ID")

    # supersede command
    supersede_p = wb_sub.add_parser("supersede", help="Supersede a decision")
    supersede_p.add_argument("id", help="Decision ID to supersede")
    supersede_p.add_argument("statement", nargs="*", help="New decision statement")
    supersede_p.add_argument("--reason", "-r", metavar="TEXT", help="Rationale")

    # hypothesis command
    hyp_p = wb_sub.add_parser("hypothesis", help="Create a hypothesis")
    hyp_p.add_argument("statement", nargs="*", help="Hypothesis statement")
    hyp_p.add_argument("--test", "-t", metavar="TEXT", help="How to test")
    hyp_p.add_argument("--disconfirmer", "-d", metavar="TEXT", help="What would prove it wrong")

    # hypotheses command
    hyps_p = wb_sub.add_parser("hypotheses", help="List hypotheses")
    hyps_p.add_argument("--limit", "-n", type=int, default=20, help="Max to show")
    hyps_p.add_argument("--all", "-a", action="store_true", help="Include resolved")
    hyps_p.add_argument("--status", "-s", choices=["active", "confirmed", "falsified"])

    # show-hypothesis command
    show_hyp_p = wb_sub.add_parser("show-hypothesis", help="Show hypothesis details")
    show_hyp_p.add_argument("id", help="Hypothesis ID")

    # confirm command
    confirm_p = wb_sub.add_parser("confirm", help="Confirm a hypothesis")
    confirm_p.add_argument("id", help="Hypothesis ID")
    confirm_p.add_argument("--note", "-n", metavar="TEXT", help="Resolution note")
    confirm_p.add_argument("--evidence", "-e", metavar="ID", help="Link confirming evidence")

    # falsify command
    falsify_p = wb_sub.add_parser("falsify", help="Falsify a hypothesis")
    falsify_p.add_argument("id", help="Hypothesis ID")
    falsify_p.add_argument("--note", "-n", metavar="TEXT", help="Resolution note")
    falsify_p.add_argument("--evidence", "-e", metavar="ID", help="Link falsifying evidence")

    # link command
    link_p = wb_sub.add_parser("link", help="Link evidence to a hypothesis")
    link_p.add_argument("hypothesis_id", help="Hypothesis ID")
    link_p.add_argument("artifact_id", help="Artifact ID")
    link_p.add_argument("--relation", "-r", choices=["supports", "falsifies"], default="supports")

    # connect command
    connect_p = wb_sub.add_parser("connect", help="Create a link between artifacts")
    connect_p.add_argument("source", help="Source artifact")
    connect_p.add_argument("dest", help="Destination artifact")
    connect_p.add_argument(
        "--relation", "-r",
        choices=["evidence", "falsifies", "implements", "refs", "supersedes", "related"],
        default="related"
    )

    # disconnect command
    disconnect_p = wb_sub.add_parser("disconnect", help="Remove a link")
    disconnect_p.add_argument("source", help="Source artifact")
    disconnect_p.add_argument("dest", help="Destination artifact")
    disconnect_p.add_argument("--relation", "-r", required=True, help="Relation type")

    # links command
    links_p = wb_sub.add_parser("links", help="List links")
    links_p.add_argument("--relation", "-r", help="Filter by relation type")
    links_p.add_argument("--limit", "-n", type=int, default=50, help="Max links to show")

    # graph command
    graph_p = wb_sub.add_parser("graph", help="Show graph around an artifact")
    graph_p.add_argument("artifact", help="Central artifact")
    graph_p.add_argument("--depth", "-d", type=int, default=1, help="Traversal depth")

    # timeline command
    timeline_p = wb_sub.add_parser("timeline", help="Show artifact timeline")
    timeline_p.add_argument("--type", "-t", choices=["capsule", "decision", "hypothesis"])
    timeline_p.add_argument("--limit", "-n", type=int, default=20, help="Max artifacts")

    # export command
    export_p = wb_sub.add_parser("export", help="Export artifacts")
    export_p.add_argument("artifact", nargs="?", help="Specific artifact to export")
    export_p.add_argument("--format", "-f", choices=["markdown", "json", "vhs"], default="markdown")
    export_p.add_argument("--type", "-t", choices=["capsule", "decision", "hypothesis"])
    export_p.add_argument("--no-links", action="store_true", help="Exclude links from export")


def handle(args: argparse.Namespace) -> int:
    """Handle wb subcommand."""
    cmd = args.wb_command

    if cmd == "capture":
        return _cmd_capture(args)
    elif cmd == "show":
        return _cmd_show(args)
    elif cmd == "capsules":
        return _cmd_capsules(args)
    elif cmd == "replay":
        return _cmd_replay(args)
    elif cmd == "decide":
        return _cmd_decide(args)
    elif cmd == "decisions":
        return _cmd_decisions(args)
    elif cmd == "show-decision":
        return _cmd_show_decision(args)
    elif cmd == "supersede":
        return _cmd_supersede(args)
    elif cmd == "hypothesis":
        return _cmd_hypothesis(args)
    elif cmd == "hypotheses":
        return _cmd_hypotheses(args)
    elif cmd == "show-hypothesis":
        return _cmd_show_hypothesis(args)
    elif cmd == "confirm":
        return _cmd_confirm(args)
    elif cmd == "falsify":
        return _cmd_falsify(args)
    elif cmd == "link":
        return _cmd_link(args)
    elif cmd == "connect":
        return _cmd_connect(args)
    elif cmd == "disconnect":
        return _cmd_disconnect(args)
    elif cmd == "links":
        return _cmd_links(args)
    elif cmd == "graph":
        return _cmd_graph(args)
    elif cmd == "timeline":
        return _cmd_timeline(args)
    elif cmd == "export":
        return _cmd_export(args)
    else:
        print(f"Unknown wb command: {cmd}", file=sys.stderr)
        return 1


# Command implementations

def _cmd_capture(args: argparse.Namespace) -> int:
    if not args.command:
        print("Error: command is required", file=sys.stderr)
        return 1

    command = " ".join(args.command)
    cwd = Path(args.cwd).resolve() if args.cwd else None
    capsule = capture(command, cwd=cwd, timeout=args.timeout)

    store = WorkbenchStore()
    store.store_capsule(capsule)

    print(format_capture_result(capsule.id, capsule.exit_code, capsule.duration_ms))

    if args.verbose or capsule.exit_code != 0:
        if capsule.stdout:
            print()
            print(color("─── stdout ───", DIM))
            print(capsule.stdout.rstrip())
        if capsule.stderr:
            print()
            print(color("─── stderr ───", DIM))
            print(capsule.stderr.rstrip())

    return 0 if capsule.exit_code == 0 else 1


def _cmd_show(args: argparse.Namespace) -> int:
    store = WorkbenchStore()
    capsule = store.get_capsule(args.id)

    if capsule is None:
        print(f"Error: capsule not found: {args.id}", file=sys.stderr)
        return 1

    if args.stdout:
        stdout = capsule.get("stdout", "")
        if stdout:
            print(stdout, end="")
        return 0

    if args.stderr:
        stderr = capsule.get("stderr", "")
        if stderr:
            print(stderr, end="")
        return 0

    print(format_capsule_detail(capsule, show_stdout=args.full, show_stderr=args.full))
    return 0


def _cmd_capsules(args: argparse.Namespace) -> int:
    store = WorkbenchStore()
    capsules = store.list_capsules(
        limit=args.limit,
        failed_only=args.failed,
        command_filter=args.command,
    )

    if not capsules:
        print(color("No capsules found.", DIM))
        return 0

    print(color(f"{'ID':<20}  {'Exit':>4}  {'Duration':>8}  {'When':>12}  Command", BOLD))
    print(color("─" * 80, DIM))

    for cap in capsules:
        print(format_capsule_row(cap))

    print()
    print(color(f"{len(capsules)} capsule(s)", DIM))
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    store = WorkbenchStore()
    capsule_data = store.get_capsule(args.id)

    if capsule_data is None:
        print(f"Error: capsule not found: {args.id}", file=sys.stderr)
        return 1

    capsule = Capsule.from_dict(capsule_data)

    if args.dry_run:
        print(format_replay_preview(capsule_data))
        return 0

    dangerous_patterns = ["rm ", "rm\t", "drop ", "delete ", "truncate "]
    is_dangerous = any(p in capsule.command.lower() for p in dangerous_patterns)

    if is_dangerous and not args.force:
        print(color("Warning: This command may be destructive:", YELLOW))
        print(f"  {capsule.command}")
        print()
        print("Use --force to run anyway, or --dry-run to preview.")
        return 1

    print(color(f"Replaying: {capsule.command}", BOLD))
    print(color(f"In: {capsule.cwd}", DIM))
    print()

    new_capsule = replay_command(capsule)
    if new_capsule is None:
        return 1

    store.store_capsule(new_capsule)
    print(format_capture_result(new_capsule.id, new_capsule.exit_code, new_capsule.duration_ms))

    if new_capsule.stdout:
        print()
        print(color("─── stdout ───", DIM))
        print(new_capsule.stdout.rstrip())

    if new_capsule.stderr:
        print()
        print(color("─── stderr ───", DIM))
        print(new_capsule.stderr.rstrip())

    if new_capsule.exit_code != capsule.exit_code:
        print()
        print(
            color(
                f"Note: Exit code changed: {capsule.exit_code} → {new_capsule.exit_code}",
                YELLOW,
            )
        )

    return 0 if new_capsule.exit_code == 0 else 1


def _cmd_decide(args: argparse.Namespace) -> int:
    if not args.statement:
        print("Error: statement is required", file=sys.stderr)
        return 1

    refs = parse_refs(args.refs)
    decision = Decision.create(
        statement=" ".join(args.statement),
        reason=args.reason,
        refs=refs,
    )

    store = WorkbenchStore()
    store.store_decision(decision)
    print(format_decision_created(decision.id))
    return 0


def _cmd_decisions(args: argparse.Namespace) -> int:
    store = WorkbenchStore()
    decisions = store.list_decisions(
        limit=args.limit,
        include_superseded=args.all,
        refs_filter=args.refs,
    )

    if not decisions:
        print(color("No decisions found.", DIM))
        return 0

    print(color(f"{'ID':<12}  {'When':>12}  Statement", BOLD))
    print(color("─" * 80, DIM))

    for dec in decisions:
        print(format_decision_row(dec))

    print()
    print(color(f"{len(decisions)} decision(s)", DIM))
    return 0


def _cmd_show_decision(args: argparse.Namespace) -> int:
    store = WorkbenchStore()
    decision = store.get_decision(args.id)

    if decision is None:
        print(f"Error: decision not found: {args.id}", file=sys.stderr)
        return 1

    print(format_decision_detail(decision))
    return 0


def _cmd_supersede(args: argparse.Namespace) -> int:
    if not args.statement:
        print("Error: new statement is required", file=sys.stderr)
        return 1

    store = WorkbenchStore()

    try:
        new_id = store.supersede_decision(
            old_decision_id=args.id,
            new_statement=" ".join(args.statement),
            new_reason=args.reason,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    old = store.get_decision(args.id)
    old_id = old["id"] if old else args.id

    print(format_decision_superseded(old_id, new_id))
    return 0


def _cmd_hypothesis(args: argparse.Namespace) -> int:
    if not args.statement:
        print("Error: statement is required", file=sys.stderr)
        return 1

    hyp = Hypothesis.create(
        statement=" ".join(args.statement),
        test=args.test,
        disconfirmer=args.disconfirmer,
    )

    store = WorkbenchStore()
    store.store_hypothesis(hyp)
    print(format_hypothesis_created(hyp.id))
    return 0


def _cmd_hypotheses(args: argparse.Namespace) -> int:
    store = WorkbenchStore()
    hypotheses = store.list_hypotheses(
        limit=args.limit,
        status_filter=args.status,
        include_resolved=args.all,
    )

    if not hypotheses:
        print(color("No hypotheses found.", DIM))
        return 0

    print(color(f"{'ID':<12}  {'Status':>10}  {'When':>12}  Statement", BOLD))
    print(color("─" * 80, DIM))

    for hyp in hypotheses:
        print(format_hypothesis_row(hyp))

    print()
    print(color(f"{len(hypotheses)} hypothesis/hypotheses", DIM))
    return 0


def _cmd_show_hypothesis(args: argparse.Namespace) -> int:
    store = WorkbenchStore()
    hypothesis = store.get_hypothesis(args.id)

    if hypothesis is None:
        print(f"Error: hypothesis not found: {args.id}", file=sys.stderr)
        return 1

    print(format_hypothesis_detail(hypothesis))
    return 0


def _cmd_confirm(args: argparse.Namespace) -> int:
    store = WorkbenchStore()

    try:
        store.confirm_hypothesis(
            hypothesis_id=args.id,
            note=args.note,
            evidence_id=args.evidence,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    hyp = store.get_hypothesis(args.id)
    hyp_id = hyp["id"] if hyp else args.id

    print(format_hypothesis_confirmed(hyp_id))
    return 0


def _cmd_falsify(args: argparse.Namespace) -> int:
    store = WorkbenchStore()

    try:
        store.falsify_hypothesis(
            hypothesis_id=args.id,
            note=args.note,
            evidence_id=args.evidence,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    hyp = store.get_hypothesis(args.id)
    hyp_id = hyp["id"] if hyp else args.id

    print(format_hypothesis_falsified(hyp_id))
    return 0


def _cmd_link(args: argparse.Namespace) -> int:
    store = WorkbenchStore()

    try:
        store.add_evidence(
            hypothesis_id=args.hypothesis_id,
            artifact_id=args.artifact_id,
            relation=args.relation,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    hyp = store.get_hypothesis(args.hypothesis_id)
    hyp_id = hyp["id"] if hyp else args.hypothesis_id

    print(format_evidence_added(hyp_id, args.artifact_id, args.relation))
    return 0


def _cmd_connect(args: argparse.Namespace) -> int:
    store = WorkbenchStore()

    src_id, src_type = parse_artifact_id(args.source)
    dst_id, dst_type = parse_artifact_id(args.dest)

    try:
        store.create_link(
            src_id=src_id,
            src_type=src_type.value,
            dst_id=dst_id,
            dst_type=dst_type.value,
            relation=args.relation,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(format_link_created(args.source, args.dest, args.relation))
    return 0


def _cmd_disconnect(args: argparse.Namespace) -> int:
    store = WorkbenchStore()

    src_id, _ = parse_artifact_id(args.source)
    dst_id, _ = parse_artifact_id(args.dest)

    deleted = store.delete_link(src_id, dst_id, args.relation)

    if not deleted:
        print("Error: link not found", file=sys.stderr)
        return 1

    print(format_link_deleted(args.source, args.dest, args.relation))
    return 0


def _cmd_links(args: argparse.Namespace) -> int:
    store = WorkbenchStore()

    links = store.get_all_links(
        relation=args.relation,
        limit=args.limit,
    )

    if not links:
        print(color("No links found.", DIM))
        return 0

    print(color("Source                    Relation        Target", BOLD))
    print(color("─" * 70, DIM))

    for link in links:
        print(format_link_row(link))

    print()
    print(color(f"{len(links)} link(s)", DIM))
    return 0


def _cmd_graph(args: argparse.Namespace) -> int:
    store = WorkbenchStore()

    artifact_id, artifact_type = parse_artifact_id(args.artifact)

    graph = store.get_artifact_graph(
        artifact_id=artifact_id,
        artifact_type=artifact_type.value,
        depth=args.depth,
    )

    if not graph["nodes"]:
        print(f"Error: artifact not found: {args.artifact}", file=sys.stderr)
        return 1

    print(format_graph(graph))
    return 0


def _cmd_timeline(args: argparse.Namespace) -> int:
    store = WorkbenchStore()

    types = None
    if args.type:
        types = [args.type]

    timeline = store.export_timeline(
        artifact_types=types,
        limit=args.limit,
    )

    if not timeline:
        print(color("No artifacts found.", DIM))
        return 0

    print(color("Type  ID            When          Summary", BOLD))
    print(color("─" * 80, DIM))

    for item in timeline:
        print(format_timeline_row(item))

    print()
    print(color(f"{len(timeline)} artifact(s)", DIM))
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    store = WorkbenchStore()

    fmt = args.format or "markdown"

    if args.artifact:
        artifact_id, artifact_type = parse_artifact_id(args.artifact)

        if fmt == "json":
            output = export_artifact_json(store, artifact_id, artifact_type.value)
        elif fmt == "markdown":
            output = export_artifact_markdown(store, artifact_id, artifact_type.value)
        elif fmt == "vhs":
            output = f"vhs://{artifact_id[:16]}"
        else:
            print(f"Error: unknown format: {fmt}", file=sys.stderr)
            return 1

        if output is None:
            print(f"Error: artifact not found: {args.artifact}", file=sys.stderr)
            return 1
    else:
        artifact_type = args.type

        if fmt == "json":
            output = export_json(store, artifact_type, include_links=not args.no_links)
        elif fmt == "markdown":
            output = export_markdown(store, artifact_type, include_links=not args.no_links)
        elif fmt == "vhs":
            output = export_vhs(store, artifact_type)
        else:
            print(f"Error: unknown format: {fmt}", file=sys.stderr)
            return 1

    print(output)
    return 0
