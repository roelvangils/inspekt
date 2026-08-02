"""
Siteimprove Alfa (SIA) accessibility engine implementation.

Alfa implements W3C ACT-Rules for comprehensive WCAG conformance testing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from .base import (
    AccessibilityEngine,
    AuditResult,
    ImpactLevel,
    NormalizedViolation,
)


class SiaEngine(AccessibilityEngine):
    """Siteimprove Alfa accessibility testing engine."""

    # =========================================================================
    # Engine Identity
    # =========================================================================

    @property
    def engine_id(self) -> str:
        return "sia"

    @property
    def npm_package(self) -> str:
        return "@siteimprove/alfa-rules"

    @property
    def cdn_url_template(self) -> str:
        # Alfa is not available via CDN - uses custom bundle
        return ""

    @property
    def lib_filename(self) -> str:
        return "sia.min.js"

    @property
    def version_basename(self) -> str:
        return "sia"

    @property
    def script_filename(self) -> str:
        return "run_sia.js"

    @property
    def min_file_size(self) -> int:
        return 500000  # ~876KB minified

    @property
    def validation_marker(self) -> str:
        return "Alfa"

    def get_description(self) -> str:
        return "ACT-Rules based accessibility conformance testing engine"

    def get_homepage(self) -> str:
        return "https://alfa.siteimprove.com/"

    # =========================================================================
    # Override version checking for custom bundle
    # =========================================================================

    def check_latest_version(self, timeout: float = 5.0) -> dict | None:
        """
        Check npm registry for the latest version.

        Note: Alfa is distributed via npm but we use a custom bundle,
        so we still check npm for version info.
        """
        return super().check_latest_version(timeout)

    def download_version(self, ver: str) -> Path | None:
        """
        Bundle Alfa from npm packages using esbuild.

        Updates @siteimprove/alfa-* packages to the target version,
        runs pnpm install, then bundles via esbuild into a temp file.
        Returns the temp file path on success, None on failure.
        """
        # Check required tools
        if not shutil.which("pnpm"):
            return None
        if not shutil.which("npx"):
            return None

        # Locate project root (where package.json and alfa-entry.mjs live)
        project_root = Path(__file__).resolve().parents[3]
        package_json_path = project_root / "package.json"
        entry_path = project_root / "alfa-entry.mjs"

        if not package_json_path.exists() or not entry_path.exists():
            return None

        # Read and backup original package.json
        original_package_json = package_json_path.read_text(encoding="utf-8")
        success = False

        try:
            # Update all @siteimprove/alfa-* versions to target
            pkg = json.loads(original_package_json)
            for section in ("dependencies", "devDependencies"):
                if section not in pkg:
                    continue
                for dep_name in list(pkg[section]):
                    if dep_name.startswith("@siteimprove/alfa-"):
                        pkg[section][dep_name] = ver

            package_json_path.write_text(
                json.dumps(pkg, indent=2) + "\n", encoding="utf-8"
            )

            # Install updated packages
            subprocess.run(
                ["pnpm", "install", "--no-frozen-lockfile"],
                cwd=str(project_root),
                capture_output=True,
                timeout=120,
                check=True,
            )

            # Bundle with esbuild
            temp_file = tempfile.NamedTemporaryFile(
                mode="wb", delete=False, suffix=".js"
            )
            temp_file.close()
            temp_path = Path(temp_file.name)

            subprocess.run(
                [
                    "npx", "esbuild", "alfa-entry.mjs",
                    "--bundle", "--minify",
                    "--format=iife", "--global-name=Alfa",
                    f"--outfile={temp_path}",
                ],
                cwd=str(project_root),
                capture_output=True,
                timeout=120,
                check=True,
            )

            # Verify output exists and meets minimum size
            if not temp_path.exists() or temp_path.stat().st_size < self.min_file_size:
                temp_path.unlink(missing_ok=True)
                return None

            success = True
            return temp_path

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            return None
        finally:
            if not success:
                # Restore original package.json so the repo stays clean on failure
                package_json_path.write_text(original_package_json, encoding="utf-8")

    def install_version(self, source_path: Path, ver: str) -> bool:
        """Install a new version with correct metadata for esbuild bundle."""
        try:
            self.vendor_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, self.lib_path)

            import hashlib
            sha256_hash = hashlib.sha256()
            with open(self.lib_path, "rb") as f:
                for block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(block)
            checksum = sha256_hash.hexdigest()

            metadata = {
                "version": ver,
                "installed_at": datetime.utcnow().isoformat() + "Z",
                "source": f"esbuild bundle from @siteimprove/alfa-rules@{ver}",
                "checksum": f"sha256:{checksum}",
            }

            with open(self.version_file, "w") as f:
                json.dump(metadata, f, indent=2)

            return True
        except OSError:
            return False

    # =========================================================================
    # Configuration
    # =========================================================================

    # WCAG level mapping for Alfa rule filtering
    # Alfa rules are tagged with WCAG success criteria
    LEVEL_MAPPING = {
        "2a": "WCAG2.0:A",
        "2aa": "WCAG2.0:AA",
        "2aaa": "WCAG2.0:AAA",
        "21a": "WCAG2.1:A",
        "21aa": "WCAG2.1:AA",
        "21aaa": "WCAG2.1:AAA",
        "22aa": "WCAG2.2:AA",
    }

    def build_config(
        self,
        level: str = "22aa",
        include_passes: bool = False,
        include_incomplete: bool = False,
        include_inapplicable: bool = False,
        **kwargs,
    ) -> dict:
        """Build Siteimprove Alfa configuration."""
        conformance = self.LEVEL_MAPPING.get(level.lower(), "WCAG2.2:AA")

        config = {
            "conformance": conformance,
            "includePassed": include_passes,
            "includeCantTell": include_incomplete,
            "includeInapplicable": include_inapplicable,
        }

        return config

    # =========================================================================
    # Execution
    # =========================================================================

    def load_library(self) -> str:
        """Load the Alfa library JavaScript code."""
        try:
            with open(self.lib_path, encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            raise RuntimeError(f"Failed to load Alfa library from {self.lib_path}: {e}")

    def load_execution_script(self, config: dict) -> str:
        """Load Alfa execution script with configuration."""
        try:
            with open(self.script_path, encoding="utf-8") as f:
                script = f.read()
        except OSError as e:
            raise RuntimeError(f"Failed to load Alfa script from {self.script_path}: {e}")

        # Inject version into config for the script to use
        config_with_version = config.copy()
        config_with_version["__version__"] = self.get_current_version() or "unknown"

        # Inject configuration
        script = script.replace("__SIA_CONFIG__", json.dumps(config_with_version))

        return script

    # =========================================================================
    # Result Normalization
    # =========================================================================

    # Map Alfa outcome types to impact levels
    # Alfa uses ACT-Rules outcomes: passed, failed, cantTell, inapplicable
    OUTCOME_TO_IMPACT = {
        "failed": ImpactLevel.SERIOUS,
        "cantTell": ImpactLevel.MODERATE,
    }

    def normalize_results(self, raw_results: dict) -> AuditResult:
        """Normalize Siteimprove Alfa results to unified format."""
        violations = []
        passes = []
        incomplete = []
        inapplicable = []

        outcomes = raw_results.get("outcomes", [])

        for outcome in outcomes:
            outcome_type = outcome.get("outcome", "")
            rule_uri = outcome.get("rule", "")
            rule_id = self._extract_rule_id(rule_uri)

            if outcome_type == "failed":
                impact = self.OUTCOME_TO_IMPACT.get(outcome_type, ImpactLevel.SERIOUS)

                violations.append(
                    NormalizedViolation(
                        rule_id=rule_id,
                        impact=impact,
                        title=outcome.get("title", rule_id),
                        description=outcome.get("description", ""),
                        help_url=self._build_help_url(rule_uri),
                        failure_summary=outcome.get("message", "ACT-Rule failed"),
                        html_snippet=outcome.get("html", ""),
                        selector=[outcome.get("selector", "")],
                        wcag_tags=self._extract_wcag_tags(outcome),
                        engine="sia",
                        raw=outcome,
                    )
                )
            elif outcome_type == "passed":
                passes.append({
                    "rule_id": rule_id,
                    "target": outcome.get("target"),
                })
            elif outcome_type == "cantTell":
                incomplete.append({
                    "rule_id": rule_id,
                    "target": outcome.get("target"),
                    "message": outcome.get("message", "Requires manual review"),
                })
            elif outcome_type == "inapplicable":
                inapplicable.append(rule_id)

        # Count outcomes by type
        failed_count = sum(1 for o in outcomes if o.get("outcome") == "failed")
        passed_count = sum(1 for o in outcomes if o.get("outcome") == "passed")
        cantTell_count = sum(1 for o in outcomes if o.get("outcome") == "cantTell")
        inapplicable_count = sum(1 for o in outcomes if o.get("outcome") == "inapplicable")

        # Count unique rules with failures (for cleaner summary display)
        failed_rules = set(
            self._extract_rule_id(o.get("rule", ""))
            for o in outcomes
            if o.get("outcome") == "failed"
        )

        return AuditResult(
            engine="sia",
            engine_version=raw_results.get("version", "unknown"),
            url=raw_results.get("url", ""),
            title=raw_results.get("title", ""),
            timestamp=raw_results.get("timestamp", ""),
            violations=violations,
            passes=passes,
            incomplete=incomplete,
            inapplicable=list(set(inapplicable)),  # Dedupe
            summary={
                "failed_count": failed_count,
                "failed_rule_count": len(failed_rules),  # Unique rules with failures
                "passed_count": passed_count,
                "cantTell_count": cantTell_count,
                "inapplicable_count": inapplicable_count,
                "total_outcomes": len(outcomes),
            },
            raw=raw_results,
        )

    def _extract_rule_id(self, rule_uri: str) -> str:
        """Extract rule ID from Alfa rule URI.

        Example: https://alfa.siteimprove.com/rules/sia-r1
        -> sia-r1
        """
        if "/" in rule_uri:
            return rule_uri.split("/")[-1]
        return rule_uri

    def _extract_wcag_tags(self, outcome: dict) -> list[str]:
        """Extract WCAG tags from Alfa outcome.

        Alfa rules are mapped to WCAG success criteria via ACT-Rules.
        """
        tags = []

        # Try to get requirements from outcome
        requirements = outcome.get("requirements", [])
        for req in requirements:
            if isinstance(req, str):
                # Format like "wcag:1.1.1" or "wcag21:1.4.11"
                if "wcag" in req.lower():
                    # Normalize to format like "wcag111" or "wcag21-1411"
                    tag = req.lower().replace(":", "").replace(".", "")
                    tags.append(tag)
            elif isinstance(req, dict):
                # May have structured requirement info
                if "id" in req:
                    tags.append(req["id"])

        # Fallback: extract from rule ID if available
        # sia-r1 through sia-r100+ map to specific WCAG SC
        rule_id = self._extract_rule_id(outcome.get("rule", ""))
        if rule_id and not tags:
            # Add generic tag based on rule
            tags.append(f"act-rule-{rule_id}")

        return tags

    def _build_help_url(self, rule_uri: str) -> str:
        """Build documentation URL for an Alfa rule."""
        if rule_uri.startswith("https://"):
            return rule_uri

        rule_id = self._extract_rule_id(rule_uri)
        return f"https://alfa.siteimprove.com/rules/{rule_id}"
