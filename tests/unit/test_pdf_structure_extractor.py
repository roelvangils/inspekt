"""
Unit tests for PDF Structure Extractor.

Tests for extracting and validating PDF tag structure trees.
"""

from __future__ import annotations


class TestStructureNode:
    """Unit tests for StructureNode dataclass."""

    def test_structure_node_properties(self):
        """Test StructureNode properties."""
        from inspekt.services.pdf_structure_extractor import StructureNode

        node = StructureNode(
            tag_type="H1",
            children=[],
            text_content="Introduction",
            alt_text=None,
            page_number=0,
        )

        assert node.tag_type == "H1"
        assert node.text_content == "Introduction"
        assert node.page_number == 0
        assert node.is_heading  # H1 should be a heading

    def test_is_heading_property(self):
        """Test is_heading property for various tag types."""
        from inspekt.services.pdf_structure_extractor import StructureNode

        heading_tags = ["H1", "H2", "H3", "H4", "H5", "H6", "H"]
        non_heading_tags = ["P", "Span", "Figure", "Table", "Document"]

        for tag in heading_tags:
            node = StructureNode(tag_type=tag, children=[])
            assert node.is_heading, f"{tag} should be recognized as heading"

        for tag in non_heading_tags:
            node = StructureNode(tag_type=tag, children=[])
            assert not node.is_heading, f"{tag} should not be recognized as heading"

    def test_heading_level_property(self):
        """Test heading_level property."""
        from inspekt.services.pdf_structure_extractor import StructureNode

        assert StructureNode(tag_type="H1").heading_level == 1
        assert StructureNode(tag_type="H2").heading_level == 2
        assert StructureNode(tag_type="H6").heading_level == 6
        assert StructureNode(tag_type="H").heading_level == 0  # Generic heading
        assert StructureNode(tag_type="P").heading_level is None

    def test_has_issues_property(self):
        """Test has_issues property."""
        from inspekt.services.pdf_structure_extractor import StructureNode

        # No issues
        node_ok = StructureNode(tag_type="P", issues=[])
        assert not node_ok.has_issues

        # Has issues
        node_with_issues = StructureNode(tag_type="Figure", issues=["Missing alt text"])
        assert node_with_issues.has_issues

    def test_display_name_property(self):
        """Test display_name property."""
        from inspekt.services.pdf_structure_extractor import StructureNode

        # With title
        node_title = StructureNode(tag_type="H1", title="Introduction")
        assert "Introduction" in node_title.display_name

        # With text content
        node_text = StructureNode(tag_type="P", text_content="Some paragraph text")
        assert "Some paragraph" in node_text.display_name

        # Just tag type
        node_plain = StructureNode(tag_type="Document")
        assert node_plain.display_name == "Document"


class TestReadingOrderItem:
    """Unit tests for ReadingOrderItem dataclass."""

    def test_reading_order_item_properties(self):
        """Test ReadingOrderItem properties."""
        from inspekt.services.pdf_structure_extractor import ReadingOrderItem

        item = ReadingOrderItem(
            index=1,
            tag_type="H1",
            text_preview="Chapter 1: Introduction",
            page_number=0,
            node_id="node_1",
        )

        assert item.index == 1
        assert item.tag_type == "H1"
        assert item.text_preview == "Chapter 1: Introduction"
        assert item.page_number == 0
        assert item.display_page == 1  # 1-indexed for display


class TestStructureStatistics:
    """Unit tests for StructureStatistics dataclass."""

    def test_structure_statistics_properties(self):
        """Test StructureStatistics properties."""
        from inspekt.services.pdf_structure_extractor import StructureStatistics

        stats = StructureStatistics(
            total_nodes=50,
            heading_count=5,
            figure_count=3,
            table_count=2,
            link_count=10,
            form_count=5,
            list_count=3,
        )

        assert stats.total_nodes == 50
        assert stats.heading_count == 5
        assert stats.figure_count == 3
        assert stats.table_count == 2


class TestStructureValidationResult:
    """Unit tests for StructureValidationResult dataclass."""

    def test_validation_with_no_issues(self):
        """Test validation with no issues."""
        from inspekt.services.pdf_structure_extractor import StructureValidationResult

        validation = StructureValidationResult(
            is_valid=True,
            has_document_tag=True,
            heading_order_valid=True,
            issues=[],
        )

        assert validation.is_valid
        assert validation.has_document_tag
        assert validation.heading_order_valid
        assert len(validation.issues) == 0

    def test_validation_with_issues(self):
        """Test validation with issues."""
        from inspekt.services.pdf_structure_extractor import StructureValidationResult

        validation = StructureValidationResult(
            is_valid=False,
            has_document_tag=False,
            heading_order_valid=False,
            issues=[
                "Missing Document root element",
                "Heading hierarchy skips from H1 to H3",
            ],
        )

        assert not validation.is_valid
        assert not validation.has_document_tag
        assert not validation.heading_order_valid
        assert len(validation.issues) == 2


class TestStructureExtractionResult:
    """Unit tests for StructureExtractionResult dataclass."""

    def test_result_with_structure(self):
        """Test result with valid structure."""
        from inspekt.services.pdf_structure_extractor import (
            StructureExtractionResult,
            StructureNode,
            StructureStatistics,
            StructureValidationResult,
        )

        root = StructureNode(tag_type="Document", children=[])
        stats = StructureStatistics(total_nodes=1, has_document_root=True)
        validation = StructureValidationResult(is_valid=True, has_document_tag=True)

        result = StructureExtractionResult(
            has_structure=True,
            root=root,
            statistics=stats,
            validation=validation,
            reading_order=[],
        )

        assert result.has_structure
        assert result.root is not None
        assert result.root.tag_type == "Document"

    def test_result_without_structure(self):
        """Test result without structure (untagged PDF)."""
        from inspekt.services.pdf_structure_extractor import (
            StructureExtractionResult,
            StructureStatistics,
            StructureValidationResult,
        )

        result = StructureExtractionResult(
            has_structure=False,
            root=None,
            statistics=StructureStatistics(total_nodes=0),
            validation=StructureValidationResult(is_valid=False, has_document_tag=False),
            reading_order=[],
        )

        assert not result.has_structure
        assert result.root is None


class TestPDFStructureExtractor:
    """Unit tests for PDFStructureExtractor class."""

    def test_initialization(self):
        """Test PDFStructureExtractor initialization."""
        from pathlib import Path

        from inspekt.services.pdf_structure_extractor import PDFStructureExtractor

        # Should initialize without opening file yet
        extractor = PDFStructureExtractor("test.pdf")
        assert extractor.pdf_path == Path("test.pdf")


class TestStandardTags:
    """Tests for standard PDF structure tags."""

    def test_standard_tags_defined(self):
        """Test that STANDARD_TAGS constant exists."""
        from inspekt.services.pdf_structure_extractor import STANDARD_TAGS

        assert STANDARD_TAGS is not None
        assert "Document" in STANDARD_TAGS
        assert "H1" in STANDARD_TAGS
        assert "P" in STANDARD_TAGS
        assert "Table" in STANDARD_TAGS
        assert "Figure" in STANDARD_TAGS

    def test_heading_tags_defined(self):
        """Test that HEADING_TAGS constant exists."""
        from inspekt.services.pdf_structure_extractor import HEADING_TAGS

        assert HEADING_TAGS is not None
        assert "H1" in HEADING_TAGS
        assert "H2" in HEADING_TAGS
        assert "H" in HEADING_TAGS
        assert "P" not in HEADING_TAGS
