"""
Tests for PDF Report JSON Reconstruction functionality (v2.0 schema).

Tests cover:
- Schema migration from v1.0 to v2.0
- JSON round-trip serialization
- New dataclass creation
- Asset manifest handling
"""

from __future__ import annotations

import json

from inspekt.services.pdf_report_data import (
    CURRENT_SCHEMA_VERSION,
    AssetManifest,
    AssetReference,
    ContrastAnalysisData,
    ContrastIssueData,
    # New v2.0 dataclasses
    CoverImageData,
    IssueScreenshotData,
    PDFReportData,
    SimpleChecksData,
    SimplePDFCheckData,
    get_schema_version,
    migrate_schema,
)

# =============================================================================
# Schema Version Tests
# =============================================================================


class TestSchemaVersion:
    """Tests for schema versioning."""

    def test_current_schema_version_is_2_0(self):
        """Current schema version should be 2.0."""
        assert CURRENT_SCHEMA_VERSION == "2.0"

    def test_get_schema_version_returns_default_for_old_data(self):
        """Old data without schema_version should default to 1.0."""
        data = {"report_version": "1.0"}
        assert get_schema_version(data) == "1.0"

    def test_get_schema_version_returns_actual_version(self):
        """Data with schema_version should return that version."""
        data = {"schema_version": "2.0"}
        assert get_schema_version(data) == "2.0"


# =============================================================================
# Schema Migration Tests
# =============================================================================


class TestSchemaMigration:
    """Tests for schema migration from v1.0 to v2.0."""

    def test_migrate_v1_to_v2_adds_schema_version(self):
        """Migration should add schema_version field."""
        v1_data = {"report_version": "1.0"}
        migrated = migrate_schema(v1_data)
        assert migrated["schema_version"] == "2.0"

    def test_migrate_v1_to_v2_adds_new_fields(self):
        """Migration should add all new v2.0 fields with defaults."""
        v1_data = {"report_version": "1.0"}
        migrated = migrate_schema(v1_data)

        assert "cover_image" in migrated
        assert "contrast_analysis" in migrated
        assert "issue_screenshots" in migrated
        assert "simple_checks" in migrated
        assert "interactive_preview" in migrated
        assert "asset_manifest" in migrated

    def test_migrate_v1_to_v2_preserves_existing_data(self):
        """Migration should preserve all existing v1.0 data."""
        v1_data = {
            "report_version": "1.0",
            "generated_at": "2025-01-15T10:30:00",
            "metadata": {
                "file_name": "test.pdf",
                "page_count": 10,
            },
        }
        migrated = migrate_schema(v1_data)

        assert migrated["report_version"] == "1.0"
        assert migrated["generated_at"] == "2025-01-15T10:30:00"
        assert migrated["metadata"]["file_name"] == "test.pdf"

    def test_migrate_v2_data_is_unchanged(self):
        """V2.0 data should pass through unchanged."""
        v2_data = {
            "schema_version": "2.0",
            "cover_image": {"image_base64": "abc123"},
        }
        migrated = migrate_schema(v2_data)
        assert migrated["cover_image"]["image_base64"] == "abc123"

    def test_migrate_does_not_mutate_original(self):
        """Migration should not modify the original data."""
        v1_data = {"report_version": "1.0"}
        migrate_schema(v1_data)
        assert "schema_version" not in v1_data


# =============================================================================
# New Dataclass Tests
# =============================================================================


class TestCoverImageData:
    """Tests for CoverImageData dataclass."""

    def test_create_with_defaults(self):
        """CoverImageData should have sensible defaults."""
        cover = CoverImageData()
        assert cover.image_base64 is None
        assert cover.asset_id is None
        assert cover.width == 0
        assert cover.height == 0

    def test_create_with_values(self):
        """CoverImageData should accept values."""
        cover = CoverImageData(
            image_base64="abc123",
            width=800,
            height=1200,
        )
        assert cover.image_base64 == "abc123"
        assert cover.width == 800
        assert cover.height == 1200


class TestContrastIssueData:
    """Tests for ContrastIssueData dataclass."""

    def test_create_contrast_issue(self):
        """ContrastIssueData should store all fields."""
        issue = ContrastIssueData(
            page=1,
            foreground_color="#333333",
            background_color="#ffffff",
            contrast_ratio=4.2,
            required_ratio=4.5,
            level="AA",
            text_sample="Sample text",
        )
        assert issue.page == 1
        assert issue.foreground_color == "#333333"
        assert issue.contrast_ratio == 4.2
        assert issue.level == "AA"


class TestContrastAnalysisData:
    """Tests for ContrastAnalysisData dataclass."""

    def test_create_with_no_issues(self):
        """ContrastAnalysisData should work with no issues."""
        analysis = ContrastAnalysisData(
            ran_analysis=True,
            pages_analyzed=5,
            issues_found=0,
        )
        assert analysis.ran_analysis is True
        assert analysis.issues == []

    def test_create_with_issues(self):
        """ContrastAnalysisData should store issues list."""
        issue = ContrastIssueData(
            page=1,
            foreground_color="#333",
            background_color="#fff",
            contrast_ratio=3.5,
            required_ratio=4.5,
            level="AA",
        )
        analysis = ContrastAnalysisData(
            ran_analysis=True,
            pages_analyzed=1,
            issues_found=1,
            aa_failures=1,
            issues=[issue],
        )
        assert len(analysis.issues) == 1
        assert analysis.aa_failures == 1


class TestSimpleChecksData:
    """Tests for SimpleChecksData dataclass."""

    def test_create_simple_checks(self):
        """SimpleChecksData should store check results."""
        check = SimplePDFCheckData(
            check_id="tagged",
            name="Tagged PDF",
            status="pass",
            severity="critical",
            message="Document is tagged",
        )
        checks = SimpleChecksData(
            ran_checks=True,
            total_checks=1,
            passed=1,
            checks=[check],
        )
        assert checks.ran_checks is True
        assert len(checks.checks) == 1
        assert checks.passed == 1


class TestAssetManifest:
    """Tests for AssetManifest dataclass."""

    def test_create_empty_manifest(self):
        """AssetManifest should work with no assets."""
        manifest = AssetManifest(assets_directory="report_assets")
        assert manifest.assets_directory == "report_assets"
        assert manifest.total_size == 0
        assert manifest.assets == []

    def test_create_manifest_with_assets(self):
        """AssetManifest should store asset references."""
        asset = AssetReference(
            asset_id="cover_001",
            filename="cover_001.png",
            asset_type="cover",
            file_size=50000,
        )
        manifest = AssetManifest(
            assets_directory="report_assets",
            total_size=50000,
            assets=[asset],
        )
        assert len(manifest.assets) == 1
        assert manifest.assets[0].asset_id == "cover_001"


# =============================================================================
# JSON Round-Trip Tests
# =============================================================================


class TestJSONRoundTrip:
    """Tests for JSON serialization and deserialization."""

    def test_basic_report_round_trip(self):
        """Basic report should survive JSON round-trip."""
        report = PDFReportData(
            report_version="1.0",
            schema_version="2.0",
            generated_at="2025-01-15T10:30:00",
        )

        json_str = report.to_json()
        restored = PDFReportData.from_json(json_str)

        assert restored.report_version == "1.0"
        assert restored.schema_version == "2.0"
        assert restored.generated_at == "2025-01-15T10:30:00"

    def test_report_with_cover_image_round_trip(self):
        """Report with cover image should survive round-trip."""
        report = PDFReportData(
            schema_version="2.0",
            cover_image=CoverImageData(
                image_base64="abc123",
                width=800,
                height=1200,
            ),
        )

        json_str = report.to_json()
        restored = PDFReportData.from_json(json_str)

        assert restored.cover_image is not None
        assert restored.cover_image.image_base64 == "abc123"
        assert restored.cover_image.width == 800

    def test_report_with_contrast_analysis_round_trip(self):
        """Report with contrast analysis should survive round-trip."""
        issue = ContrastIssueData(
            page=1,
            foreground_color="#333",
            background_color="#fff",
            contrast_ratio=3.5,
            required_ratio=4.5,
            level="AA",
        )
        report = PDFReportData(
            schema_version="2.0",
            contrast_analysis=ContrastAnalysisData(
                ran_analysis=True,
                pages_analyzed=5,
                issues_found=1,
                issues=[issue],
            ),
        )

        json_str = report.to_json()
        restored = PDFReportData.from_json(json_str)

        assert restored.contrast_analysis is not None
        assert restored.contrast_analysis.ran_analysis is True
        assert len(restored.contrast_analysis.issues) == 1
        assert restored.contrast_analysis.issues[0].page == 1

    def test_report_with_issue_screenshots_round_trip(self):
        """Report with issue screenshots should survive round-trip."""
        screenshot = IssueScreenshotData(
            violation_index=0,
            rule_id="6.1.2-1",
            page=3,
            screenshot_base64="xyz789",
        )
        report = PDFReportData(
            schema_version="2.0",
            issue_screenshots=[screenshot],
        )

        json_str = report.to_json()
        restored = PDFReportData.from_json(json_str)

        assert len(restored.issue_screenshots) == 1
        assert restored.issue_screenshots[0].rule_id == "6.1.2-1"
        assert restored.issue_screenshots[0].page == 3

    def test_report_with_simple_checks_round_trip(self):
        """Report with simple checks should survive round-trip."""
        check = SimplePDFCheckData(
            check_id="tagged",
            name="Tagged PDF",
            status="pass",
            severity="critical",
        )
        report = PDFReportData(
            schema_version="2.0",
            simple_checks=SimpleChecksData(
                ran_checks=True,
                checks=[check],
            ),
        )

        json_str = report.to_json()
        restored = PDFReportData.from_json(json_str)

        assert restored.simple_checks is not None
        assert restored.simple_checks.ran_checks is True
        assert len(restored.simple_checks.checks) == 1

    def test_report_with_asset_manifest_round_trip(self):
        """Report with asset manifest should survive round-trip."""
        asset = AssetReference(
            asset_id="cover_001",
            filename="cover_001.png",
            asset_type="cover",
            file_size=50000,
        )
        report = PDFReportData(
            schema_version="2.0",
            asset_manifest=AssetManifest(
                assets_directory="report_assets",
                assets=[asset],
            ),
        )

        json_str = report.to_json()
        restored = PDFReportData.from_json(json_str)

        assert restored.asset_manifest is not None
        assert len(restored.asset_manifest.assets) == 1
        assert restored.asset_manifest.assets[0].asset_id == "cover_001"


# =============================================================================
# Integration with Existing Data Tests
# =============================================================================


class TestIntegrationWithExistingData:
    """Tests for integration with existing v1.0 data structures."""

    def test_v1_json_loads_correctly(self):
        """V1.0 JSON data should load and migrate correctly."""
        v1_json = json.dumps(
            {
                "report_version": "1.0",
                "generated_at": "2025-01-15T10:30:00",
                "generator": "Inspekt PDF Checker",
                "metadata": {
                    "file_name": "test.pdf",
                    "file_path": "/path/to/test.pdf",
                    "file_size": 123456,
                    "page_count": 10,
                    "title": "Test Document",
                    "author": "Test Author",
                    "language": "en",
                },
                "basic_checks": {
                    # Required fields for BasicChecksData
                    "is_tagged": True,
                    "has_title": True,
                    "has_language": True,
                    "has_bookmarks": True,
                    "is_linearized": False,
                    "checks": [
                        {
                            "check_id": "tagged",
                            "name": "Tagged PDF",
                            "description": "PDF has tags",
                            "status": "pass",
                            "severity": "critical",
                        }
                    ],
                },
            }
        )

        report = PDFReportData.from_json(v1_json)

        # Check migration happened
        assert report.schema_version == "2.0"

        # Check original data preserved
        assert report.report_version == "1.0"
        assert report.metadata.file_name == "test.pdf"
        assert report.basic_checks.is_tagged is True

        # Check new fields have defaults
        assert report.cover_image is None
        assert report.contrast_analysis is None
        assert report.issue_screenshots == []

    def test_full_v2_json_loads_correctly(self):
        """Full v2.0 JSON with all sections should load correctly."""
        v2_json = json.dumps(
            {
                "report_version": "1.0",
                "schema_version": "2.0",
                "generated_at": "2025-01-15T10:30:00",
                "cover_image": {
                    "image_base64": "abc123",
                    "width": 800,
                    "height": 1200,
                },
                "contrast_analysis": {
                    "ran_analysis": True,
                    "pages_analyzed": 5,
                    "issues_found": 1,
                    "aa_failures": 1,
                    "aaa_failures": 0,
                    "issues": [
                        {
                            "page": 1,
                            "foreground_color": "#333",
                            "background_color": "#fff",
                            "contrast_ratio": 3.5,
                            "required_ratio": 4.5,
                            "level": "AA",
                        }
                    ],
                },
                "simple_checks": {
                    "ran_checks": True,
                    "total_checks": 11,
                    "passed": 9,
                    "failed": 2,
                    "checks": [],
                },
                "interactive_preview": {
                    "enabled": True,
                    "pages_rendered": 5,
                    "pages_with_overlays": [1, 2, 3, 4, 5],
                },
                "asset_manifest": {
                    "assets_directory": "report_assets",
                    "total_size": 0,
                    "assets": [],
                },
            }
        )

        report = PDFReportData.from_json(v2_json)

        assert report.cover_image.image_base64 == "abc123"
        assert report.contrast_analysis.ran_analysis is True
        assert report.simple_checks.total_checks == 11
        assert report.interactive_preview.enabled is True
        assert report.asset_manifest.assets_directory == "report_assets"
