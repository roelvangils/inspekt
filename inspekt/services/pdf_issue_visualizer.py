"""
PDF Issue Visualization Service.

Captures screenshots of PDF accessibility issues for report visualization.
Uses bounding box data from veraPDF to crop screenshots to the relevant
region of each page.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inspekt.services.pdf_checker import VeraPDFViolation
    from inspekt.services.pdf_renderer import PDFRenderer
    from inspekt.services.pdf_report_assets import PDFReportAssets

logger = logging.getLogger(__name__)


@dataclass
class IssueVisualization:
    """
    A visualization of a PDF accessibility issue.

    Contains the screenshot data and metadata for display in the report.
    """

    rule_id: str
    page_num: int  # 0-indexed
    bbox: tuple[float, float, float, float] | None
    screenshot_path: str | None  # Relative path to saved image
    description: str
    severity: str
    context: str | None = None

    @property
    def has_screenshot(self) -> bool:
        """Check if a screenshot was captured for this issue."""
        return self.screenshot_path is not None


@dataclass
class VisualizationResult:
    """
    Result of visualizing all issues in a PDF.

    Contains the list of visualizations and summary statistics.
    """

    visualizations: list[IssueVisualization] = field(default_factory=list)
    pages_rendered: int = 0
    screenshots_captured: int = 0
    screenshots_failed: int = 0

    @property
    def has_visualizations(self) -> bool:
        """Check if any visualizations were created."""
        return len(self.visualizations) > 0

    @property
    def successful_screenshots(self) -> list[IssueVisualization]:
        """Return only visualizations with successful screenshots."""
        return [v for v in self.visualizations if v.has_screenshot]


class PDFIssueVisualizer:
    """
    Visualize PDF accessibility issues with screenshots.

    Creates cropped screenshots of the regions containing violations,
    using bounding box data from veraPDF when available.
    """

    def __init__(
        self,
        renderer: PDFRenderer,
        assets: PDFReportAssets,
        dpi: int = 150,
        max_issues_per_rule: int = 1,
    ):
        """
        Initialize the visualizer.

        Args:
            renderer: PDFRenderer instance for the target PDF
            assets: PDFReportAssets instance for saving screenshots
            dpi: Resolution for screenshots (default 150)
            max_issues_per_rule: Maximum screenshots to capture per rule type
        """
        self.renderer = renderer
        self.assets = assets
        self.dpi = dpi
        self.max_issues_per_rule = max_issues_per_rule

    def visualize_issues(
        self,
        violations: list[VeraPDFViolation],
    ) -> VisualizationResult:
        """
        Create visualizations for a list of violations.

        For efficiency, only captures one screenshot per rule type
        (configurable via max_issues_per_rule). Violations without
        page numbers get the first page as a fallback.

        Args:
            violations: List of VeraPDFViolation objects

        Returns:
            VisualizationResult with all visualizations
        """
        result = VisualizationResult()
        rules_captured: dict[str, int] = {}

        for violation in violations:
            rule_id = violation.rule_id

            # Check if we've captured enough for this rule
            captured_count = rules_captured.get(rule_id, 0)
            if captured_count >= self.max_issues_per_rule:
                continue

            # Determine page number (fallback to first page if not available)
            page_num = violation.page_number if violation.page_number is not None else 0

            # Create visualization
            viz = self._create_visualization(violation, page_num)
            result.visualizations.append(viz)

            if viz.has_screenshot:
                result.screenshots_captured += 1
                rules_captured[rule_id] = captured_count + 1
            else:
                result.screenshots_failed += 1

        # Track unique pages rendered
        result.pages_rendered = len(set(
            v.page_num for v in result.visualizations if v.has_screenshot
        ))

        return result

    def _create_visualization(
        self,
        violation: VeraPDFViolation,
        page_num: int,
    ) -> IssueVisualization:
        """
        Create a single visualization for a violation.

        Args:
            violation: The violation to visualize
            page_num: Page number to screenshot

        Returns:
            IssueVisualization object
        """
        screenshot_path = None

        try:
            if violation.bbox:
                # Try to crop to the bounding box
                image_bytes = self.renderer.crop_to_bbox(
                    page_num=page_num,
                    bbox=violation.bbox,
                    padding=30,  # Extra context around the issue
                    dpi=self.dpi,
                )
            else:
                # No bbox - render full page at lower resolution for overview
                image_bytes = self.renderer.render_page(
                    page_num=page_num,
                    dpi=max(72, self.dpi // 2),  # Lower DPI for full page
                )

            if image_bytes:
                screenshot_path = self.assets.save_issue_screenshot(
                    rule_id=violation.rule_id,
                    page=page_num,
                    image_bytes=image_bytes,
                )
        except Exception as e:
            logger.warning(
                f"Failed to capture screenshot for {violation.rule_id} on page {page_num}: {e}"
            )

        return IssueVisualization(
            rule_id=violation.rule_id,
            page_num=page_num,
            bbox=violation.bbox,
            screenshot_path=screenshot_path,
            description=violation.description,
            severity=violation.severity,
            context=violation.context,
        )

    def visualize_pages_with_issues(
        self,
        violations: list[VeraPDFViolation],
        max_pages: int = 5,
    ) -> list[tuple[int, str]]:
        """
        Capture full-page screenshots of pages that have issues.

        Useful for giving an overview of problematic pages without
        focusing on specific bounding boxes.

        Args:
            violations: List of violations to identify pages
            max_pages: Maximum number of pages to capture

        Returns:
            List of (page_num, screenshot_path) tuples
        """
        # Collect unique pages with issues
        pages_with_issues = sorted(set(
            v.page_number for v in violations
            if v.page_number is not None
        ))[:max_pages]

        screenshots = []
        for page_num in pages_with_issues:
            try:
                image_bytes = self.renderer.render_page(
                    page_num=page_num,
                    dpi=100,  # Lower DPI for overview
                )
                if image_bytes:
                    path = self.assets.save_custom(
                        name=f"page_{page_num + 1}_issues",
                        image_bytes=image_bytes,
                    )
                    screenshots.append((page_num, path))
            except Exception as e:
                logger.warning(f"Failed to capture page {page_num}: {e}")

        return screenshots


def visualize_pdf_issues(
    pdf_path: Path | str,
    violations: list[VeraPDFViolation],
    assets: PDFReportAssets,
    config: dict | None = None,
) -> VisualizationResult | None:
    """
    Convenience function to visualize issues in a PDF.

    Args:
        pdf_path: Path to the PDF file
        violations: List of VeraPDFViolation objects
        assets: PDFReportAssets instance for saving screenshots
        config: Optional configuration dict with:
            - issue-screenshot-dpi: Resolution (default 150)
            - max-issues-per-rule: Max screenshots per rule (default 1)

    Returns:
        VisualizationResult, or None if rendering is unavailable
    """
    from inspekt.services.pdf_renderer import PDFRenderer, is_pymupdf_available

    if not is_pymupdf_available():
        logger.info("PyMuPDF not available, skipping issue visualization")
        return None

    if not violations:
        return VisualizationResult()

    config = config or {}
    dpi = config.get("issue-screenshot-dpi", 150)
    max_per_rule = config.get("max-issues-per-rule", 1)

    try:
        with PDFRenderer(pdf_path) as renderer:
            visualizer = PDFIssueVisualizer(
                renderer=renderer,
                assets=assets,
                dpi=dpi,
                max_issues_per_rule=max_per_rule,
            )
            return visualizer.visualize_issues(violations)
    except Exception as e:
        logger.error(f"Failed to visualize PDF issues: {e}")
        return None
