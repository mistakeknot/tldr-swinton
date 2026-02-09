"""Edit-Locality-Aware Context for code editing.

This module provides context specifically optimized for helping agents
generate correct patches, not just understand code. When an agent requests
context for editing, this module returns:

1. Target function code with clear edit boundaries
2. Patch template showing expected modification zones
3. Adjacent invariants (assertions, type hints, constants) that must be preserved

The goal is to reduce edit scope and improve patch correctness by 15-25%.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EditBoundary:
    """Defines the expected edit zone within a symbol."""

    start_line: int
    end_line: int
    context_before: int = 2  # Lines of context before edit zone
    context_after: int = 2  # Lines of context after edit zone
    boundary_type: str = "body"  # body, signature, docstring


@dataclass
class Invariant:
    """A code element that should NOT be modified during the edit."""

    kind: str  # assertion, type_hint, constant, import, decorator
    line: int
    content: str
    reason: str  # Why this shouldn't be modified


@dataclass
class PatchTemplate:
    """Template showing expected edit structure."""

    symbol_id: str
    signature: str
    current_body: str
    edit_zone_start: int
    edit_zone_end: int
    preserve_before: list[str]  # Lines to preserve before edit
    preserve_after: list[str]  # Lines to preserve after edit
    placeholder: str = "# YOUR EDIT HERE"


@dataclass
class EditContext:
    """Complete context for generating a correct edit."""

    symbol_id: str
    file_path: str
    target_code: str
    boundaries: list[EditBoundary]
    invariants: list[Invariant]
    patch_template: PatchTemplate | None
    adjacent_symbols: list[str]  # Symbols that reference or are referenced by target
    type_constraints: list[str]  # Type hints that constrain the edit

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol_id": self.symbol_id,
            "file_path": self.file_path,
            "target_code": self.target_code,
            "boundaries": [
                {
                    "start": b.start_line,
                    "end": b.end_line,
                    "type": b.boundary_type,
                }
                for b in self.boundaries
            ],
            "invariants": [
                {
                    "kind": inv.kind,
                    "line": inv.line,
                    "content": inv.content,
                    "reason": inv.reason,
                }
                for inv in self.invariants
            ],
            "patch_template": (
                {
                    "signature": self.patch_template.signature,
                    "edit_zone": [
                        self.patch_template.edit_zone_start,
                        self.patch_template.edit_zone_end,
                    ],
                    "preserve_before": self.patch_template.preserve_before,
                    "preserve_after": self.patch_template.preserve_after,
                }
                if self.patch_template
                else None
            ),
            "adjacent_symbols": self.adjacent_symbols,
            "type_constraints": self.type_constraints,
        }


class EditLocalityAnalyzer:
    """Analyzes code to extract edit-aware context."""

    def __init__(self) -> None:
        self._assertion_patterns = [
            re.compile(r"^\s*assert\s+"),
            re.compile(r"^\s*if\s+not\s+.*:\s*raise\s+"),
            re.compile(r"^\s*raise\s+\w+Error"),
        ]
        self._constant_patterns = [
            re.compile(r"^[A-Z][A-Z0-9_]*\s*="),
            re.compile(r"^\s*const\s+[A-Z]"),
        ]

    def extract_invariants(
        self,
        source_lines: list[str],
        start_line: int,
        end_line: int,
    ) -> list[Invariant]:
        """Extract invariants from a code region."""
        invariants: list[Invariant] = []

        for i, line in enumerate(source_lines[start_line - 1 : end_line], start=start_line):
            # Check for assertions
            for pattern in self._assertion_patterns:
                if pattern.match(line):
                    invariants.append(
                        Invariant(
                            kind="assertion",
                            line=i,
                            content=line.strip(),
                            reason="Assertions define expected behavior",
                        )
                    )
                    break

            # Check for type hints in function signature
            if ":" in line and "->" not in line:
                # Parameter type hint
                match = re.search(r"(\w+)\s*:\s*([A-Z]\w+)", line)
                if match:
                    invariants.append(
                        Invariant(
                            kind="type_hint",
                            line=i,
                            content=f"{match.group(1)}: {match.group(2)}",
                            reason="Type hints define interface contracts",
                        )
                    )

            # Check for return type hints
            if "->" in line:
                match = re.search(r"->\s*([A-Z]\w+(?:\[.*\])?)", line)
                if match:
                    invariants.append(
                        Invariant(
                            kind="type_hint",
                            line=i,
                            content=f"-> {match.group(1)}",
                            reason="Return type defines interface contract",
                        )
                    )

            # Check for constants
            for pattern in self._constant_patterns:
                if pattern.match(line):
                    invariants.append(
                        Invariant(
                            kind="constant",
                            line=i,
                            content=line.strip(),
                            reason="Constants should be changed in one place only",
                        )
                    )
                    break

            # Check for decorators
            if line.strip().startswith("@"):
                invariants.append(
                    Invariant(
                        kind="decorator",
                        line=i,
                        content=line.strip(),
                        reason="Decorators define symbol behavior",
                    )
                )

        return invariants

    def compute_edit_boundary(
        self,
        source_lines: list[str],
        symbol_start: int,
        symbol_end: int,
        diff_lines: list[int] | None = None,
    ) -> EditBoundary:
        """Compute the optimal edit boundary for a symbol."""
        if diff_lines:
            # If we have diff lines, narrow the edit zone
            edit_start = min(diff_lines)
            edit_end = max(diff_lines)
            return EditBoundary(
                start_line=edit_start,
                end_line=edit_end,
                context_before=min(3, edit_start - symbol_start),
                context_after=min(3, symbol_end - edit_end),
                boundary_type="diff_zone",
            )

        # Otherwise, try to find the function body (excluding docstring)
        body_start = symbol_start
        in_docstring = False
        docstring_char = None

        for i, line in enumerate(
            source_lines[symbol_start - 1 : symbol_end], start=symbol_start
        ):
            stripped = line.strip()

            # Skip signature line
            if i == symbol_start and ("def " in line or "function " in line):
                continue

            # Handle docstrings
            if not in_docstring:
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    in_docstring = True
                    docstring_char = stripped[:3]
                    if stripped.count(docstring_char) >= 2:
                        # Single-line docstring
                        in_docstring = False
                    continue
            else:
                if docstring_char and docstring_char in stripped:
                    in_docstring = False
                continue

            # Found first non-docstring, non-blank line
            if stripped and not in_docstring:
                body_start = i
                break

        return EditBoundary(
            start_line=body_start,
            end_line=symbol_end,
            context_before=body_start - symbol_start,
            context_after=0,
            boundary_type="body",
        )

    def generate_patch_template(
        self,
        source_lines: list[str],
        symbol_start: int,
        symbol_end: int,
        signature: str,
        diff_lines: list[int] | None = None,
    ) -> PatchTemplate:
        """Generate a patch template showing edit structure."""
        boundary = self.compute_edit_boundary(
            source_lines, symbol_start, symbol_end, diff_lines
        )

        # Extract lines to preserve
        preserve_before: list[str] = []
        preserve_after: list[str] = []

        # Lines between symbol start and edit zone
        for line in source_lines[symbol_start - 1 : boundary.start_line - 1]:
            preserve_before.append(line.rstrip())

        # Lines after edit zone to symbol end
        if boundary.end_line < symbol_end:
            for line in source_lines[boundary.end_line : symbol_end]:
                preserve_after.append(line.rstrip())

        current_body = "\n".join(
            source_lines[boundary.start_line - 1 : boundary.end_line]
        )

        return PatchTemplate(
            symbol_id="",  # Filled by caller
            signature=signature,
            current_body=current_body,
            edit_zone_start=boundary.start_line,
            edit_zone_end=boundary.end_line,
            preserve_before=preserve_before,
            preserve_after=preserve_after,
        )

    def extract_type_constraints(
        self,
        source: str,
        symbol_name: str,
    ) -> list[str]:
        """Extract type constraints for a symbol from Python source."""
        constraints: list[str] = []

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return constraints

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == symbol_name:
                # Extract parameter types
                for arg in node.args.args:
                    if arg.annotation:
                        try:
                            ann = ast.unparse(arg.annotation)
                            constraints.append(f"{arg.arg}: {ann}")
                        except Exception:
                            pass

                # Extract return type
                if node.returns:
                    try:
                        ret = ast.unparse(node.returns)
                        constraints.append(f"-> {ret}")
                    except Exception:
                        pass

        return constraints


def get_edit_context(
    project: str | Path,
    symbol_id: str,
    diff_lines: list[int] | None = None,
    call_graph: dict[str, list[str]] | None = None,
) -> EditContext | None:
    """Get edit-locality-aware context for a symbol.

    Args:
        project: Project root path
        symbol_id: Symbol identifier (e.g., "path/to/file.py:ClassName.method")
        diff_lines: Optional list of lines that are being modified
        call_graph: Optional call graph for finding adjacent symbols

    Returns:
        EditContext with boundaries, invariants, and patch template
    """
    project = Path(project).resolve()

    # Parse symbol_id
    if ":" not in symbol_id:
        return None

    rel_path, qualified_name = symbol_id.split(":", 1)
    file_path = project / rel_path

    if not file_path.exists():
        return None

    try:
        source = file_path.read_text()
        source_lines = source.splitlines()
    except Exception:
        return None

    # Find symbol boundaries (simplified - in practice, use HybridExtractor)
    symbol_start = 1
    symbol_end = len(source_lines)
    signature = ""

    # Simple search for function/class definition
    name = qualified_name.split(".")[-1]
    for i, line in enumerate(source_lines, 1):
        if f"def {name}(" in line or f"class {name}" in line:
            symbol_start = i
            signature = line.strip()
            # Find end by indentation
            base_indent = len(line) - len(line.lstrip())
            for j, next_line in enumerate(source_lines[i:], i + 1):
                if next_line.strip() and len(next_line) - len(next_line.lstrip()) <= base_indent:
                    symbol_end = j - 1
                    break
            else:
                symbol_end = len(source_lines)
            break

    analyzer = EditLocalityAnalyzer()

    # Extract invariants
    invariants = analyzer.extract_invariants(source_lines, symbol_start, symbol_end)

    # Compute edit boundary
    boundary = analyzer.compute_edit_boundary(
        source_lines, symbol_start, symbol_end, diff_lines
    )

    # Generate patch template
    patch_template = analyzer.generate_patch_template(
        source_lines, symbol_start, symbol_end, signature, diff_lines
    )
    patch_template.symbol_id = symbol_id

    # Extract type constraints
    type_constraints = analyzer.extract_type_constraints(source, name)

    # Find adjacent symbols from call graph
    adjacent_symbols: list[str] = []
    if call_graph:
        # Symbols that call this one
        for caller, callees in call_graph.items():
            if symbol_id in callees:
                adjacent_symbols.append(caller)
        # Symbols this one calls
        adjacent_symbols.extend(call_graph.get(symbol_id, []))

    # Extract target code
    target_code = "\n".join(source_lines[symbol_start - 1 : symbol_end])

    return EditContext(
        symbol_id=symbol_id,
        file_path=str(file_path),
        target_code=target_code,
        boundaries=[boundary],
        invariants=invariants,
        patch_template=patch_template,
        adjacent_symbols=adjacent_symbols[:10],  # Limit to most relevant
        type_constraints=type_constraints,
    )


def create_edit_locality_enricher(
    project: str | Path,
    file_sources: dict[str, str],
) -> "Callable[[list], list]":
    """Create a post-processor that adds edit boundary and invariant metadata.

    Only enriches candidates that have diff_lines in their meta.
    Compatible with ContextPackEngine's post_processors parameter.
    """
    from .contextpack_engine import Candidate

    project = Path(project).resolve()
    analyzer = EditLocalityAnalyzer()

    def enrich(candidates: list[Candidate]) -> list[Candidate]:
        enriched = []
        for candidate in candidates:
            meta = dict(candidate.meta) if candidate.meta else {}
            diff_lines = meta.get("diff_lines")

            # Only enrich candidates with diff info and line ranges
            if diff_lines and candidate.lines:
                symbol_id = candidate.symbol_id
                if ":" in symbol_id:
                    rel_path = symbol_id.split(":", 1)[0]
                    file_path = project / rel_path
                    abs_path = str(file_path)

                    source = file_sources.get(abs_path)
                    if source:
                        source_lines = source.splitlines()
                        start, end = candidate.lines

                        # Flatten diff_lines ranges to individual lines
                        flat_diff = []
                        for item in diff_lines:
                            if isinstance(item, list) and len(item) == 2:
                                flat_diff.extend(range(item[0], item[1] + 1))
                            elif isinstance(item, int):
                                flat_diff.append(item)

                        boundary = analyzer.compute_edit_boundary(
                            source_lines, start, end, flat_diff or None
                        )
                        invariants = analyzer.extract_invariants(
                            source_lines, start, end
                        )

                        meta["edit_boundary"] = {
                            "start": boundary.start_line,
                            "end": boundary.end_line,
                            "type": boundary.boundary_type,
                        }
                        meta["invariants"] = [
                            {"kind": inv.kind, "line": inv.line, "content": inv.content}
                            for inv in invariants[:5]  # Cap to avoid bloat
                        ]

            enriched.append(Candidate(
                symbol_id=candidate.symbol_id,
                relevance=candidate.relevance,
                relevance_label=candidate.relevance_label,
                order=candidate.order,
                signature=candidate.signature,
                code=candidate.code,
                lines=candidate.lines,
                meta=meta if meta else candidate.meta,
            ))
        return enriched

    return enrich


def format_edit_context_for_agent(context: EditContext) -> str:
    """Format EditContext as agent-friendly text."""
    lines = [
        f"# Edit Context for {context.symbol_id}",
        "",
        "## Target Code",
        "```",
        context.target_code,
        "```",
        "",
    ]

    if context.boundaries:
        b = context.boundaries[0]
        lines.extend(
            [
                f"## Edit Zone: lines {b.start_line}-{b.end_line} ({b.boundary_type})",
                "",
            ]
        )

    if context.invariants:
        lines.append("## Invariants (DO NOT MODIFY)")
        for inv in context.invariants:
            lines.append(f"- Line {inv.line} ({inv.kind}): `{inv.content}`")
            lines.append(f"  Reason: {inv.reason}")
        lines.append("")

    if context.type_constraints:
        lines.append("## Type Constraints")
        for tc in context.type_constraints:
            lines.append(f"- `{tc}`")
        lines.append("")

    if context.patch_template:
        pt = context.patch_template
        lines.extend(
            [
                "## Patch Template",
                "```",
                pt.signature,
            ]
        )
        if pt.preserve_before:
            lines.extend(pt.preserve_before)
        lines.append("    # === EDIT ZONE START ===")
        lines.append(f"    # Current: {len(pt.current_body.splitlines())} lines")
        lines.append("    # === EDIT ZONE END ===")
        if pt.preserve_after:
            lines.extend(pt.preserve_after)
        lines.append("```")
        lines.append("")

    if context.adjacent_symbols:
        lines.append("## Adjacent Symbols (may need updates)")
        for sym in context.adjacent_symbols[:5]:
            lines.append(f"- {sym}")

    return "\n".join(lines)
