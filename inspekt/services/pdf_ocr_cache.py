"""
PDF OCR Cache - Consolidated OCR for PDF Analysis.

Runs Tesseract OCR once per page and caches results for reuse by:
- Text layer analysis (pdf_ocr.py) - uses raw_text
- Contrast checking (pdf_contrast_checker.py) - uses text_lines with bboxes
- Text-as-image analysis - uses text_lines for detected text regions

Key optimization: pytesseract.image_to_data() returns BOTH text AND
bounding boxes in a single call, enabling significant performance gains.

Usage:
    with PDFOCRCache(pdf_path) as cache:
        # Get text lines for contrast analysis
        lines = cache.get_text_lines(page_num=0)

        # Get raw text for text layer comparison
        text = cache.get_raw_text(page_num=0)

        # Get the rendered image for color sampling
        image = cache.get_page_image(page_num=0)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

logger = logging.getLogger(__name__)

# Default OCR settings
DEFAULT_DPI = 200  # Balance between speed and accuracy
MIN_OCR_CONFIDENCE = 60  # Skip low-confidence results


@dataclass
class TextLine:
    """
    A line of text detected by OCR with bounding box.

    Attributes:
        text: The detected text content
        bbox: Bounding box as (x0, y0, x1, y1) in pixels
        height: Line height in pixels (for large text detection)
        confidence: OCR confidence score (0-100)
    """

    text: str
    bbox: tuple[int, int, int, int]  # (x0, y0, x1, y1)
    height: int
    confidence: float

    @property
    def width(self) -> int:
        """Line width in pixels."""
        return self.bbox[2] - self.bbox[0]

    @property
    def center(self) -> tuple[int, int]:
        """Center point of the bounding box."""
        x0, y0, x1, y1 = self.bbox
        return ((x0 + x1) // 2, (y0 + y1) // 2)


@dataclass
class PageOCRResult:
    """
    Cached OCR result for a single PDF page.

    Contains both structured (text_lines) and raw (raw_text) data
    to serve different analysis needs from a single OCR run.
    """

    page_num: int  # 0-indexed
    text_lines: list[TextLine] = field(default_factory=list)
    raw_text: str = ""
    render_time_ms: float = 0.0
    ocr_time_ms: float = 0.0
    image_width: int = 0
    image_height: int = 0
    error: str | None = None

    @property
    def total_time_ms(self) -> float:
        """Total processing time."""
        return self.render_time_ms + self.ocr_time_ms

    @property
    def line_count(self) -> int:
        """Number of text lines detected."""
        return len(self.text_lines)

    @property
    def char_count(self) -> int:
        """Total characters in raw text."""
        return len(self.raw_text)

    @property
    def word_count(self) -> int:
        """Word count from raw text."""
        return len(self.raw_text.split())


class PDFOCRCache:
    """
    Runs OCR once per page and caches results for reuse.

    This class consolidates OCR operations that were previously scattered
    across pdf_ocr.py, pdf_contrast_checker.py, and image_classifier.py.

    Uses pytesseract.image_to_data() which returns both text and bounding
    boxes in a single call, enabling both text extraction and contrast
    analysis from the same OCR run.

    Example:
        with PDFOCRCache(pdf_path, dpi=200) as cache:
            # Contrast analysis
            for line in cache.get_text_lines(0):
                analyze_contrast(cache.get_page_image(0), line.bbox)

            # Text comparison
            ocr_text = cache.get_raw_text(0)
            pdf_text = extract_pdf_text(pdf_path, 0)
            similarity = compare_texts(pdf_text, ocr_text)
    """

    def __init__(
        self,
        pdf_path: Path | str,
        dpi: int = DEFAULT_DPI,
        language: str = "eng",
        min_confidence: int = MIN_OCR_CONFIDENCE,
    ):
        """
        Initialize the OCR cache.

        Args:
            pdf_path: Path to the PDF file
            dpi: Rendering resolution (higher = better OCR but slower)
            language: Tesseract language code (e.g., "eng", "nld", "fra")
            min_confidence: Minimum OCR confidence to include (0-100)
        """
        self.pdf_path = Path(pdf_path)
        self.dpi = dpi
        self.language = language
        self.min_confidence = min_confidence

        self._cache: dict[int, PageOCRResult] = {}
        self._image_cache: dict[int, Image.Image] = {}
        self._fitz_doc = None

    def __enter__(self) -> PDFOCRCache:
        """Open PDF document."""
        try:
            import fitz

            self._fitz_doc = fitz.open(self.pdf_path)
        except ImportError:
            raise RuntimeError("PyMuPDF required: pip install pymupdf")
        except Exception as e:
            raise RuntimeError(f"Failed to open PDF: {e}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close PDF and clear caches."""
        if self._fitz_doc:
            self._fitz_doc.close()
            self._fitz_doc = None
        self._cache.clear()
        self._image_cache.clear()

    @property
    def page_count(self) -> int:
        """Number of pages in the PDF."""
        return len(self._fitz_doc) if self._fitz_doc else 0

    def _ensure_page_processed(self, page_num: int) -> PageOCRResult:
        """
        Ensure a page has been OCR'd, processing it if needed.

        This is the core method that runs OCR once and caches the result.
        """
        if page_num in self._cache:
            return self._cache[page_num]

        result = self._process_page(page_num)
        self._cache[page_num] = result
        return result

    def _process_page(self, page_num: int) -> PageOCRResult:
        """
        Render and OCR a single page.

        Uses pytesseract.image_to_data() to get both text and bounding
        boxes in a single call.
        """
        import fitz
        from PIL import Image

        result = PageOCRResult(page_num=page_num)

        if not self._fitz_doc or page_num >= len(self._fitz_doc):
            result.error = f"Invalid page number: {page_num}"
            return result

        # Check OCR availability
        try:
            import pytesseract
        except ImportError:
            result.error = "pytesseract not installed: pip install pytesseract"
            return result

        try:
            # Step 1: Render page to image
            render_start = time.time()

            page = self._fitz_doc[page_num]
            zoom = self.dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            # Convert to PIL Image
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            result.render_time_ms = (time.time() - render_start) * 1000
            result.image_width = pix.width
            result.image_height = pix.height

            # Cache the image for later color sampling
            self._image_cache[page_num] = img

            # Step 2: Run OCR with image_to_data for structured output
            ocr_start = time.time()

            # PSM 4: Single column, variable text sizes
            # This handles multi-column layouts better and gives line-level data
            ocr_data = pytesseract.image_to_data(
                img,
                lang=self.language,
                config="--psm 4",
                output_type=pytesseract.Output.DICT,
            )

            result.ocr_time_ms = (time.time() - ocr_start) * 1000

            # Step 3: Process OCR output into text lines
            text_lines, raw_text = self._process_ocr_data(ocr_data)
            result.text_lines = text_lines
            result.raw_text = raw_text

        except Exception as e:
            logger.warning(f"OCR failed for page {page_num + 1}: {e}")
            result.error = str(e)

        return result

    def _process_ocr_data(
        self,
        ocr_data: dict,
    ) -> tuple[list[TextLine], str]:
        """
        Process pytesseract output into structured TextLine objects.

        Groups word-level entries into lines based on block/paragraph/line
        numbers from Tesseract.

        Returns:
            Tuple of (text_lines, raw_text)
        """
        # Build lines from word-level entries (level 5)
        # Tesseract levels: 1=page, 2=block, 3=paragraph, 4=line, 5=word
        lines_dict: dict[tuple[int, int, int], dict] = {}
        raw_words: list[str] = []

        n_boxes = len(ocr_data.get("text", []))

        for i in range(n_boxes):
            level = ocr_data["level"][i]

            # Only process word-level entries with text and good confidence
            if level != 5:  # Word level
                continue

            text = ocr_data["text"][i].strip()
            conf = ocr_data["conf"][i]

            if not text:
                continue

            # Collect all words for raw text (even low confidence)
            raw_words.append(text)

            # Filter by confidence for structured lines
            if conf < self.min_confidence:
                continue

            # Create unique line key from block/paragraph/line numbers
            line_key = (
                ocr_data["block_num"][i],
                ocr_data["par_num"][i],
                ocr_data["line_num"][i],
            )

            x = ocr_data["left"][i]
            y = ocr_data["top"][i]
            w = ocr_data["width"][i]
            h = ocr_data["height"][i]

            if line_key not in lines_dict:
                lines_dict[line_key] = {
                    "x0": x,
                    "y0": y,
                    "x1": x + w,
                    "y1": y + h,
                    "height": h,
                    "words": [text],
                    "conf_sum": conf,
                    "word_count": 1,
                }
            else:
                # Expand bounding box to include this word
                line = lines_dict[line_key]
                line["x0"] = min(line["x0"], x)
                line["y0"] = min(line["y0"], y)
                line["x1"] = max(line["x1"], x + w)
                line["y1"] = max(line["y1"], y + h)
                line["height"] = max(line["height"], h)
                line["words"].append(text)
                line["conf_sum"] += conf
                line["word_count"] += 1

        # Convert to TextLine objects
        text_lines = []
        for line_data in lines_dict.values():
            text_lines.append(
                TextLine(
                    text=" ".join(line_data["words"]),
                    bbox=(
                        line_data["x0"],
                        line_data["y0"],
                        line_data["x1"],
                        line_data["y1"],
                    ),
                    height=line_data["height"],
                    confidence=line_data["conf_sum"] / line_data["word_count"],
                )
            )

        # Build raw text (preserving some structure)
        raw_text = " ".join(raw_words)

        return text_lines, raw_text

    def get_text_lines(self, page_num: int) -> list[TextLine]:
        """
        Get text lines with bounding boxes for contrast analysis.

        Args:
            page_num: 0-indexed page number

        Returns:
            List of TextLine objects with text and bboxes
        """
        result = self._ensure_page_processed(page_num)
        return result.text_lines

    def get_raw_text(self, page_num: int) -> str:
        """
        Get raw OCR text for text layer comparison.

        Args:
            page_num: 0-indexed page number

        Returns:
            Raw text string from OCR
        """
        result = self._ensure_page_processed(page_num)
        return result.raw_text

    def get_page_image(self, page_num: int) -> Image.Image | None:
        """
        Get the rendered page image for color sampling.

        The image is cached after the first OCR run for that page.

        Args:
            page_num: 0-indexed page number

        Returns:
            PIL Image or None if not available
        """
        # Ensure page is processed (which caches the image)
        self._ensure_page_processed(page_num)
        return self._image_cache.get(page_num)

    def get_page_result(self, page_num: int) -> PageOCRResult:
        """
        Get full OCR result for a page.

        Args:
            page_num: 0-indexed page number

        Returns:
            PageOCRResult with all OCR data
        """
        return self._ensure_page_processed(page_num)

    def preload_pages(
        self,
        page_nums: list[int] | None = None,
        progress_callback=None,
    ) -> None:
        """
        Preload OCR results for multiple pages.

        Useful for batch processing where you want to control the order
        of processing or show progress.

        Args:
            page_nums: List of page numbers to preload (default: all)
            progress_callback: Optional callback(current, total)
        """
        if page_nums is None:
            page_nums = list(range(self.page_count))

        for idx, page_num in enumerate(page_nums):
            if progress_callback:
                progress_callback(idx + 1, len(page_nums))
            self._ensure_page_processed(page_num)

    def get_statistics(self) -> dict:
        """
        Get cache statistics for debugging/logging.

        Returns:
            Dictionary with cache statistics
        """
        total_render = sum(r.render_time_ms for r in self._cache.values())
        total_ocr = sum(r.ocr_time_ms for r in self._cache.values())
        total_lines = sum(r.line_count for r in self._cache.values())

        return {
            "pages_cached": len(self._cache),
            "total_render_time_ms": total_render,
            "total_ocr_time_ms": total_ocr,
            "total_time_ms": total_render + total_ocr,
            "total_text_lines": total_lines,
            "avg_lines_per_page": total_lines / len(self._cache) if self._cache else 0,
        }


def select_pages_with_heading_priority(
    total_pages: int,
    heading_outline: list | None = None,
    max_pages: int = 10,
) -> list[int]:
    """
    Select pages for analysis, prioritizing those with important headings.

    This enables "smart sampling" - instead of evenly distributing pages,
    we prioritize pages that contain H1/H2 headings (main sections) since
    these are more likely to have representative styling.

    Strategy:
    1. Always include first page (title/cover)
    2. Include pages with H1/H2 headings (main sections)
    3. Fill remaining slots with even distribution

    Args:
        total_pages: Total pages in the document
        heading_outline: List of HeadingOutlineItem from structure extraction
        max_pages: Maximum pages to analyze

    Returns:
        Sorted list of 0-indexed page numbers
    """
    if total_pages <= max_pages:
        return list(range(total_pages))

    selected = {0}  # Always include first page

    # Add pages with H1/H2 headings
    if heading_outline:
        for heading in heading_outline:
            if heading.level <= 2 and heading.page is not None:
                selected.add(heading.page)
                if len(selected) >= max_pages:
                    break

    # Fill remaining slots with even distribution
    if len(selected) < max_pages:
        remaining_slots = max_pages - len(selected)
        # Calculate step size for even distribution
        step = total_pages / (remaining_slots + 1)

        for i in range(1, remaining_slots + 1):
            page = int(i * step)
            if page < total_pages:
                selected.add(page)

    # Sort and limit
    return sorted(selected)[:max_pages]


def check_ocr_available() -> tuple[bool, str | None]:
    """
    Check if OCR dependencies are available.

    Returns:
        Tuple of (is_available, reason_if_not)
    """
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True, None
    except ImportError:
        return False, "pytesseract not installed: pip install pytesseract"
    except Exception as e:
        return False, f"Tesseract OCR not available: {e}"
