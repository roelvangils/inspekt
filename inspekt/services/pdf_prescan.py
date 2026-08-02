"""
PDF Pre-scan Service for Timing Estimation.

This module provides fast PDF analysis (<1 second) to estimate document
characteristics for progress timing calculation. It samples pages rather
than scanning the entire document to keep analysis quick.

Usage:
    from inspekt.services.pdf_prescan import prescan_pdf

    result = prescan_pdf(Path("document.pdf"))
    print(f"Pages: {result.page_count}, Images: ~{result.estimated_image_count}")
"""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import fitz  # PyMuPDF


@dataclass
class PDFPrescanResult:
    """
    Quick-scan result for timing estimation.

    This lightweight structure captures just enough information to estimate
    how long the full accessibility check will take, without performing
    expensive analysis.
    """

    file_size_bytes: int
    page_count: int
    estimated_image_count: int
    has_text_layer: bool
    is_encrypted: bool
    has_structure_tree: bool
    file_complexity: Literal["simple", "moderate", "complex"]

    # Additional useful metrics
    sample_pages_analyzed: int = 0
    has_forms: bool = False
    has_annotations: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


def prescan_pdf(pdf_path: Path, max_sample_pages: int = 5) -> PDFPrescanResult:
    """
    Perform a quick (<1s) scan of PDF to estimate characteristics.

    This function samples up to `max_sample_pages` pages rather than scanning
    the entire document, making it fast enough to run before the main check
    without noticeable delay.

    Args:
        pdf_path: Path to the PDF file
        max_sample_pages: Maximum number of pages to sample for estimates

    Returns:
        PDFPrescanResult with document characteristics

    Raises:
        FileNotFoundError: If the PDF file doesn't exist
        fitz.FileDataError: If the file is not a valid PDF
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    file_size = pdf_path.stat().st_size

    doc = fitz.open(pdf_path)
    try:
        page_count = doc.page_count
        is_encrypted = doc.is_encrypted

        # Sample pages for analysis
        sample_pages = min(max_sample_pages, page_count)
        total_images = 0
        has_text = False
        has_forms = False
        has_annotations = False

        # Sample pages evenly distributed through the document
        if page_count <= max_sample_pages:
            pages_to_check = range(page_count)
        else:
            # Sample first, last, and evenly distributed pages
            step = page_count // max_sample_pages
            pages_to_check = [i * step for i in range(max_sample_pages)]
            if page_count - 1 not in pages_to_check:
                pages_to_check[-1] = page_count - 1  # Ensure last page is sampled

        for i in pages_to_check:
            page = doc[i]

            # Count images
            images = page.get_images(full=False)  # full=False is faster
            total_images += len(images)

            # Check for text layer (only need to find it once)
            if not has_text:
                text = page.get_text("text", flags=fitz.TEXT_PRESERVE_WHITESPACE)
                if text and text.strip():
                    has_text = True

            # Check for annotations (only need to find them once)
            if not has_annotations:
                annots = page.annots()
                if annots:
                    has_annotations = True

        # Extrapolate image count for full document
        if sample_pages > 0:
            estimated_images = int(total_images * (page_count / sample_pages))
        else:
            estimated_images = 0

        # Check for structure tree (tagged PDF)
        # This is a fast check via the catalog
        has_structure = False
        try:
            mark_info = doc.catalog.get("MarkInfo")
            if mark_info:
                # MarkInfo can be a direct dict or an indirect reference
                if hasattr(mark_info, "get"):
                    has_structure = bool(mark_info.get("Marked", False))
                elif isinstance(mark_info, dict):
                    has_structure = bool(mark_info.get("Marked", False))
        except Exception:
            # If we can't read it, assume no structure
            pass

        # Also check for StructTreeRoot as a backup
        if not has_structure:
            try:
                has_structure = "StructTreeRoot" in doc.catalog
            except Exception:
                pass

        # Check for forms
        try:
            if doc.is_form_pdf:
                has_forms = True
        except Exception:
            pass

        # Determine complexity
        complexity = _calculate_complexity(
            page_count=page_count,
            estimated_images=estimated_images,
            has_forms=has_forms,
            file_size=file_size,
        )

        return PDFPrescanResult(
            file_size_bytes=file_size,
            page_count=page_count,
            estimated_image_count=estimated_images,
            has_text_layer=has_text,
            is_encrypted=is_encrypted,
            has_structure_tree=has_structure,
            file_complexity=complexity,
            sample_pages_analyzed=sample_pages,
            has_forms=has_forms,
            has_annotations=has_annotations,
        )

    finally:
        doc.close()


def _calculate_complexity(
    page_count: int,
    estimated_images: int,
    has_forms: bool,
    file_size: int,
) -> Literal["simple", "moderate", "complex"]:
    """
    Determine document complexity for timing estimation.

    Complexity is based on:
    - Page count (more pages = more OCR/contrast work)
    - Image count (more images = more classification work)
    - Forms presence (forms add extra checks)
    - File size (larger files may have more embedded content)
    """
    # Scoring system
    score = 0

    # Page count contribution
    if page_count > 100:
        score += 3
    elif page_count > 50:
        score += 2
    elif page_count > 20:
        score += 1

    # Image count contribution
    if estimated_images > 100:
        score += 3
    elif estimated_images > 50:
        score += 2
    elif estimated_images > 20:
        score += 1

    # Forms add complexity
    if has_forms:
        score += 1

    # Large files (>10MB) add complexity
    if file_size > 10 * 1024 * 1024:
        score += 1

    # Map score to complexity
    if score >= 4:
        return "complex"
    elif score >= 2:
        return "moderate"
    else:
        return "simple"
