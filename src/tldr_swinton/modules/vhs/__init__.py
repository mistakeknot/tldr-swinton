"""
VHS: Content-addressed store for tool outputs.

A local content-addressed store for caching and referencing tool outputs,
enabling efficient deduplication and retrieval of LLM context artifacts.
"""

__version__ = "0.1.0"

from .store import Store, ObjectInfo, parse_ref, SCHEME

__all__ = ["Store", "ObjectInfo", "parse_ref", "SCHEME", "__version__"]
