"""
PDF Color Contrast Checker.

Detects text with insufficient contrast against backgrounds by:
1. Rendering PDF pages at high resolution (300 DPI)
2. Using OCR (pytesseract) to detect text bounding boxes
3. Sampling foreground color from text pixels
4. Sampling background color from surrounding area
5. Calculating WCAG contrast ratio
6. Reporting failures (< 4.5:1 for normal text, < 3.0:1 for large text)

This is computationally expensive and should be used selectively.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)


# WCAG 2.1 contrast requirements
NORMAL_TEXT_MIN_CONTRAST = 4.5  # AA for normal text
LARGE_TEXT_MIN_CONTRAST = 3.0   # AA for large text (18pt+ or 14pt bold)
LARGE_TEXT_PIXEL_HEIGHT = 24    # Approximate pixel height for 18pt at 96dpi


@dataclass
class ContrastIssue:
    """A detected contrast issue on a PDF page."""

    page: int  # 0-indexed
    bbox: tuple[int, int, int, int]  # (x0, y0, x1, y1) in pixels
    text_sample: str
    foreground_color: tuple[int, int, int]  # RGB
    background_color: tuple[int, int, int]  # RGB
    contrast_ratio: float
    is_large_text: bool
    required_ratio: float
    wcag_level: str = "AA"

    @property
    def display_page(self) -> int:
        """1-indexed page number."""
        return self.page + 1

    @property
    def passes(self) -> bool:
        """Whether this text passes WCAG requirements."""
        return self.contrast_ratio >= self.required_ratio

    @property
    def fg_hex(self) -> str:
        """Foreground color as hex string."""
        return "#{:02x}{:02x}{:02x}".format(*self.foreground_color)

    @property
    def bg_hex(self) -> str:
        """Background color as hex string."""
        return "#{:02x}{:02x}{:02x}".format(*self.background_color)

    @property
    def severity(self) -> str:
        """Issue severity based on how far below requirement."""
        if self.contrast_ratio >= self.required_ratio:
            return "pass"
        elif self.contrast_ratio >= self.required_ratio * 0.75:
            return "moderate"
        else:
            return "serious"


@dataclass
class PageContrastResult:
    """Contrast analysis result for a single page."""

    page: int  # 0-indexed
    issues: list[ContrastIssue] = field(default_factory=list)
    total_text_regions: int = 0
    passing_regions: int = 0
    failing_regions: int = 0
    scan_time_ms: float = 0.0
    error: str | None = None

    @property
    def display_page(self) -> int:
        """1-indexed page number."""
        return self.page + 1


@dataclass
class ContrastAnalysisResult:
    """Complete contrast analysis result."""

    pages: list[PageContrastResult] = field(default_factory=list)
    total_pages_analyzed: int = 0
    total_text_regions: int = 0
    total_issues: int = 0
    serious_issues: int = 0
    moderate_issues: int = 0

    @property
    def has_issues(self) -> bool:
        """Whether any contrast issues were found."""
        return self.total_issues > 0


def _calculate_relative_luminance(color: tuple[int, int, int]) -> float:
    """
    Calculate relative luminance of an sRGB color.

    Based on WCAG 2.1 definition:
    https://www.w3.org/TR/WCAG21/#dfn-relative-luminance
    """
    def channel_luminance(c: int) -> float:
        srgb = c / 255.0
        if srgb <= 0.04045:
            return srgb / 12.92
        return ((srgb + 0.055) / 1.055) ** 2.4

    r, g, b = color
    return 0.2126 * channel_luminance(r) + 0.7152 * channel_luminance(g) + 0.0722 * channel_luminance(b)


def calculate_contrast_ratio(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    """
    Calculate WCAG contrast ratio between two colors.

    Returns:
        Contrast ratio (1.0 to 21.0)
    """
    lum_fg = _calculate_relative_luminance(fg)
    lum_bg = _calculate_relative_luminance(bg)

    lighter = max(lum_fg, lum_bg)
    darker = min(lum_fg, lum_bg)

    return (lighter + 0.05) / (darker + 0.05)


def _sample_dominant_color(
    image,
    bbox: tuple[int, int, int, int],
    sample_count: int = 100,
) -> tuple[int, int, int]:
    """
    Sample the dominant color in a bounding box region.

    Args:
        image: PIL Image
        bbox: (x0, y0, x1, y1) bounding box
        sample_count: Number of pixels to sample

    Returns:
        RGB tuple of dominant color
    """
    import random
    from collections import Counter

    x0, y0, x1, y1 = bbox
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(image.width, x1), min(image.height, y1)

    if x1 <= x0 or y1 <= y0:
        return (0, 0, 0)

    # Sample random pixels
    pixels = []
    for _ in range(sample_count):
        x = random.randint(x0, x1 - 1)
        y = random.randint(y0, y1 - 1)
        pixel = image.getpixel((x, y))
        if isinstance(pixel, tuple):
            pixels.append(pixel[:3])  # RGB only
        else:
            pixels.append((pixel, pixel, pixel))  # Grayscale

    # Find most common color (quantized to reduce noise)
    quantized = [((p[0] // 16) * 16, (p[1] // 16) * 16, (p[2] // 16) * 16) for p in pixels]
    if not quantized:
        return (0, 0, 0)

    most_common = Counter(quantized).most_common(1)[0][0]
    return most_common


def _get_background_color(
    image,
    text_bbox: tuple[int, int, int, int],
    padding: int = 5,
) -> tuple[int, int, int]:
    """
    Sample background color around a text region.

    Expands the bounding box slightly and samples from the edges
    to get the most likely background color.
    """
    x0, y0, x1, y1 = text_bbox

    # Sample from above the text
    top_region = (x0, max(0, y0 - padding * 2), x1, y0)
    # Sample from below the text
    bottom_region = (x0, y1, x1, min(image.height, y1 + padding * 2))
    # Sample from left of text
    left_region = (max(0, x0 - padding * 2), y0, x0, y1)
    # Sample from right of text
    right_region = (x1, y0, min(image.width, x1 + padding * 2), y1)

    # Combine samples from all regions
    colors = []
    for region in [top_region, bottom_region, left_region, right_region]:
        if region[2] > region[0] and region[3] > region[1]:
            color = _sample_dominant_color(image, region, sample_count=25)
            colors.append(color)

    if not colors:
        return (255, 255, 255)  # Default to white

    # Average the sampled colors
    avg_r = sum(c[0] for c in colors) // len(colors)
    avg_g = sum(c[1] for c in colors) // len(colors)
    avg_b = sum(c[2] for c in colors) // len(colors)

    return (avg_r, avg_g, avg_b)


class PDFContrastChecker:
    """
    Checks PDF pages for color contrast issues.

    Requires:
    - PyMuPDF for page rendering
    - pytesseract for OCR text detection
    - Pillow for image processing
    """

    def __init__(self, pdf_path: Path | str):
        """
        Initialize the checker.

        Args:
            pdf_path: Path to the PDF file
        """
        self.pdf_path = Path(pdf_path)
        self._fitz_doc = None

    def __enter__(self) -> PDFContrastChecker:
        """Open PDF file."""
        try:
            import fitz
            self._fitz_doc = fitz.open(self.pdf_path)
        except ImportError:
            raise RuntimeError("PyMuPDF required for contrast checking: pip install pymupdf")
        except Exception as e:
            raise RuntimeError(f"Failed to open PDF: {e}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close PDF file."""
        if self._fitz_doc:
            self._fitz_doc.close()
            self._fitz_doc = None

    def _check_tesseract_available(self) -> bool:
        """Check if pytesseract is available and configured."""
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def analyze_page(
        self,
        page_num: int,
        dpi: int = 300,
        lang: str = "eng",
    ) -> PageContrastResult:
        """
        Analyze a single page for contrast issues.

        Args:
            page_num: 0-indexed page number
            dpi: Rendering resolution (higher = more accurate but slower)
            lang: Tesseract language code

        Returns:
            PageContrastResult with detected issues
        """
        import time

        from PIL import Image

        start_time = time.time()
        result = PageContrastResult(page=page_num)

        if not self._fitz_doc or page_num >= len(self._fitz_doc):
            result.error = "Invalid page number"
            return result

        try:
            import pytesseract
        except ImportError:
            result.error = "pytesseract not installed: pip install pytesseract"
            return result

        try:
            import fitz

            # Render page at high DPI
            page = self._fitz_doc[page_num]
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            # Convert to PIL Image
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            # Run OCR to get text bounding boxes
            ocr_data = pytesseract.image_to_data(
                img,
                lang=lang,
                output_type=pytesseract.Output.DICT,
            )

            # Process each detected text region
            n_boxes = len(ocr_data["text"])
            for i in range(n_boxes):
                text = ocr_data["text"][i].strip()
                if not text:
                    continue

                result.total_text_regions += 1

                # Get bounding box
                x = ocr_data["left"][i]
                y = ocr_data["top"][i]
                w = ocr_data["width"][i]
                h = ocr_data["height"][i]
                bbox = (x, y, x + w, y + h)

                # Determine if large text
                is_large = h >= LARGE_TEXT_PIXEL_HEIGHT * (dpi / 96)
                required_ratio = LARGE_TEXT_MIN_CONTRAST if is_large else NORMAL_TEXT_MIN_CONTRAST

                # Sample colors
                fg_color = _sample_dominant_color(img, bbox)
                bg_color = _get_background_color(img, bbox)

                # Calculate contrast
                ratio = calculate_contrast_ratio(fg_color, bg_color)

                # Check if failing
                if ratio < required_ratio:
                    result.failing_regions += 1
                    result.issues.append(ContrastIssue(
                        page=page_num,
                        bbox=bbox,
                        text_sample=text[:50],
                        foreground_color=fg_color,
                        background_color=bg_color,
                        contrast_ratio=ratio,
                        is_large_text=is_large,
                        required_ratio=required_ratio,
                    ))
                else:
                    result.passing_regions += 1

        except Exception as e:
            logger.warning(f"Error analyzing page {page_num + 1}: {e}")
            result.error = str(e)

        result.scan_time_ms = (time.time() - start_time) * 1000
        return result

    def analyze_document(
        self,
        pages: list[int] | None = None,
        dpi: int = 300,
        lang: str = "eng",
        max_issues_per_page: int = 20,
        progress_callback=None,
    ) -> ContrastAnalysisResult:
        """
        Analyze multiple pages for contrast issues.

        Args:
            pages: List of 0-indexed page numbers (default: all)
            dpi: Rendering resolution
            lang: Tesseract language code
            max_issues_per_page: Maximum issues to report per page
            progress_callback: Optional callback(current, total)

        Returns:
            ContrastAnalysisResult with all issues
        """
        result = ContrastAnalysisResult()

        if pages is None:
            pages = list(range(len(self._fitz_doc))) if self._fitz_doc else []

        result.total_pages_analyzed = len(pages)

        for idx, page_num in enumerate(pages):
            if progress_callback:
                progress_callback(idx + 1, len(pages))

            page_result = self.analyze_page(page_num, dpi=dpi, lang=lang)

            # Limit issues per page
            if len(page_result.issues) > max_issues_per_page:
                page_result.issues = page_result.issues[:max_issues_per_page]

            result.pages.append(page_result)
            result.total_text_regions += page_result.total_text_regions
            result.total_issues += len(page_result.issues)

            for issue in page_result.issues:
                if issue.severity == "serious":
                    result.serious_issues += 1
                elif issue.severity == "moderate":
                    result.moderate_issues += 1

        return result


def check_tesseract_available() -> bool:
    """Check if Tesseract OCR is available."""
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False
