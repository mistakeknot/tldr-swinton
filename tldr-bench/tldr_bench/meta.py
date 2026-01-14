from __future__ import annotations

import platform
from typing import Any


def system_metadata() -> dict[str, Any]:
    return {
        "host_os": platform.system(),
        "host_release": platform.release(),
        "host_arch": platform.machine(),
        "python_version": platform.python_version(),
    }
