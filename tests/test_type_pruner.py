from tldr_swinton.modules.core.contextpack_engine import Candidate
from tldr_swinton.modules.core.type_pruner import (
    group_callers_by_pattern,
    is_self_documenting,
    is_stdlib_or_framework,
    prune_expansion,
)


def test_is_self_documenting_typed() -> None:
    signature = "def foo(x: str) -> bool:"
    code = "def foo(x: str) -> bool:\n    return len(x) > 0\n"
    assert is_self_documenting(signature, code) is True


def test_is_self_documenting_untyped() -> None:
    signature = "def foo(x):"
    code = "def foo(x):\n    return bool(x)\n"
    assert is_self_documenting(signature, code) is False


def test_is_self_documenting_side_effects() -> None:
    signature = "def foo(path: str) -> bool:"
    code = "def foo(path: str) -> bool:\n    open(path)\n    return True\n"
    assert is_self_documenting(signature, code) is False


def test_is_stdlib_json() -> None:
    assert is_stdlib_or_framework("json.dumps") is True


def test_is_stdlib_custom() -> None:
    assert is_stdlib_or_framework("mymodule.func") is False


def test_group_callers_identical_pattern() -> None:
    callers = [
        {"symbol_id": "a.py:caller_a", "signature": "def caller(x: int, y: str) -> None", "code": "pass"},
        {"symbol_id": "b.py:caller_b", "signature": "def caller(x: int, y: str) -> None", "code": "pass"},
        {"symbol_id": "c.py:caller_c", "signature": "def caller(x: int, y: str) -> None", "code": "pass"},
    ]
    groups = group_callers_by_pattern(callers)
    assert len(groups) == 1
    assert groups[0]["count"] == 3


def test_group_callers_different_patterns() -> None:
    callers = [
        {"symbol_id": "a.py:caller_a", "signature": "def caller_a(x: int) -> None", "code": "pass"},
        {"symbol_id": "b.py:caller_b", "signature": "def caller_b(x: int, y: int) -> None", "code": "pass"},
        {"symbol_id": "c.py:caller_c", "signature": "def caller_c() -> None", "code": "pass"},
    ]
    groups = group_callers_by_pattern(callers)
    assert len(groups) == 3
    assert all(group["count"] == 1 for group in groups)


def test_prune_expansion_self_documenting() -> None:
    candidates = [
        Candidate(
            symbol_id="app.py:caller_a",
            relevance=2,
            relevance_label="caller",
            order=0,
            signature="def caller_a(x: str) -> bool",
            code="def caller_a(x: str) -> bool:\n    return x.startswith('a')\n",
        ),
        Candidate(
            symbol_id="app.py:callee",
            relevance=3,
            relevance_label="contains_diff",
            order=1,
            signature="def callee(x: str) -> bool",
            code="def callee(x: str) -> bool:\n    return bool(x)\n",
        ),
    ]
    pruned = prune_expansion(
        candidates,
        callee_signature="def callee(x: str) -> bool",
        callee_code="def callee(x: str) -> bool:\n    return bool(x)\n",
    )
    caller = next(item for item in pruned if item.symbol_id == "app.py:caller_a")
    assert caller.code is None
    assert "self_documenting_callee_signature_only" in (caller.meta or {}).get("pruned_reason", [])


def test_prune_expansion_stdlib_removed() -> None:
    candidates = [
        Candidate(
            symbol_id="json.dumps",
            relevance=2,
            relevance_label="caller",
            order=0,
            signature="def dumps(obj: dict[str, str]) -> str",
            code="return '{}'",
        ),
        Candidate(
            symbol_id="app.py:local_helper",
            relevance=2,
            relevance_label="caller",
            order=1,
            signature="def local_helper(x: int) -> int",
            code="return x + 1",
        ),
    ]
    pruned = prune_expansion(candidates)
    assert len(pruned) == 1
    assert pruned[0].symbol_id == "app.py:local_helper"


def test_prune_expansion_fan_out_capped() -> None:
    candidates = [
        Candidate(
            symbol_id=f"app.py:caller_{i}",
            relevance=2,
            relevance_label="caller",
            order=i,
            signature=f"def caller_{i}(x: int) -> None",
            code=f"def caller_{i}(x: int) -> None:\n    return None\n",
        )
        for i in range(8)
    ]
    pruned = prune_expansion(candidates, max_callers=5)
    assert len(pruned) == 5
    for item in pruned:
        assert "caller_pattern_dedup" in (item.meta or {}).get("pruned_reason", [])
