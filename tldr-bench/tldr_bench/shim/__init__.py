"""CLI shim package."""

from .adapter import assemble_prompt, resolve_model_command

__all__ = ["assemble_prompt", "resolve_model_command"]
