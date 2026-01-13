import json
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class JsonlLogger:
    path: Path

    def log(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    def log_with_timestamp(self, record: dict[str, Any]) -> None:
        record = dict(record)
        record["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.log(record)
