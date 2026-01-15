import tldr_swinton


def test_engine_exports_present():
    assert callable(tldr_swinton.engine_get_relevant_context)
    assert callable(tldr_swinton.engine_get_diff_context)
    assert callable(tldr_swinton.engine_get_cfg_context)
    assert callable(tldr_swinton.engine_get_dfg_context)
    assert callable(tldr_swinton.engine_get_pdg_context)
    assert callable(tldr_swinton.engine_get_slice)
