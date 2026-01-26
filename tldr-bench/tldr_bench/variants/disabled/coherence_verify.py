"""Coherence verification variant for benchmarking.

This variant ADDS cross-file coherence checks to context (on top of symbolkite),
helping prevent multi-file edit failures.

IMPORTANT: This is a QUALITY feature, not a compression feature.
Token counts from this variant will be HIGHER than symbolkite because
it adds verification information. The value is in ERROR PREVENTION.

Proper benchmarking should measure:
- % of cross-file type errors detected before commit
- % of signature mismatches identified
- False positive rate (warnings for correct code)
- NOT token savings (this feature adds tokens, by design)
"""

VARIANT_ID = "coherence_verify"

# Marker to indicate this is a quality feature, not compression
VARIANT_TYPE = "quality"
COMPARABLE_TO = []  # Not meant for token savings comparison
ADDS_OVERHEAD = True  # Explicitly adds tokens to base context


def build_context(task: dict) -> str:
    """Build context with coherence verification info.

    Adds cross-file dependency and type compatibility information
    to help prevent multi-file edit failures.

    NOTE: This ADDS tokens to symbolkite context. Token "savings" vs baseline
    come from symbolkite compression, not from coherence verification.
    """
    from tldr_swinton.engines.symbolkite import get_relevant_context
    from tldr_swinton.modules.core.coherence_verify import (
        CoherenceVerifier,
        EditedSymbol,
    )
    from tldr_swinton.output_formats import format_context

    from . import resolve_project_root

    project = resolve_project_root(task)
    entry = task.get("entry", "")
    if not entry:
        raise ValueError("task.entry is required")

    depth = task.get("depth", 1)
    language = task.get("language", "python")
    budget = task.get("budget")
    fmt = task.get("context_format", "text")

    # Get base context
    ctx = get_relevant_context(str(project), entry, depth=depth, language=language)
    base_output = format_context(ctx, fmt=fmt, budget_tokens=budget)

    # Add coherence verification info for expected files
    expected_files = task.get("expected_files", [])
    if expected_files:
        verifier = CoherenceVerifier(project)

        # Create mock edited symbols from expected files
        edited_symbols = []
        for file_path in expected_files:
            if ":" in entry:
                _, symbol_name = entry.rsplit(":", 1)
            else:
                symbol_name = entry

            edited_symbols.append(
                EditedSymbol(
                    file_path=str(project / file_path),
                    symbol_name=symbol_name,
                )
            )

        if edited_symbols:
            try:
                report = verifier.verify_edits(edited_symbols)
                coherence_section = f"\n\n## Cross-File Coherence\n{report.format_for_agent()}"
                base_output += coherence_section
            except Exception as e:
                base_output += f"\n\n## Cross-File Coherence\nVerification failed: {e}"

    return base_output
