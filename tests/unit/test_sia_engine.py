"""
Unit tests for Alfa accessibility engine.
"""

from unittest.mock import patch

from inspekt.services.engines.base import AuditResult, ImpactLevel, NormalizedViolation
from inspekt.services.engines.sia_engine import SiaEngine


class TestSiaEngineProperties:
    """Test SiaEngine property values."""

    def test_engine_id(self):
        engine = SiaEngine()
        assert engine.engine_id == "sia"

    def test_engine_name(self):
        engine = SiaEngine()
        assert engine.engine_name == "Alfa"

    def test_npm_package(self):
        engine = SiaEngine()
        assert engine.npm_package == "@siteimprove/alfa-rules"

    def test_lib_filename(self):
        engine = SiaEngine()
        assert engine.lib_filename == "sia.min.js"

    def test_script_filename(self):
        engine = SiaEngine()
        assert engine.script_filename == "run_sia.js"

    def test_version_basename(self):
        engine = SiaEngine()
        assert engine.version_basename == "sia"

    def test_min_file_size(self):
        engine = SiaEngine()
        assert engine.min_file_size == 500000  # ~876KB bundle

    def test_validation_marker(self):
        engine = SiaEngine()
        assert engine.validation_marker == "Alfa"

    def test_homepage(self):
        engine = SiaEngine()
        assert "alfa.siteimprove.com" in engine.get_homepage()

    def test_description(self):
        engine = SiaEngine()
        assert "ACT-Rules" in engine.get_description()


class TestSiaEngineConfiguration:
    """Test SiaEngine configuration building."""

    def test_build_config_defaults(self):
        engine = SiaEngine()
        config = engine.build_config()

        assert config["conformance"] == "WCAG2.2:AA"
        assert config["includePassed"] is False
        assert config["includeCantTell"] is False
        assert config["includeInapplicable"] is False

    def test_build_config_wcag_levels(self):
        engine = SiaEngine()

        # Test various WCAG levels
        assert engine.build_config(level="2a")["conformance"] == "WCAG2.0:A"
        assert engine.build_config(level="2aa")["conformance"] == "WCAG2.0:AA"
        assert engine.build_config(level="21aa")["conformance"] == "WCAG2.1:AA"
        assert engine.build_config(level="22aa")["conformance"] == "WCAG2.2:AA"

    def test_build_config_include_options(self):
        engine = SiaEngine()

        config = engine.build_config(
            include_passes=True,
            include_incomplete=True,
            include_inapplicable=True,
        )

        assert config["includePassed"] is True
        assert config["includeCantTell"] is True
        assert config["includeInapplicable"] is True


class TestSiaEngineInstallation:
    """Test SiaEngine installation and file handling."""

    def test_lib_path_exists(self):
        engine = SiaEngine()
        assert engine.lib_path.exists(), "Alfa bundle should be installed"

    def test_is_installed(self):
        engine = SiaEngine()
        assert engine.is_installed() is True

    def test_get_current_version(self):
        engine = SiaEngine()
        version = engine.get_current_version()
        assert version is not None
        assert "0.108" in version or version.startswith("0.")

    def test_script_path_exists(self):
        engine = SiaEngine()
        assert engine.script_path.exists(), "run_sia.js should exist"

    def test_load_library(self):
        engine = SiaEngine()
        lib_code = engine.load_library()

        assert len(lib_code) > 500000  # ~876KB
        assert "Alfa" in lib_code or "sia" in lib_code.lower()

    def test_load_execution_script(self):
        engine = SiaEngine()
        config = {"conformance": "WCAG2.2:AA"}
        script = engine.load_execution_script(config)

        assert "__SIA_CONFIG__" not in script  # Should be replaced
        assert "WCAG2.2:AA" in script  # Config should be injected
        assert "__version__" in script  # Version should be injected


class TestSiaEngineResultNormalization:
    """Test SiaEngine result normalization."""

    def test_normalize_empty_results(self):
        engine = SiaEngine()
        raw = {
            "ok": True,
            "url": "https://example.com",
            "title": "Test Page",
            "timestamp": "2024-12-24T12:00:00Z",
            "outcomes": [],
            "version": "0.108.2",
        }

        result = engine.normalize_results(raw)

        assert isinstance(result, AuditResult)
        assert result.engine == "sia"
        assert result.url == "https://example.com"
        assert result.title == "Test Page"
        assert len(result.violations) == 0

    def test_normalize_failed_outcome(self):
        engine = SiaEngine()
        raw = {
            "ok": True,
            "url": "https://example.com",
            "title": "Test Page",
            "timestamp": "2024-12-24T12:00:00Z",
            "outcomes": [
                {
                    "rule": "https://alfa.siteimprove.com/rules/sia-r2",
                    "outcome": "failed",
                    "target": "Element<img, ...>",
                    "title": "Image has accessible name",
                    "message": "Image missing alt attribute",
                    "requirements": ["wcag:1.1.1"],
                }
            ],
            "version": "0.108.2",
        }

        result = engine.normalize_results(raw)

        assert len(result.violations) == 1
        violation = result.violations[0]

        assert isinstance(violation, NormalizedViolation)
        assert violation.rule_id == "sia-r2"
        assert violation.impact == ImpactLevel.SERIOUS
        assert violation.engine == "sia"
        assert "1.1.1" in str(violation.wcag_tags) or "wcag111" in str(violation.wcag_tags)

    def test_normalize_passed_excluded_by_default(self):
        engine = SiaEngine()
        raw = {
            "ok": True,
            "url": "https://example.com",
            "title": "Test Page",
            "timestamp": "2024-12-24T12:00:00Z",
            "outcomes": [
                {
                    "rule": "sia-r1",
                    "outcome": "passed",
                    "target": "Element<title>",
                }
            ],
            "version": "0.108.2",
        }

        result = engine.normalize_results(raw)

        assert len(result.violations) == 0
        assert len(result.passes) == 1
        assert result.passes[0]["rule_id"] == "sia-r1"

    def test_normalize_summary_counts(self):
        engine = SiaEngine()
        raw = {
            "ok": True,
            "url": "https://example.com",
            "title": "Test Page",
            "timestamp": "2024-12-24T12:00:00Z",
            "outcomes": [
                {"rule": "sia-r1", "outcome": "passed"},
                {"rule": "sia-r2", "outcome": "failed"},
                {"rule": "sia-r3", "outcome": "failed"},
                {"rule": "sia-r4", "outcome": "cantTell"},
                {"rule": "sia-r5", "outcome": "inapplicable"},
            ],
            "version": "0.108.2",
        }

        result = engine.normalize_results(raw)

        assert result.summary["passed_count"] == 1
        assert result.summary["failed_count"] == 2
        assert result.summary["cantTell_count"] == 1
        assert result.summary["inapplicable_count"] == 1
        assert result.summary["total_outcomes"] == 5


class TestSiaEngineHelpers:
    """Test SiaEngine helper methods."""

    def test_extract_rule_id_from_url(self):
        engine = SiaEngine()

        assert engine._extract_rule_id("https://alfa.siteimprove.com/rules/sia-r2") == "sia-r2"
        assert engine._extract_rule_id("sia-r12") == "sia-r12"
        assert engine._extract_rule_id("https://example.com/rules/sia-r99") == "sia-r99"

    def test_build_help_url(self):
        engine = SiaEngine()

        url = engine._build_help_url("sia-r2")
        assert "alfa.siteimprove.com/rules/sia-r2" in url

        # Full URL should be returned as-is
        full_url = "https://alfa.siteimprove.com/rules/sia-r1"
        assert engine._build_help_url(full_url) == full_url

    def test_extract_wcag_tags_from_requirements(self):
        engine = SiaEngine()

        outcome = {
            "rule": "sia-r2",
            "requirements": ["wcag:1.1.1"],
        }
        tags = engine._extract_wcag_tags(outcome)

        assert len(tags) >= 1
        assert any("111" in tag or "1.1.1" in tag for tag in tags)


class TestSiaEngineDownloadNotSupported:
    """Test download_version's tool preflight."""

    def test_download_returns_none_without_bundling_tools(self):
        engine = SiaEngine()

        # Bundling needs pnpm + npx; without them download_version bails out
        with patch("inspekt.services.engines.sia_engine.shutil.which", return_value=None):
            assert engine.download_version("0.108.2") is None
