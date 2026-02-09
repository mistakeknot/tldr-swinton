"""Integration tests for context_delegation with ProjectIndex."""

from pathlib import Path

import pytest

from tldr_swinton.modules.core.context_delegation import (
    ContextDelegator,
    RetrievalPlan,
    RetrievalStep,
    create_delegation_plan,
)
from tldr_swinton.modules.core.project_index import ProjectIndex


@pytest.fixture
def indexed_project(tmp_path: Path) -> tuple[Path, ProjectIndex]:
    """A project with a built index for delegation tests."""
    (tmp_path / "api.py").write_text(
        "def handle_request(data: str) -> str:\n"
        "    return validate(data)\n"
        "\n"
        "def validate(data: str) -> bool:\n"
        "    return len(data) > 0\n"
    )
    (tmp_path / "service.py").write_text(
        "from api import handle_request\n"
        "\n"
        "class RequestService:\n"
        "    def process(self) -> str:\n"
        "        return handle_request('test')\n"
    )
    idx = ProjectIndex.build(tmp_path)
    return tmp_path, idx


class TestPlanToCandidates:
    def test_resolves_entry_points_via_index(
        self, indexed_project: tuple[Path, ProjectIndex]
    ) -> None:
        """plan_to_candidates should resolve entry point names to real symbols."""
        project, idx = indexed_project
        delegator = ContextDelegator(project)

        plan = delegator.create_plan(
            task_description="Fix the handle_request function",
            focus_areas=["handle_request"],
        )

        candidates = delegator.plan_to_candidates(plan, index=idx)

        # Should have resolved handle_request to its symbol ID
        symbol_ids = [c.symbol_id for c in candidates]
        assert any("handle_request" in sid for sid in symbol_ids)

    def test_candidates_have_signatures(
        self, indexed_project: tuple[Path, ProjectIndex]
    ) -> None:
        """Resolved candidates should carry signature info from the index."""
        project, idx = indexed_project
        delegator = ContextDelegator(project)

        plan = delegator.create_plan(
            task_description="Understand validate function",
            focus_areas=["validate"],
        )

        candidates = delegator.plan_to_candidates(plan, index=idx)

        # Find the validate candidate
        validate_candidates = [c for c in candidates if "validate" in c.symbol_id]
        assert len(validate_candidates) >= 1
        # Should have a signature
        assert validate_candidates[0].signature is not None

    def test_candidates_without_index(self, tmp_path: Path) -> None:
        """Without an index, entry points should be used as-is."""
        delegator = ContextDelegator(tmp_path)

        plan = delegator.create_plan(
            task_description="Look at some_function",
            focus_areas=["some_function"],
        )

        candidates = delegator.plan_to_candidates(plan, index=None)

        symbol_ids = [c.symbol_id for c in candidates]
        assert "some_function" in symbol_ids

    def test_priority_ordering(
        self, indexed_project: tuple[Path, ProjectIndex]
    ) -> None:
        """Earlier entry points should have higher relevance."""
        project, idx = indexed_project
        delegator = ContextDelegator(project)

        plan = delegator.create_plan(
            task_description="Fix handle_request and validate",
            focus_areas=["handle_request", "validate"],
        )

        candidates = delegator.plan_to_candidates(plan, index=idx)

        if len(candidates) >= 2:
            # First entry point should have higher relevance
            assert candidates[0].relevance >= candidates[-1].relevance


class TestCreateDelegationPlan:
    def test_edit_task_includes_caller_retrieval(self, tmp_path: Path) -> None:
        plan = create_delegation_plan(tmp_path, "Fix the process function")
        actions = [s.action for s in plan.steps]
        assert "retrieve" in actions

    def test_debug_task_includes_error_context(self, tmp_path: Path) -> None:
        plan = create_delegation_plan(tmp_path, "Debug the failing test error")
        targets = [s.target for s in plan.steps]
        assert "error_context" in targets

    def test_add_task_includes_similar_implementations(self, tmp_path: Path) -> None:
        plan = create_delegation_plan(tmp_path, "Add a new endpoint for users")
        targets = [s.target for s in plan.steps]
        assert "similar_implementations" in targets

    def test_plan_format_for_agent(self, tmp_path: Path) -> None:
        plan = create_delegation_plan(tmp_path, "Fix the login function")
        formatted = plan.format_for_agent()
        assert "# Context Retrieval Plan" in formatted
        assert "## Entry Points" in formatted
        assert "## Retrieval Steps" in formatted
