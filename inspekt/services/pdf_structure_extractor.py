"""
PDF Structure Tree Extractor.

Extracts the complete tag structure from a PDF document for
accessibility analysis and visualization. The structure tree
defines the logical reading order and semantic relationships.

Uses pikepdf to navigate the StructTreeRoot and extract:
- Tag hierarchy (Document, Part, H1-H6, P, Table, etc.)
- Attributes (Alt text, Lang, ActualText)
- Reading order sequence
- Structure validation issues
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Standard PDF structure tag types
STANDARD_TAGS = {
    # Grouping elements
    "Document",
    "Part",
    "Art",
    "Sect",
    "Div",
    "BlockQuote",
    "Caption",
    "TOC",
    "TOCI",
    "Index",
    "NonStruct",
    "Private",
    # Block-level elements
    "H",
    "H1",
    "H2",
    "H3",
    "H4",
    "H5",
    "H6",
    "P",
    "L",
    "LI",
    "Lbl",
    "LBody",
    # Table elements
    "Table",
    "TR",
    "TH",
    "TD",
    "THead",
    "TBody",
    "TFoot",
    # Inline elements
    "Span",
    "Quote",
    "Note",
    "Reference",
    "BibEntry",
    "Code",
    # Illustration elements
    "Figure",
    "Formula",
    "Form",
    # Special elements
    "Link",
    "Annot",
    "Ruby",
    "Warichu",
}

# Heading tags for hierarchy validation
HEADING_TAGS = {"H", "H1", "H2", "H3", "H4", "H5", "H6"}

# Maximum nodes to extract before stopping (prevents hanging on massive PDFs)
MAX_STRUCTURE_NODES = 5000


@dataclass
class StructureNode:
    """A node in the PDF structure tree."""

    tag_type: str  # Document, Part, H1, P, Figure, Table, etc.
    role: str | None = None  # Mapped role if using RoleMap
    title: str | None = None  # /T attribute
    alt_text: str | None = None  # /Alt attribute
    actual_text: str | None = None  # /ActualText attribute
    language: str | None = None  # /Lang attribute
    children: list[StructureNode] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    page_number: int | None = None  # 0-indexed
    text_content: str | None = None  # Extracted text preview
    has_content: bool = False
    issues: list[str] = field(default_factory=list)
    node_id: str = ""  # Unique identifier for HTML rendering
    figure_index: int | None = None  # Index for matching with image thumbnails

    @property
    def display_name(self) -> str:
        """Display name for the node."""
        if self.title:
            return f"{self.tag_type}: {self.title[:50]}"
        if self.text_content:
            return f"{self.tag_type}: {self.text_content[:50]}"
        if self.alt_text:
            return f"{self.tag_type} (alt: {self.alt_text[:30]})"
        return self.tag_type

    @property
    def is_heading(self) -> bool:
        """Check if this is a heading element."""
        return self.tag_type in HEADING_TAGS

    @property
    def heading_level(self) -> int | None:
        """Get heading level (1-6) or None if not a heading."""
        if self.tag_type == "H":
            return 0  # Generic heading
        if self.tag_type.startswith("H") and len(self.tag_type) == 2:
            try:
                return int(self.tag_type[1])
            except ValueError:
                return None
        return None

    @property
    def has_issues(self) -> bool:
        """Check if this node has any issues."""
        return len(self.issues) > 0


@dataclass
class ReadingOrderItem:
    """An item in the reading order sequence."""

    index: int  # Position in reading order (1-indexed)
    tag_type: str
    text_preview: str  # First 100 chars of content
    page_number: int  # 0-indexed
    node_id: str  # Reference to StructureNode
    has_alt_text: bool = False
    has_issues: bool = False

    @property
    def display_page(self) -> int:
        """1-indexed page number for display."""
        return self.page_number + 1


@dataclass
class HeadingOutlineItem:
    """A heading in the document outline."""

    level: int  # 1-6 (H1-H6), 0 for generic H
    text: str
    page: int | None  # 0-indexed
    node_id: str
    issues: list[str] = field(default_factory=list)

    @property
    def display_page(self) -> int | None:
        """1-indexed page number for display."""
        return self.page + 1 if self.page is not None else None

    @property
    def indent(self) -> str:
        """Indentation for text display."""
        return "  " * (self.level - 1) if self.level > 0 else ""

    @property
    def markdown_prefix(self) -> str:
        """Markdown heading prefix."""
        return "#" * max(self.level, 1)


@dataclass
class StructureStatistics:
    """Statistics about the structure tree."""

    total_nodes: int = 0
    tag_counts: dict[str, int] = field(default_factory=dict)
    heading_count: int = 0
    figure_count: int = 0
    table_count: int = 0
    link_count: int = 0
    form_count: int = 0
    list_count: int = 0
    max_heading_level: int = 0
    min_heading_level: int = 7
    has_document_root: bool = False
    nodes_with_issues: int = 0
    figures_without_alt: int = 0


@dataclass
class StructureValidationResult:
    """Result of structure tree validation."""

    is_valid: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    heading_order_valid: bool = True
    has_document_tag: bool = False
    has_reading_order: bool = False


@dataclass
class StructureExtractionResult:
    """Complete result of structure extraction."""

    root: StructureNode | None
    reading_order: list[ReadingOrderItem]
    statistics: StructureStatistics
    validation: StructureValidationResult
    has_structure: bool = False
    extraction_error: str | None = None
    heading_outline: list[HeadingOutlineItem] = field(default_factory=list)
    was_truncated: bool = False  # True if extraction was truncated due to node limit


class PDFStructureExtractor:
    """
    Extracts and validates PDF structure tree.

    Uses pikepdf to navigate the StructTreeRoot dictionary and
    build a tree of StructureNode objects representing the
    document's logical structure.
    """

    def __init__(self, pdf_path: Path | str, max_nodes: int | None = None):
        """
        Initialize the extractor with a PDF file.

        Args:
            pdf_path: Path to the PDF file
            max_nodes: Maximum nodes to extract (default: MAX_STRUCTURE_NODES)
        """
        self.pdf_path = Path(pdf_path)
        self._pdf = None
        self._role_map: dict[str, str] = {}
        self._node_counter = 0
        self._reading_order: list[ReadingOrderItem] = []
        self._max_nodes = max_nodes if max_nodes is not None else MAX_STRUCTURE_NODES
        self._extraction_truncated = False

    def __enter__(self) -> PDFStructureExtractor:
        """Open the PDF file."""
        import pikepdf

        self._pdf = pikepdf.open(self.pdf_path)
        self._load_role_map()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close the PDF file."""
        if self._pdf:
            self._pdf.close()
            self._pdf = None

    def _load_role_map(self) -> None:
        """Load the RoleMap dictionary if present."""
        if not self._pdf:
            return

        root = self._pdf.Root
        if "/StructTreeRoot" in root:
            struct_root = root["/StructTreeRoot"]
            if "/RoleMap" in struct_root:
                role_map = struct_root["/RoleMap"]
                for key in role_map:
                    mapped = str(role_map[key])
                    # Remove leading slash
                    clean_key = key.lstrip("/")
                    clean_mapped = mapped.lstrip("/")
                    self._role_map[clean_key] = clean_mapped

    def _get_next_node_id(self) -> str:
        """Generate unique node ID."""
        self._node_counter += 1
        return f"node-{self._node_counter}"

    def extract(self) -> StructureExtractionResult:
        """
        Extract the complete structure tree.

        Returns:
            StructureExtractionResult with tree, reading order, and validation
        """
        if not self._pdf:
            return StructureExtractionResult(
                root=None,
                reading_order=[],
                statistics=StructureStatistics(),
                validation=StructureValidationResult(is_valid=False, issues=["PDF not opened"]),
                has_structure=False,
                extraction_error="PDF file not opened. Use context manager.",
            )

        root_catalog = self._pdf.Root

        # Check if document has structure tree
        if "/StructTreeRoot" not in root_catalog:
            return StructureExtractionResult(
                root=None,
                reading_order=[],
                statistics=StructureStatistics(),
                validation=StructureValidationResult(
                    is_valid=False,
                    issues=["Document does not have a structure tree (not tagged)"],
                ),
                has_structure=False,
            )

        try:
            struct_root = root_catalog["/StructTreeRoot"]
            self._node_counter = 0
            self._reading_order = []

            # Extract the tree starting from StructTreeRoot
            root_node = self._extract_node(struct_root, is_root=True)

            # Calculate statistics
            statistics = self._calculate_statistics(root_node)

            # Validate the structure
            validation = self._validate_structure(root_node, statistics)

            # Extract heading outline
            heading_outline = self._get_heading_outline(root_node)

            return StructureExtractionResult(
                root=root_node,
                reading_order=self._reading_order,
                statistics=statistics,
                validation=validation,
                has_structure=True,
                heading_outline=heading_outline,
                was_truncated=self._extraction_truncated,
            )

        except Exception as e:
            logger.warning(f"Failed to extract structure tree: {e}")
            return StructureExtractionResult(
                root=None,
                reading_order=[],
                statistics=StructureStatistics(),
                validation=StructureValidationResult(is_valid=False, issues=[str(e)]),
                has_structure=False,
                extraction_error=str(e),
            )

    def _extract_node(
        self,
        element,
        is_root: bool = False,
        parent_page: int | None = None,
    ) -> StructureNode | None:
        """
        Recursively extract a structure element and its children.

        Args:
            element: pikepdf structure element object
            is_root: Whether this is the StructTreeRoot
            parent_page: Page number from parent (for inheritance)

        Returns:
            StructureNode representing this element, or None if extraction limit reached
        """

        # Check if we've hit the extraction limit
        if self._node_counter >= self._max_nodes:
            if not self._extraction_truncated:
                self._extraction_truncated = True
                logger.debug(f"Structure tree extraction truncated at {self._max_nodes} nodes")
            return None

        node_id = self._get_next_node_id()

        # Determine tag type
        if is_root:
            tag_type = "StructTreeRoot"
        else:
            tag_type = str(element.get("/S", "Unknown")).lstrip("/")

        # Get mapped role if using custom tags
        role = self._role_map.get(tag_type)

        # Extract attributes
        title = self._get_string_attr(element, "/T")
        alt_text = self._get_string_attr(element, "/Alt")
        actual_text = self._get_string_attr(element, "/ActualText")
        language = self._get_string_attr(element, "/Lang")

        # Get page number
        page_number = parent_page
        if "/Pg" in element:
            try:
                page_ref = element["/Pg"]
                # Find page index
                for i, page in enumerate(self._pdf.pages):
                    if page.obj == page_ref:
                        page_number = i
                        break
            except Exception:
                pass

        # Extract additional attributes
        attributes = {}
        for key in ["/E", "/ID", "/A", "/C", "/R", "/P"]:
            if key in element:
                attr_name = key.lstrip("/")
                try:
                    attributes[attr_name] = str(element[key])
                except Exception:
                    pass

        # Extract text content preview
        text_content = None
        has_content = False
        if "/K" in element:
            k_value = element["/K"]
            text_content = self._extract_text_preview(k_value)
            has_content = text_content is not None and len(text_content.strip()) > 0

        # Validate and collect issues
        issues = self._validate_node(tag_type, alt_text, role, has_content)

        node = StructureNode(
            tag_type=tag_type,
            role=role,
            title=title,
            alt_text=alt_text,
            actual_text=actual_text,
            language=language,
            attributes=attributes,
            page_number=page_number,
            text_content=text_content,
            has_content=has_content,
            issues=issues,
            node_id=node_id,
        )

        # Add to reading order if it has content
        if has_content and not is_root and page_number is not None:
            self._reading_order.append(
                ReadingOrderItem(
                    index=len(self._reading_order) + 1,
                    tag_type=tag_type,
                    text_preview=text_content[:100] if text_content else "",
                    page_number=page_number,
                    node_id=node_id,
                    has_alt_text=alt_text is not None,
                    has_issues=len(issues) > 0,
                )
            )

        # Process children
        if "/K" in element:
            k_value = element["/K"]
            children = self._get_children(k_value, page_number)
            node.children = children

        return node

    def _get_children(self, k_value, parent_page: int | None) -> list[StructureNode]:
        """Extract child nodes from /K entry."""
        import pikepdf

        children = []

        # Stop if we've hit the extraction limit
        if self._extraction_truncated:
            return children

        if isinstance(k_value, pikepdf.Array):
            for item in k_value:
                if self._extraction_truncated:
                    break
                child = self._process_k_item(item, parent_page)
                if child:
                    children.append(child)
        else:
            child = self._process_k_item(k_value, parent_page)
            if child:
                children.append(child)

        return children

    def _process_k_item(self, item, parent_page: int | None) -> StructureNode | None:
        """Process a single /K item."""
        import pikepdf

        # Dictionary is a structure element
        if isinstance(item, pikepdf.Dictionary):
            if "/S" in item:  # Has a type - it's a structure element
                return self._extract_node(item, parent_page=parent_page)
            elif "/Type" in item:
                # Could be MCR (marked content reference) or OBJR (object reference)
                type_val = str(item.get("/Type", "")).lstrip("/")
                if type_val == "MCR":
                    # Marked content reference - get page
                    return None  # MCRs don't create structure nodes
                elif type_val == "OBJR":
                    # Object reference (annotation, form field)
                    return None  # OBJRs don't create structure nodes

        # Integer is a marked content ID - not a structure node
        return None

    def _extract_text_preview(self, k_value) -> str | None:
        """Extract text preview from content references."""
        import pikepdf

        # This is a simplified implementation
        # Full text extraction would require parsing content streams
        texts = []

        def collect_text(item):
            if isinstance(item, (str, pikepdf.String)):
                texts.append(str(item))
            elif isinstance(item, pikepdf.Array):
                for sub_item in item:
                    collect_text(sub_item)
            elif isinstance(item, pikepdf.Dictionary):
                if "/ActualText" in item:
                    texts.append(str(item["/ActualText"]))
                elif "/Alt" in item:
                    texts.append(str(item["/Alt"]))

        collect_text(k_value)

        if texts:
            return " ".join(texts)[:200]
        return None

    def _get_string_attr(self, element, key: str) -> str | None:
        """Safely get a string attribute."""
        if key in element:
            try:
                value = element[key]
                if value:
                    return str(value).strip()
            except Exception:
                pass
        return None

    def _validate_node(
        self,
        tag_type: str,
        alt_text: str | None,
        role: str | None,
        has_content: bool,
    ) -> list[str]:
        """Validate a single structure node."""
        issues = []

        # Figures should have alt text
        effective_tag = role if role else tag_type
        if effective_tag == "Figure" and not alt_text:
            issues.append("Figure missing alternative text")

        # Unknown/non-standard tags without role mapping
        if tag_type not in STANDARD_TAGS and not role:
            issues.append(f"Non-standard tag '{tag_type}' not mapped to standard role")

        return issues

    def _calculate_statistics(self, root: StructureNode) -> StructureStatistics:
        """Calculate statistics from the structure tree."""
        stats = StructureStatistics()
        stats.has_document_root = root.tag_type == "Document" or any(
            c.tag_type == "Document" for c in root.children
        )

        def traverse(node: StructureNode):
            stats.total_nodes += 1

            effective_tag = node.role if node.role else node.tag_type
            stats.tag_counts[effective_tag] = stats.tag_counts.get(effective_tag, 0) + 1

            if node.has_issues:
                stats.nodes_with_issues += 1

            if effective_tag in HEADING_TAGS:
                stats.heading_count += 1
                level = node.heading_level
                if level is not None and level > 0:
                    stats.max_heading_level = max(stats.max_heading_level, level)
                    stats.min_heading_level = min(stats.min_heading_level, level)

            if effective_tag == "Figure":
                stats.figure_count += 1
                if not node.alt_text:
                    stats.figures_without_alt += 1

            if effective_tag == "Table":
                stats.table_count += 1

            if effective_tag == "Link":
                stats.link_count += 1

            if effective_tag == "Form":
                stats.form_count += 1

            if effective_tag == "L":
                stats.list_count += 1

            for child in node.children:
                traverse(child)

        traverse(root)

        # Fix min heading level if no headings
        if stats.min_heading_level == 7:
            stats.min_heading_level = 0

        return stats

    def _validate_structure(
        self,
        root: StructureNode,
        stats: StructureStatistics,
    ) -> StructureValidationResult:
        """Validate the overall structure tree."""
        issues = []
        warnings = []
        heading_order_valid = True

        # Check for Document root
        has_document = stats.has_document_root

        if not has_document:
            issues.append("Missing /Document root element")

        # Check heading order
        heading_sequence = []

        def collect_headings(node: StructureNode):
            effective_tag = node.role if node.role else node.tag_type
            if effective_tag in HEADING_TAGS:
                level = node.heading_level
                if level is not None:
                    heading_sequence.append(level)
            for child in node.children:
                collect_headings(child)

        collect_headings(root)

        # Validate heading sequence (shouldn't skip levels)
        last_level = 0
        for level in heading_sequence:
            if level > 0 and level > last_level + 1:
                heading_order_valid = False
                issues.append(f"Heading level skipped: H{last_level} to H{level}")
                break
            if level > 0:
                last_level = level

        # Check for figures without alt text
        if stats.figures_without_alt > 0:
            issues.append(f"{stats.figures_without_alt} figure(s) missing alternative text")

        # Check for reading order
        has_reading_order = len(self._reading_order) > 0

        if not has_reading_order:
            warnings.append("No content found in structure tree")

        is_valid = len(issues) == 0

        return StructureValidationResult(
            is_valid=is_valid,
            issues=issues,
            warnings=warnings,
            heading_order_valid=heading_order_valid,
            has_document_tag=has_document,
            has_reading_order=has_reading_order,
        )

    def _get_heading_outline(self, root: StructureNode) -> list[HeadingOutlineItem]:
        """
        Extract heading outline from the structure tree.

        Collects all headings (H, H1-H6) in document order and identifies
        hierarchy issues like skipped levels.
        """
        outline: list[HeadingOutlineItem] = []
        last_level = 0

        def traverse(node: StructureNode):
            nonlocal last_level

            effective_tag = node.role if node.role else node.tag_type

            if effective_tag in HEADING_TAGS:
                level = node.heading_level
                if level is None:
                    level = 0  # Generic H

                # Get heading text
                text = node.text_content or node.title or node.alt_text or "(No text)"

                # Check for issues
                issues = []
                if level > 0 and level > last_level + 1:
                    issues.append(f"Skipped from H{last_level} to H{level}")

                outline.append(
                    HeadingOutlineItem(
                        level=level,
                        text=text[:200],  # Truncate long headings
                        page=node.page_number,
                        node_id=node.node_id,
                        issues=issues,
                    )
                )

                if level > 0:
                    last_level = level

            # Traverse children
            for child in node.children:
                traverse(child)

        traverse(root)
        return outline


def extract_structure(pdf_path: Path | str) -> StructureExtractionResult:
    """
    Convenience function to extract structure from a PDF.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        StructureExtractionResult with complete structure analysis
    """
    with PDFStructureExtractor(pdf_path) as extractor:
        return extractor.extract()


def get_structure_summary(result: StructureExtractionResult) -> str:
    """
    Generate a human-readable summary of the structure.

    Args:
        result: StructureExtractionResult from extraction

    Returns:
        Multi-line string summary
    """
    if not result.has_structure:
        return "Document is not tagged (no structure tree)"

    lines = [
        "Structure Tree Summary",
        "=" * 40,
        f"Total nodes: {result.statistics.total_nodes}",
    ]

    if result.statistics.heading_count > 0:
        lines.append(
            f"Headings: {result.statistics.heading_count} "
            f"(H{result.statistics.min_heading_level}-H{result.statistics.max_heading_level})"
        )

    if result.statistics.figure_count > 0:
        alt_info = ""
        if result.statistics.figures_without_alt > 0:
            alt_info = f" ({result.statistics.figures_without_alt} missing alt text)"
        lines.append(f"Figures: {result.statistics.figure_count}{alt_info}")

    if result.statistics.table_count > 0:
        lines.append(f"Tables: {result.statistics.table_count}")

    if result.statistics.link_count > 0:
        lines.append(f"Links: {result.statistics.link_count}")

    if result.statistics.list_count > 0:
        lines.append(f"Lists: {result.statistics.list_count}")

    lines.append("")
    lines.append("Validation:")
    if result.validation.is_valid:
        lines.append("  ✓ Structure is valid")
    else:
        for issue in result.validation.issues:
            lines.append(f"  ✗ {issue}")

    for warning in result.validation.warnings:
        lines.append(f"  ⚠ {warning}")

    return "\n".join(lines)


def format_heading_outline_text(outline: list[HeadingOutlineItem]) -> str:
    """
    Format heading outline as indented text.

    Args:
        outline: List of HeadingOutlineItem from extraction

    Returns:
        Multi-line string with indented heading hierarchy
    """
    if not outline:
        return "No headings found"

    lines = []
    for item in outline:
        # Create visual representation
        level_indicator = f"H{item.level}" if item.level > 0 else "H"
        page_indicator = f" (p. {item.display_page})" if item.display_page else ""
        issue_indicator = " ⚠" if item.issues else ""

        lines.append(
            f"{item.indent}{level_indicator}: {item.text}{page_indicator}{issue_indicator}"
        )

    return "\n".join(lines)


def format_heading_outline_markdown(outline: list[HeadingOutlineItem]) -> str:
    """
    Format heading outline as Markdown.

    Args:
        outline: List of HeadingOutlineItem from extraction

    Returns:
        Markdown string with heading hierarchy
    """
    if not outline:
        return "*No headings found*"

    lines = []
    for item in outline:
        prefix = item.markdown_prefix
        text = item.text
        page_note = f" *(page {item.display_page})*" if item.display_page else ""

        if item.issues:
            lines.append(f"{prefix} {text}{page_note} ⚠️")
            for issue in item.issues:
                lines.append(f"  > **Issue:** {issue}")
        else:
            lines.append(f"{prefix} {text}{page_note}")

    return "\n".join(lines)
