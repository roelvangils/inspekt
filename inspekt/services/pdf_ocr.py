"""
PDF OCR Service for Text Layer Comparison.

Compares the embedded text layer of a PDF with OCR-extracted text
to detect scanned/image-only documents that may have incomplete
or missing text layers.

Implements graceful degradation:
- If Tesseract is not installed, OCR features are silently disabled
- If pytesseract is not installed, appropriate hints are shown

Usage:
    # Check availability
    if is_tesseract_available():
        result = compare_text_layers(pdf_path)

    # Or use the higher-level function that handles unavailability
    result = analyze_text_discrepancy(pdf_path, config)
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inspekt.services.pdf_renderer import PDFRenderer

logger = logging.getLogger(__name__)


# Re-export OCR availability functions from the global service
# This maintains backward compatibility for existing imports
from inspekt.services.ocr_service import (  # noqa: E402
    get_ocr_availability,
    is_pytesseract_available,
    is_tesseract_available,
)


@dataclass
class TextDiff:
    """
    A single diff segment showing changes between PDF and OCR text.

    Used for character-level comparison visualization.
    """

    diff_type: str  # "equal", "insert", "delete", "replace"
    pdf_segment: str  # Text from PDF layer
    ocr_segment: str  # Text from OCR
    position: int  # Starting position in original text

    @property
    def is_change(self) -> bool:
        """Check if this segment represents a change."""
        return self.diff_type != "equal"

    @property
    def html_pdf_class(self) -> str:
        """CSS class for PDF side visualization."""
        return {"equal": "", "insert": "", "delete": "diff-delete", "replace": "diff-replace"}[
            self.diff_type
        ]

    @property
    def html_ocr_class(self) -> str:
        """CSS class for OCR side visualization."""
        return {"equal": "", "insert": "diff-insert", "delete": "", "replace": "diff-replace"}[
            self.diff_type
        ]


@dataclass
class TextDiffResult:
    """
    Complete character-level diff result for a page.
    """

    diffs: list[TextDiff] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    replacements: int = 0
    unchanged_ratio: float = 0.0

    @property
    def total_changes(self) -> int:
        """Total number of change segments."""
        return self.insertions + self.deletions + self.replacements

    @property
    def has_changes(self) -> bool:
        """Check if there are any differences."""
        return self.total_changes > 0


@dataclass
class PageTextComparison:
    """
    Comparison result for a single page.
    """

    page_num: int  # 0-indexed
    pdf_text: str
    ocr_text: str
    similarity: float  # 0.0 to 1.0
    pdf_char_count: int
    ocr_char_count: int
    diff_result: TextDiffResult | None = None  # Character-level diff
    thumbnail_base64: str | None = None  # Base64-encoded page thumbnail (small)
    lightbox_base64: str | None = None  # Base64-encoded larger image for lightbox

    @property
    def has_significant_discrepancy(self) -> bool:
        """Check if there's a significant difference between layers."""
        # Significant if similarity < 0.9 or char counts differ by > 20%
        if self.similarity < 0.9:
            return True

        if self.pdf_char_count == 0 and self.ocr_char_count > 50:
            return True  # PDF has no text but OCR found content

        if self.pdf_char_count > 0:
            ratio = abs(self.pdf_char_count - self.ocr_char_count) / self.pdf_char_count
            if ratio > 0.2:
                return True

        return False

    @property
    def is_image_only(self) -> bool:
        """Check if page appears to be image-only (no PDF text but OCR found text)."""
        return self.pdf_char_count < 20 and self.ocr_char_count > 50


@dataclass
class TextDiscrepancyResult:
    """
    Result of analyzing text layer discrepancies across a PDF.
    """

    pages_analyzed: int
    pages_with_discrepancy: int
    image_only_pages: int
    overall_similarity: float
    page_comparisons: list[PageTextComparison] = field(default_factory=list)
    ocr_available: bool = True
    unavailable_reason: str | None = None
    # Sampling information
    is_sampled: bool = False  # True if not all pages were analyzed
    total_document_pages: int = 0  # Total pages in the PDF
    sampling_description: str | None = None  # e.g., "50 of 333 pages (sampled)"

    @property
    def is_likely_scanned(self) -> bool:
        """Check if document appears to be predominantly scanned."""
        if self.pages_analyzed == 0:
            return False

        # If > 50% of pages are image-only, likely scanned
        image_ratio = self.image_only_pages / self.pages_analyzed
        return image_ratio > 0.5

    @property
    def needs_warning(self) -> bool:
        """Check if a warning should be shown about text layer issues."""
        return self.is_likely_scanned or self.pages_with_discrepancy > 0

    @property
    def problematic_pages(self) -> list[PageTextComparison]:
        """Return pages with significant discrepancies."""
        return [p for p in self.page_comparisons if p.has_significant_discrepancy]


class PDFOCRService:
    """
    OCR service for PDF text comparison.

    Uses Tesseract OCR (via pytesseract) to extract text from rendered
    PDF pages and compare with the embedded text layer.
    """

    def __init__(self, language: str = "eng"):
        """
        Initialize the OCR service.

        Args:
            language: Tesseract language code (default: "eng" for English).
                      Use "nld" for Dutch, "fra" for French, etc.

        Raises:
            ImportError: If pytesseract is not installed
            RuntimeError: If Tesseract binary is not available
        """
        if not is_pytesseract_available():
            raise ImportError(
                "pytesseract is required for OCR. Install it with: pip install pytesseract"
            )

        if not is_tesseract_available():
            raise RuntimeError(
                "Tesseract OCR is not installed. "
                "Install it with: brew install tesseract (macOS) or "
                "apt-get install tesseract-ocr (Ubuntu)"
            )

        self.language = language

    def ocr_image(self, image_bytes: bytes) -> str:
        """
        Perform OCR on an image.

        Args:
            image_bytes: PNG or JPEG image data

        Returns:
            Extracted text string
        """
        import pytesseract
        from PIL import Image

        image = Image.open(BytesIO(image_bytes))
        text = pytesseract.image_to_string(image, lang=self.language)
        return _normalize_text(text)

    def ocr_page(
        self,
        renderer: PDFRenderer,
        page_num: int,
        dpi: int = 150,
    ) -> str:
        """
        Perform OCR on a rendered PDF page.

        Args:
            renderer: PDFRenderer instance
            page_num: 0-indexed page number
            dpi: Resolution for rendering (higher = better OCR but slower)

        Returns:
            Extracted text string
        """
        image_bytes = renderer.render_page(page_num, dpi=dpi)
        return self.ocr_image(image_bytes)


def extract_pdf_text(pdf_path: Path | str, page_num: int) -> str:
    """
    Extract the embedded text layer from a PDF page.

    Uses pdfminer.six for text extraction.

    Args:
        pdf_path: Path to the PDF file
        page_num: 0-indexed page number

    Returns:
        Extracted text string
    """
    try:
        from pdfminer.high_level import extract_text
        from pdfminer.pdfpage import PDFPage

        with open(pdf_path, "rb") as f:
            pages = list(PDFPage.get_pages(f, pagenos=[page_num]))
            if not pages:
                return ""

        # Extract text for specific page
        text = extract_text(str(pdf_path), page_numbers=[page_num])
        return _normalize_text(text)
    except Exception as e:
        logger.warning(f"Failed to extract PDF text from page {page_num}: {e}")
        return ""


def _normalize_text(text: str) -> str:
    """
    Normalize text for comparison.

    - Convert to lowercase
    - Remove excess whitespace
    - Remove special characters that OCR often misreads
    """
    text = text.lower()
    text = re.sub(r"\s+", " ", text)  # Collapse whitespace
    text = re.sub(r"[^\w\s]", "", text)  # Remove punctuation
    return text.strip()


def compare_texts(pdf_text: str, ocr_text: str) -> float:
    """
    Calculate similarity between PDF text and OCR text.

    Uses difflib's SequenceMatcher for a ratio between 0 and 1.

    Args:
        pdf_text: Text from PDF layer
        ocr_text: Text from OCR

    Returns:
        Similarity ratio (0.0 to 1.0)
    """
    if not pdf_text and not ocr_text:
        return 1.0  # Both empty = identical

    if not pdf_text or not ocr_text:
        return 0.0  # One empty = completely different

    # Use SequenceMatcher for fuzzy comparison
    return SequenceMatcher(None, pdf_text, ocr_text).ratio()


def generate_character_diff(
    pdf_text: str,
    ocr_text: str,
    max_segments: int = 100,
) -> TextDiffResult:
    """
    Generate character-level diff between PDF and OCR text.

    Uses difflib to identify insertions, deletions, and replacements
    at the word level for clearer visualization.

    Args:
        pdf_text: Text from PDF layer
        ocr_text: Text from OCR
        max_segments: Maximum diff segments to return (for performance)

    Returns:
        TextDiffResult with detailed diff information
    """
    from difflib import SequenceMatcher

    diffs: list[TextDiff] = []
    insertions = 0
    deletions = 0
    replacements = 0
    equal_chars = 0
    total_chars = max(len(pdf_text), len(ocr_text), 1)

    # Handle empty cases
    if not pdf_text and not ocr_text:
        return TextDiffResult(unchanged_ratio=1.0)

    if not pdf_text:
        return TextDiffResult(
            diffs=[TextDiff("insert", "", ocr_text[:500], 0)],
            insertions=1,
            unchanged_ratio=0.0,
        )

    if not ocr_text:
        return TextDiffResult(
            diffs=[TextDiff("delete", pdf_text[:500], "", 0)],
            deletions=1,
            unchanged_ratio=0.0,
        )

    # Split into words for more meaningful diffs
    pdf_words = pdf_text.split()
    ocr_words = ocr_text.split()

    matcher = SequenceMatcher(None, pdf_words, ocr_words)
    position = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        pdf_segment = " ".join(pdf_words[i1:i2])
        ocr_segment = " ".join(ocr_words[j1:j2])

        if len(diffs) >= max_segments:
            break

        if tag == "equal":
            equal_chars += len(pdf_segment)
            # Only include context if it's short or at boundaries
            if len(pdf_segment) <= 50 or len(diffs) < 3 or len(diffs) >= max_segments - 3:
                diffs.append(
                    TextDiff(
                        diff_type="equal",
                        pdf_segment=pdf_segment[:100],
                        ocr_segment=ocr_segment[:100],
                        position=position,
                    )
                )
            elif diffs and diffs[-1].diff_type == "equal":
                # Merge consecutive equal segments
                pass
            else:
                # Add ellipsis placeholder for long unchanged sections
                diffs.append(
                    TextDiff(
                        diff_type="equal",
                        pdf_segment="…",
                        ocr_segment="…",
                        position=position,
                    )
                )

        elif tag == "replace":
            replacements += 1
            diffs.append(
                TextDiff(
                    diff_type="replace",
                    pdf_segment=pdf_segment[:200],
                    ocr_segment=ocr_segment[:200],
                    position=position,
                )
            )

        elif tag == "delete":
            deletions += 1
            diffs.append(
                TextDiff(
                    diff_type="delete",
                    pdf_segment=pdf_segment[:200],
                    ocr_segment="",
                    position=position,
                )
            )

        elif tag == "insert":
            insertions += 1
            diffs.append(
                TextDiff(
                    diff_type="insert",
                    pdf_segment="",
                    ocr_segment=ocr_segment[:200],
                    position=position,
                )
            )

        position += len(pdf_segment)

    unchanged_ratio = equal_chars / total_chars if total_chars > 0 else 1.0

    return TextDiffResult(
        diffs=diffs,
        insertions=insertions,
        deletions=deletions,
        replacements=replacements,
        unchanged_ratio=unchanged_ratio,
    )


def generate_diff_html(diff_result: TextDiffResult, side: str = "both") -> str:
    """
    Generate HTML visualization of text differences.

    Args:
        diff_result: TextDiffResult from generate_character_diff
        side: "pdf", "ocr", or "both" for side-by-side

    Returns:
        HTML string with highlighted differences
    """
    if not diff_result.diffs:
        return "<p>No text to compare</p>"

    if side == "both":
        pdf_html = _generate_side_html(diff_result, "pdf")
        ocr_html = _generate_side_html(diff_result, "ocr")
        return f"""
        <div class="diff-comparison">
            <div class="diff-side pdf-side">
                <h4>PDF Text Layer</h4>
                <pre>{pdf_html}</pre>
            </div>
            <div class="diff-side ocr-side">
                <h4>OCR Result</h4>
                <pre>{ocr_html}</pre>
            </div>
        </div>
        """
    else:
        return _generate_side_html(diff_result, side)


def _generate_side_html(diff_result: TextDiffResult, side: str) -> str:
    """Generate HTML for one side of the diff."""
    import html

    parts = []
    for diff in diff_result.diffs:
        text = diff.pdf_segment if side == "pdf" else diff.ocr_segment
        escaped = html.escape(text)

        if diff.diff_type == "equal":
            parts.append(escaped)
        elif diff.diff_type == "replace":
            css_class = diff.html_pdf_class if side == "pdf" else diff.html_ocr_class
            parts.append(f'<span class="{css_class}">{escaped}</span>')
        elif diff.diff_type == "delete" and side == "pdf":
            parts.append(f'<span class="diff-delete">{escaped}</span>')
        elif diff.diff_type == "insert" and side == "ocr":
            parts.append(f'<span class="diff-insert">{escaped}</span>')

    return " ".join(parts)


def _select_pages_for_analysis(
    total_pages: int,
    max_pages: int = 50,
    analyze_all: bool = False,
) -> tuple[list[int], bool]:
    """
    Select pages for OCR analysis using smart sampling.

    For large documents, this uses stratified sampling to ensure coverage
    of front matter, middle content, and back matter.

    Args:
        total_pages: Total number of pages in the PDF
        max_pages: Maximum pages to analyze (default 50)
        analyze_all: If True, analyze all pages regardless of max_pages

    Returns:
        tuple: (list of 0-indexed page numbers, is_sampled flag)

    Strategy:
    - If analyze_all=True: return all pages
    - If total_pages <= max_pages: analyze all pages
    - If total_pages > max_pages: sample representatively
      - First 10 pages (important front matter)
      - Last 5 pages (appendices, back matter)
      - 35 random pages from the middle
    """
    import random

    if analyze_all or total_pages <= max_pages:
        return list(range(total_pages)), False

    # Smart sampling for large documents
    first_count = min(10, total_pages)  # First 10 pages
    last_count = min(5, total_pages)  # Last 5 pages
    middle_sample_count = max_pages - first_count - last_count  # Remaining for middle

    first_pages = list(range(first_count))  # Pages 0-9 (or fewer)
    last_pages = list(range(total_pages - last_count, total_pages))  # Last 5

    # Middle section: sample from remaining pages (10 to total-5)
    middle_start = first_count
    middle_end = total_pages - last_count

    if middle_end > middle_start:
        middle_range = list(range(middle_start, middle_end))
        # Use fixed seed for reproducibility - same PDF always gets same pages
        random.seed(42)
        middle_pages = sorted(
            random.sample(middle_range, min(middle_sample_count, len(middle_range)))
        )
    else:
        middle_pages = []

    # Combine and deduplicate
    all_pages = sorted(set(first_pages + middle_pages + last_pages))

    return all_pages, True


def _render_page_thumbnail(
    renderer: PDFRenderer,
    page_num: int,
    max_size: int = 150,
) -> str | None:
    """
    Render a PDF page as a base64-encoded thumbnail.

    Args:
        renderer: PDFRenderer instance
        page_num: 0-indexed page number
        max_size: Maximum width/height in pixels (maintains aspect ratio)

    Returns:
        Base64-encoded PNG string, or None if rendering fails
    """
    try:
        from PIL import Image

        # Render at low DPI for thumbnail (72 DPI is sufficient)
        png_bytes = renderer.render_page(page_num, dpi=72)

        # Resize with Pillow
        img = Image.open(BytesIO(png_bytes))
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

        # Convert to base64
        output = BytesIO()
        img.save(output, format="PNG", optimize=True)

        import base64

        return base64.b64encode(output.getvalue()).decode("ascii")
    except Exception as e:
        logger.warning(f"Failed to render thumbnail for page {page_num}: {e}")
        return None


def _render_page_images(
    renderer: PDFRenderer,
    page_num: int,
    thumbnail_size: int = 150,
    lightbox_size: int = 800,
) -> tuple[str | None, str | None]:
    """
    Render a PDF page as both a thumbnail and a larger lightbox image.

    Args:
        renderer: PDFRenderer instance
        page_num: 0-indexed page number
        thumbnail_size: Maximum width/height for thumbnail (default 150px)
        lightbox_size: Maximum width/height for lightbox (default 800px)

    Returns:
        Tuple of (thumbnail_base64, lightbox_base64), either may be None on failure
    """
    try:
        import base64

        from PIL import Image

        # Render at higher DPI for the lightbox version (150 DPI for better quality)
        png_bytes = renderer.render_page(page_num, dpi=150)
        img = Image.open(BytesIO(png_bytes))

        # Generate lightbox version first (from the higher-res source)
        lightbox_img = img.copy()
        lightbox_img.thumbnail((lightbox_size, lightbox_size), Image.Resampling.LANCZOS)
        lightbox_output = BytesIO()
        lightbox_img.save(lightbox_output, format="PNG", optimize=True)
        lightbox_base64 = base64.b64encode(lightbox_output.getvalue()).decode("ascii")

        # Generate thumbnail (smaller version)
        img.thumbnail((thumbnail_size, thumbnail_size), Image.Resampling.LANCZOS)
        thumb_output = BytesIO()
        img.save(thumb_output, format="PNG", optimize=True)
        thumbnail_base64 = base64.b64encode(thumb_output.getvalue()).decode("ascii")

        return thumbnail_base64, lightbox_base64
    except Exception as e:
        logger.warning(f"Failed to render images for page {page_num}: {e}")
        return None, None


def analyze_text_discrepancy(
    pdf_path: Path | str,
    config: dict | None = None,
) -> TextDiscrepancyResult:
    """
    Analyze text layer discrepancies in a PDF.

    This is the main entry point that handles graceful degradation
    when OCR is unavailable.

    Args:
        pdf_path: Path to the PDF file
        config: Optional configuration dict with:
            - max-ocr-pages: Maximum pages to analyze (default 50)
            - ocr-analyze-all: Analyze all pages when True
            - text-discrepancy-threshold: Similarity threshold (default 0.10)
            - ocr-include-thumbnails: Include page thumbnails (default True)

    Returns:
        TextDiscrepancyResult with analysis results
    """
    config = config or {}
    max_pages = config.get("max-ocr-pages", 50)
    analyze_all = config.get("ocr-analyze-all", False)
    include_thumbnails = config.get("ocr-include-thumbnails", True)

    # Check OCR availability
    available, reason = get_ocr_availability()
    if not available:
        return TextDiscrepancyResult(
            pages_analyzed=0,
            pages_with_discrepancy=0,
            image_only_pages=0,
            overall_similarity=1.0,
            ocr_available=False,
            unavailable_reason=reason,
        )

    # Import here to avoid import errors when OCR is unavailable
    from inspekt.services.pdf_renderer import PDFRenderer, is_pymupdf_available

    if not is_pymupdf_available():
        return TextDiscrepancyResult(
            pages_analyzed=0,
            pages_with_discrepancy=0,
            image_only_pages=0,
            overall_similarity=1.0,
            ocr_available=False,
            unavailable_reason="PyMuPDF not installed (required for rendering)",
        )

    pdf_path = Path(pdf_path)
    ocr_service = PDFOCRService()

    try:
        with PDFRenderer(pdf_path) as renderer:
            total_pages = renderer.page_count

            # Use smart page selection for large documents
            pages_to_analyze, is_sampled = _select_pages_for_analysis(
                total_pages, max_pages, analyze_all
            )

            # Generate sampling description
            sampling_description = None
            if is_sampled:
                sampling_description = f"{len(pages_to_analyze)} of {total_pages} pages (sampled)"
            elif total_pages > 0:
                sampling_description = f"All {total_pages} pages analyzed"

            comparisons: list[PageTextComparison] = []

            # Use thread pool for parallel OCR (I/O bound)
            # Each thread opens its own PDF document for thread safety
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(
                        _compare_page,
                        pdf_path,
                        page_num,
                        ocr_service,
                        True,  # include_diff
                        include_thumbnails,  # include_thumbnail
                    ): page_num
                    for page_num in pages_to_analyze
                }

                for future in as_completed(futures):
                    page_num = futures[future]
                    try:
                        comparison = future.result()
                        if comparison:
                            comparisons.append(comparison)
                    except Exception as e:
                        logger.warning(f"Failed to analyze page {page_num}: {e}")

            # Sort by page number
            comparisons.sort(key=lambda c: c.page_num)

            # Calculate statistics
            pages_with_discrepancy = sum(1 for c in comparisons if c.has_significant_discrepancy)
            image_only_pages = sum(1 for c in comparisons if c.is_image_only)

            if comparisons:
                overall_similarity = sum(c.similarity for c in comparisons) / len(comparisons)
            else:
                overall_similarity = 1.0

            return TextDiscrepancyResult(
                pages_analyzed=len(comparisons),
                pages_with_discrepancy=pages_with_discrepancy,
                image_only_pages=image_only_pages,
                overall_similarity=overall_similarity,
                page_comparisons=comparisons,
                ocr_available=True,
                is_sampled=is_sampled,
                total_document_pages=total_pages,
                sampling_description=sampling_description,
            )

    except Exception as e:
        logger.error(f"Failed to analyze text discrepancies: {e}")
        return TextDiscrepancyResult(
            pages_analyzed=0,
            pages_with_discrepancy=0,
            image_only_pages=0,
            overall_similarity=1.0,
            ocr_available=False,
            unavailable_reason=str(e),
        )


def _compare_page(
    pdf_path: Path,
    page_num: int,
    ocr_service: PDFOCRService,
    include_diff: bool = True,
    include_thumbnail: bool = True,
) -> PageTextComparison | None:
    """
    Compare PDF and OCR text for a single page.

    Each call opens its own PDF document handle for thread safety.

    Args:
        pdf_path: Path to the PDF file
        page_num: 0-indexed page number
        ocr_service: PDFOCRService instance
        include_diff: Whether to include character-level diff
        include_thumbnail: Whether to generate a page thumbnail

    Returns:
        PageTextComparison or None if comparison fails
    """
    from inspekt.services.pdf_renderer import PDFRenderer

    try:
        # Extract PDF text layer
        pdf_text = extract_pdf_text(pdf_path, page_num)

        # Open our own renderer for thread safety (PyMuPDF is not thread-safe)
        with PDFRenderer(pdf_path) as renderer:
            # Render and OCR the page
            ocr_text = ocr_service.ocr_page(renderer, page_num, dpi=150)

            # Calculate similarity
            similarity = compare_texts(pdf_text, ocr_text)

            # Generate character-level diff if requested and there are differences
            diff_result = None
            if include_diff and similarity < 0.95:
                diff_result = generate_character_diff(pdf_text, ocr_text)

            # Generate page thumbnail and lightbox image if requested
            thumbnail_base64 = None
            lightbox_base64 = None
            if include_thumbnail:
                thumbnail_base64, lightbox_base64 = _render_page_images(
                    renderer, page_num, thumbnail_size=150, lightbox_size=800
                )

        return PageTextComparison(
            page_num=page_num,
            pdf_text=pdf_text[:500],  # Truncate for storage
            ocr_text=ocr_text[:500],
            similarity=similarity,
            pdf_char_count=len(pdf_text),
            ocr_char_count=len(ocr_text),
            diff_result=diff_result,
            thumbnail_base64=thumbnail_base64,
            lightbox_base64=lightbox_base64,
        )
    except Exception as e:
        logger.warning(f"Failed to compare page {page_num}: {e}")
        return None
