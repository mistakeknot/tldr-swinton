from __future__ import annotations

from enum import Enum


class AdaptivePolicy(str, Enum):
    """Routing policy applied only when the adaptive condition is active."""

    CURRENT = "current"
    TOOL_ONLY = "tool_only"
    ONE_SHOT = "one_shot"


def parse_adaptive_policy(value: AdaptivePolicy | str) -> AdaptivePolicy:
    if isinstance(value, AdaptivePolicy):
        return value
    try:
        return AdaptivePolicy(value)
    except ValueError as exc:
        choices = ", ".join(policy.value for policy in AdaptivePolicy)
        raise ValueError(
            f"unknown adaptive policy {value!r}; choose from {choices}"
        ) from exc
