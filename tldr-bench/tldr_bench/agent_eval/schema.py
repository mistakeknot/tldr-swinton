from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Condition(str, Enum):
    BASELINE = "baseline"
    ADAPTIVE = "adaptive"


class TaskCategory(str, Enum):
    NEGATIVE_CONTROL = "negative_control"
    CROSS_FILE_BUG = "cross_file_bug"
    DIFF_REGRESSION = "diff_regression"
    DEPENDENCY_REFACTOR = "dependency_refactor"


@dataclass(frozen=True)
class TaskSpec:
    id: str
    title: str
    category: TaskCategory
    eligible_for_tldrs: bool
    prompt: str
    mutation_path: Path
    grader_path: Path
    grader_timeout_s: int = 120


@dataclass(frozen=True)
class TraceMetrics:
    model: str | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    tool_calls: int = 0
    tldrs_calls: int = 0
    raw_read_calls: int = 0
    compactions: int = 0
    commands: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TraceMetrics":
        values = dict(data)
        values["commands"] = tuple(values.get("commands", ()))
        values["errors"] = tuple(values.get("errors", ()))
        return cls(**values)


@dataclass(frozen=True)
class GradeResult:
    passed: bool
    exit_code: int
    tests_passed: int | None = None
    tests_total: int | None = None
    stdout: str = ""
    stderr: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GradeResult":
        return cls(**data)


@dataclass(frozen=True)
class RunOutcome:
    task_id: str
    condition: Condition
    repeat: int
    agent_exit_code: int
    agent_timed_out: bool
    elapsed_ms: int
    patch_hash: str
    trace: TraceMetrics
    grade: GradeResult
    contaminated: bool = False
    contamination_reasons: tuple[str, ...] = ()

    @property
    def cell_id(self) -> str:
        return f"{self.task_id}__{self.condition.value}__r{self.repeat:02d}"

    @property
    def success(self) -> bool:
        return self.grade.passed

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["condition"] = self.condition.value
        data["cell_id"] = self.cell_id
        data["success"] = self.success
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunOutcome":
        values = dict(data)
        values.pop("cell_id", None)
        values.pop("success", None)
        values["condition"] = Condition(values["condition"])
        values["trace"] = TraceMetrics.from_dict(values["trace"])
        values["grade"] = GradeResult.from_dict(values["grade"])
        values["contamination_reasons"] = tuple(
            values.get("contamination_reasons", ())
        )
        return cls(**values)


@dataclass(frozen=True)
class GateThresholds:
    max_additional_failures: int = 1
    min_eligible_token_savings: float = 0.20
    max_negative_control_overhead: float = 0.05
    max_latency_regression: float = 0.10
    min_routing_precision: float = 0.80


@dataclass(frozen=True)
class EvaluationReport:
    outcomes: tuple[RunOutcome, ...]
    thresholds: GateThresholds = field(default_factory=GateThresholds)
    verdict: str = "inconclusive"
