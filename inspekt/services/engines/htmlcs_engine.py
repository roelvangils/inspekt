"""
HTML_CodeSniffer accessibility engine implementation.
"""

from __future__ import annotations

import json

from .base import (
    AccessibilityEngine,
    AuditResult,
    ImpactLevel,
    NormalizedViolation,
)


class HtmlcsEngine(AccessibilityEngine):
    """HTML_CodeSniffer accessibility testing engine."""

    # =========================================================================
    # Engine Identity
    # =========================================================================

    @property
    def engine_id(self) -> str:
        return "hcs"

    @property
    def npm_package(self) -> str:
        return "html_codesniffer"

    @property
    def cdn_url_template(self) -> str:
        return "https://cdn.jsdelivr.net/npm/html_codesniffer@{version}/build/HTMLCS.js"

    @property
    def lib_filename(self) -> str:
        return "htmlcs.min.js"

    @property
    def version_basename(self) -> str:
        return "htmlcs"

    @property
    def script_filename(self) -> str:
        return "run_htmlcs.js"

    @property
    def min_file_size(self) -> int:
        return 50000  # ~100KB

    @property
    def validation_marker(self) -> str:
        return "HTMLCS"

    def get_description(self) -> str:
        return "HTML_CodeSniffer accessibility testing engine (Pa11y)"

    def get_homepage(self) -> str:
        return "https://squizlabs.github.io/HTML_CodeSniffer/"

    # =========================================================================
    # Configuration
    # =========================================================================

    # WCAG level to HTMLCS standard mapping
    # Note: HTMLCS supports WCAG 2.1 but not 2.2 yet
    LEVEL_MAPPING = {
        "2a": "WCAG2A",
        "2aa": "WCAG2AA",
        "2aaa": "WCAG2AAA",
        "21a": "WCAG2A",      # Falls back to 2.0 A (includes some 2.1)
        "21aa": "WCAG2AA",    # Falls back to 2.0 AA (includes some 2.1)
        "22aa": "WCAG2AA",    # Falls back to 2.1 AA (no 2.2 support)
    }

    def build_config(
        self,
        level: str = "22aa",
        include_passes: bool = False,
        include_incomplete: bool = False,
        include_notices: bool = False,
        **kwargs,
    ) -> dict:
        """Build HTML_CodeSniffer configuration."""
        standard = self.LEVEL_MAPPING.get(level.lower(), "WCAG2AA")

        config = {
            "standard": standard,
            "includeNotices": include_notices,
            "includeWarnings": include_incomplete,
        }

        return config

    # =========================================================================
    # Execution
    # =========================================================================

    def load_library(self) -> str:
        """Load the HTML_CodeSniffer library JavaScript code."""
        with open(self.lib_path) as f:
            return f.read()

    def load_execution_script(self, config: dict) -> str:
        """Load HTMLCS execution script with configuration."""
        with open(self.script_path) as f:
            script = f.read()

        # Inject configuration
        script = script.replace("__HTMLCS_CONFIG__", json.dumps(config))

        return script

    # =========================================================================
    # Result Normalization
    # =========================================================================

    # HTMLCS message types to impact mapping
    # Type 1 = Error, Type 2 = Warning, Type 3 = Notice
    TYPE_TO_IMPACT = {
        1: ImpactLevel.CRITICAL,   # Error
        2: ImpactLevel.MODERATE,   # Warning
        3: ImpactLevel.MINOR,      # Notice
    }

    def normalize_results(self, raw_results: dict) -> AuditResult:
        """Normalize HTML_CodeSniffer results to unified format."""
        violations = []
        messages = raw_results.get("messages", [])

        for msg in messages:
            msg_type = msg.get("type", 3)
            impact = self.TYPE_TO_IMPACT.get(msg_type, ImpactLevel.MINOR)

            # Extract WCAG code from the message code
            # Format: WCAG2AA.Principle1.Guideline1_3.1_3_1.H44
            code = msg.get("code", "")
            wcag_tags = self._extract_wcag_tags(code)

            violations.append(
                NormalizedViolation(
                    rule_id=code,
                    impact=impact,
                    title=self._get_rule_title(code),
                    description=msg.get("message", ""),
                    help_url=self._build_help_url(code),
                    failure_summary=msg.get("message", ""),
                    html_snippet=msg.get("element", ""),
                    selector=[msg.get("selector", "")],
                    wcag_tags=wcag_tags,
                    engine="htmlcs",
                    raw=msg,
                )
            )

        # Count by type
        error_count = sum(1 for m in messages if m.get("type") == 1)
        warning_count = sum(1 for m in messages if m.get("type") == 2)
        notice_count = sum(1 for m in messages if m.get("type") == 3)

        return AuditResult(
            engine="htmlcs",
            engine_version=raw_results.get("version", "unknown"),
            url=raw_results.get("url", ""),
            title=raw_results.get("title", ""),
            timestamp=raw_results.get("timestamp", ""),
            violations=violations,
            passes=[],  # HTMLCS doesn't report passes
            incomplete=[],
            inapplicable=[],
            summary={
                "error_count": error_count,
                "warning_count": warning_count,
                "notice_count": notice_count,
                "total_count": len(messages),
            },
            raw=raw_results,
        )

    def _extract_wcag_tags(self, code: str) -> list[str]:
        """Extract WCAG tags from HTMLCS code.

        Example: WCAG2AA.Principle1.Guideline1_3.1_3_1.H44
        -> ['wcag2aa', 'wcag131']
        """
        tags = []
        parts = code.split(".")

        if parts:
            # First part is the standard (e.g., WCAG2AA)
            standard = parts[0].lower()
            if standard.startswith("wcag"):
                tags.append(standard)

            # Try to extract SC number (e.g., 1_3_1 -> wcag131)
            for part in parts:
                if part.startswith("Guideline"):
                    continue
                # Look for pattern like 1_3_1
                if "_" in part and part[0].isdigit():
                    sc = part.replace("_", "")
                    tags.append(f"wcag{sc}")
                    break

        return tags

    def _get_rule_title(self, code: str) -> str:
        """Get a human-readable title from the HTMLCS code."""
        # Extract the technique code (last part)
        parts = code.split(".")
        if len(parts) >= 2:
            # Return the technique (e.g., H44, F68, etc.)
            technique = parts[-1] if parts[-1] else parts[-2]
            return f"WCAG Technique {technique}"
        return code

    def _build_help_url(self, code: str) -> str:
        """Build documentation URL for an HTMLCS code."""
        # HTMLCS codes map to WCAG techniques
        parts = code.split(".")
        if len(parts) >= 1:
            # Try to build URL to WCAG technique
            technique = parts[-1] if parts[-1] else ""
            if technique.startswith("H") or technique.startswith("F"):
                return f"https://www.w3.org/WAI/WCAG21/Techniques/html/{technique}"
            elif technique.startswith("G"):
                return f"https://www.w3.org/WAI/WCAG21/Techniques/general/{technique}"
            elif technique.startswith("C"):
                return f"https://www.w3.org/WAI/WCAG21/Techniques/css/{technique}"

        return "https://squizlabs.github.io/HTML_CodeSniffer/Standards/WCAG2/"
