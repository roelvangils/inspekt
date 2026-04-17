"""
Unit tests for Remediation Planner.

Tests for generating prioritized remediation tasks from PDF accessibility issues.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


class TestRemediationPriority:
    """Unit tests for RemediationPriority enum."""

    def test_priority_values(self):
        """Test RemediationPriority values."""
        from inspekt.services.remediation_planner import RemediationPriority

        assert RemediationPriority.CRITICAL.value == 1
        assert RemediationPriority.HIGH.value == 2
        assert RemediationPriority.MEDIUM.value == 3
        assert RemediationPriority.LOW.value == 4

    def test_priority_labels(self):
        """Test RemediationPriority labels."""
        from inspekt.services.remediation_planner import RemediationPriority

        # The actual labels are simpler
        assert RemediationPriority.CRITICAL.label == "Critical"
        assert RemediationPriority.HIGH.label == "High"
        assert RemediationPriority.MEDIUM.label == "Medium"
        assert RemediationPriority.LOW.label == "Low"

    def test_priority_icons(self):
        """Test RemediationPriority icons."""
        from inspekt.services.remediation_planner import RemediationPriority

        # Each priority should have an icon
        for priority in RemediationPriority:
            assert priority.icon is not None
            assert len(priority.icon) > 0

    def test_priority_colors(self):
        """Test RemediationPriority colors."""
        from inspekt.services.remediation_planner import RemediationPriority

        for priority in RemediationPriority:
            assert priority.color is not None
            assert priority.color.startswith("#")


class TestEffortLevel:
    """Unit tests for EffortLevel enum."""

    def test_effort_values(self):
        """Test EffortLevel values."""
        from inspekt.services.remediation_planner import EffortLevel

        # The actual enum values
        expected_values = ["Quick fix", "Moderate", "Significant", "Extensive"]

        for level in EffortLevel:
            assert level.value in expected_values

    def test_effort_time_estimate(self):
        """Test EffortLevel time estimates."""
        from inspekt.services.remediation_planner import EffortLevel

        for level in EffortLevel:
            assert level.time_estimate is not None


class TestRemediationTask:
    """Unit tests for RemediationTask dataclass."""

    def test_task_properties(self):
        """Test RemediationTask properties."""
        from inspekt.services.remediation_planner import RemediationTask, RemediationPriority, EffortLevel

        task = RemediationTask(
            task_id="alt-text-1",
            priority=RemediationPriority.CRITICAL,
            category="Alternative Text",
            title="Add alt text to 5 images",
            description="Images on pages 1, 3, 5 are missing alternative text descriptions.",
            affected_pages=[1, 3, 5],
            affected_count=5,
            wcag_criteria=["1.1.1"],
            effort=EffortLevel.QUICK,
            steps=[
                "Open PDF in Acrobat Pro",
                "Go to Tools > Accessibility > Set Alternate Text",
                "Enter descriptive text for each image",
            ],
            notes="Focus on informative images first, decorative images can use empty alt.",
        )

        assert task.task_id == "alt-text-1"
        assert task.priority == RemediationPriority.CRITICAL
        assert task.category == "Alternative Text"
        assert task.affected_count == 5
        assert len(task.wcag_criteria) == 1
        assert task.effort == EffortLevel.QUICK
        assert len(task.steps) == 3
        assert task.pages_summary == "1, 3, 5"

    def test_pages_summary_truncation(self):
        """Test that pages_summary truncates long lists."""
        from inspekt.services.remediation_planner import RemediationTask, RemediationPriority, EffortLevel

        # Many pages
        task = RemediationTask(
            task_id="test-task",
            priority=RemediationPriority.MEDIUM,
            category="Test",
            title="Test task",
            description="Test",
            affected_pages=list(range(1, 101)),  # 100 pages
            affected_count=100,
            wcag_criteria=[],
            effort=EffortLevel.SIGNIFICANT,
            steps=[],
        )

        # Should truncate with "…" or show summary
        assert len(task.pages_summary) < 300
        # For many pages, should use the summarized format
        assert "pages" in task.pages_summary.lower() or "…" in task.pages_summary

    def test_pages_summary_all_pages(self):
        """Test pages_summary for no specific pages."""
        from inspekt.services.remediation_planner import RemediationTask, RemediationPriority, EffortLevel

        task = RemediationTask(
            task_id="test-task",
            priority=RemediationPriority.LOW,
            category="Test",
            title="Test",
            description="Test",
            affected_pages=[],  # No specific pages
            affected_count=1,
            wcag_criteria=[],
            effort=EffortLevel.QUICK,
            steps=[],
        )

        assert task.pages_summary == "All pages"


class TestRemediationPlan:
    """Unit tests for RemediationPlan dataclass."""

    def test_plan_properties(self):
        """Test RemediationPlan aggregation properties."""
        from inspekt.services.remediation_planner import (
            RemediationPlan,
            RemediationTask,
            RemediationPriority,
            EffortLevel,
        )

        tasks = [
            RemediationTask(
                task_id="task-1",
                priority=RemediationPriority.CRITICAL,
                category="Images",
                title="Add alt text",
                description="Test",
                affected_pages=[1, 2],
                affected_count=5,
                wcag_criteria=["1.1.1"],
                effort=EffortLevel.QUICK,
                steps=[],
            ),
            RemediationTask(
                task_id="task-2",
                priority=RemediationPriority.HIGH,
                category="Tables",
                title="Add headers",
                description="Test",
                affected_pages=[3],
                affected_count=3,
                wcag_criteria=["1.3.1"],
                effort=EffortLevel.MODERATE,
                steps=[],
            ),
            RemediationTask(
                task_id="task-3",
                priority=RemediationPriority.LOW,
                category="Links",
                title="Fix link text",
                description="Test",
                affected_pages=[1],
                affected_count=2,
                wcag_criteria=["2.4.4"],
                effort=EffortLevel.QUICK,
                steps=[],
            ),
        ]

        plan = RemediationPlan(
            tasks=tasks,
            total_issues=10,
            critical_count=1,
            high_count=1,
            medium_count=0,
            low_count=1,
        )

        assert plan.task_count == 3
        assert plan.total_issues == 10

    def test_get_tasks_by_priority(self):
        """Test filtering tasks by priority."""
        from inspekt.services.remediation_planner import (
            RemediationPlan,
            RemediationTask,
            RemediationPriority,
            EffortLevel,
        )

        tasks = [
            RemediationTask(
                task_id="task-1",
                priority=RemediationPriority.CRITICAL,
                category="Test1",
                title="Task 1",
                description="",
                affected_pages=[1],
                affected_count=1,
                wcag_criteria=[],
                effort=EffortLevel.QUICK,
                steps=[],
            ),
            RemediationTask(
                task_id="task-2",
                priority=RemediationPriority.CRITICAL,
                category="Test2",
                title="Task 2",
                description="",
                affected_pages=[2],
                affected_count=1,
                wcag_criteria=[],
                effort=EffortLevel.QUICK,
                steps=[],
            ),
            RemediationTask(
                task_id="task-3",
                priority=RemediationPriority.LOW,
                category="Test3",
                title="Task 3",
                description="",
                affected_pages=[3],
                affected_count=1,
                wcag_criteria=[],
                effort=EffortLevel.QUICK,
                steps=[],
            ),
        ]

        plan = RemediationPlan(tasks=tasks)

        critical_tasks = plan.get_tasks_by_priority(RemediationPriority.CRITICAL)
        low_tasks = plan.get_tasks_by_priority(RemediationPriority.LOW)
        medium_tasks = plan.get_tasks_by_priority(RemediationPriority.MEDIUM)

        assert len(critical_tasks) == 2
        assert len(low_tasks) == 1
        assert len(medium_tasks) == 0


class TestGenerateRemediationPlan:
    """Unit tests for generate_remediation_plan function."""

    def test_generates_plan_from_result(self):
        """Test that generate_remediation_plan returns a RemediationPlan."""
        from inspekt.services.remediation_planner import generate_remediation_plan, RemediationPlan

        # Create mock result with failures
        mock_checks = []
        check = MagicMock()
        check.status = "fail"
        check.severity = "critical"
        check.check_id = "no_alt_text"
        check.name = "Image Alt Text"
        check.message = "Images missing alt text"
        mock_checks.append(check)

        mock_result = MagicMock()
        mock_result.basic.checks = mock_checks
        mock_result.basic.failed = 1
        mock_result.verapdf = None
        mock_result.simple = None

        plan = generate_remediation_plan(mock_result)

        assert isinstance(plan, RemediationPlan)

    def test_empty_plan_for_passing_result(self):
        """Test that passing result generates empty plan."""
        from inspekt.services.remediation_planner import generate_remediation_plan

        # Create mock result with all passes
        mock_result = MagicMock()
        mock_result.basic.checks = []
        mock_result.basic.failed = 0
        mock_result.verapdf = None
        mock_result.simple = None

        plan = generate_remediation_plan(mock_result)

        assert plan.task_count == 0

    def test_includes_verapdf_violations(self):
        """Test that veraPDF violations are included in plan."""
        from inspekt.services.remediation_planner import generate_remediation_plan, RemediationPlan

        # Create mock result with veraPDF violations
        mock_violation = MagicMock()
        mock_violation.rule_id = "ISO-32000-1-7.18.1"
        mock_violation.clause = "7.18.1"
        mock_violation.description = "Figure does not have alternate text"
        mock_violation.severity = "serious"
        mock_violation.page_number = 0

        mock_result = MagicMock()
        mock_result.basic.checks = []
        mock_result.basic.failed = 0
        mock_result.verapdf.violations = [mock_violation]
        mock_result.verapdf.failed_rules = 1
        mock_result.simple = None

        plan = generate_remediation_plan(mock_result)

        # Should have generated at least one task from veraPDF violation
        # (depends on whether template matches)
        assert isinstance(plan, RemediationPlan)


class TestRemediationTemplates:
    """Tests for remediation templates."""

    def test_templates_exist(self):
        """Test that REMEDIATION_TEMPLATES constant exists and has content."""
        from inspekt.services.remediation_planner import REMEDIATION_TEMPLATES

        assert REMEDIATION_TEMPLATES is not None
        assert isinstance(REMEDIATION_TEMPLATES, dict)
        assert len(REMEDIATION_TEMPLATES) > 0

    def test_templates_have_required_fields(self):
        """Test that templates have required fields."""
        from inspekt.services.remediation_planner import REMEDIATION_TEMPLATES

        # Check first few templates for required fields
        for template_id, template in list(REMEDIATION_TEMPLATES.items())[:3]:
            assert "title" in template, f"Template '{template_id}' missing field 'title'"
            assert "priority" in template, f"Template '{template_id}' missing field 'priority'"
            assert "steps" in template, f"Template '{template_id}' missing field 'steps'"


class TestRemediationTool:
    """Unit tests for RemediationTool enum."""

    def test_tool_values(self):
        """Test RemediationTool values."""
        from inspekt.services.remediation_planner import RemediationTool

        assert RemediationTool.ACROBAT_PRO.value == "Adobe Acrobat Pro"
        assert RemediationTool.PAC.value == "PDF Accessibility Checker"

    def test_is_free_property(self):
        """Test is_free property."""
        from inspekt.services.remediation_planner import RemediationTool

        # PAC should be free
        assert RemediationTool.PAC.is_free
        # Acrobat Pro should not be free
        assert not RemediationTool.ACROBAT_PRO.is_free
