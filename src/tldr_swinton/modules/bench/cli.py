"""Bench CLI - subcommand handler for tldrs bench."""

from __future__ import annotations

import argparse
import sys


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Add the 'bench' subcommand to the main CLI parser."""
    bench_parser = subparsers.add_parser(
        "bench",
        help="Benchmarking harness for agent improvements",
        description="Evaluate and validate agent performance improvements.",
    )
    bench_sub = bench_parser.add_subparsers(dest="bench_command", required=True)

    # run command
    run_p = bench_sub.add_parser("run", help="Run benchmark suite")
    run_p.add_argument("suite", nargs="?", help="Benchmark suite to run")
    run_p.add_argument("--dataset", "-d", help="Dataset path or name")
    run_p.add_argument("--output", "-o", help="Output file for results")

    # list command
    bench_sub.add_parser("list", help="List available benchmark suites")

    # report command
    report_p = bench_sub.add_parser("report", help="Generate benchmark report")
    report_p.add_argument("results", nargs="?", help="Results file to report on")
    report_p.add_argument("--format", "-f", choices=["text", "json", "markdown"], default="text")

    # compare command
    compare_p = bench_sub.add_parser("compare", help="Compare benchmark results")
    compare_p.add_argument("baseline", help="Baseline results file")
    compare_p.add_argument("current", help="Current results file")


def handle(args: argparse.Namespace) -> int:
    """Handle bench subcommand."""
    cmd = args.bench_command

    if cmd == "run":
        print("Benchmark running not yet implemented.", file=sys.stderr)
        print("This module will integrate with tldrs-bench datasets.")
        return 1

    elif cmd == "list":
        print("Available benchmark suites:")
        print("  (none configured)")
        print()
        print("Configure datasets in ~/.tldrs/bench/ or via --dataset")
        return 0

    elif cmd == "report":
        print("Benchmark reporting not yet implemented.", file=sys.stderr)
        return 1

    elif cmd == "compare":
        print("Benchmark comparison not yet implemented.", file=sys.stderr)
        return 1

    else:
        print(f"Unknown bench command: {cmd}", file=sys.stderr)
        return 1
