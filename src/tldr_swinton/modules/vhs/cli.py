"""VHS CLI - subcommand handler for tldrs vhs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .store import Store
from . import __version__


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    """Add the 'vhs' subcommand to the main CLI parser."""
    vhs_parser = subparsers.add_parser(
        "vhs",
        help="Content-addressed store for tool outputs",
        description="Local content-addressed store for caching and referencing tool outputs.",
    )
    vhs_sub = vhs_parser.add_subparsers(dest="vhs_command", required=True)

    # put
    put_p = vhs_sub.add_parser("put", help="Store a file or stdin")
    put_p.add_argument("file", nargs="?", default="-", help="File path or '-' for stdin")
    put_p.add_argument("--compress", action="store_true", help="Compress stored payload (zlib)")
    put_p.add_argument(
        "--compress-min-bytes",
        type=int,
        default=None,
        help="Compress if payload is at least N bytes",
    )

    # get
    get_p = vhs_sub.add_parser("get", help="Fetch a ref to stdout or file")
    get_p.add_argument("ref", help="vhs://<hash> or raw hash")
    get_p.add_argument("--out", default=None, help="Output file path")

    # cat
    cat_p = vhs_sub.add_parser("cat", help="Alias for get (stdout)")
    cat_p.add_argument("ref", help="vhs://<hash> or raw hash")

    # has
    has_p = vhs_sub.add_parser("has", help="Check if ref exists (exit 0/1)")
    has_p.add_argument("ref", help="vhs://<hash> or raw hash")

    # info
    info_p = vhs_sub.add_parser("info", help="Show metadata for a ref")
    info_p.add_argument("ref", help="vhs://<hash> or raw hash")

    # rm
    rm_p = vhs_sub.add_parser("rm", help="Delete a ref")
    rm_p.add_argument("ref", help="vhs://<hash> or raw hash")

    # ls
    ls_p = vhs_sub.add_parser("ls", help="List recent refs")
    ls_p.add_argument("--limit", type=int, default=20, help="Max results (default: 20)")
    ls_p.add_argument("--jsonl", action="store_true", help="Emit one JSON object per line")

    # stats
    vhs_sub.add_parser("stats", help="Show store statistics")

    # gc
    gc_p = vhs_sub.add_parser("gc", help="Garbage-collect old blobs")
    gc_p.add_argument("--max-age-days", type=int, default=None, help="Delete blobs unused for N days")
    gc_p.add_argument("--max-size-mb", type=int, default=None, help="Cap total store size in MB")
    gc_p.add_argument("--dry-run", action="store_true", help="Report what would be deleted")
    gc_p.add_argument("--keep-last", type=int, default=0, help="Protect newest N blobs from GC")


def handle(args: argparse.Namespace) -> int:
    """Handle vhs subcommand."""
    store = Store()
    cmd = args.vhs_command

    if cmd == "put":
        if args.file == "-":
            ref = store.put(
                sys.stdin.buffer,
                compress=args.compress,
                compress_min_bytes=args.compress_min_bytes,
            )
        else:
            with open(args.file, "rb") as f:
                ref = store.put(
                    f,
                    compress=args.compress,
                    compress_min_bytes=args.compress_min_bytes,
                )
        print(ref)
        return 0

    if cmd == "get":
        out = Path(args.out) if args.out else None
        try:
            store.get(args.ref, out=out)
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    if cmd == "cat":
        try:
            store.get(args.ref, out=None)
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    if cmd == "has":
        return 0 if store.has(args.ref) else 1

    if cmd == "info":
        info = store.info(args.ref)
        if info is None:
            print("{}")
            return 1
        print(json.dumps(info.__dict__, indent=2))
        return 0

    if cmd == "rm":
        try:
            deleted = store.delete(args.ref)
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        if not deleted:
            print("Error: ref not found", file=sys.stderr)
            return 1
        print(json.dumps({"deleted": True}, indent=2))
        return 0

    if cmd == "ls":
        items = store.list(limit=args.limit)
        if args.jsonl:
            for item in items:
                print(json.dumps(item.__dict__))
        else:
            print(json.dumps([i.__dict__ for i in items], indent=2))
        return 0

    if cmd == "stats":
        print(json.dumps(store.stats(), indent=2))
        return 0

    if cmd == "gc":
        result = store.gc(
            args.max_age_days,
            args.max_size_mb,
            dry_run=args.dry_run,
            keep_last=args.keep_last,
        )
        print(json.dumps(result, indent=2))
        return 0

    print("Unknown vhs command", file=sys.stderr)
    return 1
