"""
Machine-readable manifest of tldrs capabilities.

Used by interbench sync tooling to detect when eval coverage drifts
behind the CLI's actual formats, flags, and commands.

Usage:
    tldrs manifest           # compact JSON
    tldrs manifest --pretty  # indented JSON
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from . import __version__

# Commands that matter for interbench evaluation.
# Internal/utility commands (tree, warm, daemon, etc.) are excluded.
_EVAL_COMMANDS = frozenset({
    "context",
    "diff-context",
    "distill",
    "hotspots",
    "slice",
    "structural",
})

# Scoring hints tell check_tldrs_sync.py which formats need
# dedicated parse_* functions in score_tokens.py.
_SCORING_HINTS: dict[str, dict[str, Any]] = {
    "packed-json": {
        "signals": ["_aliases", "_paths"],
        "metrics": ["alias_count"],
    },
    "cache-friendly": {
        "signals": ["cache_hints"],
        "metrics": ["prefix_tokens", "cache_hit_rate"],
    },
    "columnar-json": {
        "signals": ["_schema"],
        "metrics": [],
    },
    "ultracompact": {
        "signals": [],
        "metrics": [],
    },
}

_ZOOM_DESCRIPTIONS = {
    "L0": "Module map",
    "L1": "Signatures",
    "L2": "Body sketch",
    "L3": "Windowed",
    "L4": "Full",
}


def _extract_choices(action: argparse.Action) -> list[str] | None:
    """Return the choices list for an argparse action, or None."""
    if action.choices:
        return sorted(str(c) for c in action.choices)
    return None


def _classify_flags(subparser: argparse.ArgumentParser) -> dict[str, Any]:
    """Classify a subparser's optional arguments into boolean vs valued."""
    boolean: list[str] = []
    valued: dict[str, Any] = {}

    for action in subparser._actions:
        # Skip positional args and help
        if not action.option_strings or isinstance(action, argparse._HelpAction):
            continue

        # Use the longest option string (--foo over -f)
        flag = max(action.option_strings, key=len)

        # Skip internal/non-eval flags
        if flag in ("--machine", "--output", "--include", "--lang"):
            continue

        if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
            boolean.append(flag)
        else:
            choices = _extract_choices(action)
            if choices:
                valued[flag] = choices
            elif action.type is int:
                valued[flag] = "int"
            else:
                valued[flag] = "string"

    return {"boolean": sorted(boolean), "valued": valued}


def build_manifest(parser: argparse.ArgumentParser) -> dict[str, Any]:
    """Build a manifest dict by introspecting the argparse parser tree.

    Args:
        parser: The top-level ArgumentParser with subparsers registered.

    Returns:
        Manifest dict ready for JSON serialization.
    """
    commands: dict[str, Any] = {}

    # Navigate to the subparsers choices dict
    for action in parser._subparsers._group_actions:
        if isinstance(action, argparse._SubParsersAction):
            for cmd_name, subparser in action.choices.items():
                if cmd_name not in _EVAL_COMMANDS:
                    continue

                cmd_info: dict[str, Any] = {}

                # Extract --format choices
                for sub_action in subparser._actions:
                    if any(s == "--format" for s in sub_action.option_strings):
                        choices = _extract_choices(sub_action)
                        if choices:
                            cmd_info["formats"] = choices
                        break

                # Extract flags
                cmd_info["flags"] = _classify_flags(subparser)

                commands[cmd_name] = cmd_info

    manifest = {
        "version": __version__,
        "manifest_schema": 1,
        "commands": commands,
        "scoring_hints": _SCORING_HINTS,
        "zoom_levels": _ZOOM_DESCRIPTIONS,
    }

    return manifest
