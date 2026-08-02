"""
IBM Equal Access accessibility engine implementation.
"""

from __future__ import annotations

import json

from .base import (
    AccessibilityEngine,
    AuditResult,
    ImpactLevel,
    NormalizedViolation,
)


class IbmEngine(AccessibilityEngine):
    """IBM Equal Access accessibility testing engine."""

    # =========================================================================
    # Engine Identity
    # =========================================================================

    @property
    def engine_id(self) -> str:
        return "eac"

    @property
    def npm_package(self) -> str:
        return "accessibility-checker-engine"

    @property
    def cdn_url_template(self) -> str:
        return "https://unpkg.com/accessibility-checker-engine@{version}/ace.js"

    @property
    def lib_filename(self) -> str:
        return "ace.min.js"

    @property
    def version_basename(self) -> str:
        return "ace"

    @property
    def script_filename(self) -> str:
        return "run_ibm.js"

    @property
    def min_file_size(self) -> int:
        return 100000  # ~600KB

    @property
    def validation_marker(self) -> str:
        return "ace"

    def get_description(self) -> str:
        return "IBM Equal Access accessibility testing engine"

    def get_homepage(self) -> str:
        return "https://www.ibm.com/able/toolkit/verify/automated/"

    # =========================================================================
    # Configuration
    # =========================================================================

    # WCAG level to IBM guideline mapping
    LEVEL_MAPPING = {
        "2a": ["WCAG_2_0"],
        "2aa": ["WCAG_2_0"],
        "2aaa": ["WCAG_2_0"],
        "21a": ["WCAG_2_1"],
        "21aa": ["WCAG_2_1"],
        "22aa": ["WCAG_2_2"],
    }

    def build_config(
        self,
        level: str = "22aa",
        include_passes: bool = False,
        include_incomplete: bool = False,
        report_levels: list[str] | None = None,
        **kwargs,
    ) -> dict:
        """Build IBM Equal Access configuration."""
        guidelines = self.LEVEL_MAPPING.get(level.lower(), ["WCAG_2_2"])

        config = {
            "policies": guidelines,
            "reportLevels": report_levels or ["violation", "potentialviolation"],
        }

        return config

    # =========================================================================
    # Execution
    # =========================================================================

    def load_library(self) -> str:
        """Load the IBM Equal Access library JavaScript code."""
        with open(self.lib_path) as f:
            return f.read()

    def load_execution_script(self, config: dict) -> str:
        """Load IBM execution script with configuration."""
        with open(self.script_path) as f:
            script = f.read()

        # Inject configuration
        script = script.replace("__IBM_CONFIG__", json.dumps(config))

        return script

    # =========================================================================
    # Result Normalization
    # =========================================================================

    # IBM level to impact mapping
    LEVEL_TO_IMPACT = {
        "violation": ImpactLevel.CRITICAL,
        "potentialviolation": ImpactLevel.SERIOUS,
        "recommendation": ImpactLevel.MODERATE,
        "potentialrecommendation": ImpactLevel.MINOR,
        "manual": ImpactLevel.MINOR,
    }

    def normalize_results(self, raw_results: dict) -> AuditResult:
        """Normalize IBM Equal Access results to unified format."""
        violations = []
        result_data = raw_results.get("result", {})

        for issue in result_data.get("issues", []):
            level = issue.get("level", "recommendation")
            impact = self.LEVEL_TO_IMPACT.get(level, ImpactLevel.MINOR)

            violations.append(
                NormalizedViolation(
                    rule_id=issue.get("ruleId", ""),
                    impact=impact,
                    title=issue.get("message", ""),
                    description=issue.get("message", ""),
                    help_url=self._build_help_url(issue.get("ruleId", "")),
                    failure_summary=issue.get("message", ""),
                    html_snippet=issue.get("snippet", ""),
                    selector=[issue.get("path", "")],
                    wcag_tags=issue.get("wcag", []),
                    engine="ibm",
                    raw=issue,
                )
            )

        summary = result_data.get("summary", {})

        return AuditResult(
            engine="ibm",
            engine_version="unknown",  # IBM doesn't expose version in results
            url=result_data.get("url", ""),
            title=result_data.get("title", ""),
            timestamp="",
            violations=violations,
            passes=[],  # IBM structures passes differently
            incomplete=[],
            inapplicable=[],
            summary={
                "violation_count": summary.get("violation", 0),
                "potential_violation_count": summary.get("potentialviolation", 0),
                "recommendation_count": summary.get("recommendation", 0),
                "manual_count": summary.get("manual", 0),
            },
            raw=raw_results,
        )

    def _build_help_url(self, rule_id: str) -> str:
        """Build IBM documentation URL for a rule."""
        # IBM rule IDs map to their documentation
        return f"https://www.ibm.com/able/guidelines/ci162/checkpoint/{rule_id}.html"
