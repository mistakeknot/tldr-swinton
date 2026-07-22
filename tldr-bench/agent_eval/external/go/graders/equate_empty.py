from __future__ import annotations

from pathlib import Path
import subprocess
import sys


workspace = Path(sys.argv[1])
test_file = workspace / "cmp/cmpopts/agent_eval_hidden_test.go"
test_file.write_text(
    """package cmpopts_test

import (
    "testing"

    "github.com/google/go-cmp/cmp"
    "github.com/google/go-cmp/cmp/cmpopts"
)

func TestAgentEvalEquateEmpty(t *testing.T) {
    if !cmp.Equal([]int(nil), []int{}, cmpopts.EquateEmpty()) {
        t.Error("nil and empty slices should compare equal")
    }
    if cmp.Equal([]int{1}, []int{}, cmpopts.EquateEmpty()) {
        t.Error("non-empty and empty slices must not compare equal")
    }
    if !cmp.Equal(map[string]int(nil), map[string]int{}, cmpopts.EquateEmpty()) {
        t.Error("nil and empty maps should compare equal")
    }
    if cmp.Equal(map[string]int{"x": 1}, map[string]int{}, cmpopts.EquateEmpty()) {
        t.Error("non-empty and empty maps must not compare equal")
    }
}
"""
)
try:
    result = subprocess.run(
        ["go", "test", "./cmp/cmpopts", "-run", "^TestAgentEvalEquateEmpty$", "-count=1"],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
        timeout=90,
    )
finally:
    test_file.unlink(missing_ok=True)

passed = 4 if result.returncode == 0 else 0
print(f"EVAL_TESTS passed={passed} total=4")
print(result.stdout, end="")
print(result.stderr, end="", file=sys.stderr)
raise SystemExit(result.returncode)
