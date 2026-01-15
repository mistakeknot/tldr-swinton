from evals import agent_workflow_eval as awe


def test_build_diff_context_args_includes_compress() -> None:
    args = awe.build_diff_context_args("/tmp/project", "chunk-summary", 2000)
    assert "--compress" in args
    assert "chunk-summary" in args


def test_build_diff_context_args_omits_compress_when_none() -> None:
    args = awe.build_diff_context_args("/tmp/project", None, 2000)
    assert "--compress" not in args


def test_parse_args_defaults_to_no_compress() -> None:
    args = awe.parse_args([])
    assert args.compress is None
    assert args.budget == 2000


def test_parse_args_accepts_compress_and_budget() -> None:
    args = awe.parse_args(["--compress", "chunk-summary", "--budget", "1500"])
    assert args.compress == "chunk-summary"
    assert args.budget == 1500
