"""Recursive Context Delegation (Self-Managing Context).

This module enables agents to manage their own context incrementally,
rather than doing a single large retrieval upfront. Instead of returning
raw context, it returns a retrieval plan that the agent executes step-by-step.

Key features:
1. Accepts task description + current context
2. Returns retrieval plan (not raw context) agent executes incrementally
3. Suggests pruning/expansion based on intermediate results

Expected impact: 50%+ reduction in wasted retrieval.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
import subprocess
from typing import Any, Literal

from .distill_formatter import DistilledContext, distill_from_candidates


@dataclass
class RetrievalStep:
    """A single step in the retrieval plan."""

    step_id: str
    action: Literal["retrieve", "prune", "expand", "verify"]
    target: str  # Symbol ID, query, or file path
    rationale: str
    priority: int  # 1 = highest
    depends_on: list[str] = field(default_factory=list)
    estimated_tokens: int | None = None
    optional: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action": self.action,
            "target": self.target,
            "rationale": self.rationale,
            "priority": self.priority,
            "depends_on": self.depends_on,
            "estimated_tokens": self.estimated_tokens,
            "optional": self.optional,
        }


@dataclass
class RetrievalPlan:
    """Complete plan for incremental context retrieval."""

    task_description: str
    steps: list[RetrievalStep]
    total_estimated_tokens: int
    recommended_budget: int
    entry_points: list[str]
    completion_criteria: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_description": self.task_description,
            "steps": [s.to_dict() for s in self.steps],
            "total_estimated_tokens": self.total_estimated_tokens,
            "recommended_budget": self.recommended_budget,
            "entry_points": self.entry_points,
            "completion_criteria": self.completion_criteria,
        }

    def get_next_steps(
        self, completed: set[str], max_steps: int = 3
    ) -> list[RetrievalStep]:
        """Get next steps to execute based on completed steps."""
        available = []
        for step in self.steps:
            if step.step_id in completed:
                continue
            # Check dependencies
            if all(dep in completed for dep in step.depends_on):
                available.append(step)

        # Sort by priority
        available.sort(key=lambda s: s.priority)
        return available[:max_steps]

    def format_for_agent(self) -> str:
        """Format the plan in a way agents can easily parse and execute."""
        lines = [
            "# Context Retrieval Plan",
            "",
            f"**Task**: {self.task_description}",
            f"**Estimated tokens**: {self.total_estimated_tokens}",
            f"**Recommended budget**: {self.recommended_budget}",
            "",
            "## Entry Points",
        ]

        for ep in self.entry_points:
            lines.append(f"- `{ep}`")

        lines.extend(["", "## Retrieval Steps", ""])

        for step in sorted(self.steps, key=lambda s: s.priority):
            optional_tag = " (optional)" if step.optional else ""
            deps = f" [after: {', '.join(step.depends_on)}]" if step.depends_on else ""
            tokens = f" (~{step.estimated_tokens} tokens)" if step.estimated_tokens else ""

            lines.append(f"### Step {step.step_id}: {step.action.upper()}{optional_tag}")
            lines.append(f"Target: `{step.target}`{tokens}")
            lines.append(f"Rationale: {step.rationale}{deps}")
            lines.append("")

        lines.extend([
            "## Completion Criteria",
            self.completion_criteria,
            "",
            "## Execution Instructions",
            "1. Execute steps in priority order",
            "2. After each step, evaluate if you have enough context",
            "3. Skip optional steps if budget is tight",
            "4. Stop when completion criteria are met",
        ])

        return "\n".join(lines)


@dataclass
class IntermediateResult:
    """Result from executing a retrieval step."""

    step_id: str
    success: bool
    context_added: str | None
    tokens_used: int
    findings: list[str]
    suggested_next: list[str]


class ContextDelegator:
    """Creates and manages context retrieval plans."""

    # Token estimates per action type
    TOKEN_ESTIMATES = {
        "symbol_context": 200,
        "file_structure": 100,
        "call_graph": 150,
        "type_info": 80,
        "import_graph": 60,
    }

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root).resolve()

    def create_plan(
        self,
        task_description: str,
        current_context: list[str] | None = None,
        budget_tokens: int = 8000,
        focus_areas: list[str] | None = None,
    ) -> RetrievalPlan:
        """Create a retrieval plan for the given task.

        Args:
            task_description: What the agent is trying to accomplish
            current_context: Symbols already in context (to avoid re-retrieval)
            budget_tokens: Maximum tokens to use
            focus_areas: Optional specific areas to focus on (files, modules)

        Returns:
            RetrievalPlan with ordered steps
        """
        current_context = current_context or []
        focus_areas = focus_areas or []

        steps: list[RetrievalStep] = []
        step_counter = 1

        # Parse task to identify key actions
        task_lower = task_description.lower()
        is_edit_task = any(w in task_lower for w in ["edit", "fix", "modify", "refactor", "update", "change"])
        is_understand_task = any(w in task_lower for w in ["understand", "explain", "how does", "what is"])
        is_debug_task = any(w in task_lower for w in ["debug", "error", "bug", "issue", "failing"])
        is_add_task = any(w in task_lower for w in ["add", "create", "implement", "new"])

        # Extract potential entry points from task
        entry_points = self._extract_entry_points(task_description, focus_areas)

        # Step 1: Always start with structure understanding
        steps.append(
            RetrievalStep(
                step_id=f"s{step_counter}",
                action="retrieve",
                target="project_structure",
                rationale="Understand project layout before diving into specifics",
                priority=1,
                estimated_tokens=100,
            )
        )
        step_counter += 1

        # Step 2: Get entry point context
        for i, entry in enumerate(entry_points[:3]):
            if entry not in current_context:
                steps.append(
                    RetrievalStep(
                        step_id=f"s{step_counter}",
                        action="retrieve",
                        target=entry,
                        rationale=f"Primary entry point #{i+1} for task",
                        priority=2,
                        depends_on=["s1"],
                        estimated_tokens=self.TOKEN_ESTIMATES["symbol_context"],
                    )
                )
                step_counter += 1

        # Step 3: Task-specific steps
        if is_edit_task:
            steps.append(
                RetrievalStep(
                    step_id=f"s{step_counter}",
                    action="retrieve",
                    target="callers_of_target",
                    rationale="Understand what depends on code being edited",
                    priority=3,
                    depends_on=[s.step_id for s in steps if s.priority == 2],
                    estimated_tokens=self.TOKEN_ESTIMATES["call_graph"],
                )
            )
            step_counter += 1

            steps.append(
                RetrievalStep(
                    step_id=f"s{step_counter}",
                    action="verify",
                    target="type_compatibility",
                    rationale="Verify edit won't break type contracts",
                    priority=4,
                    depends_on=[f"s{step_counter-1}"],
                    estimated_tokens=self.TOKEN_ESTIMATES["type_info"],
                    optional=True,
                )
            )
            step_counter += 1

        elif is_debug_task:
            steps.append(
                RetrievalStep(
                    step_id=f"s{step_counter}",
                    action="retrieve",
                    target="error_context",
                    rationale="Get context around error location",
                    priority=3,
                    depends_on=[s.step_id for s in steps if s.priority == 2],
                    estimated_tokens=self.TOKEN_ESTIMATES["symbol_context"] * 2,
                )
            )
            step_counter += 1

            steps.append(
                RetrievalStep(
                    step_id=f"s{step_counter}",
                    action="retrieve",
                    target="data_flow_to_error",
                    rationale="Trace data flow to understand error cause",
                    priority=4,
                    depends_on=[f"s{step_counter-1}"],
                    estimated_tokens=self.TOKEN_ESTIMATES["call_graph"],
                )
            )
            step_counter += 1

        elif is_add_task:
            steps.append(
                RetrievalStep(
                    step_id=f"s{step_counter}",
                    action="retrieve",
                    target="similar_implementations",
                    rationale="Find similar existing patterns to follow",
                    priority=3,
                    depends_on=["s1"],
                    estimated_tokens=self.TOKEN_ESTIMATES["symbol_context"] * 2,
                )
            )
            step_counter += 1

            steps.append(
                RetrievalStep(
                    step_id=f"s{step_counter}",
                    action="retrieve",
                    target="integration_points",
                    rationale="Identify where new code needs to integrate",
                    priority=4,
                    depends_on=[f"s{step_counter-1}"],
                    estimated_tokens=self.TOKEN_ESTIMATES["import_graph"],
                )
            )
            step_counter += 1

        # Step 4: Optional expansion/pruning
        steps.append(
            RetrievalStep(
                step_id=f"s{step_counter}",
                action="expand",
                target="related_context",
                rationale="Expand context if initial retrieval insufficient",
                priority=5,
                depends_on=[s.step_id for s in steps if s.priority <= 4],
                estimated_tokens=self.TOKEN_ESTIMATES["symbol_context"],
                optional=True,
            )
        )
        step_counter += 1

        steps.append(
            RetrievalStep(
                step_id=f"s{step_counter}",
                action="prune",
                target="unused_context",
                rationale="Remove context that turned out to be irrelevant",
                priority=6,
                depends_on=[f"s{step_counter-1}"],
                estimated_tokens=0,
                optional=True,
            )
        )

        # Estimate total tokens
        total_tokens = sum(s.estimated_tokens or 0 for s in steps if not s.optional)

        # Generate completion criteria
        if is_edit_task:
            criteria = "Have enough context to: (1) understand target code, (2) know all callers, (3) verify type compatibility"
        elif is_debug_task:
            criteria = "Have enough context to: (1) see error location, (2) trace data flow, (3) identify root cause"
        elif is_add_task:
            criteria = "Have enough context to: (1) follow existing patterns, (2) know integration points, (3) avoid conflicts"
        else:
            criteria = "Have enough context to fully understand the relevant code paths"

        return RetrievalPlan(
            task_description=task_description,
            steps=steps,
            total_estimated_tokens=total_tokens,
            recommended_budget=min(budget_tokens, total_tokens + 500),
            entry_points=entry_points,
            completion_criteria=criteria,
        )

    def distill(
        self,
        project_root: str | Path,
        task: str,
        budget: int = 1500,
        session_id: str | None = None,
        language: str | None = None,
    ) -> DistilledContext:
        from .api import get_diff_context, get_symbol_context_pack
        from .contextpack_engine import Candidate

        lang = language or "python"
        project_path = Path(project_root).resolve()
        plan = self.create_plan(task)
        all_candidates: list[Candidate] = []

        def _is_git_repo(path: Path) -> bool:
            try:
                result = subprocess.run(
                    ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
                    text=True,
                    capture_output=True,
                )
                return result.returncode == 0
            except Exception:
                return False

        def _to_lines(raw: Any) -> tuple[int, int] | None:
            if isinstance(raw, tuple) and len(raw) == 2:
                return int(raw[0]), int(raw[1])
            if isinstance(raw, list) and len(raw) >= 2:
                return int(raw[0]), int(raw[1])
            return None

        def _relevance(label: str | None, fallback: int = 1) -> int:
            if label is None:
                return fallback
            if label.startswith("depth_"):
                try:
                    depth = int(label.split("_", 1)[1])
                    return max(1, 5 - depth)
                except Exception:
                    return fallback
            mapping = {
                "contains_diff": 5,
                "entry_point": 5,
                "caller": 4,
                "callee": 3,
                "adjacent": 2,
            }
            return mapping.get(label, fallback)

        def _pack_to_candidates(pack: Any, start_order: int) -> list[Candidate]:
            result: list[Candidate] = []
            slices: list[Any]
            if isinstance(pack, dict):
                slices = list(pack.get("slices", []))
            else:
                slices = list(getattr(pack, "slices", []) or [])

            for idx, item in enumerate(slices):
                if isinstance(item, dict):
                    symbol_id = str(item.get("id", ""))
                    label = item.get("relevance")
                    signature = item.get("signature")
                    code = item.get("code")
                    lines = _to_lines(item.get("lines"))
                    meta = {
                        key: value
                        for key, value in item.items()
                        if key not in {"id", "relevance", "signature", "code", "lines"}
                    }
                else:
                    symbol_id = str(getattr(item, "id", ""))
                    label = getattr(item, "relevance", None)
                    signature = getattr(item, "signature", None)
                    code = getattr(item, "code", None)
                    lines = _to_lines(getattr(item, "lines", None))
                    raw_meta = getattr(item, "meta", None)
                    meta = raw_meta if isinstance(raw_meta, dict) else {}

                if not symbol_id:
                    continue

                result.append(
                    Candidate(
                        symbol_id=symbol_id,
                        relevance=_relevance(str(label) if label is not None else None),
                        relevance_label=str(label) if label is not None else None,
                        order=start_order + idx,
                        signature=signature,
                        code=code,
                        lines=lines,
                        meta=meta or None,
                    )
                )
            return result

        if _is_git_repo(project_path):
            try:
                if session_id:
                    from .engines.delta import get_diff_context_with_delta

                    diff_pack = get_diff_context_with_delta(
                        project_path,
                        session_id,
                        budget_tokens=max(500, budget),
                        language=lang,
                    )
                else:
                    diff_pack = get_diff_context(
                        project_path,
                        budget_tokens=max(500, budget),
                        language=lang,
                    )
                all_candidates.extend(_pack_to_candidates(diff_pack, len(all_candidates)))
            except Exception:
                pass

        symbol_budget = max(200, budget // max(1, len(plan.entry_points)))
        for entry in plan.entry_points:
            try:
                if session_id:
                    from .engines.delta import get_context_pack_with_delta

                    symbol_pack = get_context_pack_with_delta(
                        str(project_path),
                        entry,
                        session_id,
                        depth=2,
                        language=lang,
                        budget_tokens=symbol_budget,
                    )
                else:
                    symbol_pack = get_symbol_context_pack(
                        project_path,
                        entry,
                        depth=2,
                        language=lang,
                        budget_tokens=symbol_budget,
                    )
                all_candidates.extend(_pack_to_candidates(symbol_pack, len(all_candidates)))
            except Exception:
                continue

        deduped: dict[str, Candidate] = {}
        for candidate in all_candidates:
            existing = deduped.get(candidate.symbol_id)
            if existing is None:
                deduped[candidate.symbol_id] = candidate
                continue

            existing_meta = existing.meta if isinstance(existing.meta, dict) else {}
            candidate_meta = candidate.meta if isinstance(candidate.meta, dict) else {}
            merged_meta = {**existing_meta, **candidate_meta} or None

            prefer_candidate = (
                candidate.relevance,
                1 if candidate.code else 0,
                1 if candidate.signature else 0,
            ) > (
                existing.relevance,
                1 if existing.code else 0,
                1 if existing.signature else 0,
            )

            preferred = candidate if prefer_candidate else existing
            alternate = existing if prefer_candidate else candidate

            deduped[candidate.symbol_id] = Candidate(
                symbol_id=preferred.symbol_id,
                relevance=max(existing.relevance, candidate.relevance),
                relevance_label=preferred.relevance_label or alternate.relevance_label,
                order=min(existing.order, candidate.order),
                signature=preferred.signature or alternate.signature,
                code=preferred.code or alternate.code,
                lines=preferred.lines or alternate.lines,
                meta=merged_meta,
            )

        merged_candidates = sorted(
            deduped.values(),
            key=lambda c: (-c.relevance, c.order, c.symbol_id),
        )
        return distill_from_candidates(merged_candidates, task, budget=budget)

    def _extract_entry_points(
        self, task_description: str, focus_areas: list[str]
    ) -> list[str]:
        """Extract likely entry points from task description."""
        entry_points = list(focus_areas)

        # Simple heuristic: look for quoted names or CamelCase
        import re

        # Quoted strings
        quoted = re.findall(r"['\"`]([^'\"`]+)['\"`]", task_description)
        entry_points.extend(quoted)

        # CamelCase words
        camel = re.findall(r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b", task_description)
        entry_points.extend(camel)

        # snake_case function names
        snake = re.findall(r"\b([a-z][a-z0-9_]+(?:_[a-z0-9]+)+)\b", task_description)
        entry_points.extend(snake)

        return list(dict.fromkeys(entry_points))[:5]  # Dedupe, limit to 5

    def suggest_adjustment(
        self,
        plan: RetrievalPlan,
        completed_steps: list[IntermediateResult],
        remaining_budget: int,
    ) -> dict[str, Any]:
        """Suggest adjustments based on intermediate results.

        Args:
            plan: Original retrieval plan
            completed_steps: Results from completed steps
            remaining_budget: Remaining token budget

        Returns:
            Dict with suggested adjustments
        """
        completed_ids = {r.step_id for r in completed_steps}
        total_tokens_used = sum(r.tokens_used for r in completed_steps)

        # Check if we found what we needed
        all_successful = all(r.success for r in completed_steps)

        # Collect suggested next steps from results
        suggested_from_results = []
        for result in completed_steps:
            suggested_from_results.extend(result.suggested_next)

        suggestions: dict[str, Any] = {
            "tokens_used": total_tokens_used,
            "remaining_budget": remaining_budget,
            "completed_steps": len(completed_steps),
            "all_successful": all_successful,
        }

        if remaining_budget < 200:
            suggestions["recommendation"] = "prune"
            suggestions["message"] = "Low budget remaining. Prune unused context and stop."
            suggestions["next_steps"] = []
        elif not all_successful:
            suggestions["recommendation"] = "retry_or_expand"
            failed = [r for r in completed_steps if not r.success]
            suggestions["message"] = f"{len(failed)} steps failed. Consider alternative approaches."
            suggestions["next_steps"] = suggested_from_results[:2]
        else:
            next_steps = plan.get_next_steps(completed_ids, max_steps=2)
            if next_steps:
                suggestions["recommendation"] = "continue"
                suggestions["message"] = "Continue with next steps in plan."
                suggestions["next_steps"] = [s.step_id for s in next_steps]
            else:
                suggestions["recommendation"] = "complete"
                suggestions["message"] = "Plan complete. Evaluate if you have enough context."
                suggestions["next_steps"] = []

        return suggestions


    def plan_to_candidates(
        self,
        plan: RetrievalPlan,
        index: "ProjectIndex | None" = None,
    ) -> "list[Candidate]":
        """Convert a retrieval plan's entry points into resolved Candidates.

        Uses the shared ProjectIndex to resolve entry point names to
        actual symbol IDs, then builds Candidate objects suitable for
        ContextPackEngine.

        Args:
            plan: A RetrievalPlan with entry_points
            index: Optional ProjectIndex for symbol resolution

        Returns:
            List of Candidate objects for the entry points
        """
        from .contextpack_engine import Candidate

        candidates: list[Candidate] = []

        for priority, entry in enumerate(plan.entry_points):
            resolved_ids = [entry]  # Default: use as-is

            if index is not None:
                resolved, _ = index.resolve_entry_symbols(entry, allow_ambiguous=True)
                if resolved:
                    resolved_ids = resolved

            for symbol_id in resolved_ids:
                signature = None
                lines = None
                if index is not None:
                    func_info = index.symbol_index.get(symbol_id)
                    if func_info:
                        signature = index.signature_overrides.get(
                            symbol_id, func_info.signature()
                        )
                        lines = (func_info.line_number, func_info.line_number)

                candidates.append(
                    Candidate(
                        symbol_id=symbol_id,
                        relevance=max(1, len(plan.entry_points) - priority),
                        relevance_label="entry_point",
                        order=priority,
                        signature=signature,
                        lines=lines,
                    )
                )

        return candidates


def create_delegation_plan(
    project: str | Path,
    task_description: str,
    current_context: list[str] | None = None,
    budget_tokens: int = 8000,
    focus_areas: list[str] | None = None,
) -> RetrievalPlan:
    """Convenience function to create a retrieval plan.

    Args:
        project: Project root path
        task_description: What the agent is trying to accomplish
        current_context: Symbols already retrieved
        budget_tokens: Maximum tokens to use
        focus_areas: Optional specific areas to focus on

    Returns:
        RetrievalPlan with ordered steps
    """
    delegator = ContextDelegator(Path(project))
    return delegator.create_plan(
        task_description=task_description,
        current_context=current_context,
        budget_tokens=budget_tokens,
        focus_areas=focus_areas,
    )
