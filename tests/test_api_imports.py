import importlib


def test_api_imports_dataclasses() -> None:
    api = importlib.import_module("tldr_swinton.api")
    assert hasattr(api, "FunctionContext")
    assert hasattr(api, "RelevantContext")
