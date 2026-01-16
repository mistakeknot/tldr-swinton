from pathlib import Path
import json

from tldr_swinton.daemon import cached_context


def test_cached_context_json_uses_contextpack(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("def foo():\n    return 1\n")
    result = cached_context(
        None,
        str(tmp_path),
        "foo",
        "python",
        2,
        "json",
        200,
        False,
    )
    assert result["status"] == "ok"
    payload = json.loads(result["result"])
    assert "slices" in payload
    assert payload["slices"]
