"""
PDF Page Rendering Service.

Renders PDF pages to images using PyMuPDF (fitz) for:
- Cover page previews
- Issue location screenshots with bounding box cropping
- Coordinate transformation (PDF bottom-left to image top-left)

PyMuPDF is preferred over pdf2image because:
- Pure Python wheels (no poppler binary dependency)
- Native bounding box coordinate handling
- Better performance with C++ core
- Apple Silicon native support
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def is_pymupdf_available() -> bool:
    """
    Check if PyMuPDF is installed.

    Returns:
        True if PyMuPDF can be imported, False otherwise.
    """
    try:
        import fitz  # noqa: F401 - PyMuPDF

        return True
    except ImportError:
        return False


class PDFRenderer:
    """
    Render PDF pages to images using PyMuPDF.

    Provides methods for rendering full pages, cover previews,
    and cropped regions around specific bounding boxes.
    """

    def __init__(self, pdf_path: Path | str):
        """
        Initialize the renderer with a PDF file.

        Args:
            pdf_path: Path to the PDF file

        Raises:
            ImportError: If PyMuPDF is not installed
            FileNotFoundError: If the PDF file doesn't exist
        """
        if not is_pymupdf_available():
            raise ImportError(
                "PyMuPDF is required for PDF rendering. "
                "Install it with: pip install pymupdf>=1.23.0"
            )

        import fitz

        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")

        self._doc = fitz.open(str(self.pdf_path))

    def __enter__(self) -> PDFRenderer:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - close the document."""
        self.close()

    def close(self) -> None:
        """Close the PDF document."""
        if self._doc:
            self._doc.close()
            self._doc = None

    @property
    def page_count(self) -> int:
        """Return the number of pages in the PDF."""
        return len(self._doc) if self._doc else 0

    def get_page_dimensions(self, page_num: int) -> tuple[float, float]:
        """
        Get the dimensions of a page in PDF points.

        Args:
            page_num: 0-indexed page number

        Returns:
            Tuple of (width, height) in PDF points
        """
        if not self._doc or page_num < 0 or page_num >= len(self._doc):
            return (0.0, 0.0)

        page = self._doc[page_num]
        rect = page.rect
        return (rect.width, rect.height)

    def render_page(
        self,
        page_num: int,
        dpi: int = 150,
        format: str = "png",
    ) -> bytes:
        """
        Render a full page to an image.

        Args:
            page_num: 0-indexed page number
            dpi: Resolution for rendering (default 150)
            format: Output format - "png" or "jpg" (default "png")

        Returns:
            Image bytes in the specified format

        Raises:
            ValueError: If page number is invalid
        """
        if not self._doc:
            raise ValueError("PDF document is not open")

        if page_num < 0 or page_num >= len(self._doc):
            raise ValueError(f"Invalid page number {page_num}. Document has {len(self._doc)} pages")

        import fitz

        page = self._doc[page_num]

        # Calculate zoom factor from DPI (72 DPI is PDF standard)
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)

        # Render page to pixmap
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)

        # Convert to bytes
        if format.lower() == "jpg":
            return pixmap.tobytes(output="jpeg", jpg_quality=92)
        else:
            return pixmap.tobytes(output="png")

    def render_cover(
        self,
        dpi: int = 150,
        max_height: int = 600,
        format: str = "png",
    ) -> bytes:
        """
        Render the first page as a cover preview.

        The image is scaled down if it exceeds max_height while
        maintaining aspect ratio.

        Args:
            dpi: Base resolution for rendering (default 150)
            max_height: Maximum height in pixels (default 600)
            format: Output format - "png" or "jpg" (default "png")

        Returns:
            Image bytes in the specified format
        """
        if not self._doc or len(self._doc) == 0:
            raise ValueError("PDF document is empty or not open")

        import fitz

        page = self._doc[0]
        rect = page.rect

        # Calculate the required zoom to get max_height
        # Start with DPI-based zoom
        base_zoom = dpi / 72.0
        rendered_height = rect.height * base_zoom

        # If rendered height exceeds max_height, scale down
        if rendered_height > max_height:
            zoom = max_height / rect.height
        else:
            zoom = base_zoom

        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)

        if format.lower() == "jpg":
            return pixmap.tobytes(output="jpeg", jpg_quality=92)
        else:
            return pixmap.tobytes(output="png")

    def crop_to_bbox(
        self,
        page_num: int,
        bbox: tuple[float, float, float, float],
        padding: int = 20,
        dpi: int = 150,
        format: str = "png",
    ) -> bytes | None:
        """
        Crop a page to show a specific bounding box region.

        The bounding box is in PDF coordinates (bottom-left origin),
        which are automatically transformed to image coordinates.

        Args:
            page_num: 0-indexed page number
            bbox: Bounding box as (x1, y1, x2, y2) in PDF coordinates
            padding: Extra pixels around the bbox (default 20)
            dpi: Resolution for rendering (default 150)
            format: Output format - "png" or "jpg" (default "png")

        Returns:
            Cropped image bytes, or None if the bbox is invalid
        """
        if not self._doc:
            return None

        if page_num < 0 or page_num >= len(self._doc):
            logger.warning(f"Invalid page number {page_num} for cropping")
            return None

        import fitz

        page = self._doc[page_num]
        page_rect = page.rect

        # Transform PDF coordinates (bottom-left origin) to page coordinates
        # PyMuPDF uses top-left origin internally, same as images
        x1, y1, x2, y2 = bbox

        # Ensure coordinates are ordered correctly
        x_min = min(x1, x2)
        x_max = max(x1, x2)
        y_min = min(y1, y2)  # In PDF coords, y increases upward
        y_max = max(y1, y2)

        # Transform Y coordinates: PDF y=0 is at bottom, image y=0 is at top
        # For a page with height H:
        # image_y = H - pdf_y
        img_y1 = page_rect.height - y_max  # Top of bbox in image coords
        img_y2 = page_rect.height - y_min  # Bottom of bbox in image coords

        # Create the clip rectangle with padding
        padding_pts = padding * (72.0 / dpi)  # Convert pixel padding to points

        clip_rect = fitz.Rect(
            max(0, x_min - padding_pts),
            max(0, img_y1 - padding_pts),
            min(page_rect.width, x_max + padding_pts),
            min(page_rect.height, img_y2 + padding_pts),
        )

        # Validate the clip rectangle
        if clip_rect.is_empty or clip_rect.is_infinite:
            logger.warning(f"Invalid clip rectangle for bbox {bbox}")
            return None

        # Render the clipped region
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix, clip=clip_rect, alpha=False)

        if format.lower() == "jpg":
            return pixmap.tobytes(output="jpeg", jpg_quality=92)
        else:
            return pixmap.tobytes(output="png")

    def transform_coordinates(
        self,
        page_num: int,
        bbox: tuple[float, float, float, float],
    ) -> tuple[float, float, float, float] | None:
        """
        Transform PDF coordinates to image coordinates.

        PDF uses bottom-left origin; images use top-left origin.

        Args:
            page_num: 0-indexed page number
            bbox: Bounding box as (x1, y1, x2, y2) in PDF coordinates

        Returns:
            Bounding box in image coordinates, or None if invalid
        """
        if not self._doc or page_num < 0 or page_num >= len(self._doc):
            return None

        page = self._doc[page_num]
        page_height = page.rect.height

        x1, y1, x2, y2 = bbox

        # Transform Y coordinates
        # PDF: y=0 at bottom, increases upward
        # Image: y=0 at top, increases downward
        img_y1 = page_height - max(y1, y2)  # Top in image coords
        img_y2 = page_height - min(y1, y2)  # Bottom in image coords

        return (min(x1, x2), img_y1, max(x1, x2), img_y2)


def render_pdf_cover(pdf_path: Path | str, max_height: int = 400) -> bytes | None:
    """
    Convenience function to render a PDF cover page.

    Args:
        pdf_path: Path to the PDF file
        max_height: Maximum height in pixels

    Returns:
        PNG image bytes, or None on error
    """
    try:
        with PDFRenderer(pdf_path) as renderer:
            return renderer.render_cover(max_height=max_height)
    except Exception as e:
        logger.error(f"Failed to render PDF cover: {e}")
        return None


def render_pdf_page(
    pdf_path: Path | str,
    page_num: int,
    dpi: int = 150,
) -> bytes | None:
    """
    Convenience function to render a single PDF page.

    Args:
        pdf_path: Path to the PDF file
        page_num: 0-indexed page number
        dpi: Resolution for rendering

    Returns:
        PNG image bytes, or None on error
    """
    try:
        with PDFRenderer(pdf_path) as renderer:
            return renderer.render_page(page_num, dpi=dpi)
    except Exception as e:
        logger.error(f"Failed to render PDF page: {e}")
        return None
