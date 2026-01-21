from __future__ import annotations

from pathlib import Path


class PathTraversalError(ValueError):
    """Raised when a path attempts to escape its container via directory traversal.

    This is a security error indicating an attempted path traversal attack
    (e.g., using ../../../etc/passwd to escape the project directory).
    """


def _validate_path_containment(file_path: str, base_path: str | None = None) -> Path:
    """Validate that file_path doesn't escape base_path via traversal.

    Detects directory traversal attacks (../..) and symlink escapes.

    Args:
        file_path: The path to validate
        base_path: Optional container directory. If None, detects traversal
                   patterns that escape the apparent starting directory.

    Returns:
        Resolved Path object

    Raises:
        PathTraversalError: If path contains traversal or escapes base
        ValueError: If path is empty or whitespace-only
    """
    if not file_path or not file_path.strip():
        raise ValueError("Path cannot be empty or whitespace-only")

    if "\x00" in file_path:
        raise ValueError("Path contains null byte")

    try:
        resolved = Path(file_path).resolve()
    except OSError as e:
        raise ValueError(f"Invalid path: {e}")

    if ".." in file_path:
        if base_path:
            base = Path(base_path).resolve()
            try:
                if not resolved.is_relative_to(base):
                    raise PathTraversalError(
                        f"Path '{file_path}' escapes base directory '{base_path}' via traversal"
                    )
            except ValueError:
                raise PathTraversalError(
                    f"Path '{file_path}' escapes base directory '{base_path}'"
                )
        else:
            path_obj = Path(file_path)
            parts = list(path_obj.parts)

            i = 0
            while i < len(parts) - 1:
                current = parts[i]
                next_part = parts[i + 1]

                if current in ("/", "\\") or (len(current) == 2 and current[1] == ":"):
                    i += 1
                    continue

                if current not in (".", "..") and next_part == "..":
                    raise PathTraversalError(
                        f"Path '{file_path}' contains directory traversal pattern '{current}/..'"
                    )
                i += 1

    try:
        path_exists = resolved.exists()
    except (OSError, TypeError):
        path_exists = False

    if path_exists:
        original_path = Path(file_path)
        try:
            is_symlink = original_path.is_symlink()
        except (OSError, TypeError):
            is_symlink = False

        if is_symlink:
            try:
                target = original_path.readlink()
                abs_target = (original_path.parent / target).resolve()

                if base_path:
                    base = Path(base_path).resolve()
                    if not abs_target.is_relative_to(base):
                        raise PathTraversalError(
                            f"Symlink '{file_path}' points outside base directory '{base_path}'"
                        )
                else:
                    symlink_parent = original_path.parent.resolve()
                    if not abs_target.is_relative_to(symlink_parent):
                        raise PathTraversalError(
                            f"Symlink '{file_path}' points outside its containing directory"
                        )
            except OSError:
                pass

    return resolved


def _resolve_source(source_or_path: str) -> tuple[str, str | None]:
    """Resolve source code from either source string or file path."""
    if len(source_or_path) < 500:
        try:
            _validate_path_containment(source_or_path)

            path = Path(source_or_path)
            if path.exists() and path.is_file():
                return path.read_text(encoding="utf-8"), str(path)
        except PathTraversalError:
            raise
        except (OSError, ValueError):
            pass

    return source_or_path, None
