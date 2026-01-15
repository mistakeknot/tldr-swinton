from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BenchInstance:
    instance_id: str
    prompt: str
    dataset: str
    repo: str | None = None
    base_commit: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "instance_id": self.instance_id,
            "prompt": self.prompt,
            "dataset": self.dataset,
        }
        if self.repo:
            data["repo"] = self.repo
        if self.base_commit:
            data["base_commit"] = self.base_commit
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data
