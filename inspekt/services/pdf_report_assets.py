"""
PDF Report Asset Management.

Manages external asset files (images) for PDF accessibility reports.
Assets are stored in a `{report_name}_assets/` directory alongside the HTML report,
enabling smaller HTML files with lazy-loaded images.

Directory structure:
    report.html
    report_assets/
        cover.png           # First page preview
        issue_001.png       # Issue screenshot (rule-id_page)
        issue_002.png
        discrepancy_p3.png  # Text discrepancy page screenshots
        ...
"""

from __future__ import annotations

import base64
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class PDFReportAssets:
    """
    Manage external asset files for PDF accessibility reports.

    Creates and manages an assets directory alongside the report HTML file.
    All images are stored as external files to keep the HTML small and
    enable lazy loading of images.
    """

    def __init__(self, report_path: Path | str):
        """
        Initialize asset manager for a report.

        Args:
            report_path: Path to the HTML report file
        """
        self.report_path = Path(report_path)

        # Create assets directory name based on report filename
        # e.g., "report.html" -> "report_assets/"
        stem = self.report_path.stem
        self.assets_dir = self.report_path.parent / f"{stem}_assets"

        self._issue_counter = 0
        self._saved_assets: list[Path] = []

    def ensure_directory(self) -> Path:
        """
        Ensure the assets directory exists.

        Returns:
            Path to the assets directory
        """
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        return self.assets_dir

    def get_relative_path(self, asset_path: Path) -> str:
        """
        Get the relative path from the report to an asset.

        Args:
            asset_path: Absolute path to the asset

        Returns:
            Relative path suitable for use in HTML src attributes
        """
        # Assets are in a sibling directory to the report
        return f"{self.assets_dir.name}/{asset_path.name}"

    def save_cover(self, image_bytes: bytes, format: str = "png") -> str:
        """
        Save the cover page image.

        Args:
            image_bytes: PNG or JPEG image data
            format: Image format ("png" or "jpg")

        Returns:
            Relative path to the saved image for use in HTML
        """
        self.ensure_directory()

        ext = "jpg" if format.lower() in ("jpg", "jpeg") else "png"
        cover_path = self.assets_dir / f"cover.{ext}"
        cover_path.write_bytes(image_bytes)
        self._saved_assets.append(cover_path)

        return self.get_relative_path(cover_path)

    def save_issue_screenshot(
        self,
        rule_id: str,
        page: int,
        image_bytes: bytes,
        format: str = "png",
    ) -> str:
        """
        Save an issue screenshot.

        Args:
            rule_id: The rule ID (used in filename)
            page: Page number (0-indexed)
            image_bytes: PNG or JPEG image data
            format: Image format ("png" or "jpg")

        Returns:
            Relative path to the saved image for use in HTML
        """
        self.ensure_directory()

        self._issue_counter += 1
        # Sanitize rule_id for filename (replace invalid chars)
        safe_rule_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in rule_id)

        ext = "jpg" if format.lower() in ("jpg", "jpeg") else "png"
        filename = f"issue_{self._issue_counter:03d}_{safe_rule_id}_p{page + 1}.{ext}"
        issue_path = self.assets_dir / filename
        issue_path.write_bytes(image_bytes)
        self._saved_assets.append(issue_path)

        return self.get_relative_path(issue_path)

    def save_discrepancy_screenshot(
        self,
        page: int,
        image_bytes: bytes,
        format: str = "png",
    ) -> str:
        """
        Save a text discrepancy page screenshot.

        Args:
            page: Page number (0-indexed)
            image_bytes: PNG or JPEG image data
            format: Image format ("png" or "jpg")

        Returns:
            Relative path to the saved image for use in HTML
        """
        self.ensure_directory()

        ext = "jpg" if format.lower() in ("jpg", "jpeg") else "png"
        filename = f"discrepancy_p{page + 1}.{ext}"
        discrepancy_path = self.assets_dir / filename
        discrepancy_path.write_bytes(image_bytes)
        self._saved_assets.append(discrepancy_path)

        return self.get_relative_path(discrepancy_path)

    def save_custom(
        self,
        name: str,
        image_bytes: bytes,
        format: str = "png",
    ) -> str:
        """
        Save a custom asset with a specific name.

        Args:
            name: Base name for the file (without extension)
            image_bytes: PNG or JPEG image data
            format: Image format ("png" or "jpg")

        Returns:
            Relative path to the saved image for use in HTML
        """
        self.ensure_directory()

        ext = "jpg" if format.lower() in ("jpg", "jpeg") else "png"
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        asset_path = self.assets_dir / f"{safe_name}.{ext}"
        asset_path.write_bytes(image_bytes)
        self._saved_assets.append(asset_path)

        return self.get_relative_path(asset_path)

    def cleanup(self) -> None:
        """
        Remove the assets directory and all its contents.

        Use this to clean up when report generation fails or when
        regenerating a report.
        """
        if self.assets_dir.exists():
            try:
                shutil.rmtree(self.assets_dir)
            except OSError as e:
                logger.warning(f"Failed to clean up assets directory: {e}")

    def cleanup_orphaned(self) -> int:
        """
        Remove any assets that weren't saved in this session.

        Useful for cleaning up stale assets from previous report
        generations.

        Returns:
            Number of orphaned assets removed
        """
        if not self.assets_dir.exists():
            return 0

        removed = 0
        saved_names = {p.name for p in self._saved_assets}

        for path in self.assets_dir.iterdir():
            if path.name not in saved_names:
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass

        # Remove directory if empty
        try:
            if not any(self.assets_dir.iterdir()):
                self.assets_dir.rmdir()
        except OSError:
            pass

        return removed

    @property
    def has_assets(self) -> bool:
        """Check if any assets have been saved."""
        return len(self._saved_assets) > 0

    @property
    def asset_count(self) -> int:
        """Return the number of saved assets."""
        return len(self._saved_assets)

    @staticmethod
    def image_to_data_uri(image_bytes: bytes, format: str = "png") -> str:
        """
        Convert image bytes to a data URI for inline embedding.

        Use this fallback when external assets can't be created
        (e.g., permission issues).

        Args:
            image_bytes: Image data
            format: Image format ("png" or "jpg")

        Returns:
            Data URI string suitable for img src attribute
        """
        mime = "image/jpeg" if format.lower() in ("jpg", "jpeg") else "image/png"
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{mime};base64,{encoded}"
