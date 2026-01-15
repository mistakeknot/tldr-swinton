from __future__ import annotations

from ..pdg_extractor import extract_pdg
from ..path_utils import _resolve_source


def get_pdg_context(
    source_or_path: str,
    function_name: str,
    language: str = "python",
) -> dict | None:
    """Get program dependence graph context for a function."""
    source_code, _ = _resolve_source(source_or_path)
    pdg = extract_pdg(source_code, function_name, language)
    if pdg is None:
        return None

    return pdg.to_compact_dict()
