"""
Unit tests for PDF Report Assets service.

Tests the asset directory management for PDF accessibility reports.
"""

from __future__ import annotations

from pathlib import Path

import pytest


class TestPDFReportAssets:
    """Tests for PDFReportAssets class."""

    @pytest.fixture
    def assets_manager(self, tmp_path):
        """Create an assets manager with a temp directory."""
        from inspekt.services.pdf_report_assets import PDFReportAssets

        report_path = tmp_path / "test_report.html"
        return PDFReportAssets(report_path)

    def test_init_creates_correct_assets_dir_name(self, assets_manager):
        """Test that assets directory is named correctly."""
        assert assets_manager.assets_dir.name == "test_report_assets"

    def test_ensure_directory_creates_dir(self, assets_manager):
        """Test that ensure_directory creates the directory."""
        assert not assets_manager.assets_dir.exists()

        result = assets_manager.ensure_directory()

        assert assets_manager.assets_dir.exists()
        assert result == assets_manager.assets_dir

    def test_save_cover_creates_file(self, assets_manager):
        """Test saving a cover image."""
        image_bytes = b"PNG_IMAGE_DATA"

        relative_path = assets_manager.save_cover(image_bytes)

        # Check the file was created
        cover_path = assets_manager.assets_dir / "cover.png"
        assert cover_path.exists()
        assert cover_path.read_bytes() == image_bytes

        # Check the relative path is correct
        assert relative_path == "test_report_assets/cover.png"

    def test_save_cover_jpg_format(self, assets_manager):
        """Test saving a cover image as JPEG."""
        image_bytes = b"JPEG_IMAGE_DATA"

        relative_path = assets_manager.save_cover(image_bytes, format="jpg")

        cover_path = assets_manager.assets_dir / "cover.jpg"
        assert cover_path.exists()
        assert "cover.jpg" in relative_path

    def test_save_issue_screenshot(self, assets_manager):
        """Test saving an issue screenshot."""
        image_bytes = b"ISSUE_SCREENSHOT"

        relative_path = assets_manager.save_issue_screenshot(
            rule_id="ISO-32000-1-7.2.1-1",
            page=0,
            image_bytes=image_bytes,
        )

        # Check file exists
        assert assets_manager.assets_dir.exists()
        files = list(assets_manager.assets_dir.glob("issue_*.png"))
        assert len(files) == 1

        # Check content
        assert files[0].read_bytes() == image_bytes

        # Check relative path format
        assert "issue_001" in relative_path
        assert "ISO-32000-1-7_2_1-1" in relative_path  # Dots converted to underscores
        assert "p1" in relative_path

    def test_save_issue_screenshot_increments_counter(self, assets_manager):
        """Test that issue screenshots have incrementing counters."""
        assets_manager.save_issue_screenshot("rule-1", 0, b"data1")
        assets_manager.save_issue_screenshot("rule-2", 1, b"data2")
        assets_manager.save_issue_screenshot("rule-3", 2, b"data3")

        files = sorted(assets_manager.assets_dir.glob("issue_*.png"))
        assert len(files) == 3

        # Check incrementing names
        assert "issue_001" in files[0].name
        assert "issue_002" in files[1].name
        assert "issue_003" in files[2].name

    def test_save_discrepancy_screenshot(self, assets_manager):
        """Test saving a discrepancy screenshot."""
        image_bytes = b"DISCREPANCY_DATA"

        relative_path = assets_manager.save_discrepancy_screenshot(
            page=2,
            image_bytes=image_bytes,
        )

        # Check file exists
        discrepancy_path = assets_manager.assets_dir / "discrepancy_p3.png"
        assert discrepancy_path.exists()
        assert discrepancy_path.read_bytes() == image_bytes
        assert "discrepancy_p3.png" in relative_path

    def test_save_custom_asset(self, assets_manager):
        """Test saving a custom asset."""
        image_bytes = b"CUSTOM_DATA"

        relative_path = assets_manager.save_custom(
            name="my-custom-image",
            image_bytes=image_bytes,
        )

        custom_path = assets_manager.assets_dir / "my-custom-image.png"
        assert custom_path.exists()
        assert custom_path.read_bytes() == image_bytes

    def test_cleanup_removes_directory(self, assets_manager):
        """Test that cleanup removes the entire assets directory."""
        assets_manager.save_cover(b"test")
        assert assets_manager.assets_dir.exists()

        assets_manager.cleanup()

        assert not assets_manager.assets_dir.exists()

    def test_cleanup_orphaned_removes_old_files(self, assets_manager):
        """Test cleanup_orphaned removes files not saved in this session."""
        # Create the directory and add an "old" file manually
        assets_manager.ensure_directory()
        old_file = assets_manager.assets_dir / "old_orphan.png"
        old_file.write_bytes(b"old data")

        # Save a new file
        assets_manager.save_cover(b"new data")

        # Cleanup orphaned
        removed = assets_manager.cleanup_orphaned()

        # Old file should be removed
        assert removed == 1
        assert not old_file.exists()

        # New file should remain
        assert (assets_manager.assets_dir / "cover.png").exists()

    def test_has_assets_false_initially(self, assets_manager):
        """Test has_assets is False before saving anything."""
        assert assets_manager.has_assets is False

    def test_has_assets_true_after_save(self, assets_manager):
        """Test has_assets is True after saving."""
        assets_manager.save_cover(b"test")
        assert assets_manager.has_assets is True

    def test_asset_count(self, assets_manager):
        """Test asset_count property."""
        assert assets_manager.asset_count == 0

        assets_manager.save_cover(b"test1")
        assert assets_manager.asset_count == 1

        assets_manager.save_issue_screenshot("rule", 0, b"test2")
        assert assets_manager.asset_count == 2


class TestImageToDataUri:
    """Tests for the image_to_data_uri static method."""

    def test_png_data_uri(self):
        """Test PNG data URI generation."""
        from inspekt.services.pdf_report_assets import PDFReportAssets

        image_bytes = b"PNG_DATA"
        result = PDFReportAssets.image_to_data_uri(image_bytes, format="png")

        assert result.startswith("data:image/png;base64,")

    def test_jpg_data_uri(self):
        """Test JPEG data URI generation."""
        from inspekt.services.pdf_report_assets import PDFReportAssets

        image_bytes = b"JPEG_DATA"
        result = PDFReportAssets.image_to_data_uri(image_bytes, format="jpg")

        assert result.startswith("data:image/jpeg;base64,")

    def test_data_uri_is_valid_base64(self):
        """Test that the data URI contains valid base64."""
        import base64

        from inspekt.services.pdf_report_assets import PDFReportAssets

        original = b"test image data"
        result = PDFReportAssets.image_to_data_uri(original)

        # Extract base64 part
        _, base64_part = result.split(",", 1)

        # Decode and verify
        decoded = base64.b64decode(base64_part)
        assert decoded == original
