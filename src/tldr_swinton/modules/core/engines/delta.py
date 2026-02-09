"""Delta-first context extraction engine.

Orchestrates the delta-first extraction pattern: get signatures first,
compute ETags, check delta against session cache, then only extract code
for changed symbols. This avoids wasted extraction for unchanged symbols.

Moved from cli.py to make delta logic reusable by the daemon and future
API consumers.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..contextpack_engine import ContextPack


def relevance_to_int(label: str | None) -> int:
    """Convert relevance label to integer for sorting."""
    if not label:
        return 0
    mapping = {
        "contains_diff": 100,
        "caller": 80,
        "callee": 80,
        "test": 60,
        "signature_only": 20,
    }
    return mapping.get(label, 50)


def _collect_diff_text(project_root: Path, base_ref: str, head_ref: str) -> str:
    """Run git diff three ways (committed, staged, unstaged) and concatenate."""
    def _run_diff(args: list[str]) -> str:
        result = subprocess.run(
            ["git", "-C", str(project_root), "diff", "--unified=0"] + args,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            return ""
        return result.stdout

    diff_text = _run_diff([f"{base_ref}..{head_ref}"])
    diff_text += _run_diff(["--staged"])
    diff_text += _run_diff([])
    return diff_text


def get_context_pack_with_delta(
    project: str,
    entry_point: str,
    session_id: str,
    depth: int = 2,
    language: str = "python",
    budget_tokens: int | None = None,
    include_docstrings: bool = False,
) -> "ContextPack":
    """Get context pack with delta detection against session cache.

    Uses delta-first extraction: gets signatures first, checks delta,
    then only extracts code for changed symbols. This avoids wasted
    extraction for unchanged symbols.

    Returns a ContextPack where unchanged symbols have code=None and are
    listed in the `unchanged` field. Changed/new symbols include full code.
    """
    from .symbolkite import get_signatures_for_entry
    from ..contextpack_engine import Candidate, ContextPack, ContextPackEngine
    from ..state_store import StateStore

    project_root = Path(project).resolve()
    store = StateStore(project_root)

    # DELTA-FIRST: Get signatures only (no code extraction yet)
    signatures_result = get_signatures_for_entry(
        project,
        entry_point,
        depth=depth,
        language=language,
        disambiguate=True,
    )

    # Handle error case (ambiguous)
    if isinstance(signatures_result, dict) and signatures_result.get("error"):
        return ContextPack(slices=[], unchanged=[], rehydrate={})

    signatures = signatures_result
    if not signatures:
        return ContextPack(slices=[], unchanged=[], rehydrate={})

    # Compute ETags from signatures only (not code)
    symbol_etags = {}
    for sig in signatures:
        content = sig.signature
        etag = hashlib.sha256(content.encode()).hexdigest()
        symbol_etags[sig.symbol_id] = etag

    # Check delta against session cache
    delta_result = store.check_delta(session_id, symbol_etags)

    # Now extract code ONLY for changed symbols
    from ..api import get_symbol_context_pack

    # If all symbols unchanged, return early with signatures only
    if not delta_result.changed:
        candidates = [
            Candidate(
                symbol_id=sig.symbol_id,
                relevance=max(1, (depth - sig.depth) + 1),
                relevance_label=f"depth_{sig.depth}",
                order=i,
                signature=sig.signature,
                code=None,  # All unchanged - no code needed
                lines=(sig.line, sig.line) if sig.line else None,
                meta={"calls": sig.calls},
            )
            for i, sig in enumerate(signatures)
        ]

        engine = ContextPackEngine()
        pack = engine.build_context_pack_delta(
            candidates,
            delta_result,
            budget_tokens=budget_tokens,
        )
        return pack

    # Some symbols changed - need to get full pack for code extraction
    # but we can now be selective about what we include
    full_pack_dict = get_symbol_context_pack(
        project,
        entry_point,
        depth=depth,
        language=language,
        budget_tokens=None,  # Get all symbols first
        include_docstrings=include_docstrings,
    )

    # Handle ambiguous case
    if full_pack_dict.get("error"):
        return ContextPack(slices=[], unchanged=[], rehydrate={})

    slices_data = full_pack_dict.get("slices", [])
    if not slices_data:
        return ContextPack(slices=[], unchanged=[], rehydrate={})

    # Build candidates with code only for changed symbols
    slice_map = {s["id"]: s for s in slices_data}
    candidates = []

    for i, sig in enumerate(signatures):
        is_changed = sig.symbol_id in delta_result.changed
        slice_data = slice_map.get(sig.symbol_id, {})

        candidates.append(
            Candidate(
                symbol_id=sig.symbol_id,
                relevance=relevance_to_int(slice_data.get("relevance")) or max(1, (depth - sig.depth) + 1),
                relevance_label=slice_data.get("relevance") or f"depth_{sig.depth}",
                order=i,
                signature=sig.signature,
                code=slice_data.get("code") if is_changed else None,  # Only include code for changed
                lines=tuple(slice_data["lines"]) if slice_data.get("lines") else None,
                meta=slice_data.get("meta") or {"calls": sig.calls},
            )
        )

    engine = ContextPackEngine()
    delta_pack = engine.build_context_pack_delta(
        candidates,
        delta_result,
        budget_tokens=budget_tokens,
    )

    # Record deliveries for changed symbols
    deliveries = []
    for s in delta_pack.slices:
        if s.id in (delta_pack.unchanged or []):
            continue
        deliveries.append({
            "symbol_id": s.id,
            "etag": symbol_etags.get(s.id, ""),
            "representation": "full" if s.code else "signature",
            "vhs_ref": None,
            "token_estimate": len(s.code) // 4 if s.code else len(s.signature) // 4,
        })

    if deliveries:
        from ..state_store import _compute_repo_fingerprint
        fingerprint = _compute_repo_fingerprint(project_root)
        store.open_session(session_id, fingerprint, language)
        store.record_deliveries_batch(session_id, deliveries)

    return delta_pack


def get_diff_context_with_delta(
    project: Path,
    session_id: str,
    base: str | None = None,
    head: str = "HEAD",
    budget_tokens: int | None = None,
    language: str = "python",
    compress: str | None = None,
) -> "ContextPack":
    """Get diff context pack with delta detection against session cache.

    Uses delta-first extraction: parses diff hunks, gets signatures first,
    checks delta, then only extracts code for changed symbols. This avoids
    wasted extraction for unchanged symbols.

    Returns a ContextPack where unchanged symbols have code=None and are
    listed in the `unchanged` field. Changed/new symbols include full code.

    This is where delta mode provides real savings - diff-context includes
    code bodies, so skipping unchanged code saves significant tokens.
    """
    from .difflens import parse_unified_diff, get_diff_signatures
    from ..contextpack_engine import Candidate, ContextPack, ContextPackEngine
    from ..state_store import StateStore

    project_root = project.resolve()
    store = StateStore(project_root)

    # Parse diff to get hunks
    base_ref = base or "HEAD~1"
    head_ref = head or "HEAD"

    diff_text = _collect_diff_text(project_root, base_ref, head_ref)

    hunks = parse_unified_diff(diff_text)
    if not hunks:
        # Fallback to recent files
        from ..api import get_diff_context
        full_pack = get_diff_context(
            project_root,
            base=base,
            head=head,
            budget_tokens=budget_tokens,
            language=language,
            compress=compress,
        )
        return ContextPack(
            slices=[],
            unchanged=[],
            rehydrate={},
            budget_used=full_pack.get("budget_used", 0),
        )

    # DELTA-FIRST: Get signatures only (no code extraction yet)
    signatures = get_diff_signatures(project_root, hunks, language=language)

    if not signatures:
        return ContextPack(slices=[], unchanged=[], rehydrate={})

    # Compute ETags from signature + diff_lines (which identifies what changed)
    symbol_etags = {}
    for sig in signatures:
        # Include diff lines in etag so changes to the symbol's diff portion are detected
        content = f"{sig.signature}\n{','.join(map(str, sig.diff_lines))}"
        etag = hashlib.sha256(content.encode()).hexdigest()
        symbol_etags[sig.symbol_id] = etag

    # Check delta against session cache
    delta_result = store.check_delta(session_id, symbol_etags)

    # If all symbols unchanged, return early with signatures only
    if not delta_result.changed:
        relevance_score = {"contains_diff": 100, "caller": 80, "callee": 80, "adjacent": 50}
        candidates = [
            Candidate(
                symbol_id=sig.symbol_id,
                relevance=relevance_score.get(sig.relevance_label, 50),
                relevance_label=sig.relevance_label,
                order=i,
                signature=sig.signature,
                code=None,  # All unchanged - no code needed
                lines=(sig.line, sig.line) if sig.line else None,
                meta={"diff_lines": sig.diff_lines},
            )
            for i, sig in enumerate(signatures)
        ]

        engine = ContextPackEngine()
        pack = engine.build_context_pack_delta(
            candidates,
            delta_result,
            budget_tokens=budget_tokens,
        )
        return pack

    # Some symbols changed - need to get full pack for code extraction
    from ..api import get_diff_context

    full_pack_dict = get_diff_context(
        project_root,
        base=base,
        head=head,
        budget_tokens=None,  # Get all symbols first
        language=language,
        compress=compress,
    )

    slices_data = full_pack_dict.get("slices", [])

    # Build slice lookup
    slice_map = {s["id"]: s for s in slices_data}

    # Build candidates with code only for changed symbols
    relevance_score = {"contains_diff": 100, "caller": 80, "callee": 80, "adjacent": 50}
    candidates = []

    for i, sig in enumerate(signatures):
        is_changed = sig.symbol_id in delta_result.changed
        slice_data = slice_map.get(sig.symbol_id, {})

        candidates.append(
            Candidate(
                symbol_id=sig.symbol_id,
                relevance=relevance_to_int(slice_data.get("relevance")) or relevance_score.get(sig.relevance_label, 50),
                relevance_label=slice_data.get("relevance") or sig.relevance_label,
                order=i,
                signature=sig.signature,
                code=slice_data.get("code") if is_changed else None,  # Only include code for changed
                lines=tuple(slice_data["lines"]) if slice_data.get("lines") and len(slice_data["lines"]) == 2 else None,
                meta={k: v for k, v in slice_data.items() if k not in ("id", "relevance", "signature", "code", "lines")} or {"diff_lines": sig.diff_lines},
            )
        )

    engine = ContextPackEngine()
    delta_pack = engine.build_context_pack_delta(
        candidates,
        delta_result,
        budget_tokens=budget_tokens,
    )

    # Record deliveries for changed symbols
    deliveries = []
    for s in delta_pack.slices:
        if s.id in (delta_pack.unchanged or []):
            continue
        deliveries.append({
            "symbol_id": s.id,
            "etag": symbol_etags.get(s.id, ""),
            "representation": "full" if s.code else "signature",
            "vhs_ref": None,
            "token_estimate": len(s.code) // 4 if s.code else len(s.signature) // 4,
        })

    if deliveries:
        from ..state_store import _compute_repo_fingerprint
        fingerprint = _compute_repo_fingerprint(project_root)
        store.open_session(session_id, fingerprint, language)
        store.record_deliveries_batch(session_id, deliveries)

    return delta_pack
