"""
TLDR Structured Error Codes for Agent-Parseable Failures.

Error codes that agents can programmatically handle:
- TLDRS_ERR_NO_INDEX: Semantic search needs index
- TLDRS_ERR_AMBIGUOUS: Multiple symbols match query
- TLDRS_ERR_DAEMON: Daemon not running or unreachable
- TLDRS_ERR_PARSE: File parsing failed
- TLDRS_ERR_NOT_FOUND: Symbol or file not found
- TLDRS_ERR_TIMEOUT: Operation timed out
"""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# Error codes
ERR_NO_INDEX = "TLDRS_ERR_NO_INDEX"
ERR_AMBIGUOUS = "TLDRS_ERR_AMBIGUOUS"
ERR_DAEMON = "TLDRS_ERR_DAEMON"
ERR_PARSE = "TLDRS_ERR_PARSE"
ERR_NOT_FOUND = "TLDRS_ERR_NOT_FOUND"
ERR_TIMEOUT = "TLDRS_ERR_TIMEOUT"
ERR_INTERNAL = "TLDRS_ERR_INTERNAL"


@dataclass
class TLDRSError:
    """Structured error response for machine parsing."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "error": True,
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


def make_error(code: str, message: str, **details) -> dict:
    """Create a structured error response dict."""
    return TLDRSError(code=code, message=message, details=details).to_dict()


def log_and_return_empty(
    logger_: logging.Logger,
    level: int,
    message: str,
    exc: Exception | None = None,
    return_value: Any = None,
) -> Any:
    """
    Log exception and return a default value.

    Used to replace silent `except: pass` with logged fallbacks.
    """
    if exc:
        logger_.log(level, f"{message}: {exc}")
    else:
        logger_.log(level, message)
    return return_value if return_value is not None else []


def make_ambiguous_error(candidates: list[str], query: str) -> dict:
    """Create an ambiguous symbol error with candidate list."""
    return make_error(
        ERR_AMBIGUOUS,
        f"Multiple symbols match '{query}'. Please specify one of the candidates.",
        candidates=candidates,
        query=query,
    )


def make_no_index_error(project: str) -> dict:
    """Create a no semantic index error."""
    return make_error(
        ERR_NO_INDEX,
        "Semantic index not found. Run 'tldrs semantic index' first.",
        project=project,
        hint="tldrs semantic index --project .",
    )


def make_daemon_error(project: str, reason: str = "unreachable") -> dict:
    """Create a daemon error."""
    return make_error(
        ERR_DAEMON,
        f"Daemon {reason}. Start with 'tldrs daemon start'.",
        project=project,
        hint="tldrs daemon start --project .",
    )


def make_parse_error(file_path: str, reason: str) -> dict:
    """Create a parse error."""
    return make_error(
        ERR_PARSE,
        f"Failed to parse {file_path}: {reason}",
        file=file_path,
    )


def make_not_found_error(item_type: str, name: str) -> dict:
    """Create a not found error."""
    return make_error(
        ERR_NOT_FOUND,
        f"{item_type} '{name}' not found",
        type=item_type,
        name=name,
    )
