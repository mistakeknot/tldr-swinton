from tldr_bench.shim.server import run_cli


def test_run_cli_echo():
    result = run_cli("hello", ["/bin/cat"], 5)
    assert result == "hello"
