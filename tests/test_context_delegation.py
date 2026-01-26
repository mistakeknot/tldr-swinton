"""Tests for recursive context delegation."""

import tempfile
from pathlib import Path

import pytest

from tldr_swinton.modules.core.context_delegation import (
    ContextDelegator,
    IntermediateResult,
    RetrievalPlan,
    RetrievalStep,
    create_delegation_plan,
)


class TestRetrievalStep:
    def test_to_dict(self):
        step = RetrievalStep(
            step_id="s1",
            action="retrieve",
            target="MyClass.method",
            rationale="Primary entry point",
            priority=1,
            estimated_tokens=200,
        )

        d = step.to_dict()

        assert d["step_id"] == "s1"
        assert d["action"] == "retrieve"
        assert d["target"] == "MyClass.method"
        assert d["priority"] == 1

    def test_optional_step(self):
        step = RetrievalStep(
            step_id="s2",
            action="prune",
            target="unused",
            rationale="Remove if not needed",
            priority=5,
            optional=True,
        )

        assert step.optional is True


class TestRetrievalPlan:
    def test_to_dict(self):
        plan = RetrievalPlan(
            task_description="Fix bug in parser",
            steps=[
                RetrievalStep("s1", "retrieve", "target", "reason", 1),
            ],
            total_estimated_tokens=500,
            recommended_budget=800,
            entry_points=["Parser.parse"],
            completion_criteria="Understand the bug",
        )

        d = plan.to_dict()

        assert d["task_description"] == "Fix bug in parser"
        assert len(d["steps"]) == 1
        assert d["total_estimated_tokens"] == 500

    def test_get_next_steps_no_deps(self):
        plan = RetrievalPlan(
            task_description="Test",
            steps=[
                RetrievalStep("s1", "retrieve", "a", "r", 1),
                RetrievalStep("s2", "retrieve", "b", "r", 2),
                RetrievalStep("s3", "retrieve", "c", "r", 3),
            ],
            total_estimated_tokens=600,
            recommended_budget=800,
            entry_points=[],
            completion_criteria="Done",
        )

        next_steps = plan.get_next_steps(completed=set(), max_steps=2)

        assert len(next_steps) == 2
        assert next_steps[0].step_id == "s1"
        assert next_steps[1].step_id == "s2"

    def test_get_next_steps_with_deps(self):
        plan = RetrievalPlan(
            task_description="Test",
            steps=[
                RetrievalStep("s1", "retrieve", "a", "r", 1),
                RetrievalStep("s2", "retrieve", "b", "r", 2, depends_on=["s1"]),
                RetrievalStep("s3", "retrieve", "c", "r", 3, depends_on=["s2"]),
            ],
            total_estimated_tokens=600,
            recommended_budget=800,
            entry_points=[],
            completion_criteria="Done",
        )

        # No steps completed - only s1 available
        next_steps = plan.get_next_steps(completed=set())
        assert len(next_steps) == 1
        assert next_steps[0].step_id == "s1"

        # s1 completed - s2 now available
        next_steps = plan.get_next_steps(completed={"s1"})
        assert len(next_steps) == 1
        assert next_steps[0].step_id == "s2"

    def test_format_for_agent(self):
        plan = RetrievalPlan(
            task_description="Refactor the auth module",
            steps=[
                RetrievalStep("s1", "retrieve", "project_structure", "Initial layout", 1, estimated_tokens=100),
                RetrievalStep("s2", "retrieve", "AuthService", "Main target", 2, depends_on=["s1"]),
            ],
            total_estimated_tokens=300,
            recommended_budget=500,
            entry_points=["AuthService"],
            completion_criteria="Understand auth flow",
        )

        output = plan.format_for_agent()

        assert "# Context Retrieval Plan" in output
        assert "Refactor the auth module" in output
        assert "AuthService" in output
        assert "Step s1: RETRIEVE" in output
        assert "Execution Instructions" in output


class TestContextDelegator:
    def test_create_plan_basic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            delegator = ContextDelegator(Path(tmpdir))

            plan = delegator.create_plan(
                task_description="Understand the parser module",
                budget_tokens=4000,
            )

            assert plan.task_description == "Understand the parser module"
            assert len(plan.steps) > 0
            assert plan.total_estimated_tokens > 0

    def test_create_plan_edit_task(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            delegator = ContextDelegator(Path(tmpdir))

            plan = delegator.create_plan(
                task_description="Fix bug in UserService.validate method",
                budget_tokens=4000,
            )

            # Edit tasks should include callers step
            actions = [s.action for s in plan.steps]
            assert "retrieve" in actions

            # Should extract UserService or validate as entry point
            all_targets = [s.target for s in plan.steps]
            assert any("caller" in t.lower() for t in all_targets) or len(plan.entry_points) > 0

    def test_create_plan_debug_task(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            delegator = ContextDelegator(Path(tmpdir))

            plan = delegator.create_plan(
                task_description="Debug the failing test in auth module",
                budget_tokens=4000,
            )

            assert "debug" in plan.task_description.lower() or "failing" in plan.task_description.lower()
            # Should have error context step
            targets = [s.target for s in plan.steps]
            assert any("error" in t.lower() or "data_flow" in t.lower() for t in targets)

    def test_create_plan_add_task(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            delegator = ContextDelegator(Path(tmpdir))

            plan = delegator.create_plan(
                task_description="Add a new caching layer to the API",
                budget_tokens=4000,
            )

            targets = [s.target for s in plan.steps]
            # Should have similar implementations or integration points
            assert any("similar" in t.lower() or "integration" in t.lower() for t in targets)

    def test_create_plan_with_focus(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            delegator = ContextDelegator(Path(tmpdir))

            plan = delegator.create_plan(
                task_description="Refactor code",
                focus_areas=["src/auth/", "UserService"],
                budget_tokens=4000,
            )

            # Focus areas should be in entry points
            assert "src/auth/" in plan.entry_points or "UserService" in plan.entry_points

    def test_create_plan_with_current_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            delegator = ContextDelegator(Path(tmpdir))

            plan = delegator.create_plan(
                task_description="Continue working on 'parse_config'",
                current_context=["parse_config", "Config"],
                budget_tokens=4000,
            )

            # Symbols in current_context should not be re-retrieved as entry points
            # (they might still be in steps for caller analysis etc.)
            assert plan is not None  # Just verify plan creation works

    def test_extract_entry_points(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            delegator = ContextDelegator(Path(tmpdir))

            entry_points = delegator._extract_entry_points(
                "Fix the UserService.authenticate method in the 'auth_module'",
                focus_areas=[],
            )

            assert "UserService" in entry_points or "authenticate" in entry_points
            assert "auth_module" in entry_points

    def test_suggest_adjustment_low_budget(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            delegator = ContextDelegator(Path(tmpdir))

            plan = delegator.create_plan("test task", budget_tokens=4000)
            completed = [
                IntermediateResult(
                    step_id="s1",
                    success=True,
                    context_added="some code",
                    tokens_used=3900,
                    findings=["found main class"],
                    suggested_next=[],
                )
            ]

            suggestion = delegator.suggest_adjustment(plan, completed, remaining_budget=100)

            assert suggestion["recommendation"] == "prune"
            assert "Low budget" in suggestion["message"]

    def test_suggest_adjustment_continue(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            delegator = ContextDelegator(Path(tmpdir))

            plan = delegator.create_plan("test task", budget_tokens=4000)
            completed = [
                IntermediateResult(
                    step_id="s1",
                    success=True,
                    context_added="some code",
                    tokens_used=500,
                    findings=[],
                    suggested_next=[],
                )
            ]

            suggestion = delegator.suggest_adjustment(plan, completed, remaining_budget=3500)

            assert suggestion["recommendation"] == "continue"


class TestCreateDelegationPlan:
    def test_convenience_function(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            plan = create_delegation_plan(
                project=project,
                task_description="Implement feature X",
                budget_tokens=5000,
            )

            assert isinstance(plan, RetrievalPlan)
            assert plan.task_description == "Implement feature X"
            assert len(plan.steps) > 0
