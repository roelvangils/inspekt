"""
PDF Tag Visualizer.

Renders PDF pages with visual overlays showing:
- Tag boundaries (colored rectangles)
- Tag type labels
- Reading order numbers
- Issue indicators

Similar to PAC's visual preview feature.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# Tag type to color mapping (Tailwind-inspired)
TAG_COLORS = {
    # Headings (warm colors - progressively cooler)
    "H1": "#dc2626",  # Red-600
    "H2": "#ea580c",  # Orange-600
    "H3": "#ca8a04",  # Yellow-600
    "H4": "#65a30d",  # Lime-600
    "H5": "#16a34a",  # Green-600
    "H6": "#0d9488",  # Teal-600

    # Content (cool colors)
    "P": "#0284c7",       # Sky-600 (blue)
    "Span": "#7c3aed",    # Violet-600

    # Structure elements
    "Document": "#1f2937",  # Gray-800
    "Part": "#374151",      # Gray-700
    "Sect": "#4b5563",      # Gray-600
    "Div": "#6b7280",       # Gray-500
    "Art": "#0891b2",       # Cyan-600

    # Media
    "Figure": "#a855f7",    # Purple-500
    "Formula": "#ec4899",   # Pink-500
    "Caption": "#f472b6",   # Pink-400

    # Tables
    "Table": "#06b6d4",     # Cyan-500
    "TR": "#67e8f9",        # Cyan-300
    "TH": "#0e7490",        # Cyan-700
    "TD": "#22d3ee",        # Cyan-400

    # Lists
    "L": "#f97316",         # Orange-500
    "LI": "#fb923c",        # Orange-400
    "Lbl": "#fdba74",       # Orange-300
    "LBody": "#fed7aa",     # Orange-200

    # Links and navigation
    "Link": "#eab308",      # Yellow-500
    "Reference": "#facc15", # Yellow-400
    "Annot": "#fde047",     # Yellow-300
    "TOC": "#84cc16",       # Lime-500
    "TOCI": "#a3e635",      # Lime-400

    # Forms
    "Form": "#ec4899",      # Pink-500

    # Block-level elements
    "BlockQuote": "#8b5cf6", # Violet-500
    "Quote": "#a78bfa",      # Violet-400
    "Note": "#c4b5fd",       # Violet-300
    "Code": "#6366f1",       # Indigo-500
    "Index": "#818cf8",      # Indigo-400

    # Default
    "Unknown": "#9ca3af",   # Gray-400
}


@dataclass
class TagOverlay:
    """Visual representation of a tag on a PDF page."""

    tag_type: str
    bbox: tuple[float, float, float, float]  # PDF coords (x0, y0, x1, y1)
    reading_order: int
    text_preview: str | None = None
    alt_text: str | None = None
    has_issues: bool = False
    node_id: str | None = None
    detected_language: str | None = None

    @property
    def color(self) -> str:
        """Get the color for this tag type."""
        # Check for heading levels
        if self.tag_type.startswith("H") and len(self.tag_type) == 2:
            return TAG_COLORS.get(self.tag_type, TAG_COLORS["H6"])
        return TAG_COLORS.get(self.tag_type, TAG_COLORS["Unknown"])

    @property
    def display_name(self) -> str:
        """Get a display-friendly tag name."""
        return self.tag_type


@dataclass
class PageTagVisualization:
    """Tag visualization for a single page."""

    page_num: int  # 0-indexed
    width: float   # Page width in points
    height: float  # Page height in points
    tags: list[TagOverlay] = field(default_factory=list)
    image_base64: str | None = None  # Rendered visualization

    @property
    def display_page(self) -> int:
        """1-indexed page number."""
        return self.page_num + 1


class PDFTagVisualizer:
    """
    Renders PDF pages with tag structure overlays.

    Uses PyMuPDF for page rendering and Pillow for overlay drawing.
    """

    def __init__(self, pdf_path: Path | str):
        """
        Initialize the visualizer.

        Args:
            pdf_path: Path to the PDF file
        """
        self.pdf_path = Path(pdf_path)
        self._pdf = None
        self._fitz_doc = None

    def __enter__(self) -> PDFTagVisualizer:
        """Open PDF files."""
        import pikepdf
        self._pdf = pikepdf.open(self.pdf_path)

        try:
            import fitz
            self._fitz_doc = fitz.open(self.pdf_path)
        except ImportError:
            logger.warning("PyMuPDF not available for rendering")
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

    def extract_page_tags(self, page_num: int) -> list[TagOverlay]:
        """
        Extract tag overlays for a specific page.

        Uses PyMuPDF's TEXT_COLLECT_STRUCTURE flag which provides the structure
        tree with tag types and computed bounding boxes for text content.

        Args:
            page_num: 0-indexed page number

        Returns:
            List of TagOverlay objects for elements on this page
        """
        # Prefer PyMuPDF's structure extraction (more reliable bounding boxes)
        if self._fitz_doc and page_num < len(self._fitz_doc):
            tags = self._extract_tags_via_fitz(page_num)
            if tags:
                return tags

        # Fall back to pikepdf-based extraction
        return self._extract_tags_via_pikepdf(page_num)

    def _extract_tags_via_fitz(self, page_num: int) -> list[TagOverlay]:
        """
        Extract tags using PyMuPDF's TEXT_COLLECT_STRUCTURE flag.

        This is the preferred method as it provides accurate bounding boxes
        computed from the actual text rendering.
        """
        try:
            import fitz
        except ImportError:
            return []

        page = self._fitz_doc[page_num]
        flags = fitz.TEXT_COLLECT_STRUCTURE | fitz.TEXT_PRESERVE_WHITESPACE

        try:
            result = page.get_text("rawdict", flags=flags)
        except Exception as e:
            logger.debug(f"Failed to get structured text: {e}")
            return []

        tags = []
        reading_order = [0]  # Use list for mutable counter in nested function

        def compute_bbox_from_block(block: dict) -> tuple[float, float, float, float] | None:
            """Recursively compute bounding box from block and all descendants."""
            block_type = block.get("type")

            if block_type == 0:  # Text block - has valid bbox
                bbox = block.get("bbox")
                if bbox and len(bbox) == 4:
                    return tuple(bbox)
                return None

            elif block_type == 2:  # Structure block
                # Aggregate bboxes from all nested blocks
                all_bboxes = []
                for child in block.get("blocks", []):
                    child_bbox = compute_bbox_from_block(child)
                    if child_bbox:
                        all_bboxes.append(child_bbox)

                if all_bboxes:
                    # Union of all child bboxes
                    x0 = min(b[0] for b in all_bboxes)
                    y0 = min(b[1] for b in all_bboxes)
                    x1 = max(b[2] for b in all_bboxes)
                    y1 = max(b[3] for b in all_bboxes)
                    return (x0, y0, x1, y1)

            return None

        def extract_text_from_block(block: dict) -> str:
            """Recursively extract text from a block."""
            block_type = block.get("type")
            text_parts = []

            if block_type == 0:  # Text block
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        chars = span.get("chars", [])
                        text_parts.append("".join(c.get("c", "") for c in chars))
            elif block_type == 2:  # Structure block
                for child in block.get("blocks", []):
                    text_parts.append(extract_text_from_block(child))

            return " ".join(text_parts).strip()

        def traverse_structure(block: dict, depth: int = 0):
            """Traverse structure tree and extract tags with bboxes."""
            block_type = block.get("type")

            if block_type == 2:  # Structure element
                # Get tag type from 'std' (standardized) or 'raw' field
                tag_type = block.get("std") or block.get("raw", "")

                # Skip Document-level container and abstract structure elements
                skip_tags = {"Document", "Part", "Sect", "Div", "Art", "BlockQuote"}

                if tag_type and tag_type not in skip_tags:
                    bbox = compute_bbox_from_block(block)

                    if bbox:
                        # Convert from PyMuPDF coords (origin top-left) to PDF coords (origin bottom-left)
                        page_height = page.rect.height
                        pdf_bbox = (bbox[0], page_height - bbox[3], bbox[2], page_height - bbox[1])

                        reading_order[0] += 1

                        # Get text preview for content elements
                        text_preview = None
                        detected_language = None
                        if tag_type in ("P", "Span", "H1", "H2", "H3", "H4", "H5", "H6", "Caption", "LBody", "TD", "TH"):
                            text = extract_text_from_block(block)
                            text_preview = text[:200] if text else None
                            # Detect language if text is long enough
                            if text and len(text) >= 50:
                                from inspekt.services.pdf_report import _detect_language_from_text
                                detected_language = _detect_language_from_text(text, sample_size=500)

                        tags.append(TagOverlay(
                            tag_type=tag_type,
                            bbox=pdf_bbox,
                            reading_order=reading_order[0],
                            text_preview=text_preview,
                            alt_text=None,  # PyMuPDF doesn't expose Alt text directly
                            has_issues=False,
                            detected_language=detected_language,
                        ))

                # Always traverse children to find nested content
                for child in block.get("blocks", []):
                    traverse_structure(child, depth + 1)

        # Process all top-level blocks
        for block in result.get("blocks", []):
            traverse_structure(block)

        return tags

    def _extract_tags_via_pikepdf(self, page_num: int) -> list[TagOverlay]:
        """
        Extract tags using pikepdf structure tree traversal.

        This is a fallback method when PyMuPDF extraction fails.
        Note: Bounding box extraction via MCID is unreliable.
        """
        if not self._pdf:
            return []

        tags = []
        reading_order = 0

        root = self._pdf.Root
        if "/StructTreeRoot" not in root:
            logger.debug("No structure tree found")
            return tags

        struct_root = root["/StructTreeRoot"]

        # Build page reference to index lookup table (O(n) once, not O(n²))
        # This dramatically speeds up traversal for large PDFs
        page_ref_to_index = {}
        for i, page in enumerate(self._pdf.pages):
            try:
                # Use objgen tuple as hashable key for the page object reference
                page_ref_to_index[page.obj.objgen] = i
            except Exception:
                pass

        # Limit traversal to prevent extremely slow processing on large PDFs
        max_elements = 50000  # Stop after this many elements
        elements_visited = [0]

        def traverse(element, inherited_page=None, depth=0):
            nonlocal reading_order
            import pikepdf

            # Safety limits to prevent runaway traversal
            elements_visited[0] += 1
            if elements_visited[0] > max_elements or depth > 100:
                return

            if isinstance(element, pikepdf.Dictionary):
                current_page = inherited_page

                # Check for page reference - use cached lookup (O(1) instead of O(n))
                if "/Pg" in element:
                    try:
                        page_ref = element["/Pg"]
                        # Use objgen tuple for O(1) lookup
                        ref_key = page_ref.objgen
                        if ref_key in page_ref_to_index:
                            current_page = page_ref_to_index[ref_key]
                    except Exception:
                        pass

                # Early skip: if this element is on a different page and has no
                # children that could be on our target page, skip it entirely
                # (This is a heuristic - structure isn't always page-ordered)
                if current_page is not None and current_page != page_num:
                    # Check if any children might be on a different page
                    # If this element explicitly references another page, skip its subtree
                    if "/Pg" in element:
                        return

                # Get tag type
                tag_type = str(element.get("/S", "")).lstrip("/")

                # Skip non-tag elements
                if not tag_type:
                    # Still traverse children
                    if "/K" in element:
                        k_value = element["/K"]
                        if isinstance(k_value, pikepdf.Array):
                            for child in k_value:
                                traverse(child, current_page, depth + 1)
                        else:
                            traverse(k_value, current_page, depth + 1)
                    return

                # Try to get bounding box from MCR
                bbox = self._extract_bbox_from_element(element, page_num)

                # Only include if we found a bbox on this page
                if bbox and current_page == page_num:
                    reading_order += 1

                    # Get text content preview
                    text_preview = None
                    if "/ActualText" in element:
                        text_preview = str(element["/ActualText"])[:50]
                    elif tag_type in ("P", "Span", "H1", "H2", "H3", "H4", "H5", "H6", "Caption"):
                        text_preview = self._extract_text_from_element(element)[:50] if self._extract_text_from_element(element) else None

                    # Get alt text for figures
                    alt_text = None
                    if "/Alt" in element:
                        alt_text = str(element["/Alt"])

                    tags.append(TagOverlay(
                        tag_type=tag_type,
                        bbox=bbox,
                        reading_order=reading_order,
                        text_preview=text_preview,
                        alt_text=alt_text,
                        has_issues=False,
                    ))

                # Traverse children
                if "/K" in element:
                    k_value = element["/K"]
                    if isinstance(k_value, pikepdf.Array):
                        for child in k_value:
                            traverse(child, current_page, depth + 1)
                    else:
                        traverse(k_value, current_page, depth + 1)

        traverse(struct_root)
        return tags

    def _extract_bbox_from_element(
        self,
        element,
        target_page: int,
    ) -> tuple[float, float, float, float] | None:
        """
        Extract bounding box from a structure element.

        Tries multiple approaches:
        1. Direct /BBox attribute
        2. MCR (Marked Content Reference) with MCID
        3. Content stream analysis
        """
        import pikepdf

        # Try direct BBox first
        if "/BBox" in element:
            try:
                bbox = element["/BBox"]
                return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
            except Exception:
                pass

        # Try to get from MCR via /K
        if "/K" in element:
            k_value = element["/K"]

            # Single MCR
            if isinstance(k_value, pikepdf.Dictionary):
                if "/MCID" in k_value:
                    mcid = int(k_value["/MCID"])
                    return self._get_bbox_for_mcid(target_page, mcid)

            # Array of MCRs or children
            elif isinstance(k_value, pikepdf.Array):
                for item in k_value:
                    if isinstance(item, pikepdf.Dictionary) and "/MCID" in item:
                        mcid = int(item["/MCID"])
                        bbox = self._get_bbox_for_mcid(target_page, mcid)
                        if bbox:
                            return bbox
                    elif isinstance(item, int):
                        # Direct MCID reference
                        bbox = self._get_bbox_for_mcid(target_page, int(item))
                        if bbox:
                            return bbox

            # Single MCID
            elif isinstance(k_value, int):
                return self._get_bbox_for_mcid(target_page, int(k_value))

        return None

    def _get_bbox_for_mcid(
        self,
        page_num: int,
        mcid: int,
    ) -> tuple[float, float, float, float] | None:
        """
        Get bounding box for a Marked Content ID using PyMuPDF.

        Args:
            page_num: 0-indexed page number
            mcid: Marked Content ID

        Returns:
            Bounding box (x0, y0, x1, y1) or None
        """
        if not self._fitz_doc or page_num >= len(self._fitz_doc):
            return None

        try:
            page = self._fitz_doc[page_num]

            # Try to get text dict with blocks
            text_dict = page.get_text("dict", flags=0)

            # Search through blocks for MCID
            for block in text_dict.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        # PyMuPDF may include mcid in span info
                        if span.get("mcid") == mcid:
                            bbox = span.get("bbox")
                            if bbox:
                                return tuple(bbox)

            # Fallback: estimate from page dimensions
            # This is a rough approximation when precise bbox isn't available
            page_rect = page.rect
            return None  # Return None if we can't find the exact bbox

        except Exception as e:
            logger.debug(f"Failed to get bbox for MCID {mcid}: {e}")
            return None

    def _extract_text_from_element(self, element) -> str:
        """Extract text content from a structure element."""
        import pikepdf

        text_parts = []

        if "/ActualText" in element:
            return str(element["/ActualText"])

        if "/K" in element:
            k_value = element["/K"]
            if isinstance(k_value, str):
                text_parts.append(str(k_value))
            elif isinstance(k_value, pikepdf.Array):
                for item in k_value:
                    if isinstance(item, str):
                        text_parts.append(str(item))

        return " ".join(text_parts)

    def render_page_with_tags(
        self,
        page_num: int,
        tags: list[TagOverlay] | None = None,
        dpi: int = 150,
        show_reading_order: bool = True,
        show_labels: bool = True,
        highlight_issues: bool = True,
    ) -> bytes:
        """
        Render a PDF page with tag boundaries overlaid.

        Args:
            page_num: 0-indexed page number
            tags: List of TagOverlay objects (extracted if not provided)
            dpi: Rendering resolution
            show_reading_order: Whether to show reading order numbers
            show_labels: Whether to show tag type labels
            highlight_issues: Whether to highlight elements with issues

        Returns:
            PNG image bytes
        """
        if not self._fitz_doc:
            raise RuntimeError("PyMuPDF not available")

        if tags is None:
            tags = self.extract_page_tags(page_num)


        # Render the page
        import fitz
        from PIL import Image, ImageDraw, ImageFont
        page = self._fitz_doc[page_num]
        zoom = dpi / 72  # 72 is the default PDF resolution
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        # Convert to PIL Image
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        draw = ImageDraw.Draw(img, "RGBA")

        # Try to load a font for labels
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size=int(12 * zoom))
            small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size=int(10 * zoom))
        except Exception:
            font = ImageFont.load_default()
            small_font = font

        # Draw tag overlays
        for tag in tags:
            # Scale bbox from PDF coordinates to image coordinates
            x0, y0, x1, y1 = tag.bbox
            # PDF coordinates have origin at bottom-left, PIL at top-left
            page_height = page.rect.height
            scaled_bbox = (
                x0 * zoom,
                (page_height - y1) * zoom,  # Flip Y
                x1 * zoom,
                (page_height - y0) * zoom,  # Flip Y
            )

            # Get color with transparency
            color_hex = tag.color
            # Convert hex to RGBA with transparency
            r = int(color_hex[1:3], 16)
            g = int(color_hex[3:5], 16)
            b = int(color_hex[5:7], 16)
            fill_color = (r, g, b, 40)  # 40/255 ~= 15% opacity
            outline_color = (r, g, b, 200)  # 200/255 ~= 78% opacity

            # Draw filled rectangle
            draw.rectangle(scaled_bbox, fill=fill_color, outline=outline_color, width=2)

            # Draw issue indicator
            if highlight_issues and tag.has_issues:
                # Red triangle warning indicator
                warn_x = scaled_bbox[2] - 15
                warn_y = scaled_bbox[1] + 5
                draw.polygon([
                    (warn_x, warn_y + 12),
                    (warn_x + 6, warn_y),
                    (warn_x + 12, warn_y + 12),
                ], fill=(220, 38, 38, 230))

            # Draw reading order number
            if show_reading_order:
                circle_x = scaled_bbox[0] - 12
                circle_y = scaled_bbox[1] - 12
                circle_r = 10
                draw.ellipse(
                    [circle_x, circle_y, circle_x + circle_r * 2, circle_y + circle_r * 2],
                    fill=(30, 41, 59, 220),  # Slate-800
                    outline=(248, 250, 252, 255),  # Slate-50
                )
                # Draw number
                order_text = str(tag.reading_order)
                try:
                    text_bbox = draw.textbbox((0, 0), order_text, font=small_font)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_height = text_bbox[3] - text_bbox[1]
                except AttributeError:
                    # Fallback for older Pillow
                    text_width, text_height = small_font.getsize(order_text) if hasattr(small_font, 'getsize') else (10, 10)
                draw.text(
                    (circle_x + circle_r - text_width / 2, circle_y + circle_r - text_height / 2 - 2),
                    order_text,
                    fill=(255, 255, 255, 255),
                    font=small_font,
                )

            # Draw tag type label
            if show_labels:
                label_text = tag.tag_type
                label_x = scaled_bbox[0] + 4
                label_y = scaled_bbox[1] + 2
                # Background for label
                try:
                    label_bbox = draw.textbbox((0, 0), label_text, font=small_font)
                    label_width = label_bbox[2] - label_bbox[0]
                    label_height = label_bbox[3] - label_bbox[1]
                except AttributeError:
                    label_width, label_height = small_font.getsize(label_text) if hasattr(small_font, 'getsize') else (30, 12)
                draw.rectangle(
                    [label_x, label_y, label_x + label_width + 6, label_y + label_height + 4],
                    fill=(r, g, b, 200),
                )
                draw.text(
                    (label_x + 3, label_y + 2),
                    label_text,
                    fill=(255, 255, 255, 255),
                    font=small_font,
                )

        # Convert to PNG bytes
        output = io.BytesIO()
        img.save(output, format="PNG", optimize=True)
        return output.getvalue()

    def render_reading_order_visualization(
        self,
        page_num: int,
        tags: list[TagOverlay] | None = None,
        dpi: int = 150,
        show_arrows: bool = True,
        highlight_issues: bool = True,
    ) -> tuple[bytes, list[dict]]:
        """
        Render a PDF page with reading order visualization.

        Shows numbered circles at element centroids connected by arrows,
        highlighting potential reading order issues.

        Args:
            page_num: 0-indexed page number
            tags: List of TagOverlay objects (extracted if not provided)
            dpi: Rendering resolution
            show_arrows: Whether to draw arrows between elements
            highlight_issues: Whether to highlight reading order issues

        Returns:
            Tuple of (PNG image bytes, list of detected issues)
        """
        if not self._fitz_doc:
            raise RuntimeError("PyMuPDF not available")

        if tags is None:
            tags = self.extract_page_tags(page_num)

        import math

        import fitz
        from PIL import Image, ImageDraw, ImageFont

        issues = []

        # Render the page
        page = self._fitz_doc[page_num]
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        # Convert to PIL Image
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        draw = ImageDraw.Draw(img, "RGBA")

        # Load font
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size=int(14 * zoom))
        except Exception:
            font = ImageFont.load_default()

        page_height = page.rect.height

        # Calculate centroids for each tag
        centroids = []
        for tag in tags:
            x0, y0, x1, y1 = tag.bbox
            # Scale and flip Y
            cx = ((x0 + x1) / 2) * zoom
            cy = (page_height - (y0 + y1) / 2) * zoom
            centroids.append((cx, cy, tag))

        # Draw arrows connecting consecutive elements
        if show_arrows and len(centroids) > 1:
            for i in range(len(centroids) - 1):
                cx1, cy1, _ = centroids[i]
                cx2, cy2, _ = centroids[i + 1]

                # Calculate distance
                distance = math.sqrt((cx2 - cx1) ** 2 + (cy2 - cy1) ** 2)

                # Detect potential issues
                is_issue = False

                # Issue: backwards jump (next element is significantly higher/left)
                if cy2 < cy1 - 50 * zoom and abs(cx2 - cx1) < 100 * zoom:
                    is_issue = True
                    issues.append({
                        "type": "backwards_jump",
                        "from_order": i + 1,
                        "to_order": i + 2,
                        "message": f"Reading order jumps backwards from element {i + 1} to {i + 2}",
                    })

                # Issue: large horizontal jump might indicate column skipping
                if abs(cx2 - cx1) > pix.width * 0.4:
                    is_issue = True
                    issues.append({
                        "type": "column_jump",
                        "from_order": i + 1,
                        "to_order": i + 2,
                        "message": f"Large horizontal jump between elements {i + 1} and {i + 2} (possible column issue)",
                    })

                # Draw arrow line
                arrow_color = (220, 38, 38, 180) if is_issue else (30, 64, 175, 120)  # Red if issue, blue otherwise
                draw.line([(cx1, cy1), (cx2, cy2)], fill=arrow_color, width=int(2 * zoom))

                # Draw arrowhead
                angle = math.atan2(cy2 - cy1, cx2 - cx1)
                arrow_size = 8 * zoom
                ax1 = cx2 - arrow_size * math.cos(angle - math.pi / 6)
                ay1 = cy2 - arrow_size * math.sin(angle - math.pi / 6)
                ax2 = cx2 - arrow_size * math.cos(angle + math.pi / 6)
                ay2 = cy2 - arrow_size * math.sin(angle + math.pi / 6)
                draw.polygon([(cx2, cy2), (ax1, ay1), (ax2, ay2)], fill=arrow_color)

        # Draw numbered circles at centroids
        circle_radius = 12 * zoom
        for i, (cx, cy, tag) in enumerate(centroids):
            # Circle background
            is_issue_element = any(
                issue["from_order"] == i + 1 or issue["to_order"] == i + 1
                for issue in issues
            )
            circle_color = (220, 38, 38, 240) if is_issue_element else (30, 41, 59, 230)

            draw.ellipse(
                [cx - circle_radius, cy - circle_radius, cx + circle_radius, cy + circle_radius],
                fill=circle_color,
                outline=(255, 255, 255, 255),
                width=int(2 * zoom),
            )

            # Number text
            order_text = str(i + 1)
            try:
                text_bbox = draw.textbbox((0, 0), order_text, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
            except AttributeError:
                text_width, text_height = 10, 12
            draw.text(
                (cx - text_width / 2, cy - text_height / 2 - 2),
                order_text,
                fill=(255, 255, 255, 255),
                font=font,
            )

        # Convert to PNG bytes
        output = io.BytesIO()
        img.save(output, format="PNG", optimize=True)
        return output.getvalue(), issues

    def visualize_pages(
        self,
        pages: list[int] | None = None,
        dpi: int = 150,
        show_reading_order: bool = True,
        show_labels: bool = True,
    ) -> list[PageTagVisualization]:
        """
        Generate visualizations for multiple pages.

        Args:
            pages: List of 0-indexed page numbers (default: all pages)
            dpi: Rendering resolution
            show_reading_order: Whether to show reading order numbers
            show_labels: Whether to show tag type labels

        Returns:
            List of PageTagVisualization objects
        """
        import base64

        if pages is None:
            pages = list(range(len(self._fitz_doc))) if self._fitz_doc else []

        results = []
        for page_num in pages:
            if not self._fitz_doc or page_num >= len(self._fitz_doc):
                continue

            page = self._fitz_doc[page_num]
            tags = self.extract_page_tags(page_num)

            # Only render if there are tags
            image_base64 = None
            if tags:
                try:
                    image_bytes = self.render_page_with_tags(
                        page_num,
                        tags,
                        dpi=dpi,
                        show_reading_order=show_reading_order,
                        show_labels=show_labels,
                    )
                    image_base64 = base64.b64encode(image_bytes).decode("ascii")
                except Exception as e:
                    logger.warning(f"Failed to render page {page_num + 1}: {e}")

            results.append(PageTagVisualization(
                page_num=page_num,
                width=page.rect.width,
                height=page.rect.height,
                tags=tags,
                image_base64=image_base64,
            ))

        return results


def parse_page_range(page_spec: str, max_pages: int) -> list[int]:
    """
    Parse a page specification string.

    Args:
        page_spec: Page specification (e.g., "1,2,3" or "1-5" or "1,3-5,7")
        max_pages: Maximum number of pages in the document

    Returns:
        List of 0-indexed page numbers
    """
    pages = set()
    parts = page_spec.split(",")

    for part in parts:
        part = part.strip()
        if "-" in part:
            # Range
            start, end = part.split("-", 1)
            try:
                start_num = int(start.strip())
                end_num = int(end.strip())
                for p in range(max(1, start_num), min(max_pages + 1, end_num + 1)):
                    pages.add(p - 1)  # Convert to 0-indexed
            except ValueError:
                continue
        else:
            # Single page
            try:
                p = int(part)
                if 1 <= p <= max_pages:
                    pages.add(p - 1)  # Convert to 0-indexed
            except ValueError:
                continue

    return sorted(pages)
