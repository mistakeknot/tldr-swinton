"""
TLDR-Swinton: Modular Platform for Coding Agent Performance

A centralized, modular platform for improving coding agent performance and
efficiency with methods that are tested and validated.

Modules:
- core: Multi-layer code intelligence (AST, CFG, DFG, PDG, semantic search)
- vhs: Content-addressed store for tool outputs
- workbench: Session artifacts (capsules, decisions, hypotheses, links)
- bench: Benchmarking harness for validating improvements

Key features:
- 5 layers of code analysis (ARISTODE pattern)
- 95%+ token savings through intelligent extraction
- Semantic search with embeddings
- Session state tracking for agent workflows
"""

try:
    from importlib.metadata import version
    __version__ = version("tldr-swinton")
except Exception:
    __version__ = "0.3.0"
__author__ = "Steve Yegge"

# Re-export core module contents for backward compatibility
# Users can still do: from tldr_swinton import extract_file
from .modules.core import (
    # Original
    SignatureExtractor,
    # Engines
    engine_get_cfg_context,
    engine_get_dfg_context,
    engine_get_diff_context,
    engine_get_pdg_context,
    engine_get_relevant_context,
    engine_get_slice,
    # Layer 1: AST
    extract_python,
    extract_file,
    # Layer 2: Call Graph
    extract_call_graph,
    # Layer 3: CFG
    CFGInfo,
    CFGBlock,
    CFGEdge,
    extract_python_cfg,
    # Layer 4: DFG
    DFGInfo,
    VarRef,
    DataflowEdge,
    extract_python_dfg,
    # Layer 5: PDG
    PDGInfo,
    PDGNode,
    PDGEdge,
    extract_python_pdg,
    extract_pdg,
)

# Module access
from . import modules

# Backward compatibility: expose core submodules at package level
# This allows: from tldr_swinton.api import get_relevant_context
import sys
from .modules.core import api
from .modules.core import analysis
from .modules.core import output_formats
from .modules.core import contextpack_engine
from .modules.core import engines
from .modules.core import cross_file_calls
from .modules.core import symbol_registry
from .modules.core import daemon
from .modules.core import mcp_server
from .modules.semantic import index
from .modules.semantic import semantic as semantic_mod
from .modules.core import state_store
from .modules.core import tldrsignore
from .modules.core import ast_extractor

# Patch sys.modules for backward compatibility with old import paths
sys.modules['tldr_swinton.api'] = api
sys.modules['tldr_swinton.analysis'] = analysis
sys.modules['tldr_swinton.output_formats'] = output_formats
sys.modules['tldr_swinton.contextpack_engine'] = contextpack_engine
sys.modules['tldr_swinton.engines'] = engines
sys.modules['tldr_swinton.cross_file_calls'] = cross_file_calls
sys.modules['tldr_swinton.symbol_registry'] = symbol_registry
sys.modules['tldr_swinton.daemon'] = daemon
sys.modules['tldr_swinton.mcp_server'] = mcp_server
sys.modules['tldr_swinton.index'] = index
sys.modules['tldr_swinton.semantic'] = semantic_mod
sys.modules['tldr_swinton.state_store'] = state_store
sys.modules['tldr_swinton.tldrsignore'] = tldrsignore
sys.modules['tldr_swinton.ast_extractor'] = ast_extractor

# Also alias engines submodules
from .modules.core.engines import symbolkite
sys.modules['tldr_swinton.engines.symbolkite'] = symbolkite

# Additional module aliases
from .modules.core import hybrid_extractor
from .modules.core import vhs_store
from .modules.core import workspace
sys.modules['tldr_swinton.hybrid_extractor'] = hybrid_extractor
sys.modules['tldr_swinton.vhs_store'] = vhs_store
sys.modules['tldr_swinton.workspace'] = workspace

__all__ = [
    # Modules
    "modules",
    # Original
    "SignatureExtractor",
    # Engines (stable entry points)
    "engine_get_cfg_context",
    "engine_get_dfg_context",
    "engine_get_diff_context",
    "engine_get_pdg_context",
    "engine_get_relevant_context",
    "engine_get_slice",
    # Layer 1: AST
    "extract_python",
    "extract_file",
    # Layer 2: Call Graph
    "extract_call_graph",
    # Layer 3: CFG
    "CFGInfo",
    "CFGBlock",
    "CFGEdge",
    "extract_python_cfg",
    # Layer 4: DFG
    "DFGInfo",
    "VarRef",
    "DataflowEdge",
    "extract_python_dfg",
    # Layer 5: PDG (multi-language via extract_pdg)
    "PDGInfo",
    "PDGNode",
    "PDGEdge",
    "extract_python_pdg",
    "extract_pdg",
]
