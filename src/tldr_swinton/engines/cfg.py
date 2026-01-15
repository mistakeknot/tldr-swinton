from __future__ import annotations

from ..cfg_extractor import (
    CFGInfo,
    extract_c_cfg,
    extract_cpp_cfg,
    extract_csharp_cfg,
    extract_elixir_cfg,
    extract_go_cfg,
    extract_java_cfg,
    extract_kotlin_cfg,
    extract_lua_cfg,
    extract_php_cfg,
    extract_python_cfg,
    extract_ruby_cfg,
    extract_rust_cfg,
    extract_scala_cfg,
    extract_swift_cfg,
    extract_typescript_cfg,
)
from ..path_utils import _resolve_source


def get_cfg_context(
    source_or_path: str,
    function_name: str,
    language: str = "python",
) -> dict:
    """Get control flow graph context for a function."""
    source_code, _ = _resolve_source(source_or_path)

    cfg_extractors = {
        "python": extract_python_cfg,
        "typescript": extract_typescript_cfg,
        "javascript": extract_typescript_cfg,
        "go": extract_go_cfg,
        "rust": extract_rust_cfg,
        "java": extract_java_cfg,
        "c": extract_c_cfg,
        "cpp": extract_cpp_cfg,
        "ruby": extract_ruby_cfg,
        "php": extract_php_cfg,
        "swift": extract_swift_cfg,
        "csharp": extract_csharp_cfg,
        "lua": extract_lua_cfg,
        "elixir": extract_elixir_cfg,
        "kotlin": extract_kotlin_cfg,
        "scala": extract_scala_cfg,
    }

    extractor_fn = cfg_extractors.get(language, extract_python_cfg)

    try:
        cfg_info: CFGInfo = extractor_fn(source_code, function_name)
        if cfg_info is None:
            return {
                "function": function_name,
                "blocks": [],
                "edges": [],
                "entry_block": 0,
                "exit_blocks": [],
                "cyclomatic_complexity": 0,
            }
        return cfg_info.to_dict()
    except Exception:
        return {
            "function": function_name,
            "blocks": [],
            "edges": [],
            "entry_block": 0,
            "exit_blocks": [],
            "cyclomatic_complexity": 0,
        }
