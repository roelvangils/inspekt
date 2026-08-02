"""
Unit tests for the accessibility HTML report generator and enriched data builder.

Tests _build_enriched_report_data() from accessibility.py
and generate_a11y_report_html() from a11y_report.py.
"""

import json

import pytest

from inspekt.app.cli.accessibility import (
    _build_enriched_report_data,
    _extract_engine_rule_details,
)
from inspekt.services.a11y_report import (
    _esc,
    _format_level,
    generate_a11y_report_html,
)

# ── Fixtures ──────────────────────────────────────────

@pytest.fixture
def axe_engine_results():
    """Minimal axe-core engine results with violations and passes."""
    return {
        "axe": {
            "violations": [
                {
                    "id": "image-alt",
                    "impact": "critical",
                    "description": "Images must have alternate text",
                    "helpUrl": "https://dequeuniversity.com/rules/axe/4.10/image-alt",
                    "nodes": [
                        {
                            "target": ["img.hero"],
                            "html": '<img class="hero" src="photo.jpg">',
                            "failureSummary": "Element does not have an alt attribute",
                        }
                    ],
                    "nodeCount": 1,
                    "tags": ["wcag2a", "wcag111"],
                },
                {
                    "id": "color-contrast",
                    "impact": "serious",
                    "description": "Elements must have sufficient color contrast",
                    "helpUrl": "https://dequeuniversity.com/rules/axe/4.10/color-contrast",
                    "nodes": [
                        {"target": [".text"], "html": "<p>low contrast</p>", "failureSummary": "Ratio 2.5:1"},
                        {"target": [".link"], "html": "<a>link</a>", "failureSummary": "Ratio 3.1:1"},
                    ],
                    "nodeCount": 2,
                    "tags": ["wcag2aa", "wcag143"],
                },
            ],
            "passes": [
                {"id": "html-has-lang", "description": "html has lang", "nodes": [{}], "nodeCount": 1},
            ],
            "incomplete": [
                {"id": "aria-allowed-attr", "description": "Check aria", "nodes": [{}], "nodeCount": 1, "tags": ["wcag2a", "wcag412"]},
            ],
        }
    }


@pytest.fixture
def multi_engine_results(axe_engine_results):
    """Multi-engine results with axe and eac."""
    results = dict(axe_engine_results)
    results["eac"] = {
        "issues": [
            {"ruleId": "img_alt_valid", "level": "violation", "message": "Image alt is empty", "snippet": "<img>", "path": {"dom": "html > body > main > img"}},
            {"ruleId": "img_alt_valid", "level": "violation", "message": "Image alt is empty", "snippet": "<img>", "path": {"dom": "html > body > aside > img"}},
            {"ruleId": "aria_role_valid", "level": "pass", "message": "ARIA role is valid"},
        ],
    }
    return results


@pytest.fixture
def consolidated_single():
    """Consolidated results for single engine."""
    return {
        "1.1.1": {"axe_status": "violation", "axe_count": 1, "axe_impact": "critical"},
        "1.4.3": {"axe_status": "violation", "axe_count": 2, "axe_impact": "serious"},
        "3.1.1": {"axe_status": "pass", "axe_count": 0, "axe_impact": ""},
    }


@pytest.fixture
def consolidated_multi():
    """Consolidated results for multiple engines with disagreements."""
    return {
        "1.1.1": {
            "axe_status": "violation", "axe_count": 1, "axe_impact": "critical",
            "eac_status": "violation", "eac_count": 2, "eac_impact": "violation",
        },
        "1.4.3": {
            "axe_status": "violation", "axe_count": 2, "axe_impact": "serious",
            "eac_status": "pass", "eac_count": 0, "eac_impact": "",
        },
        "3.1.1": {
            "axe_status": "pass", "axe_count": 0, "axe_impact": "",
            "eac_status": "pass", "eac_count": 0, "eac_impact": "",
        },
    }


@pytest.fixture
def versions():
    return {"axe": "4.10.2", "eac": "3.1.0"}


# ── _extract_engine_rule_details Tests ────────────────

class TestExtractEngineRuleDetails:
    """Tests for _extract_engine_rule_details()."""

    def test_axe_violations_extracted(self, axe_engine_results):
        details = _extract_engine_rule_details(axe_engine_results, ["axe"])
        axe = details["axe"]

        assert len(axe["violations"]) == 2
        assert axe["violations"][0]["rule_id"] == "image-alt"
        assert axe["violations"][0]["impact"] == "critical"
        assert axe["violations"][0]["count"] == 1
        assert len(axe["violations"][0]["nodes"]) == 1

    def test_axe_passes_extracted(self, axe_engine_results):
        details = _extract_engine_rule_details(axe_engine_results, ["axe"])
        assert len(details["axe"]["passes"]) == 1
        assert details["axe"]["passes"][0]["rule_id"] == "html-has-lang"

    def test_axe_incomplete_extracted(self, axe_engine_results):
        details = _extract_engine_rule_details(axe_engine_results, ["axe"])
        assert len(details["axe"]["incomplete"]) == 1

    def test_axe_impact_summary(self, axe_engine_results):
        details = _extract_engine_rule_details(axe_engine_results, ["axe"])
        impact = details["axe"]["impact_summary"]
        assert impact["critical"] == 1
        assert impact["serious"] == 2

    def test_eac_violations_grouped(self, multi_engine_results):
        details = _extract_engine_rule_details(multi_engine_results, ["eac"])
        eac = details["eac"]
        assert len(eac["violations"]) == 1  # Grouped by rule
        assert eac["violations"][0]["rule_id"] == "img_alt_valid"
        assert eac["violations"][0]["count"] == 2

    def test_eac_path_as_string(self):
        """EAC path field can be a plain string instead of a dict."""
        results = {
            "eac": {
                "issues": [
                    {"ruleId": "img_alt", "level": "violation", "message": "Missing alt", "snippet": "<img>", "path": "/html/body/img"},
                ],
            }
        }
        details = _extract_engine_rule_details(results, ["eac"])
        eac = details["eac"]
        assert len(eac["violations"]) == 1
        # Should not crash, selector extracted from string path
        assert eac["violations"][0]["nodes"][0]["selector"] != ""

    def test_error_engine_captured(self):
        results = {"axe": {"error": "Timeout after 60s"}}
        details = _extract_engine_rule_details(results, ["axe"])
        assert details["axe"]["error"] == "Timeout after 60s"

    def test_empty_results(self):
        results = {"axe": {"violations": [], "passes": [], "incomplete": []}}
        details = _extract_engine_rule_details(results, ["axe"])
        assert details["axe"]["violations"] == []
        assert details["axe"]["passes"] == []

    def test_node_cap_at_10(self):
        """Nodes should be capped at 10 per rule."""
        violations = [{
            "id": "test-rule",
            "impact": "minor",
            "description": "test",
            "nodes": [{"target": [f"el-{i}"], "html": f"<div>{i}</div>", "failureSummary": ""} for i in range(20)],
            "nodeCount": 20,
        }]
        results = {"axe": {"violations": violations, "passes": [], "incomplete": []}}
        details = _extract_engine_rule_details(results, ["axe"])
        assert len(details["axe"]["violations"][0]["nodes"]) == 10


# ── _build_enriched_report_data Tests ────────────────

class TestBuildEnrichedReportData:
    """Tests for _build_enriched_report_data()."""

    def test_basic_structure(self, axe_engine_results, consolidated_single, versions):
        data = _build_enriched_report_data(
            url="https://example.com",
            level="21aa",
            engine_list=["axe"],
            engine_results=axe_engine_results,
            consolidated=consolidated_single,
            versions=versions,
        )

        assert data["url"] == "https://example.com"
        assert data["level"] == "21aa"
        assert "timestamp" in data
        assert data["execution_order"] == ["axe"]

    def test_engines_enriched(self, axe_engine_results, consolidated_single, versions):
        data = _build_enriched_report_data(
            url="https://example.com",
            level="21aa",
            engine_list=["axe"],
            engine_results=axe_engine_results,
            consolidated=consolidated_single,
            versions=versions,
        )

        axe = data["engines"]["axe"]
        assert axe["name"] == "Axe-core"
        assert axe["abbr"] == "AXE"
        assert axe["version"] == "4.10.2"
        assert "passes" in axe
        assert "incomplete" in axe
        assert "impact_summary" in axe

    def test_consolidated_enriched(self, axe_engine_results, consolidated_single, versions):
        data = _build_enriched_report_data(
            url="https://example.com",
            level="21aa",
            engine_list=["axe"],
            engine_results=axe_engine_results,
            consolidated=consolidated_single,
            versions=versions,
        )

        sc_111 = data["consolidated"]["1.1.1"]
        assert sc_111["description"] == "Non-text Content"
        assert sc_111["conformance_level"] == "A"
        assert sc_111["wcag_version"] == "2.0"
        # Original fields preserved
        assert sc_111["axe_status"] == "violation"
        assert sc_111["axe_count"] == 1

    def test_analysis_section(self, multi_engine_results, consolidated_multi, versions):
        data = _build_enriched_report_data(
            url="https://example.com",
            level="21aa",
            engine_list=["axe", "eac"],
            engine_results=multi_engine_results,
            consolidated=consolidated_multi,
            versions=versions,
        )

        analysis = data["analysis"]
        assert analysis["total_criteria_with_issues"] == 2
        assert analysis["total_criteria_evaluated"] == 3

    def test_disagreements_detected(self, multi_engine_results, consolidated_multi, versions):
        data = _build_enriched_report_data(
            url="https://example.com",
            level="21aa",
            engine_list=["axe", "eac"],
            engine_results=multi_engine_results,
            consolidated=consolidated_multi,
            versions=versions,
        )

        disagreements = data["analysis"]["disagreements"]
        assert len(disagreements) == 1
        assert disagreements[0]["sc"] == "1.4.3"
        assert len(disagreements[0]["failing_engines"]) == 1
        assert disagreements[0]["failing_engines"][0]["engine"] == "axe"

    def test_engine_details_included(self, axe_engine_results, consolidated_single, versions):
        data = _build_enriched_report_data(
            url="https://example.com",
            level="21aa",
            engine_list=["axe"],
            engine_results=axe_engine_results,
            consolidated=consolidated_single,
            versions=versions,
        )

        assert "engine_details" in data
        assert "axe" in data["engine_details"]
        assert len(data["engine_details"]["axe"]["violations"]) == 2

    def test_recommendations_included(self, axe_engine_results, consolidated_single, versions):
        data = _build_enriched_report_data(
            url="https://example.com",
            level="21aa",
            engine_list=["axe"],
            engine_results=axe_engine_results,
            consolidated=consolidated_single,
            versions=versions,
            include_recommendations=True,
        )

        assert "recommendations" in data
        assert "total" in data["recommendations"]

    def test_recommendations_excluded_by_default(self, axe_engine_results, consolidated_single, versions):
        data = _build_enriched_report_data(
            url="https://example.com",
            level="21aa",
            engine_list=["axe"],
            engine_results=axe_engine_results,
            consolidated=consolidated_single,
            versions=versions,
        )

        assert "recommendations" not in data

    def test_json_serializable(self, axe_engine_results, consolidated_single, versions):
        """Enriched data must be JSON serializable."""
        data = _build_enriched_report_data(
            url="https://example.com",
            level="21aa",
            engine_list=["axe"],
            engine_results=axe_engine_results,
            consolidated=consolidated_single,
            versions=versions,
            include_recommendations=True,
        )

        # This should not raise
        json_str = json.dumps(data, indent=2)
        parsed = json.loads(json_str)
        assert parsed["url"] == "https://example.com"


# ── HTML Report Generator Tests ──────────────────────

class TestGenerateA11yReportHtml:
    """Tests for generate_a11y_report_html()."""

    def _make_enriched_data(self, **overrides):
        """Create minimal enriched data for testing."""
        base = {
            "url": "https://example.com",
            "timestamp": "2025-01-01T00:00:00Z",
            "level": "21aa",
            "engines": {
                "axe": {
                    "name": "Axe-core",
                    "abbr": "AXE",
                    "version": "4.10.2",
                    "violations": 3,
                    "passes": 10,
                    "incomplete": 1,
                    "error": None,
                    "impact_summary": {"critical": 1, "serious": 2, "moderate": 0, "minor": 0},
                }
            },
            "execution_order": ["axe"],
            "consolidated": {
                "1.1.1": {
                    "axe_status": "violation",
                    "axe_count": 1,
                    "axe_impact": "critical",
                    "description": "Non-text Content",
                    "conformance_level": "A",
                    "wcag_version": "2.0",
                },
            },
            "analysis": {
                "total_criteria_with_issues": 1,
                "agreement_percentage": 100,
                "total_criteria_evaluated": 1,
                "full_agreement_count": 1,
                "disagreements": [],
                "disparities": [],
            },
            "engine_details": {
                "axe": {
                    "violations": [
                        {
                            "rule_id": "image-alt",
                            "impact": "critical",
                            "count": 1,
                            "description": "Images must have alternate text",
                            "help_url": "https://dequeuniversity.com/rules/axe/4.10/image-alt",
                            "nodes": [{"selector": "img.hero", "html": "<img>", "failure_summary": "No alt"}],
                        }
                    ],
                    "passes": [],
                    "incomplete": [],
                    "impact_summary": {"critical": 1, "serious": 0, "moderate": 0, "minor": 0},
                }
            },
        }
        base.update(overrides)
        return base

    def test_returns_html_string(self):
        html = generate_a11y_report_html(self._make_enriched_data())
        assert isinstance(html, str)
        assert html.startswith("<!DOCTYPE html>")

    def test_contains_url(self):
        html = generate_a11y_report_html(self._make_enriched_data())
        assert "https://example.com" in html

    def test_contains_timestamp(self):
        html = generate_a11y_report_html(self._make_enriched_data())
        assert "2025-01-01T00:00:00Z" in html

    def test_contains_level(self):
        html = generate_a11y_report_html(self._make_enriched_data())
        assert "2.1 AA" in html

    def test_contains_engine_card(self):
        html = generate_a11y_report_html(self._make_enriched_data())
        assert "Axe-core" in html
        assert "v4.10.2" in html

    def test_contains_wcag_table(self):
        html = generate_a11y_report_html(self._make_enriched_data())
        assert "1.1.1" in html
        assert "Non-text Content" in html

    def test_contains_engine_details(self):
        html = generate_a11y_report_html(self._make_enriched_data())
        assert "image-alt" in html
        assert "Images must have alternate text" in html

    def test_contains_theme_toggle(self):
        html = generate_a11y_report_html(self._make_enriched_data())
        assert 'id="theme-toggle"' in html
        assert "inspekt-theme" in html  # localStorage key

    def test_contains_skip_link(self):
        html = generate_a11y_report_html(self._make_enriched_data())
        assert 'class="skip-link"' in html
        assert 'href="#main-content"' in html

    def test_contains_aria_tabs(self):
        html = generate_a11y_report_html(self._make_enriched_data())
        assert 'role="tablist"' in html
        assert 'role="tab"' in html
        assert 'role="tabpanel"' in html

    def test_single_engine_no_disagreements_section(self):
        html = generate_a11y_report_html(self._make_enriched_data())
        assert 'id="disagreements"' not in html

    def test_multi_engine_shows_disagreements(self):
        data = self._make_enriched_data(
            execution_order=["axe", "eac"],
            engines={
                "axe": {"name": "Axe-core", "abbr": "AXE", "version": "4.10.2", "violations": 1, "passes": 0, "incomplete": 0, "error": None},
                "eac": {"name": "Equal Access", "abbr": "EAC", "version": "3.1.0", "violations": 0, "passes": 1, "incomplete": 0, "error": None},
            },
            analysis={
                "total_criteria_with_issues": 1,
                "agreement_percentage": 50,
                "total_criteria_evaluated": 2,
                "full_agreement_count": 1,
                "disagreements": [{"sc": "1.1.1", "description": "Non-text Content", "conformance_level": "A", "failing_engines": [{"engine": "axe", "abbr": "AXE", "count": 1}], "passing_engines": [{"engine": "eac", "abbr": "EAC"}]}],
                "disparities": [],
            },
        )
        html = generate_a11y_report_html(data)
        assert 'id="disagreements"' in html
        assert "AXE (1)" in html

    def test_multi_engine_shows_agreement_gauge(self):
        data = self._make_enriched_data(
            execution_order=["axe", "eac"],
            engines={
                "axe": {"name": "Axe-core", "abbr": "AXE", "version": "4.10.2", "violations": 1, "passes": 0, "incomplete": 0, "error": None},
                "eac": {"name": "Equal Access", "abbr": "EAC", "version": "3.1.0", "violations": 1, "passes": 0, "incomplete": 0, "error": None},
            },
        )
        html = generate_a11y_report_html(data)
        assert "agreement-gauge" in html

    def test_xss_prevention(self):
        """Ensure HTML entities are escaped in user-provided content."""
        data = self._make_enriched_data(url="https://evil.com/<script>alert(1)</script>")
        html = generate_a11y_report_html(data)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_empty_consolidated(self):
        data = self._make_enriched_data(consolidated={})
        html = generate_a11y_report_html(data)
        assert "No criteria to display" in html

    def test_recommendations_section(self):
        data = self._make_enriched_data(
            recommendations={
                "total": 2,
                "by_sc": {
                    "1.1.1": [
                        {"engine": "axe", "rule_id": "image-alt", "level": "incomplete", "message": "Check alt text"},
                    ],
                },
            }
        )
        html = generate_a11y_report_html(data)
        assert 'id="recommendations"' in html
        assert "Check alt text" in html

    def test_engine_error_card(self):
        data = self._make_enriched_data(
            engines={
                "axe": {"name": "Axe-core", "abbr": "AXE", "version": "4.10.2", "violations": 0, "passes": 0, "incomplete": 0, "error": "Timeout"},
            },
            engine_details={"axe": {"error": "Timeout"}},
        )
        html = generate_a11y_report_html(data)
        assert "engine-card-error" in html
        assert "Timeout" in html

    def test_print_stylesheet(self):
        html = generate_a11y_report_html(self._make_enriched_data())
        assert "@media print" in html


# ── Helper Function Tests ────────────────────────────

class TestHelperFunctions:
    """Tests for utility functions in a11y_report.py."""

    def test_format_level_21aa(self):
        assert _format_level("21aa") == "2.1 AA"

    def test_format_level_2a(self):
        assert _format_level("2a") == "2.0 A"

    def test_format_level_22aa(self):
        assert _format_level("22aa") == "2.2 AA"

    def test_format_level_2aaa(self):
        assert _format_level("2aaa") == "2.0 AAA"

    def test_esc_html(self):
        assert _esc("<script>") == "&lt;script&gt;"

    def test_esc_empty(self):
        assert _esc("") == ""

    def test_esc_none(self):
        assert _esc(None) == ""
