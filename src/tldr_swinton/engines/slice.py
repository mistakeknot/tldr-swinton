from __future__ import annotations

from ..pdg_extractor import extract_pdg
from ..path_utils import _resolve_source


def get_slice(
    source_or_path: str,
    function_name: str,
    line: int,
    direction: str = "backward",
    variable: str | None = None,
    language: str = "python",
) -> set[int]:
    """Get program slice lines for a function."""
    if direction not in ("backward", "forward"):
        raise ValueError(
            f"Invalid direction '{direction}'. Must be 'backward' or 'forward'."
        )

    source_code, _ = _resolve_source(source_or_path)
    pdg = extract_pdg(source_code, function_name, language)
    if pdg is None:
        return set()

    if direction == "backward":
        return pdg.backward_slice(line, variable)
    return pdg.forward_slice(line, variable)
