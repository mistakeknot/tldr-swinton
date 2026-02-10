from tldr_swinton.modules.core.incremental_diff import (
    compute_symbol_diff,
    format_incremental,
    is_diff_worthwhile,
)


def test_compute_symbol_diff_basic() -> None:
    old_code = "def greet(name):\n    return f'Hello, {name}'\n"
    new_code = "def greet(name):\n    return f'Hi, {name}'\n"
    diff = compute_symbol_diff(old_code, new_code)
    assert diff is not None
    assert "@@" in diff
    assert "-    return f'Hello, {name}'" in diff
    assert "+    return f'Hi, {name}'" in diff


def test_compute_symbol_diff_identical() -> None:
    code = "def noop():\n    pass\n"
    assert compute_symbol_diff(code, code) is None


def test_is_diff_worthwhile_small_change() -> None:
    old_code = "def f():\n" + "\n".join(f"    x{i} = {i}" for i in range(20)) + "\n"
    new_code = old_code.replace("x10 = 10", "x10 = 11")
    diff = compute_symbol_diff(old_code, new_code)
    assert diff is not None
    assert is_diff_worthwhile(diff, new_code)


def test_is_diff_worthwhile_rewrite() -> None:
    old_code = "\n".join(f"old_{i}" for i in range(30)) + "\n"
    new_code = "\n".join(f"new_{i}" for i in range(30)) + "\n"
    diff = compute_symbol_diff(old_code, new_code)
    assert diff is not None
    assert not is_diff_worthwhile(diff, new_code)


def test_is_diff_worthwhile_many_hunks() -> None:
    diff = "\n".join(["@@ -1 +1 @@", "@@ -2 +2 @@", "@@ -3 +3 @@", "@@ -4 +4 @@", "@@ -5 +5 @@", "@@ -6 +6 @@"])
    assert not is_diff_worthwhile(diff, "x" * 1000)


def test_format_incremental() -> None:
    diff = "@@ -1 +1 @@\n-old\n+new\n"
    out = format_incremental(
        "src/main.py:greet",
        "def greet(name):",
        diff,
        "abcdef0123456789",
    )
    assert "src/main.py:greet" in out
    assert "def greet(name):" in out
    assert "etag:abcdef01" in out
    assert "@@ -1 +1 @@" in out


def test_format_incremental_etag_prefix() -> None:
    out = format_incremental(
        "a.py:f",
        "def f():",
        "@@ -1 +1 @@\n-old\n+new\n",
        "1234567890abcdef",
    )
    assert "etag:12345678" in out
    assert "etag:1234567890" not in out
