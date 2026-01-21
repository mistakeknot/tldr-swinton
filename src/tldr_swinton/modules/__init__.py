"""TLDR-Swinton modules.

Modules:
- core: Multi-layer code intelligence (AST, CFG, DFG, PDG, semantic search)
- vhs: Content-addressed store for tool outputs
- workbench: Session artifacts (capsules, decisions, hypotheses, links)
- bench: Benchmarking harness for validating improvements
"""

# Lazy imports to avoid circular dependencies and optional module issues
def __getattr__(name: str):
    if name == "core":
        from . import core
        return core
    elif name == "vhs":
        from . import vhs
        return vhs
    elif name == "workbench":
        from . import workbench
        return workbench
    elif name == "bench":
        from . import bench
        return bench
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["core", "vhs", "workbench", "bench"]
