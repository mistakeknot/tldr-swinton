"""Export: Format artifacts for external consumption.

Supports VHS (content-addressed reference), Markdown (human-readable),
and JSON (machine-readable) formats.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import WorkbenchStore


def export_vhs(store: "WorkbenchStore", artifact_type: str | None = None) -> str:
    """Export artifacts as a VHS reference.

    VHS refs are content-addressed hashes that tldr-swinton can include.

    Args:
        store: WorkbenchStore instance.
        artifact_type: Filter by type (capsule, decision, hypothesis), or all.

    Returns:
        VHS reference string (vhs://<hash>).
    """
    # Get timeline
    types = [artifact_type] if artifact_type else None
    timeline = store.export_timeline(artifact_types=types)

    # Create content hash
    content = json.dumps(timeline, sort_keys=True, default=str)
    hash_hex = hashlib.sha256(content.encode()).hexdigest()[:16]

    return f"vhs://{hash_hex}"


def export_markdown(
    store: "WorkbenchStore",
    artifact_type: str | None = None,
    include_links: bool = True,
) -> str:
    """Export artifacts as Markdown.

    Args:
        store: WorkbenchStore instance.
        artifact_type: Filter by type (capsule, decision, hypothesis), or all.
        include_links: Include link information.

    Returns:
        Markdown formatted string.
    """
    types = [artifact_type] if artifact_type else None
    timeline = store.export_timeline(artifact_types=types)

    lines: list[str] = []
    lines.append("# Workbench Artifacts")
    lines.append("")
    lines.append(f"*Exported: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append("")

    # Group by type
    capsules = [t for t in timeline if t["type"] == "capsule"]
    decisions = [t for t in timeline if t["type"] == "decision"]
    hypotheses = [t for t in timeline if t["type"] == "hypothesis"]

    if decisions:
        lines.append("## Decisions")
        lines.append("")
        for item in decisions:
            dec = item["data"]
            status = " *(superseded)*" if dec.get("superseded_by") else ""
            lines.append(f"### `{dec['id']}`{status}")
            lines.append("")
            lines.append(f"**{dec['statement']}**")
            if dec.get("reason"):
                lines.append("")
                lines.append(f"*Reason:* {dec['reason']}")
            if dec.get("refs"):
                lines.append("")
                lines.append(f"*Affects:* `{', '.join(dec['refs'])}`")
            lines.append("")

    if hypotheses:
        lines.append("## Hypotheses")
        lines.append("")
        for item in hypotheses:
            hyp = item["data"]
            status_emoji = {
                "active": "\u2753",  # ❓
                "confirmed": "\u2705",  # ✅
                "falsified": "\u274c",  # ❌
            }.get(hyp["status"], "")
            lines.append(f"### `{hyp['id']}` {status_emoji}")
            lines.append("")
            lines.append(f"**{hyp['statement']}**")
            lines.append("")
            lines.append(f"*Status:* {hyp['status']}")
            if hyp.get("test"):
                lines.append(f"*Test:* {hyp['test']}")
            if hyp.get("disconfirmer"):
                lines.append(f"*Disconfirmer:* {hyp['disconfirmer']}")
            if hyp.get("resolution_note"):
                lines.append(f"*Note:* {hyp['resolution_note']}")
            if hyp.get("evidence"):
                lines.append("")
                lines.append("*Evidence:*")
                for ev in hyp["evidence"]:
                    lines.append(
                        f"  - `{ev['artifact_type']}:{ev['artifact_id']}` ({ev['relation']})"
                    )
            lines.append("")

    if capsules:
        lines.append("## Capsules")
        lines.append("")
        for item in capsules:
            cap = item["data"]
            exit_emoji = "\u2705" if cap["exit_code"] == 0 else "\u274c"
            lines.append(f"### `capsule:{cap['id'][:12]}` {exit_emoji}")
            lines.append("")
            lines.append("```bash")
            lines.append(f"{cap['command']}")
            lines.append("```")
            lines.append("")
            lines.append(f"*Exit:* {cap['exit_code']} | *Duration:* {cap['duration_ms']}ms")
            lines.append("")

    # Links section
    if include_links:
        all_links = store.get_all_links(limit=50)
        if all_links:
            lines.append("## Links")
            lines.append("")
            lines.append("| Source | Relation | Target |")
            lines.append("|--------|----------|--------|")
            for link in all_links:
                src = f"`{link['src_type']}:{link['src_id'][:8]}`"
                dst = f"`{link['dst_type']}:{link['dst_id'][:8]}`"
                lines.append(f"| {src} | {link['relation']} | {dst} |")
            lines.append("")

    return "\n".join(lines)


def export_json(
    store: "WorkbenchStore",
    artifact_type: str | None = None,
    include_links: bool = True,
    pretty: bool = True,
) -> str:
    """Export artifacts as JSON.

    Args:
        store: WorkbenchStore instance.
        artifact_type: Filter by type (capsule, decision, hypothesis), or all.
        include_links: Include link information.
        pretty: Pretty-print JSON.

    Returns:
        JSON formatted string.
    """
    types = [artifact_type] if artifact_type else None
    timeline = store.export_timeline(artifact_types=types)

    result = {
        "exported_at": datetime.now().isoformat(),
        "artifacts": timeline,
    }

    if include_links:
        result["links"] = store.get_all_links(limit=100)

    if pretty:
        return json.dumps(result, indent=2, default=str)
    return json.dumps(result, default=str)


def export_artifact_markdown(
    store: "WorkbenchStore",
    artifact_id: str,
    artifact_type: str,
) -> str | None:
    """Export a single artifact as Markdown.

    Args:
        store: WorkbenchStore instance.
        artifact_id: Artifact ID.
        artifact_type: Artifact type.

    Returns:
        Markdown formatted string, or None if not found.
    """
    exported = store.export_artifact(artifact_id, artifact_type)
    if exported is None:
        return None

    lines: list[str] = []
    data = exported["data"]

    if artifact_type == "capsule":
        lines.append(f"# Capsule: `{data['id']}`")
        lines.append("")
        lines.append("```bash")
        lines.append(data["command"])
        lines.append("```")
        lines.append("")
        lines.append(f"- **CWD:** `{data['cwd']}`")
        lines.append(f"- **Exit:** {data['exit_code']}")
        lines.append(f"- **Duration:** {data['duration_ms']}ms")
        lines.append(f"- **Started:** {data['started_at']}")
        if data.get("stdout"):
            lines.append("")
            lines.append("## stdout")
            lines.append("```")
            lines.append(data["stdout"][:2000])
            if len(data["stdout"]) > 2000:
                lines.append(f"... ({len(data['stdout'])} bytes total)")
            lines.append("```")
        if data.get("stderr"):
            lines.append("")
            lines.append("## stderr")
            lines.append("```")
            lines.append(data["stderr"][:1000])
            if len(data["stderr"]) > 1000:
                lines.append(f"... ({len(data['stderr'])} bytes total)")
            lines.append("```")

    elif artifact_type == "decision":
        status = " *(superseded)*" if data.get("superseded_by") else ""
        lines.append(f"# Decision: `{data['id']}`{status}")
        lines.append("")
        lines.append(f"**{data['statement']}**")
        if data.get("reason"):
            lines.append("")
            lines.append(f"*Reason:* {data['reason']}")
        if data.get("refs"):
            lines.append("")
            lines.append(f"*Affects:* `{', '.join(data['refs'])}`")
        lines.append("")
        lines.append(f"*Created:* {data['created_at']}")

    elif artifact_type == "hypothesis":
        lines.append(f"# Hypothesis: `{data['id']}`")
        lines.append("")
        lines.append(f"**{data['statement']}**")
        lines.append("")
        lines.append(f"*Status:* {data['status']}")
        if data.get("test"):
            lines.append(f"*Test:* {data['test']}")
        if data.get("disconfirmer"):
            lines.append(f"*Disconfirmer:* {data['disconfirmer']}")
        lines.append(f"*Created:* {data['created_at']}")
        if data.get("resolved_at"):
            lines.append(f"*Resolved:* {data['resolved_at']}")
        if data.get("resolution_note"):
            lines.append(f"*Note:* {data['resolution_note']}")
        if data.get("evidence"):
            lines.append("")
            lines.append("## Evidence")
            for ev in data["evidence"]:
                lines.append(
                    f"- `{ev['artifact_type']}:{ev['artifact_id']}` ({ev['relation']})"
                )

    # Add links
    if exported["outgoing_links"] or exported["incoming_links"]:
        lines.append("")
        lines.append("## Links")
        if exported["outgoing_links"]:
            lines.append("")
            lines.append("### Outgoing")
            for link in exported["outgoing_links"]:
                lines.append(
                    f"- --{link['relation']}--> `{link['dst_type']}:{link['dst_id']}`"
                )
        if exported["incoming_links"]:
            lines.append("")
            lines.append("### Incoming")
            for link in exported["incoming_links"]:
                lines.append(
                    f"- <--{link['relation']}-- `{link['src_type']}:{link['src_id']}`"
                )

    return "\n".join(lines)


def export_artifact_json(
    store: "WorkbenchStore",
    artifact_id: str,
    artifact_type: str,
    pretty: bool = True,
) -> str | None:
    """Export a single artifact as JSON.

    Args:
        store: WorkbenchStore instance.
        artifact_id: Artifact ID.
        artifact_type: Artifact type.
        pretty: Pretty-print JSON.

    Returns:
        JSON formatted string, or None if not found.
    """
    exported = store.export_artifact(artifact_id, artifact_type)
    if exported is None:
        return None

    if pretty:
        return json.dumps(exported, indent=2, default=str)
    return json.dumps(exported, default=str)
