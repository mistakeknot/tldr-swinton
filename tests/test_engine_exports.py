import tldr_swinton


def test_engine_exports_present():
    assert callable(tldr_swinton.engine_get_relevant_context)
    assert callable(tldr_swinton.engine_get_diff_context)
    assert callable(tldr_swinton.engine_get_cfg_context)
    assert callable(tldr_swinton.engine_get_dfg_context)
    assert callable(tldr_swinton.engine_get_pdg_context)
    assert callable(tldr_swinton.engine_get_slice)


def test_structural_engine_export():
    """Structural search is available if ast-grep-py is installed."""
    try:
        import ast_grep_py  # noqa: F401

        assert callable(tldr_swinton.engine_get_structural_search)
    except ImportError:
        # Optional dependency; export may be missing when not installed.
        pass
