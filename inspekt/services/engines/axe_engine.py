"""
Axe-core accessibility engine implementation.
"""

from __future__ import annotations

import json

from .base import (
    AccessibilityEngine,
    AuditResult,
    ImpactLevel,
    NormalizedViolation,
)


class AxeEngine(AccessibilityEngine):
    """Axe-core accessibility testing engine."""

    # =========================================================================
    # Engine Identity
    # =========================================================================

    @property
    def engine_id(self) -> str:
        return "axe"

    @property
    def npm_package(self) -> str:
        return "axe-core"

    @property
    def cdn_url_template(self) -> str:
        return "https://cdn.jsdelivr.net/npm/axe-core@{version}/axe.min.js"

    @property
    def lib_filename(self) -> str:
        return "axe-core.min.js"

    @property
    def version_basename(self) -> str:
        return "axe-core"

    @property
    def script_filename(self) -> str:
        return "run_axe.js"

    @property
    def min_file_size(self) -> int:
        return 50000  # ~500KB minified

    @property
    def validation_marker(self) -> str:
        return "axe"

    def get_description(self) -> str:
        return "Deque's axe-core accessibility testing engine"

    def get_homepage(self) -> str:
        return "https://www.deque.com/axe/"

    # =========================================================================
    # Configuration
    # =========================================================================

    # WCAG level to axe tags mapping
    LEVEL_MAPPING = {
        "2a": ["wcag2a"],
        "2aa": ["wcag2a", "wcag2aa"],
        "2aaa": ["wcag2a", "wcag2aa", "wcag2aaa"],
        "21a": ["wcag2a", "wcag21a"],
        "21aa": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
        "22aa": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"],
    }

    def build_config(
        self,
        level: str = "22aa",
        include_passes: bool = False,
        include_incomplete: bool = False,
        tags: str | None = None,
        disable_rules: list[str] | None = None,
        enable_rules: list[str] | None = None,
        **kwargs,
    ) -> dict:
        """Build axe-core configuration."""
        config = {"resultTypes": ["violations"]}

        if include_passes:
            config["resultTypes"].append("passes")
        if include_incomplete:
            config["resultTypes"].append("incomplete")

        # Enable specific rules only
        if enable_rules:
            config["runOnly"] = {"type": "rule", "values": enable_rules}
            return config

        # Use WCAG level-based tags
        axe_tags = self.LEVEL_MAPPING.get(level.lower(), ["wcag2a", "wcag2aa"]).copy()

        if tags:
            additional = [t.strip() for t in tags.split(",")]
            axe_tags.extend(additional)

        config["runOnly"] = {"type": "tag", "values": axe_tags}

        if disable_rules:
            config["rules"] = {rid: {"enabled": False} for rid in disable_rules}

        return config

    # =========================================================================
    # Execution
    # =========================================================================

    def load_library(self) -> str:
        """Load the axe-core library JavaScript code."""
        with open(self.lib_path) as f:
            return f.read()

    def load_execution_script(self, config: dict) -> str:
        """Load axe execution script with configuration."""
        with open(self.script_path) as f:
            script = f.read()

        # Inject configuration
        script = script.replace("__AXE_CONFIG__", json.dumps(config))

        return script

    # =========================================================================
    # Result Normalization
    # =========================================================================

    # Impact level mapping
    IMPACT_MAPPING = {
        "critical": ImpactLevel.CRITICAL,
        "serious": ImpactLevel.SERIOUS,
        "moderate": ImpactLevel.MODERATE,
        "minor": ImpactLevel.MINOR,
    }

    def normalize_results(self, raw_results: dict) -> AuditResult:
        """Normalize axe-core results to unified format."""
        violations = []

        for violation in raw_results.get("violations", []):
            impact = self.IMPACT_MAPPING.get(
                violation.get("impact", "minor"), ImpactLevel.MINOR
            )

            for node in violation.get("nodes", []):
                violations.append(
                    NormalizedViolation(
                        rule_id=violation["id"],
                        impact=impact,
                        title=violation.get("help", ""),
                        description=violation.get("description", ""),
                        help_url=violation.get("helpUrl", ""),
                        failure_summary=node.get("failureSummary", ""),
                        html_snippet=node.get("html", ""),
                        selector=node.get("target", []),
                        wcag_tags=violation.get("tags", []),
                        engine="axe",
                        raw=node,
                    )
                )

        summary = raw_results.get("summary", {})

        return AuditResult(
            engine="axe",
            engine_version=raw_results.get("axeVersion", "unknown"),
            url=raw_results.get("url", ""),
            title=raw_results.get("title", ""),
            timestamp=raw_results.get("timestamp", ""),
            violations=violations,
            passes=raw_results.get("passes", []),
            incomplete=raw_results.get("incomplete", []),
            inapplicable=raw_results.get("inapplicable", []),
            summary={
                "violation_count": summary.get("violationCount", len(raw_results.get("violations", []))),
                "pass_count": summary.get("passCount", 0),
                "incomplete_count": summary.get("incompleteCount", 0),
                "critical_count": summary.get("criticalCount", 0),
                "serious_count": summary.get("seriousCount", 0),
                "moderate_count": summary.get("moderateCount", 0),
                "minor_count": summary.get("minorCount", 0),
            },
            raw=raw_results,
        )
