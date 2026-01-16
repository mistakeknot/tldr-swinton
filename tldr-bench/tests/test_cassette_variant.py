from types import SimpleNamespace

from tldr_bench.variants import cassette


def test_cassette_build_context_uses_tldrs_cli(monkeypatch):
    calls = {}

    def fake_which(name):
        return "/usr/local/bin/tldrs" if name == "tldrs" else None

    def fake_run(cmd, capture_output, text, env, check):
        calls["cmd"] = cmd
        calls["env"] = env
        return SimpleNamespace(
            stdout="vhs://abc\n# Summary: test\n# Preview:\nline\n",
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(cassette.shutil, "which", fake_which)
    monkeypatch.setattr(cassette.subprocess, "run", fake_run)

    task = {
        "entry": "src/tldr_swinton/engines/symbolkite.py:get_relevant_context",
        "depth": 1,
        "language": "python",
        "budget": 123,
        "context_format": "text",
        "project": ".",
    }

    out = cassette.build_context(task)

    assert out.startswith("vhs://abc")
    assert calls["cmd"][0] == "tldrs"
    assert "--output" in calls["cmd"]
