"""
PDF Content Auditor.

Performs detailed audits of specific content types that commonly
have accessibility issues:
- Images: Alt text, decorative marking
- Tables: Headers, scope, structure
- Forms: Labels, tooltips, field types
- Links: Descriptive text, destinations

Uses pikepdf and PyMuPDF to extract and analyze content.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Maximum pages to audit (prevents hanging on massive PDFs)
MAX_AUDIT_PAGES = 50


# Non-descriptive link text patterns
NON_DESCRIPTIVE_PATTERNS = [
    r"^click\s*here$",
    r"^here$",
    r"^read\s*more$",
    r"^more$",
    r"^learn\s*more$",
    r"^link$",
    r"^this\s*link$",
    r"^download$",
    r"^pdf$",
    r"^\d+$",  # Just numbers
    r"^[.,;:!?]+$",  # Just punctuation
]


def _is_garbage_text(text: str) -> bool:
    """
    Detect if extracted text is likely garbage from misaligned link rectangles.

    PDF link annotations often have bounding boxes that don't align with the
    actual text layer, especially in scanned PDFs or PDFs with complex layouts.
    This results in extracting random character fragments.

    Args:
        text: The extracted text to check

    Returns:
        True if the text appears to be garbage, False otherwise
    """
    if not text:
        return True

    # Very short fragments (1-3 chars) are suspicious unless common words
    if len(text) <= 3 and text.lower() not in {'see', 'go', 'to', 'url', 'www', 'pdf', 'faq'}:
        return True

    # Too many newlines for the text length suggests fragmented extraction
    # (text from multiple unrelated areas falling within the link rectangle)
    if text:
        newline_ratio = text.count('\n') / len(text)
        if newline_ratio > 0.2:  # More than 20% newlines
            return True

    # Random URL-like fragments (partial protocol strings)
    garbage_fragments = {'://', '//', ':/w', '://w', 'http', 'https', 'www', 'mailto', 'ftp'}
    if text.strip() in garbage_fragments:
        return True

    # Check for high ratio of non-alphabetic characters (excluding spaces and common punctuation)
    alpha_chars = sum(1 for c in text if c.isalpha())
    if len(text) > 5 and alpha_chars / len(text) < 0.3:  # Less than 30% letters
        return True

    # Check for fragmented multi-line text (multiple short words/fragments)
    # e.g., "HAB\n$285\noutr" - multiple fragments separated by newlines
    if '\n' in text:
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if len(lines) >= 2:
            # If most lines are very short (< 5 chars), it's likely fragmented
            short_lines = sum(1 for line in lines if len(line) < 5)
            if short_lines >= len(lines) * 0.6:  # 60% or more lines are short
                return True

    return False


def _clean_toc_text(text: str) -> str:
    """
    Clean up TOC-style link text that has leading page numbers.

    Table of Contents entries often appear as "3\nChapter Title" or "12\t Section Name".
    This removes the leading page number pattern.

    Only cleans when there's a clear TOC separator (tab, newline) to avoid
    accidentally stripping numbers that are part of the content (e.g., "5 tips").

    Args:
        text: The link text to clean

    Returns:
        Cleaned text with TOC page numbers removed
    """
    if not text:
        return text

    # Remove leading numbers followed by tab, newline, or multiple spaces (TOC pattern)
    # e.g., "3\nBorealis Exterior" -> "Borealis Exterior"
    # e.g., "12\tChapter Name" -> "Chapter Name"
    # Only match when there's a clear separator (tab, newline, or 2+ spaces)
    cleaned = re.sub(r'^\d+(?:[\t\n]|\s{2,})\s*', '', text)

    return cleaned.strip()


@dataclass
class ImageAudit:
    """Audit result for a single image."""

    page: int  # 0-indexed
    index: int  # Index on page
    bbox: tuple[float, float, float, float] | None = None  # (x0, y0, x1, y1)
    width: float = 0
    height: float = 0
    has_alt_text: bool = False
    alt_text: str | None = None
    is_decorative: bool = False
    image_type: str | None = None  # JPEG, PNG, etc.
    bits_per_component: int | None = None
    color_space: str | None = None
    issues: list[str] = field(default_factory=list)
    screenshot_path: str | None = None  # For report visualization
    thumbnail_base64: str | None = None  # Base64-encoded thumbnail for inline embedding
    lightbox_base64: str | None = None  # Larger image for lightbox view

    # AI Image Classification (Phase 1 enhancement)
    image_category: str | None = None  # photograph, illustration, chart_or_graph, etc.
    category_confidence: float = 0.0  # 0-1 confidence score
    classification_method: str | None = None  # clip, vision_ai, heuristic

    # AI Alt-Text Suggestions (Phase 3 enhancement)
    ai_suggested_alt: str | None = None  # AI-generated alt text suggestion
    ai_provider_used: str | None = None  # Which AI provider generated the suggestion

    @property
    def display_page(self) -> int:
        """1-indexed page number."""
        return self.page + 1

    @property
    def status(self) -> str:
        """Overall status: pass, warn, or fail."""
        if self.is_decorative:
            return "pass"
        if self.has_alt_text:
            return "pass"
        return "fail"

    @property
    def category_display_name(self) -> str:
        """Human-readable category name."""
        if not self.image_category:
            return "Unknown"
        return self.image_category.replace("_", " ").title()

    @property
    def category_needs_warning(self) -> bool:
        """Whether this category warrants a warning in reports."""
        return self.image_category in ("table_as_image", "text_as_image")

    @property
    def confidence_level(self) -> str:
        """Get confidence level as high/medium/low for display."""
        if self.category_confidence >= 0.6:
            return "high"
        elif self.category_confidence >= 0.4:
            return "medium"
        else:
            return "low"

    @property
    def alt_guidance(self) -> str:
        """Get category-specific alt-text writing guidance."""
        from inspekt.services.image_classifier import ALT_TEXT_GUIDANCE, ImageCategory

        if not self.image_category:
            return ALT_TEXT_GUIDANCE.get(ImageCategory.UNKNOWN, "")
        try:
            category = ImageCategory(self.image_category)
            return ALT_TEXT_GUIDANCE.get(category, "")
        except ValueError:
            return ""


@dataclass
class VectorGraphicAudit:
    """Audit result for a detected vector graphic (icon, shape, diagram)."""

    page: int  # 0-indexed
    index: int  # Index on page
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1)
    width: float
    height: float

    # Accessibility
    has_alt_text: bool = False
    alt_text: str | None = None
    is_decorative: bool = False

    # Vector properties
    path_count: int = 0  # Number of drawing operations in this cluster
    fill_colors: int = 0  # Number of distinct fill colors

    # Rendered preview
    thumbnail_base64: str | None = None
    lightbox_base64: str | None = None

    issues: list[str] = field(default_factory=list)

    @property
    def display_page(self) -> int:
        """1-indexed page number."""
        return self.page + 1

    @property
    def status(self) -> str:
        """Overall status: pass or fail."""
        if self.is_decorative or self.has_alt_text:
            return "pass"
        return "fail"

    @property
    def size_display(self) -> str:
        """Size for display."""
        return f"{self.width:.0f}×{self.height:.0f}"


@dataclass
class VisualContentItem:
    """
    Unified adapter for images and vector graphics.

    This class provides a common interface for displaying both bitmap images
    and vector graphics in a single unified table with type-based filtering.
    It adapts the existing ImageAudit and VectorGraphicAudit dataclasses
    without modifying their structure.
    """

    # Common fields
    page: int  # 0-indexed
    index: int  # Index on page
    bbox: tuple[float, float, float, float] | None
    width: float
    height: float
    has_alt_text: bool
    alt_text: str | None
    is_decorative: bool
    thumbnail_base64: str | None
    lightbox_base64: str | None
    issues: list[str]

    # Type discriminator
    content_type: str  # "bitmap" or "vector"

    # Bitmap-specific (None for vectors)
    image_type: str | None = None  # JPEG, PNG, etc.
    image_category: str | None = None  # photograph, illustration, etc.
    category_confidence: float = 0.0
    classification_method: str | None = None
    ai_suggested_alt: str | None = None
    ai_provider_used: str | None = None

    # Vector-specific (None for bitmaps)
    path_count: int | None = None
    fill_colors: int | None = None

    @property
    def display_page(self) -> int:
        """1-indexed page number."""
        return self.page + 1

    @property
    def status(self) -> str:
        """Overall status: pass or fail."""
        if self.is_decorative or self.has_alt_text:
            return "pass"
        return "fail"

    @property
    def size_display(self) -> str:
        """Size for display."""
        return f"{int(self.width)}×{int(self.height)}"

    @property
    def is_bitmap(self) -> bool:
        """Check if this is a bitmap image."""
        return self.content_type == "bitmap"

    @property
    def is_vector(self) -> bool:
        """Check if this is a vector graphic."""
        return self.content_type == "vector"

    @property
    def category_display_name(self) -> str:
        """Human-readable category name for bitmaps, or 'Vector' for vectors."""
        if self.is_vector:
            return "Vector"
        if not self.image_category:
            return "Unknown"
        return self.image_category.replace("_", " ").title()

    @property
    def category_needs_warning(self) -> bool:
        """Whether this category warrants a warning in reports."""
        if self.is_vector:
            return False
        return self.image_category in ("table_as_image", "text_as_image")

    @property
    def confidence_level(self) -> str:
        """Get confidence level as high/medium/low for display."""
        if self.is_vector:
            return "high"  # Vectors are definitively vectors
        if self.category_confidence >= 0.6:
            return "high"
        elif self.category_confidence >= 0.4:
            return "medium"
        else:
            return "low"

    @property
    def complexity_info(self) -> str:
        """Get complexity info for vectors (path count, colors)."""
        if not self.is_vector:
            return ""
        parts = []
        if self.path_count and self.path_count > 0:
            parts.append(f"{self.path_count} paths")
        if self.fill_colors and self.fill_colors > 0:
            parts.append(f"{self.fill_colors} colors")
        return ", ".join(parts) if parts else ""

    @classmethod
    def from_image(cls, img: "ImageAudit") -> "VisualContentItem":
        """Create a VisualContentItem from an ImageAudit."""
        return cls(
            page=img.page,
            index=img.index,
            bbox=img.bbox,
            width=img.width,
            height=img.height,
            has_alt_text=img.has_alt_text,
            alt_text=img.alt_text,
            is_decorative=img.is_decorative,
            thumbnail_base64=img.thumbnail_base64,
            lightbox_base64=img.lightbox_base64,
            issues=img.issues,
            content_type="bitmap",
            # Bitmap-specific
            image_type=img.image_type,
            image_category=img.image_category,
            category_confidence=img.category_confidence,
            classification_method=img.classification_method,
            ai_suggested_alt=img.ai_suggested_alt,
            ai_provider_used=img.ai_provider_used,
        )

    @classmethod
    def from_vector(cls, vg: "VectorGraphicAudit") -> "VisualContentItem":
        """Create a VisualContentItem from a VectorGraphicAudit."""
        return cls(
            page=vg.page,
            index=vg.index,
            bbox=vg.bbox,
            width=vg.width,
            height=vg.height,
            has_alt_text=vg.has_alt_text,
            alt_text=vg.alt_text,
            is_decorative=vg.is_decorative,
            thumbnail_base64=vg.thumbnail_base64,
            lightbox_base64=vg.lightbox_base64,
            issues=vg.issues,
            content_type="vector",
            # Vector-specific
            path_count=vg.path_count,
            fill_colors=vg.fill_colors,
        )


@dataclass
class TableAudit:
    """Audit result for a single table."""

    page: int  # 0-indexed
    index: int  # Index on page
    bbox: tuple[float, float, float, float] | None = None
    row_count: int = 0
    col_count: int = 0
    has_headers: bool = False
    header_cells: int = 0
    has_scope: bool = False
    scope_type: str | None = None  # row, col, both
    has_caption: bool = False
    caption_text: str | None = None
    is_layout_table: bool = False
    issues: list[str] = field(default_factory=list)

    @property
    def display_page(self) -> int:
        """1-indexed page number."""
        return self.page + 1

    @property
    def size_str(self) -> str:
        """Table size as string."""
        return f"{self.row_count}×{self.col_count}"

    @property
    def status(self) -> str:
        """Overall status: pass, warn, or fail."""
        if self.is_layout_table:
            return "warn"  # Layout tables should be avoided
        if not self.has_headers:
            return "fail"
        if self.row_count > 1 and self.col_count > 1 and not self.has_scope:
            return "warn"  # Complex tables need scope
        return "pass"


@dataclass
class FormFieldAudit:
    """Audit result for a single form field."""

    page: int  # 0-indexed
    index: int  # Index on page
    field_name: str | None = None  # Internal field name
    field_type: str = "unknown"  # text, checkbox, radio, button, select, signature
    bbox: tuple[float, float, float, float] | None = None
    has_label: bool = False
    label_text: str | None = None
    has_tooltip: bool = False
    tooltip_text: str | None = None
    is_required: bool = False
    is_readonly: bool = False
    default_value: str | None = None
    issues: list[str] = field(default_factory=list)

    @property
    def display_page(self) -> int:
        """1-indexed page number."""
        return self.page + 1

    @property
    def accessible_name(self) -> str | None:
        """Best available accessible name."""
        return self.tooltip_text or self.label_text or self.field_name

    @property
    def status(self) -> str:
        """Overall status: pass, warn, or fail."""
        if not self.has_tooltip and not self.has_label:
            return "fail"
        if not self.has_tooltip:
            return "warn"  # Tooltip is preferred for AT
        return "pass"


@dataclass
class LinkAudit:
    """Audit result for a single link."""

    page: int  # 0-indexed
    index: int  # Index on page
    bbox: tuple[float, float, float, float] | None = None
    link_text: str | None = None
    destination: str | None = None  # URL or internal reference
    destination_type: str = "unknown"  # uri, goto, gotor, named
    is_internal: bool = False
    is_descriptive: bool = True
    alt_text: str | None = None  # From annotation
    issues: list[str] = field(default_factory=list)

    @property
    def display_page(self) -> int:
        """1-indexed page number."""
        return self.page + 1

    @property
    def display_destination(self) -> str:
        """Destination for display (truncated if long)."""
        if not self.destination:
            return "Unknown"
        if len(self.destination) > 60:
            return self.destination[:57] + "…"
        return self.destination

    @property
    def status(self) -> str:
        """Overall status: pass, warn, or fail."""
        if not self.link_text and not self.alt_text:
            return "fail"
        if not self.is_descriptive:
            return "warn"
        return "pass"


@dataclass
class ListAudit:
    """Audit result for a single list structure."""

    page: int  # 0-indexed
    index: int  # Index on page
    item_count: int = 0
    has_proper_structure: bool = True
    items_with_label: int = 0
    items_with_body: int = 0
    nested_list_count: int = 0
    issues: list[str] = field(default_factory=list)

    @property
    def display_page(self) -> int:
        """1-indexed page number."""
        return self.page + 1

    @property
    def status(self) -> str:
        """Overall status: pass, warn, or fail."""
        if not self.has_proper_structure:
            return "fail"
        if self.item_count > 0 and self.items_with_body == 0:
            return "fail"
        if self.item_count > 0 and self.items_with_body < self.item_count:
            return "warn"
        return "pass"


# Annotation types that should be checked for accessibility
ACCESSIBLE_ANNOTATION_TYPES = {
    0: "Text",           # Sticky notes
    2: "FreeText",
    8: "Highlight",
    9: "Underline",
    10: "Squiggly",
    11: "StrikeOut",
    13: "Stamp",
    17: "FileAttachment",
    18: "Sound",
}


@dataclass
class AnnotationAudit:
    """Audit result for a single annotation."""

    page: int  # 0-indexed
    index: int  # Index on page
    annotation_type: str
    type_code: int
    bbox: tuple[float, float, float, float] | None = None
    has_contents: bool = False
    contents: str | None = None
    has_title: bool = False
    title: str | None = None
    subject: str | None = None
    issues: list[str] = field(default_factory=list)

    @property
    def display_page(self) -> int:
        """1-indexed page number."""
        return self.page + 1

    @property
    def accessible_description(self) -> str | None:
        """Best available accessible description."""
        return self.contents or self.subject or self.title

    @property
    def status(self) -> str:
        """Overall status: pass, warn, or fail."""
        # Critical types that need descriptions
        if self.annotation_type in ("Text", "FileAttachment", "Sound", "Stamp"):
            return "fail" if not self.accessible_description else "pass"
        # Markup types where description is recommended but not critical
        if self.annotation_type in ("Highlight", "Underline", "Squiggly", "StrikeOut"):
            return "warn" if not self.accessible_description else "pass"
        return "pass"


@dataclass
class ContentAuditResult:
    """Complete content audit result."""

    images: list[ImageAudit] = field(default_factory=list)
    tables: list[TableAudit] = field(default_factory=list)
    forms: list[FormFieldAudit] = field(default_factory=list)
    links: list[LinkAudit] = field(default_factory=list)
    lists: list[ListAudit] = field(default_factory=list)
    annotations: list[AnnotationAudit] = field(default_factory=list)
    vector_graphics: list[VectorGraphicAudit] = field(default_factory=list)

    # Summary counts
    total_images: int = 0
    images_without_alt: int = 0
    images_decorative: int = 0

    total_tables: int = 0
    tables_without_headers: int = 0
    tables_layout: int = 0

    total_form_fields: int = 0
    fields_without_labels: int = 0

    total_links: int = 0
    links_non_descriptive: int = 0
    links_missing_text: int = 0

    total_lists: int = 0
    lists_with_issues: int = 0

    total_annotations: int = 0
    annotations_without_description: int = 0

    # Vector graphics
    total_vector_graphics: int = 0
    vector_graphics_without_alt: int = 0
    vector_graphics_decorative: int = 0

    extraction_errors: list[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        """Check if any content has issues."""
        return (
            self.images_without_alt > 0
            or self.tables_without_headers > 0
            or self.fields_without_labels > 0
            or self.links_non_descriptive > 0
            or self.links_missing_text > 0
            or self.lists_with_issues > 0
            or self.annotations_without_description > 0
            or self.vector_graphics_without_alt > 0
        )

    # Visual content helpers (unified images + vectors)

    def get_visual_content(self) -> list[VisualContentItem]:
        """
        Get all visual content (images + vectors) as a unified list.

        Returns items sorted by page number, then by index within page.
        """
        items: list[VisualContentItem] = []

        # Convert images to visual content items
        for img in self.images:
            items.append(VisualContentItem.from_image(img))

        # Convert vectors to visual content items
        for vg in self.vector_graphics:
            items.append(VisualContentItem.from_vector(vg))

        # Sort by page, then by index
        items.sort(key=lambda x: (x.page, x.index))
        return items

    @property
    def total_visual_content(self) -> int:
        """Total count of all visual content (images + vectors)."""
        return self.total_images + self.total_vector_graphics

    @property
    def visual_content_without_alt(self) -> int:
        """Count of visual content items without alt text."""
        return self.images_without_alt + self.vector_graphics_without_alt

    @property
    def visual_content_decorative(self) -> int:
        """Count of decorative visual content items."""
        return self.images_decorative + self.vector_graphics_decorative


class PDFContentAuditor:
    """
    Audits PDF content for accessibility issues.

    Analyzes images, tables, forms, and links to identify
    common accessibility problems that need remediation.
    """

    def __init__(self, pdf_path: Path | str):
        """
        Initialize the auditor.

        Args:
            pdf_path: Path to the PDF file
        """
        self.pdf_path = Path(pdf_path)
        self._pdf = None
        self._fitz_doc = None

    def __enter__(self) -> "PDFContentAuditor":
        """Open PDF files."""
        import pikepdf
        self._pdf = pikepdf.open(self.pdf_path)

        # Try to open with PyMuPDF for additional extraction
        try:
            import fitz
            self._fitz_doc = fitz.open(self.pdf_path)
        except ImportError:
            logger.debug("PyMuPDF not available for content extraction")
        except Exception as e:
            logger.warning(f"Failed to open PDF with PyMuPDF: {e}")

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close PDF files."""
        if self._pdf:
            self._pdf.close()
            self._pdf = None
        if self._fitz_doc:
            self._fitz_doc.close()
            self._fitz_doc = None

    def audit(self) -> ContentAuditResult:
        """
        Perform complete content audit.

        Returns:
            ContentAuditResult with all content audits
        """
        result = ContentAuditResult()

        try:
            # Audit images
            result.images = self._audit_images()
            result.total_images = len(result.images)
            result.images_without_alt = sum(
                1 for img in result.images
                if not img.has_alt_text and not img.is_decorative
            )
            result.images_decorative = sum(
                1 for img in result.images if img.is_decorative
            )
        except Exception as e:
            logger.warning(f"Error auditing images: {e}")
            result.extraction_errors.append(f"Images: {e}")

        try:
            # Audit tables
            result.tables = self._audit_tables()
            result.total_tables = len(result.tables)
            result.tables_without_headers = sum(
                1 for tbl in result.tables if not tbl.has_headers
            )
            result.tables_layout = sum(
                1 for tbl in result.tables if tbl.is_layout_table
            )
        except Exception as e:
            logger.warning(f"Error auditing tables: {e}")
            result.extraction_errors.append(f"Tables: {e}")

        try:
            # Audit form fields
            result.forms = self._audit_forms()
            result.total_form_fields = len(result.forms)
            result.fields_without_labels = sum(
                1 for f in result.forms
                if not f.has_tooltip and not f.has_label
            )
        except Exception as e:
            logger.warning(f"Error auditing forms: {e}")
            result.extraction_errors.append(f"Forms: {e}")

        try:
            # Audit links
            result.links = self._audit_links()
            result.total_links = len(result.links)
            result.links_non_descriptive = sum(
                1 for link in result.links if not link.is_descriptive
            )
            result.links_missing_text = sum(
                1 for link in result.links
                if not link.link_text and not link.alt_text
            )
        except Exception as e:
            logger.warning(f"Error auditing links: {e}")
            result.extraction_errors.append(f"Links: {e}")

        try:
            # Audit lists (L/LI/Lbl/LBody structure)
            result.lists = self._audit_lists()
            result.total_lists = len(result.lists)
            result.lists_with_issues = sum(
                1 for lst in result.lists if lst.status != "pass"
            )
        except Exception as e:
            logger.warning(f"Error auditing lists: {e}")
            result.extraction_errors.append(f"Lists: {e}")

        try:
            # Audit annotations (non-link)
            result.annotations = self._audit_annotations()
            result.total_annotations = len(result.annotations)
            result.annotations_without_description = sum(
                1 for ann in result.annotations
                if ann.status in ("fail", "warn")
            )
        except Exception as e:
            logger.warning(f"Error auditing annotations: {e}")
            result.extraction_errors.append(f"Annotations: {e}")

        try:
            # Audit vector graphics (icons, shapes)
            result.vector_graphics = self._audit_vector_graphics()
            result.total_vector_graphics = len(result.vector_graphics)
            result.vector_graphics_without_alt = sum(
                1 for vg in result.vector_graphics
                if not vg.has_alt_text and not vg.is_decorative
            )
            result.vector_graphics_decorative = sum(
                1 for vg in result.vector_graphics if vg.is_decorative
            )
        except Exception as e:
            logger.warning(f"Error auditing vector graphics: {e}")
            result.extraction_errors.append(f"Vector graphics: {e}")

        return result

    def get_image_thumbnail(
        self,
        page_num: int,
        image_index: int,
        max_size: int = 150,
    ) -> str | None:
        """
        Extract image as base64 thumbnail.

        Args:
            page_num: 0-indexed page number
            image_index: Index of image on the page
            max_size: Maximum dimension (width or height) in pixels

        Returns:
            Base64-encoded PNG suitable for <img src="data:image/png;base64,…">
            Returns None if extraction fails
        """
        if not self._fitz_doc:
            return None

        try:
            import base64
            import fitz
            from io import BytesIO

            page = self._fitz_doc[page_num]
            images = page.get_images(full=True)

            if image_index >= len(images):
                return None

            xref = images[image_index][0]

            # Extract the image
            pix = fitz.Pixmap(self._fitz_doc, xref)

            # Convert CMYK to RGB if necessary
            if pix.n - pix.alpha > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)

            # Get PNG bytes from PyMuPDF
            png_bytes = pix.tobytes("png")

            # Resize using Pillow if needed
            if max(pix.width, pix.height) > max_size:
                try:
                    from PIL import Image

                    img = Image.open(BytesIO(png_bytes))
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

                    # Save resized image to bytes
                    output = BytesIO()
                    img.save(output, format="PNG", optimize=True)
                    png_bytes = output.getvalue()
                except ImportError:
                    # Pillow not available, use original size
                    pass

            return base64.b64encode(png_bytes).decode("ascii")

        except Exception as e:
            logger.warning(f"Failed to extract image thumbnail: {e}")
            return None

    def get_image_dual_size(
        self,
        page_num: int,
        image_index: int,
        thumbnail_size: int = 100,
        lightbox_size: int = 600,
    ) -> tuple[str | None, str | None]:
        """
        Extract image as both thumbnail and lightbox versions.

        Args:
            page_num: 0-indexed page number
            image_index: Index of image on the page
            thumbnail_size: Maximum dimension for thumbnail (default 100px)
            lightbox_size: Maximum dimension for lightbox (default 600px)

        Returns:
            Tuple of (thumbnail_base64, lightbox_base64), either may be None
        """
        if not self._fitz_doc:
            return None, None

        try:
            import base64
            import fitz
            from io import BytesIO
            from PIL import Image

            page = self._fitz_doc[page_num]
            images = page.get_images(full=True)

            if image_index >= len(images):
                return None, None

            xref = images[image_index][0]

            # Extract the image
            pix = fitz.Pixmap(self._fitz_doc, xref)

            # Convert CMYK to RGB if necessary
            if pix.n - pix.alpha > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)

            # Get PNG bytes from PyMuPDF
            png_bytes = pix.tobytes("png")

            # Open with Pillow
            img = Image.open(BytesIO(png_bytes))

            # Generate lightbox version (larger)
            lightbox_img = img.copy()
            if max(img.width, img.height) > lightbox_size:
                lightbox_img.thumbnail((lightbox_size, lightbox_size), Image.Resampling.LANCZOS)
            lightbox_output = BytesIO()
            lightbox_img.save(lightbox_output, format="PNG", optimize=True)
            lightbox_base64 = base64.b64encode(lightbox_output.getvalue()).decode("ascii")

            # Generate thumbnail (smaller)
            img.thumbnail((thumbnail_size, thumbnail_size), Image.Resampling.LANCZOS)
            thumb_output = BytesIO()
            img.save(thumb_output, format="PNG", optimize=True)
            thumbnail_base64 = base64.b64encode(thumb_output.getvalue()).decode("ascii")

            return thumbnail_base64, lightbox_base64

        except Exception as e:
            logger.warning(f"Failed to extract dual-size images: {e}")
            return None, None

    def get_image_bytes(self, page_num: int, image_index: int) -> bytes | None:
        """
        Extract raw image bytes for classification.

        Args:
            page_num: 0-indexed page number
            image_index: Index of image on the page

        Returns:
            Raw PNG bytes or None if extraction fails
        """
        if not self._fitz_doc:
            return None

        try:
            import fitz

            page = self._fitz_doc[page_num]
            images = page.get_images(full=True)

            if image_index >= len(images):
                return None

            xref = images[image_index][0]

            # Extract the image
            pix = fitz.Pixmap(self._fitz_doc, xref)

            # Convert CMYK to RGB if necessary
            if pix.n - pix.alpha > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)

            return pix.tobytes("png")

        except Exception as e:
            logger.warning(f"Failed to extract image bytes: {e}")
            return None

    def classify_images(
        self,
        images: list[ImageAudit],
        use_clip: bool = True,
        use_vision_ai: bool = False,
        ai_provider: str | None = None,
        progress_callback: Any | None = None,
    ) -> list[ImageAudit]:
        """
        Classify images into accessibility-relevant categories.

        Args:
            images: List of ImageAudit objects to classify
            use_clip: Whether to try CLIP classification first (fast, local)
            use_vision_ai: Whether to use Vision AI (slower, costs money)
            ai_provider: AI provider for Vision AI
            progress_callback: Optional callback(current, total) for progress

        Returns:
            Same list of ImageAudit objects with classification fields populated
        """
        from inspekt.services.image_classifier import get_classifier

        classifier = get_classifier()

        for idx, img in enumerate(images):
            if progress_callback:
                progress_callback(idx + 1, len(images))

            try:
                # Get image data
                image_bytes = self.get_image_bytes(img.page, img.index)
                image_base64 = img.thumbnail_base64 or img.lightbox_base64

                # Classify the image
                result = classifier.classify(
                    image_bytes=image_bytes,
                    image_base64=image_base64,
                    width=img.width,
                    height=img.height,
                    color_space=img.color_space,
                    bits_per_component=img.bits_per_component,
                    use_clip=use_clip,
                    use_vision_ai=use_vision_ai,
                    ai_provider=ai_provider,
                )

                # Update the image audit
                img.image_category = result.category.value
                img.category_confidence = result.confidence
                img.classification_method = result.method

            except Exception as e:
                logger.warning(f"Failed to classify image on page {img.page + 1}: {e}")

        return images

    def generate_alt_text_suggestions(
        self,
        images: list[ImageAudit],
        ai_provider: str | None = None,
        document_title: str | None = None,
        progress_callback: Any | None = None,
    ) -> list[ImageAudit]:
        """
        Generate AI alt-text suggestions for images missing alt text.

        Args:
            images: List of ImageAudit objects
            ai_provider: AI provider to use
            document_title: Document title for context
            progress_callback: Optional callback(current, total) for progress

        Returns:
            Same list with ai_suggested_alt populated for images needing alt text
        """
        from inspekt.services.image_classifier import generate_alt_text_suggestion, ImageCategory

        images_needing_alt = [
            img for img in images
            if not img.has_alt_text and not img.is_decorative
        ]

        for idx, img in enumerate(images_needing_alt):
            if progress_callback:
                progress_callback(idx + 1, len(images_needing_alt))

            try:
                # Get base64 image data
                image_base64 = img.lightbox_base64 or img.thumbnail_base64
                if not image_base64:
                    continue

                # Determine category
                try:
                    category = ImageCategory(img.image_category) if img.image_category else ImageCategory.UNKNOWN
                except ValueError:
                    category = ImageCategory.UNKNOWN

                # Generate suggestion
                context = f"Document: {document_title}" if document_title else None
                suggestion = generate_alt_text_suggestion(
                    image_base64=image_base64,
                    category=category,
                    document_context=context,
                    provider=ai_provider,
                )

                if suggestion and suggestion.upper() != "DECORATIVE":
                    img.ai_suggested_alt = suggestion
                    img.ai_provider_used = ai_provider or "thoth"
                elif suggestion and suggestion.upper() == "DECORATIVE":
                    # AI thinks this should be decorative
                    img.ai_suggested_alt = "[Marked as decorative by AI]"
                    img.ai_provider_used = ai_provider or "thoth"

            except Exception as e:
                logger.warning(f"Failed to generate alt text for image on page {img.page + 1}: {e}")

        return images

    def _audit_images(self) -> list[ImageAudit]:
        """Audit all images in the PDF."""
        images = []

        # Use structure tree to find Figure elements with alt text info
        figure_alt_texts = self._extract_figure_alt_texts()

        # Use PyMuPDF to extract images
        if self._fitz_doc:
            total_pages = len(self._fitz_doc)
            pages_to_audit = min(total_pages, MAX_AUDIT_PAGES)
            if pages_to_audit < total_pages:
                logger.info(f"Content audit limited to first {pages_to_audit} of {total_pages} pages")

            for page_num in range(pages_to_audit):
                page = self._fitz_doc[page_num]
                image_list = page.get_images(full=True)

                for img_idx, img_info in enumerate(image_list):
                    xref = img_info[0]

                    # Get image properties
                    try:
                        base_image = self._fitz_doc.extract_image(xref)
                        width = base_image.get("width", 0)
                        height = base_image.get("height", 0)
                        color_space = base_image.get("colorspace", 1)
                        bpc = base_image.get("bpc", 8)
                        ext = base_image.get("ext", "")
                    except Exception:
                        width, height = img_info[2], img_info[3]
                        color_space = None
                        bpc = None
                        ext = ""

                    # Get image bounding box on page
                    # PyMuPDF returns coordinates in top-left origin (screen coords)
                    bbox = None
                    try:
                        rects = page.get_image_rects(xref)
                        if rects:
                            # Use first occurrence if image appears multiple times
                            rect = rects[0]
                            bbox = (rect.x0, rect.y0, rect.x1, rect.y1)
                    except Exception as e:
                        logger.debug(f"Failed to get image rect for xref {xref}: {e}")

                    # Check for alt text from structure
                    alt_text = figure_alt_texts.get((page_num, img_idx))
                    has_alt = alt_text is not None and len(alt_text.strip()) > 0

                    # Small images are often decorative
                    is_decorative = width < 50 or height < 50

                    issues = []
                    if not has_alt and not is_decorative:
                        issues.append("Missing alternative text")

                    images.append(ImageAudit(
                        page=page_num,
                        index=img_idx,
                        bbox=bbox,
                        width=width,
                        height=height,
                        has_alt_text=has_alt,
                        alt_text=alt_text,
                        is_decorative=is_decorative,
                        image_type=ext.upper() if ext else None,
                        bits_per_component=bpc,
                        color_space=str(color_space) if color_space else None,
                        issues=issues,
                    ))

        return images

    def _extract_figure_alt_texts(self) -> dict[tuple[int, int], str]:
        """Extract alt text from Figure elements in structure tree."""
        alt_texts = {}
        nodes_visited = [0]  # Use list to allow modification in nested function
        max_nodes = 5000  # Limit traversal for large PDFs

        if not self._pdf:
            return alt_texts

        root = self._pdf.Root
        if "/StructTreeRoot" not in root:
            return alt_texts

        struct_root = root["/StructTreeRoot"]

        def traverse(element, page_num=None, fig_counter=None, depth=0):
            # Limit traversal
            if nodes_visited[0] >= max_nodes or depth > 50:
                return
            nodes_visited[0] += 1

            if fig_counter is None:
                fig_counter = {}

            import pikepdf

            if isinstance(element, pikepdf.Dictionary):
                # Get page number if available (only check pages we're auditing)
                if "/Pg" in element:
                    try:
                        page_ref = element["/Pg"]
                        # Only check first MAX_AUDIT_PAGES pages
                        pages_to_check = min(len(self._pdf.pages), MAX_AUDIT_PAGES)
                        for i in range(pages_to_check):
                            if self._pdf.pages[i].obj == page_ref:
                                page_num = i
                                break
                    except Exception:
                        pass

                # Check if this is a Figure
                tag = str(element.get("/S", "")).lstrip("/")
                if tag == "Figure" and "/Alt" in element:
                    alt = str(element["/Alt"]).strip()
                    if page_num is not None and page_num < MAX_AUDIT_PAGES:
                        if page_num not in fig_counter:
                            fig_counter[page_num] = 0
                        alt_texts[(page_num, fig_counter[page_num])] = alt
                        fig_counter[page_num] += 1

                # Traverse children
                if "/K" in element and nodes_visited[0] < max_nodes:
                    k_value = element["/K"]
                    if isinstance(k_value, pikepdf.Array):
                        for child in k_value:
                            if nodes_visited[0] >= max_nodes:
                                break
                            traverse(child, page_num, fig_counter, depth + 1)
                    else:
                        traverse(k_value, page_num, fig_counter, depth + 1)

        traverse(struct_root)
        return alt_texts

    def _audit_tables(self) -> list[TableAudit]:
        """Audit all tables in the PDF."""
        tables = []
        nodes_visited = [0]
        max_nodes = 5000

        if not self._pdf:
            return tables

        root = self._pdf.Root
        if "/StructTreeRoot" not in root:
            return tables

        struct_root = root["/StructTreeRoot"]
        table_index = 0

        def traverse(element, page_num=None, depth=0):
            nonlocal table_index

            # Limit traversal
            if nodes_visited[0] >= max_nodes or depth > 50:
                return
            nodes_visited[0] += 1

            import pikepdf

            if isinstance(element, pikepdf.Dictionary):
                # Get page number (only check pages we're auditing)
                if "/Pg" in element:
                    try:
                        page_ref = element["/Pg"]
                        pages_to_check = min(len(self._pdf.pages), MAX_AUDIT_PAGES)
                        for i in range(pages_to_check):
                            if self._pdf.pages[i].obj == page_ref:
                                page_num = i
                                break
                    except Exception:
                        pass

                tag = str(element.get("/S", "")).lstrip("/")

                if tag == "Table" and (page_num is None or page_num < MAX_AUDIT_PAGES):
                    table_audit = self._analyze_table(element, page_num or 0, table_index)
                    tables.append(table_audit)
                    table_index += 1

                # Traverse children
                if "/K" in element and nodes_visited[0] < max_nodes:
                    k_value = element["/K"]
                    if isinstance(k_value, pikepdf.Array):
                        for child in k_value:
                            if nodes_visited[0] >= max_nodes:
                                break
                            traverse(child, page_num, depth + 1)
                    else:
                        traverse(k_value, page_num, depth + 1)

        traverse(struct_root)
        return tables

    def _analyze_table(self, table_element, page_num: int, index: int) -> TableAudit:
        """Analyze a single table element."""
        import pikepdf

        row_count = 0
        col_count = 0
        header_cells = 0
        has_scope = False

        def count_cells(element):
            nonlocal row_count, col_count, header_cells, has_scope

            if isinstance(element, pikepdf.Dictionary):
                tag = str(element.get("/S", "")).lstrip("/")

                if tag == "TR":
                    row_count += 1
                    # Count columns in first row
                    if row_count == 1 and "/K" in element:
                        k = element["/K"]
                        if isinstance(k, pikepdf.Array):
                            col_count = len(k)
                        else:
                            col_count = 1

                elif tag == "TH":
                    header_cells += 1
                    # Check for scope attribute
                    if "/A" in element:
                        attrs = element["/A"]
                        if isinstance(attrs, pikepdf.Dictionary):
                            if "/Scope" in attrs:
                                has_scope = True
                        elif isinstance(attrs, pikepdf.Array):
                            for attr in attrs:
                                if isinstance(attr, pikepdf.Dictionary) and "/Scope" in attr:
                                    has_scope = True

                if "/K" in element:
                    k = element["/K"]
                    if isinstance(k, pikepdf.Array):
                        for child in k:
                            count_cells(child)
                    else:
                        count_cells(k)

        count_cells(table_element)

        has_headers = header_cells > 0

        # Determine scope type
        scope_type = None
        if has_scope:
            if row_count > 0 and header_cells == col_count:
                scope_type = "col"
            elif col_count > 0 and header_cells == row_count:
                scope_type = "row"
            else:
                scope_type = "both"

        # Layout table detection (single row/col or very small)
        is_layout = row_count <= 1 or col_count <= 1

        issues = []
        if not has_headers and not is_layout:
            issues.append("Table has no header cells (TH)")
        if row_count > 1 and col_count > 1 and has_headers and not has_scope:
            issues.append("Complex table missing scope attributes")

        return TableAudit(
            page=page_num,
            index=index,
            row_count=row_count,
            col_count=col_count,
            has_headers=has_headers,
            header_cells=header_cells,
            has_scope=has_scope,
            scope_type=scope_type,
            is_layout_table=is_layout,
            issues=issues,
        )

    def _audit_forms(self) -> list[FormFieldAudit]:
        """Audit all form fields in the PDF."""
        forms = []

        if not self._pdf:
            return forms

        root = self._pdf.Root

        # Check for AcroForm
        if "/AcroForm" not in root:
            return forms

        acro_form = root["/AcroForm"]
        if "/Fields" not in acro_form:
            return forms

        fields = acro_form["/Fields"]

        def process_field(field, index: int, page_num: int = 0):
            import pikepdf

            if not isinstance(field, pikepdf.Dictionary):
                return None

            # Get field type
            ft = str(field.get("/FT", "")).lstrip("/")
            field_type_map = {
                "Tx": "text",
                "Btn": "button",  # Will refine below
                "Ch": "select",
                "Sig": "signature",
            }
            field_type = field_type_map.get(ft, "unknown")

            # Refine button type
            if ft == "Btn":
                flags = int(field.get("/Ff", 0))
                if flags & (1 << 16):  # Pushbutton
                    field_type = "button"
                elif flags & (1 << 15):  # Radio
                    field_type = "radio"
                else:
                    field_type = "checkbox"

            # Get field name
            field_name = None
            if "/T" in field:
                field_name = str(field["/T"])

            # Get tooltip (TU = alternate field name for AT)
            tooltip = None
            if "/TU" in field:
                tooltip = str(field["/TU"])

            # Get page
            if "/P" in field:
                try:
                    page_ref = field["/P"]
                    for i, page in enumerate(self._pdf.pages):
                        if page.obj == page_ref:
                            page_num = i
                            break
                except Exception:
                    pass

            # Check if required
            flags = int(field.get("/Ff", 0))
            is_required = bool(flags & 2)
            is_readonly = bool(flags & 1)

            # Get default value
            default_value = None
            if "/V" in field:
                default_value = str(field["/V"])

            # Determine if has label (from structure or TU)
            has_tooltip = tooltip is not None and len(tooltip.strip()) > 0
            has_label = field_name is not None and len(field_name.strip()) > 0

            issues = []
            if not has_tooltip and not has_label:
                issues.append("Form field has no accessible name")
            elif not has_tooltip:
                issues.append("Form field missing tooltip (TU attribute)")

            return FormFieldAudit(
                page=page_num,
                index=index,
                field_name=field_name,
                field_type=field_type,
                has_label=has_label,
                label_text=field_name,
                has_tooltip=has_tooltip,
                tooltip_text=tooltip,
                is_required=is_required,
                is_readonly=is_readonly,
                default_value=default_value,
                issues=issues,
            )

        # Process all fields
        for idx, field in enumerate(fields):
            audit = process_field(field, idx)
            if audit:
                forms.append(audit)

        return forms

    def _audit_links(self) -> list[LinkAudit]:
        """Audit all links in the PDF."""
        links = []

        # Use PyMuPDF for link extraction
        if self._fitz_doc:
            pages_to_audit = min(len(self._fitz_doc), MAX_AUDIT_PAGES)
            for page_num in range(pages_to_audit):
                page = self._fitz_doc[page_num]
                page_links = page.get_links()

                for link_idx, link in enumerate(page_links):
                    kind = link.get("kind", 0)
                    dest = None
                    dest_type = "unknown"
                    is_internal = False

                    # Determine link type and destination
                    # PyMuPDF link kinds:
                    # 0 = LINK_NONE (no destination)
                    # 1 = LINK_GOTO (internal page jump)
                    # 2 = LINK_URI (external URL)
                    # 3 = LINK_GOTOR (to another file)
                    # 4 = LINK_LAUNCH (launch external app)
                    # 5 = LINK_NAMED (named destination)
                    if kind == 0:  # LINK_NONE
                        dest = None
                        dest_type = "none"
                    elif kind == 1:  # LINK_GOTO
                        dest_page = link.get("page", -1)
                        dest = f"Page {dest_page + 1}" if dest_page >= 0 else "Unknown"
                        dest_type = "goto"
                        is_internal = True
                    elif kind == 2:  # LINK_URI
                        dest = link.get("uri", "")
                        dest_type = "uri"
                    elif kind == 3:  # LINK_GOTOR (to another file)
                        dest = link.get("file", "")
                        dest_type = "gotor"
                    elif kind == 4:  # LINK_LAUNCH (launch external application)
                        dest = link.get("file", "")
                        dest_type = "launch"
                    elif kind == 5:  # LINK_NAMED
                        dest = link.get("name", "")
                        dest_type = "named"

                    # Get link rect
                    rect = link.get("from", None)
                    bbox = None
                    if rect:
                        bbox = (rect.x0, rect.y0, rect.x1, rect.y1)

                    # Extract link text - use a multi-step approach for reliability
                    link_text = None
                    alt_text = None

                    # Step 1: Try to get alt text from annotation "Contents" field
                    # This is the proper way to provide accessible link text in PDFs
                    alt_text = link.get("contents", None)
                    if alt_text and isinstance(alt_text, str):
                        alt_text = alt_text.strip()
                        if not alt_text:
                            alt_text = None

                    # Step 2: Extract text from bounding box
                    raw_text = None
                    if rect:
                        try:
                            raw_text = page.get_text("text", clip=rect).strip()
                        except Exception:
                            pass

                    # Step 3: Clean up extracted text
                    if raw_text:
                        # Clean TOC-style entries (strip leading page numbers)
                        cleaned_text = _clean_toc_text(raw_text)

                        # Check for garbage text (misaligned rectangles)
                        if not _is_garbage_text(cleaned_text):
                            link_text = cleaned_text

                    # If we have alt text but no link text, use alt text as display
                    if alt_text and not link_text:
                        link_text = alt_text

                    # Check if descriptive
                    is_descriptive = True
                    if link_text:
                        for pattern in NON_DESCRIPTIVE_PATTERNS:
                            if re.match(pattern, link_text.lower()):
                                is_descriptive = False
                                break

                    issues = []
                    if not link_text:
                        issues.append("Link has no visible text")
                    elif not is_descriptive:
                        issues.append(f"Non-descriptive link text: '{link_text}'")

                    links.append(LinkAudit(
                        page=page_num,
                        index=link_idx,
                        bbox=bbox,
                        link_text=link_text,
                        destination=dest,
                        destination_type=dest_type,
                        is_internal=is_internal,
                        is_descriptive=is_descriptive,
                        alt_text=alt_text,
                        issues=issues,
                    ))

        return links

    def _audit_lists(self) -> list[ListAudit]:
        """
        Audit all lists in the PDF for proper L/LI/Lbl/LBody structure.

        Validates Matterhorn 13-001, 13-002 requirements for list semantics.
        """
        lists = []
        nodes_visited = [0]
        max_nodes = 5000

        if not self._pdf:
            return lists

        root = self._pdf.Root
        if "/StructTreeRoot" not in root:
            return lists

        struct_root = root["/StructTreeRoot"]
        list_index = 0

        def traverse(element, page_num=None, depth=0):
            nonlocal list_index

            # Limit traversal
            if nodes_visited[0] >= max_nodes or depth > 50:
                return
            nodes_visited[0] += 1

            import pikepdf

            if isinstance(element, pikepdf.Dictionary):
                # Get page number (only check pages we're auditing)
                if "/Pg" in element:
                    try:
                        page_ref = element["/Pg"]
                        pages_to_check = min(len(self._pdf.pages), MAX_AUDIT_PAGES)
                        for i in range(pages_to_check):
                            if self._pdf.pages[i].obj == page_ref:
                                page_num = i
                                break
                    except Exception:
                        pass

                tag = str(element.get("/S", "")).lstrip("/")

                if tag == "L" and (page_num is None or page_num < MAX_AUDIT_PAGES):
                    list_audit = self._analyze_list(element, page_num or 0, list_index)
                    lists.append(list_audit)
                    list_index += 1

                # Traverse children
                if "/K" in element and nodes_visited[0] < max_nodes:
                    k_value = element["/K"]
                    if isinstance(k_value, pikepdf.Array):
                        for child in k_value:
                            if nodes_visited[0] >= max_nodes:
                                break
                            traverse(child, page_num, depth + 1)
                    else:
                        traverse(k_value, page_num, depth + 1)

        traverse(struct_root)
        return lists

    def _analyze_list(self, list_element, page_num: int, index: int) -> ListAudit:
        """
        Analyze a single list element for proper structure.

        Validates:
        - L should contain only LI children
        - LI should contain Lbl and/or LBody
        - Nested lists should be inside LBody, not directly under L
        """
        import pikepdf

        item_count = 0
        items_with_label = 0
        items_with_body = 0
        nested_list_count = 0
        has_proper_structure = True
        issues = []

        def check_list_item(li_element):
            """Check a single list item."""
            nonlocal items_with_label, items_with_body, nested_list_count
            nonlocal has_proper_structure, issues

            has_lbl = False
            has_lbody = False

            if "/K" not in li_element:
                issues.append("List item has no content")
                has_proper_structure = False
                return

            k_value = li_element["/K"]
            children = k_value if isinstance(k_value, pikepdf.Array) else [k_value]

            for child in children:
                if isinstance(child, pikepdf.Dictionary):
                    child_tag = str(child.get("/S", "")).lstrip("/")
                    if child_tag == "Lbl":
                        has_lbl = True
                    elif child_tag == "LBody":
                        has_lbody = True
                        # Check for nested lists in LBody (this is correct)
                        if "/K" in child:
                            lbody_k = child["/K"]
                            lbody_children = lbody_k if isinstance(lbody_k, pikepdf.Array) else [lbody_k]
                            for lbody_child in lbody_children:
                                if isinstance(lbody_child, pikepdf.Dictionary):
                                    lbody_tag = str(lbody_child.get("/S", "")).lstrip("/")
                                    if lbody_tag == "L":
                                        nested_list_count += 1
                    elif child_tag == "L":
                        # Nested list directly under LI (wrong - should be in LBody)
                        issues.append("Nested list should be inside LBody, not directly under LI")
                        has_proper_structure = False
                        nested_list_count += 1

            if has_lbl:
                items_with_label += 1
            if has_lbody:
                items_with_body += 1

            # At minimum, LI should have LBody or some content
            if not has_lbody and not has_lbl:
                issues.append("List item missing both Lbl and LBody")

        def analyze_children(element):
            """Analyze direct children of L element."""
            nonlocal item_count, has_proper_structure, issues

            if "/K" not in element:
                issues.append("List has no children")
                has_proper_structure = False
                return

            k_value = element["/K"]
            children = k_value if isinstance(k_value, pikepdf.Array) else [k_value]

            for child in children:
                if isinstance(child, pikepdf.Dictionary):
                    child_tag = str(child.get("/S", "")).lstrip("/")
                    if child_tag == "LI":
                        item_count += 1
                        check_list_item(child)
                    elif child_tag == "L":
                        # Nested list directly under L (wrong structure)
                        issues.append("Nested list directly under L (should be in LI/LBody)")
                        has_proper_structure = False
                    else:
                        # Non-LI child under L
                        issues.append(f"Invalid child '{child_tag}' directly under L (should be LI)")
                        has_proper_structure = False

        analyze_children(list_element)

        # Summary validation
        if item_count == 0:
            issues.append("List contains no list items")
            has_proper_structure = False
        elif items_with_body == 0:
            issues.append("No list items have LBody content")

        return ListAudit(
            page=page_num,
            index=index,
            item_count=item_count,
            has_proper_structure=has_proper_structure,
            items_with_label=items_with_label,
            items_with_body=items_with_body,
            nested_list_count=nested_list_count,
            issues=issues,
        )

    def _audit_annotations(self) -> list[AnnotationAudit]:
        """
        Audit non-link annotations for accessibility.

        Checks Text (sticky notes), Highlight, Stamp, FileAttachment, etc.
        for accessible descriptions.
        """
        annotations = []

        # Use PyMuPDF for annotation extraction
        if self._fitz_doc:
            pages_to_audit = min(len(self._fitz_doc), MAX_AUDIT_PAGES)
            for page_num in range(pages_to_audit):
                page = self._fitz_doc[page_num]
                ann_idx = 0

                for annot in page.annots():
                    if annot is None:
                        continue

                    # Get annotation type
                    annot_type = annot.type[0]  # Integer type code

                    # Skip links (type 1) and widgets/form fields (type 20)
                    if annot_type in (1, 20):
                        continue

                    # Only process known annotation types
                    if annot_type not in ACCESSIBLE_ANNOTATION_TYPES:
                        continue

                    type_name = ACCESSIBLE_ANNOTATION_TYPES[annot_type]

                    # Get annotation properties
                    rect = annot.rect
                    bbox = (rect.x0, rect.y0, rect.x1, rect.y1) if rect else None

                    # Get accessible content
                    contents = annot.info.get("content", None)
                    title = annot.info.get("title", None)
                    subject = annot.info.get("subject", None)

                    # Clean up values
                    contents = contents.strip() if contents else None
                    title = title.strip() if title else None
                    subject = subject.strip() if subject else None

                    has_contents = bool(contents)
                    has_title = bool(title)

                    issues = []
                    accessible_desc = contents or subject or title

                    # Check for missing descriptions
                    if type_name in ("Text", "FileAttachment", "Sound", "Stamp"):
                        if not accessible_desc:
                            issues.append(f"{type_name} annotation missing accessible description")
                    elif type_name in ("Highlight", "Underline", "Squiggly", "StrikeOut"):
                        if not accessible_desc:
                            issues.append(f"{type_name} annotation has no explanation note")

                    annotations.append(AnnotationAudit(
                        page=page_num,
                        index=ann_idx,
                        annotation_type=type_name,
                        type_code=annot_type,
                        bbox=bbox,
                        has_contents=has_contents,
                        contents=contents,
                        has_title=has_title,
                        title=title,
                        subject=subject,
                        issues=issues,
                    ))
                    ann_idx += 1

        return annotations

    def _audit_vector_graphics(self) -> list[VectorGraphicAudit]:
        """
        Detect and audit vector graphics (icons, shapes) in the PDF.

        Uses PyMuPDF's get_drawings() to find vector path operations,
        then clusters them by proximity to identify distinct icon-like objects.

        Checks both:
        - Artifact regions (decorative, correctly excluded)
        - Figure regions with alt text (properly tagged)

        Returns:
            List of VectorGraphicAudit for detected vector graphics
        """
        vectors = []

        if not self._fitz_doc:
            return vectors

        pages_to_audit = min(len(self._fitz_doc), MAX_AUDIT_PAGES)

        for page_num in range(pages_to_audit):
            page = self._fitz_doc[page_num]

            try:
                drawings = page.get_drawings()
            except Exception as e:
                logger.debug(f"Failed to get drawings from page {page_num + 1}: {e}")
                continue

            # Get artifact regions from content stream (decorative)
            artifact_regions = self._get_artifact_regions(page)

            # Get Figure regions with alt text from content stream + structure tree
            figure_regions = self._get_figure_regions_with_alt(page, page_num)

            # Find icon-like clusters
            clusters = self._cluster_vector_drawings(drawings)

            for idx, cluster in enumerate(clusters):
                bbox = cluster["bbox"]
                width = bbox[2] - bbox[0]
                height = bbox[3] - bbox[1]

                # Check if this cluster is inside an artifact region (decorative)
                is_artifact = self._is_in_artifact_region(bbox, artifact_regions)

                # Heuristic: very small shapes are also likely decorative
                is_decorative = is_artifact or width < 15 or height < 15

                # Check if this cluster is inside a Figure region (tagged)
                alt_text = None
                has_alt_text = False
                if not is_decorative:
                    alt_text = self._find_figure_alt_for_bbox(bbox, figure_regions)
                    has_alt_text = alt_text is not None and len(alt_text.strip()) > 0

                issues = []
                if not is_decorative and not has_alt_text:
                    issues.append("Vector graphic without alternative text")

                vectors.append(VectorGraphicAudit(
                    page=page_num,
                    index=idx,
                    bbox=bbox,
                    width=width,
                    height=height,
                    has_alt_text=has_alt_text,
                    alt_text=alt_text,
                    is_decorative=is_decorative,
                    path_count=cluster["path_count"],
                    fill_colors=cluster["color_count"],
                    issues=issues,
                ))

        return vectors

    def _get_artifact_regions(self, page) -> list[tuple[float, float, float, float]]:
        """
        Extract artifact bounding boxes from page content stream.

        In tagged PDFs, decorative content is marked with /Artifact BMC...EMC
        in the content stream. This method parses those markers to find
        artifact regions.

        Args:
            page: PyMuPDF page object

        Returns:
            List of bounding boxes (x0, y0, x1, y1) for artifact regions
        """
        import re

        artifact_regions = []

        try:
            contents = page.get_contents()
            if not contents:
                return artifact_regions

            doc = page.parent

            for xref in contents:
                stream = doc.xref_stream(xref)
                if not stream:
                    continue

                if isinstance(stream, bytes):
                    stream = stream.decode('latin-1', errors='replace')

                # Find artifact sections: /Artifact BMC ... EMC
                artifact_pattern = r'/Artifact[^\n]*BMC(.*?)EMC'
                matches = re.findall(artifact_pattern, stream, re.DOTALL)

                for match in matches:
                    # Find rectangle operations (x y w h re)
                    rect_pattern = r'([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+re'
                    rects = re.findall(rect_pattern, match)
                    for r in rects:
                        x, y, w, h = float(r[0]), float(r[1]), float(r[2]), float(r[3])
                        # Convert to (x0, y0, x1, y1) format
                        artifact_regions.append((x, y, x + w, y + h))

                    # Also detect Form XObjects (images/logos) via transformation matrix
                    if '/Fm' in match and 'Do' in match:
                        cm_pattern = r'([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s+cm'
                        cm_match = re.search(cm_pattern, match)
                        if cm_match:
                            a, b, c, d, e, f = [float(x) for x in cm_match.groups()]
                            # a, d are scale factors; e, f are translation
                            # Approximate bounding box from transformation
                            width = abs(a) if abs(a) > 1 else 100
                            height = abs(d) if abs(d) > 1 else 100
                            artifact_regions.append((e, f - height, e + width, f))

        except Exception as e:
            logger.debug(f"Failed to extract artifact regions: {e}")

        return artifact_regions

    def _is_in_artifact_region(
        self,
        bbox: tuple[float, float, float, float],
        artifact_regions: list[tuple[float, float, float, float]],
        tolerance: float = 5.0,
    ) -> bool:
        """
        Check if a bounding box is inside any artifact region.

        Args:
            bbox: Bounding box to check (x0, y0, x1, y1)
            artifact_regions: List of artifact bounding boxes
            tolerance: Overlap tolerance in points

        Returns:
            True if bbox overlaps with any artifact region
        """
        x0, y0, x1, y1 = bbox

        for ax0, ay0, ax1, ay1 in artifact_regions:
            # Check for overlap with tolerance
            if not (x1 < ax0 - tolerance or ax1 < x0 - tolerance or
                    y1 < ay0 - tolerance or ay1 < y0 - tolerance):
                return True

        return False

    def _get_figure_regions_with_alt(
        self,
        page,
        page_num: int,
    ) -> list[tuple[tuple[float, float, float, float], str | None]]:
        """
        Extract Figure marked content regions with their alt text.

        In tagged PDFs, meaningful graphics are marked with /Figure BDC...EMC
        or /Figure <</MCID N>> BDC...EMC in the content stream. This method
        parses those markers to find Figure regions and looks up their alt text
        in the structure tree.

        Args:
            page: PyMuPDF page object
            page_num: 0-indexed page number

        Returns:
            List of (bbox, alt_text) tuples for Figure regions
        """
        import re

        figure_regions = []

        # First, build a map of MCIDs to alt text from the structure tree
        mcid_to_alt = self._get_mcid_alt_texts_for_page(page_num)

        try:
            contents = page.get_contents()
            if not contents:
                return figure_regions

            doc = page.parent

            for xref in contents:
                stream = doc.xref_stream(xref)
                if not stream:
                    continue

                if isinstance(stream, bytes):
                    stream = stream.decode('latin-1', errors='replace')

                # Find Figure sections with MCID: /Figure <</MCID N>> BDC ... EMC
                figure_mcid_pattern = r'/Figure\s*<<\s*/MCID\s*(\d+)\s*>>\s*BDC(.*?)EMC'
                matches = re.findall(figure_mcid_pattern, stream, re.DOTALL)

                for mcid_str, content in matches:
                    mcid = int(mcid_str)
                    alt_text = mcid_to_alt.get(mcid)

                    # Find rectangle operations (x y w h re)
                    rect_pattern = r'([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+re'
                    rects = re.findall(rect_pattern, content)
                    for r in rects:
                        x, y, w, h = float(r[0]), float(r[1]), float(r[2]), float(r[3])
                        bbox = (x, y, x + w, y + h)
                        figure_regions.append((bbox, alt_text))

                    # Also detect Form XObjects via transformation matrix
                    if 'Do' in content:
                        cm_pattern = r'([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s+cm'
                        cm_match = re.search(cm_pattern, content)
                        if cm_match:
                            a, b, c, d, e, f = [float(x) for x in cm_match.groups()]
                            width = abs(a) if abs(a) > 1 else 100
                            height = abs(d) if abs(d) > 1 else 100
                            bbox = (e, f - height, e + width, f)
                            figure_regions.append((bbox, alt_text))

                # Also handle simple /Figure BMC without MCID (less common)
                simple_figure_pattern = r'/Figure\s+BMC(.*?)EMC'
                simple_matches = re.findall(simple_figure_pattern, stream, re.DOTALL)
                for content in simple_matches:
                    # These don't have MCIDs, so no alt text lookup possible
                    rect_pattern = r'([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+re'
                    rects = re.findall(rect_pattern, content)
                    for r in rects:
                        x, y, w, h = float(r[0]), float(r[1]), float(r[2]), float(r[3])
                        bbox = (x, y, x + w, y + h)
                        # No alt text for simple BMC markers
                        figure_regions.append((bbox, None))

        except Exception as e:
            logger.debug(f"Failed to extract Figure regions: {e}")

        return figure_regions

    def _get_mcid_alt_texts_for_page(self, page_num: int) -> dict[int, str]:
        """
        Get a mapping of MCID to alt text for Figure elements on a specific page.

        Args:
            page_num: 0-indexed page number

        Returns:
            Dict mapping MCID to alt text string
        """
        mcid_to_alt = {}

        if not self._pdf:
            return mcid_to_alt

        root = self._pdf.Root
        if "/StructTreeRoot" not in root:
            return mcid_to_alt

        struct_root = root["/StructTreeRoot"]
        nodes_visited = [0]
        max_nodes = 5000

        def traverse(element, current_page=None, depth=0):
            if nodes_visited[0] >= max_nodes or depth > 50:
                return
            nodes_visited[0] += 1

            import pikepdf

            if isinstance(element, pikepdf.Dictionary):
                # Track page from /Pg reference
                if "/Pg" in element:
                    try:
                        page_ref = element["/Pg"]
                        for i in range(min(len(self._pdf.pages), MAX_AUDIT_PAGES)):
                            if self._pdf.pages[i].obj == page_ref:
                                current_page = i
                                break
                    except Exception:
                        pass

                # Check if this is a Figure with alt text on our target page
                tag = str(element.get("/S", "")).lstrip("/")
                if tag == "Figure" and current_page == page_num:
                    alt_text = None
                    if "/Alt" in element:
                        alt_text = str(element["/Alt"]).strip()

                    # Get MCID from /K if it's an integer or dict with MCID
                    if "/K" in element:
                        k_value = element["/K"]
                        if isinstance(k_value, int):
                            mcid_to_alt[k_value] = alt_text
                        elif isinstance(k_value, pikepdf.Dictionary):
                            if "/MCID" in k_value:
                                mcid = int(k_value["/MCID"])
                                mcid_to_alt[mcid] = alt_text
                        elif isinstance(k_value, pikepdf.Array):
                            # Multiple content items
                            for item in k_value:
                                if isinstance(item, int):
                                    mcid_to_alt[item] = alt_text
                                elif isinstance(item, pikepdf.Dictionary) and "/MCID" in item:
                                    mcid = int(item["/MCID"])
                                    mcid_to_alt[mcid] = alt_text

                # Traverse children
                if "/K" in element and nodes_visited[0] < max_nodes:
                    k_value = element["/K"]
                    if isinstance(k_value, pikepdf.Array):
                        for child in k_value:
                            if nodes_visited[0] >= max_nodes:
                                break
                            if isinstance(child, pikepdf.Dictionary):
                                traverse(child, current_page, depth + 1)
                    elif isinstance(k_value, pikepdf.Dictionary):
                        traverse(k_value, current_page, depth + 1)

        traverse(struct_root)
        return mcid_to_alt

    def _find_figure_alt_for_bbox(
        self,
        bbox: tuple[float, float, float, float],
        figure_regions: list[tuple[tuple[float, float, float, float], str | None]],
        tolerance: float = 5.0,
    ) -> str | None:
        """
        Find alt text for a bounding box if it overlaps with a Figure region.

        Args:
            bbox: Bounding box to check (x0, y0, x1, y1)
            figure_regions: List of (bbox, alt_text) tuples
            tolerance: Overlap tolerance in points

        Returns:
            Alt text if found, None otherwise
        """
        x0, y0, x1, y1 = bbox

        for (fx0, fy0, fx1, fy1), alt_text in figure_regions:
            # Check for overlap with tolerance
            if not (x1 < fx0 - tolerance or fx1 < x0 - tolerance or
                    y1 < fy0 - tolerance or fy1 < y0 - tolerance):
                return alt_text

        return None

    def _cluster_vector_drawings(
        self,
        drawings: list[dict],
    ) -> list[dict]:
        """
        Cluster nearby vector drawings into distinct objects.

        Icons are often composed of multiple path operations that need
        to be grouped together. This uses spatial clustering based on
        bounding box proximity.

        Args:
            drawings: List of drawing dictionaries from page.get_drawings()

        Returns:
            List of cluster dictionaries with bbox, path_count, color_count
        """
        import fitz

        # Filter to icon-sized drawings (10-100px, roughly square)
        candidates = []
        for d in drawings:
            rect = d.get("rect")
            if not rect:
                continue

            w, h = rect.width, rect.height

            # Filter by size: icon-like (10-100px)
            if 10 < w < 100 and 10 < h < 100:
                # Check aspect ratio (roughly square-ish, allow up to 2.5:1)
                aspect = min(w, h) / max(w, h) if max(w, h) > 0 else 0
                if aspect > 0.4:
                    candidates.append({
                        "rect": rect,
                        "fill": d.get("fill"),
                    })

        if not candidates:
            return []

        # Cluster by proximity (merge overlapping/adjacent drawings)
        clusters = []
        used = set()

        for i, c in enumerate(candidates):
            if i in used:
                continue

            # Start new cluster
            cluster_rect = fitz.Rect(c["rect"])
            cluster_colors = {c["fill"]} if c["fill"] else set()
            path_count = 1
            used.add(i)

            # Iteratively find nearby drawings to merge
            # Repeat until no more merges happen
            changed = True
            while changed:
                changed = False
                for j, other in enumerate(candidates):
                    if j in used:
                        continue
                    other_rect = fitz.Rect(other["rect"])
                    # Check if within 5px of current cluster
                    expanded = cluster_rect + (-5, -5, 5, 5)
                    if expanded.intersects(other_rect):
                        cluster_rect |= other_rect  # Union of rectangles
                        if other["fill"]:
                            cluster_colors.add(other["fill"])
                        path_count += 1
                        used.add(j)
                        changed = True

            # Only include if the final cluster is still icon-sized
            final_w = cluster_rect.width
            final_h = cluster_rect.height
            if 10 < final_w < 150 and 10 < final_h < 150:
                clusters.append({
                    "bbox": tuple(cluster_rect),
                    "path_count": path_count,
                    "color_count": len(cluster_colors),
                })

        return clusters

    def get_vector_dual_size(
        self,
        page_num: int,
        bbox: tuple[float, float, float, float],
        thumbnail_size: int = 100,
        lightbox_size: int = 400,
    ) -> tuple[str | None, str | None]:
        """
        Render a vector region at two sizes for display.

        Args:
            page_num: 0-indexed page number
            bbox: Bounding box (x0, y0, x1, y1)
            thumbnail_size: Maximum dimension for thumbnail (default 100px)
            lightbox_size: Maximum dimension for lightbox (default 400px)

        Returns:
            Tuple of (thumbnail_base64, lightbox_base64), either may be None
        """
        if not self._fitz_doc:
            return None, None

        try:
            import base64
            import fitz
            from io import BytesIO
            from PIL import Image

            page = self._fitz_doc[page_num]
            clip_rect = fitz.Rect(bbox)

            # Add small padding
            clip_rect = clip_rect + (-2, -2, 2, 2)

            # Render at 4x resolution for quality
            mat = fitz.Matrix(4, 4)
            pix = page.get_pixmap(matrix=mat, clip=clip_rect, alpha=True)

            # Convert to PIL image
            if pix.alpha:
                img = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
            else:
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            # Generate lightbox version (larger)
            lightbox_img = img.copy()
            if max(img.width, img.height) > lightbox_size:
                lightbox_img.thumbnail((lightbox_size, lightbox_size), Image.Resampling.LANCZOS)
            lightbox_output = BytesIO()
            lightbox_img.save(lightbox_output, format="PNG", optimize=True)
            lightbox_base64 = base64.b64encode(lightbox_output.getvalue()).decode("ascii")

            # Generate thumbnail (smaller)
            img.thumbnail((thumbnail_size, thumbnail_size), Image.Resampling.LANCZOS)
            thumb_output = BytesIO()
            img.save(thumb_output, format="PNG", optimize=True)
            thumbnail_base64 = base64.b64encode(thumb_output.getvalue()).decode("ascii")

            return thumbnail_base64, lightbox_base64

        except Exception as e:
            logger.debug(f"Failed to render vector region: {e}")
            return None, None


def audit_pdf_content(
    pdf_path: Path | str,
    include_thumbnails: bool = False,
    max_thumbnail_size: int = 100,
) -> ContentAuditResult:
    """
    Convenience function to audit PDF content.

    Args:
        pdf_path: Path to the PDF file
        include_thumbnails: Whether to extract thumbnails for images
        max_thumbnail_size: Maximum thumbnail dimension in pixels

    Returns:
        ContentAuditResult with all content audits
    """
    with PDFContentAuditor(pdf_path) as auditor:
        result = auditor.audit()

        # Optionally populate thumbnails for images
        if include_thumbnails and result.images:
            for img in result.images[:50]:  # Limit to first 50 images
                thumbnail = auditor.get_image_thumbnail(
                    img.page,
                    img.index,
                    max_size=max_thumbnail_size,
                )
                img.thumbnail_base64 = thumbnail

        return result


def get_content_audit_summary(result: ContentAuditResult) -> str:
    """
    Generate a human-readable summary of the content audit.

    Args:
        result: ContentAuditResult from audit

    Returns:
        Multi-line string summary
    """
    lines = [
        "Content Audit Summary",
        "=" * 40,
    ]

    # Images
    if result.total_images > 0:
        lines.append(f"\nImages: {result.total_images}")
        if result.images_without_alt > 0:
            lines.append(f"  ✗ {result.images_without_alt} missing alt text")
        if result.images_decorative > 0:
            lines.append(f"  ○ {result.images_decorative} decorative")
        if result.images_without_alt == 0:
            lines.append("  ✓ All images have alt text")
    else:
        lines.append("\nImages: None found")

    # Tables
    if result.total_tables > 0:
        lines.append(f"\nTables: {result.total_tables}")
        if result.tables_without_headers > 0:
            lines.append(f"  ✗ {result.tables_without_headers} missing headers")
        if result.tables_layout > 0:
            lines.append(f"  ⚠ {result.tables_layout} layout tables")
        if result.tables_without_headers == 0 and result.tables_layout == 0:
            lines.append("  ✓ All tables properly structured")
    else:
        lines.append("\nTables: None found")

    # Forms
    if result.total_form_fields > 0:
        lines.append(f"\nForm Fields: {result.total_form_fields}")
        if result.fields_without_labels > 0:
            lines.append(f"  ✗ {result.fields_without_labels} missing labels")
        else:
            lines.append("  ✓ All fields labeled")
    else:
        lines.append("\nForm Fields: None found")

    # Links
    if result.total_links > 0:
        lines.append(f"\nLinks: {result.total_links}")
        if result.links_missing_text > 0:
            lines.append(f"  ✗ {result.links_missing_text} missing text")
        if result.links_non_descriptive > 0:
            lines.append(f"  ⚠ {result.links_non_descriptive} non-descriptive")
        if result.links_missing_text == 0 and result.links_non_descriptive == 0:
            lines.append("  ✓ All links accessible")
    else:
        lines.append("\nLinks: None found")

    # Lists
    if result.total_lists > 0:
        lines.append(f"\nLists: {result.total_lists}")
        if result.lists_with_issues > 0:
            lines.append(f"  ✗ {result.lists_with_issues} with structure issues")
        else:
            lines.append("  ✓ All lists properly structured")
    else:
        lines.append("\nLists: None found")

    # Annotations
    if result.total_annotations > 0:
        lines.append(f"\nAnnotations: {result.total_annotations}")
        if result.annotations_without_description > 0:
            lines.append(f"  ⚠ {result.annotations_without_description} missing descriptions")
        else:
            lines.append("  ✓ All annotations have descriptions")
    else:
        lines.append("\nAnnotations: None found")

    # Vector Graphics
    if result.total_vector_graphics > 0:
        lines.append(f"\nVector Graphics: {result.total_vector_graphics}")
        vector_with_alt = result.total_vector_graphics - result.vector_graphics_without_alt - result.vector_graphics_decorative
        if result.vector_graphics_decorative > 0:
            lines.append(f"  ✓ {result.vector_graphics_decorative} decorative (excluded from accessibility tree)")
        if vector_with_alt > 0:
            lines.append(f"  ✓ {vector_with_alt} with alt text")
        if result.vector_graphics_without_alt > 0:
            lines.append(f"  ✗ {result.vector_graphics_without_alt} need alt text")
        elif result.vector_graphics_decorative == 0 and vector_with_alt == 0:
            lines.append("  ✓ All vector graphics accessible")
        # Add review hint when there are decorative vectors
        if result.vector_graphics_decorative > 0:
            lines.append("  ℹ Review decorative items to verify they don't convey meaning")
    else:
        lines.append("\nVector Graphics: None found")

    return "\n".join(lines)
