"""Engine entry points for discrete context strategies."""

from .symbolkite import get_relevant_context
from .difflens import get_diff_context
from .cfg import get_cfg_context
from .dfg import get_dfg_context
from .pdg import get_pdg_context
from .slice import get_slice
from .delta import get_context_pack_with_delta, get_diff_context_with_delta, relevance_to_int

__all__ = [
    "get_relevant_context",
    "get_diff_context",
    "get_cfg_context",
    "get_dfg_context",
    "get_pdg_context",
    "get_slice",
    "get_context_pack_with_delta",
    "get_diff_context_with_delta",
    "relevance_to_int",
]

# Optional: structural search (requires ast-grep-py at runtime)
try:
    from .astgrep import get_structural_search, get_structural_context

    __all__.append("get_structural_search")
    __all__.append("get_structural_context")
except ImportError:
    pass
