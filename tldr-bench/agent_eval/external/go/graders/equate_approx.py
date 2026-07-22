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

func TestAgentEvalEquateApprox(t *testing.T) {
    if !cmp.Equal(1000.0, 1001.0, cmpopts.EquateApprox(0.0001, 2.0)) {
        t.Error("float64 difference inside absolute margin should compare equal")
    }
    if !cmp.Equal(float32(1000), float32(1001), cmpopts.EquateApprox(0.0001, 2.0)) {
        t.Error("float32 difference inside absolute margin should compare equal")
    }
    if !cmp.Equal(1000.0, 1000.5, cmpopts.EquateApprox(0.001, 0.1)) {
        t.Error("difference inside relative fraction should compare equal")
    }
    if cmp.Equal(1000.0, 1010.0, cmpopts.EquateApprox(0.001, 2.0)) {
        t.Error("difference outside both margins must not compare equal")
    }
}
"""
)
try:
    result = subprocess.run(
        ["go", "test", "./cmp/cmpopts", "-run", "^TestAgentEvalEquateApprox$", "-count=1"],
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
