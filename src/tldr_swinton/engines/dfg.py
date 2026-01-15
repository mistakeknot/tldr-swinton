from __future__ import annotations

from ..dfg_extractor import (
    DFGInfo,
    extract_c_dfg,
    extract_cpp_dfg,
    extract_csharp_dfg,
    extract_elixir_dfg,
    extract_go_dfg,
    extract_java_dfg,
    extract_kotlin_dfg,
    extract_lua_dfg,
    extract_php_dfg,
    extract_python_dfg,
    extract_ruby_dfg,
    extract_rust_dfg,
    extract_scala_dfg,
    extract_swift_dfg,
    extract_typescript_dfg,
)
from ..path_utils import _resolve_source


def get_dfg_context(
    source_or_path: str,
    function_name: str,
    language: str = "python",
) -> dict:
    """
    Get data flow analysis for a function.

    Extracts variable references (definitions, updates, uses) and
    def-use chains (dataflow edges) for the specified function.
    """
    source_code, _ = _resolve_source(source_or_path)

    dfg_extractors = {
        "python": extract_python_dfg,
        "typescript": extract_typescript_dfg,
        "javascript": extract_typescript_dfg,
        "go": extract_go_dfg,
        "rust": extract_rust_dfg,
        "java": extract_java_dfg,
        "c": extract_c_dfg,
        "cpp": extract_cpp_dfg,
        "ruby": extract_ruby_dfg,
        "php": extract_php_dfg,
        "kotlin": extract_kotlin_dfg,
        "swift": extract_swift_dfg,
        "csharp": extract_csharp_dfg,
        "scala": extract_scala_dfg,
        "lua": extract_lua_dfg,
        "elixir": extract_elixir_dfg,
    }

    extractor_fn = dfg_extractors.get(language, extract_python_dfg)

    try:
        dfg_info: DFGInfo = extractor_fn(source_code, function_name)
        return dfg_info.to_dict()
    except Exception:
        return {
            "function": function_name,
            "refs": [],
            "edges": [],
            "variables": [],
        }
