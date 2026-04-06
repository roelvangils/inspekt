"""
Unit tests for PDF Content Auditor.

Tests for auditing images, tables, forms, and links in PDFs.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


class TestImageAudit:
    """Unit tests for ImageAudit dataclass."""

    def test_image_audit_properties(self):
        """Test ImageAudit properties."""
        from inspekt.services.pdf_content_auditor import ImageAudit

        audit = ImageAudit(
            page=0,
            index=0,
            bbox=(72.0, 500.0, 300.0, 700.0),
            width=228.0,
            height=200.0,
            has_alt_text=True,
            alt_text="Company logo showing blue circle",
            is_decorative=False,
        )

        assert audit.page == 0
        assert audit.display_page == 1  # 1-indexed for display
        assert audit.width == 228.0
        assert audit.has_alt_text
        assert audit.status == "pass"  # Has alt text

    def test_image_without_alt_text(self):
        """Test ImageAudit for image without alt text."""
        from inspekt.services.pdf_content_auditor import ImageAudit

        audit = ImageAudit(
            page=0,
            index=1,
            bbox=(72.0, 500.0, 300.0, 700.0),
            width=228.0,
            height=200.0,
            has_alt_text=False,
            alt_text=None,
            is_decorative=False,
            issues=["Missing alternative text"],
        )

        assert not audit.has_alt_text
        assert audit.status == "fail"
        assert len(audit.issues) > 0

    def test_decorative_image(self):
        """Test ImageAudit for decorative image."""
        from inspekt.services.pdf_content_auditor import ImageAudit

        audit = ImageAudit(
            page=0,
            index=2,
            bbox=(0, 0, 100, 100),
            width=100.0,
            height=100.0,
            has_alt_text=False,
            alt_text=None,
            is_decorative=True,
        )

        assert audit.is_decorative
        assert audit.status == "pass"  # Decorative images don't need alt text


class TestTableAudit:
    """Unit tests for TableAudit dataclass."""

    def test_table_audit_properties(self):
        """Test TableAudit properties."""
        from inspekt.services.pdf_content_auditor import TableAudit

        audit = TableAudit(
            page=1,
            index=0,
            bbox=(72.0, 400.0, 500.0, 600.0),
            row_count=5,
            col_count=3,
            has_headers=True,
            scope_type="column",
            has_scope=True,
        )

        assert audit.page == 1
        assert audit.display_page == 2  # 1-indexed
        assert audit.row_count == 5
        assert audit.col_count == 3
        assert audit.has_headers
        assert audit.scope_type == "column"
        assert audit.size_str == "5×3"
        assert audit.status == "pass"

    def test_table_without_headers(self):
        """Test TableAudit for table without headers."""
        from inspekt.services.pdf_content_auditor import TableAudit

        audit = TableAudit(
            page=0,
            index=0,
            bbox=(72.0, 400.0, 500.0, 600.0),
            row_count=10,
            col_count=4,
            has_headers=False,
            scope_type=None,
            issues=["Missing table headers"],
        )

        assert not audit.has_headers
        assert audit.status == "fail"


class TestFormFieldAudit:
    """Unit tests for FormFieldAudit dataclass."""

    def test_form_field_audit_properties(self):
        """Test FormFieldAudit properties."""
        from inspekt.services.pdf_content_auditor import FormFieldAudit

        audit = FormFieldAudit(
            page=2,
            index=0,
            field_type="text",
            field_name="firstName",
            has_label=True,
            label_text="First Name",
            has_tooltip=True,
            tooltip_text="Enter your first name",
            is_required=True,
        )

        assert audit.page == 2
        assert audit.display_page == 3
        assert audit.field_type == "text"
        assert audit.accessible_name == "Enter your first name"  # Tooltip preferred
        assert audit.has_tooltip
        assert audit.is_required
        assert audit.status == "pass"

    def test_form_field_without_label(self):
        """Test FormFieldAudit for field without accessible name."""
        from inspekt.services.pdf_content_auditor import FormFieldAudit

        audit = FormFieldAudit(
            page=0,
            index=0,
            field_type="checkbox",
            field_name="agree",
            has_label=False,
            label_text=None,
            has_tooltip=False,
            tooltip_text=None,
            is_required=False,
            issues=["Missing accessible name/label"],
        )

        assert audit.accessible_name == "agree"  # Falls back to field_name
        assert not audit.has_tooltip
        assert audit.status == "fail"


class TestLinkAudit:
    """Unit tests for LinkAudit dataclass."""

    def test_link_audit_properties(self):
        """Test LinkAudit properties."""
        from inspekt.services.pdf_content_auditor import LinkAudit

        audit = LinkAudit(
            page=0,
            index=0,
            link_text="Read the full report",
            destination="https://example.com/report.pdf",
            destination_type="external",
            is_descriptive=True,
        )

        assert audit.page == 0
        assert audit.link_text == "Read the full report"
        assert audit.destination_type == "external"
        assert audit.is_descriptive
        assert audit.status == "pass"

    def test_non_descriptive_link(self):
        """Test LinkAudit for non-descriptive link text."""
        from inspekt.services.pdf_content_auditor import LinkAudit

        audit = LinkAudit(
            page=0,
            index=1,
            link_text="click here",
            destination="https://example.com",
            destination_type="external",
            is_descriptive=False,
            issues=["Non-descriptive link text"],
        )

        assert audit.link_text == "click here"
        assert not audit.is_descriptive
        assert audit.status == "warn"

    def test_link_missing_text(self):
        """Test LinkAudit for link without text."""
        from inspekt.services.pdf_content_auditor import LinkAudit

        audit = LinkAudit(
            page=0,
            index=2,
            link_text=None,
            destination="https://example.com",
            destination_type="external",
            is_descriptive=False,
            issues=["Link has no text"],
        )

        assert audit.link_text is None
        assert audit.status == "fail"


class TestContentAuditResult:
    """Unit tests for ContentAuditResult dataclass."""

    def test_content_audit_result_properties(self):
        """Test ContentAuditResult aggregation properties."""
        from inspekt.services.pdf_content_auditor import (
            ContentAuditResult,
            ImageAudit,
            TableAudit,
            FormFieldAudit,
            LinkAudit,
        )

        images = [
            ImageAudit(page=0, index=0, width=100, height=100, has_alt_text=True),
            ImageAudit(page=1, index=0, width=100, height=100, has_alt_text=False),
            ImageAudit(page=2, index=0, width=100, height=100, is_decorative=True),
        ]

        tables = [
            TableAudit(page=0, index=0, row_count=5, col_count=3, has_headers=True),
            TableAudit(page=1, index=0, row_count=10, col_count=4, has_headers=False),
        ]

        forms = [
            FormFieldAudit(page=0, index=0, field_type="text", field_name="name", has_label=True, has_tooltip=True),
            FormFieldAudit(page=0, index=1, field_type="text", field_name="email", has_label=False, has_tooltip=False),
        ]

        links = [
            LinkAudit(page=0, index=0, link_text="Learn more", destination="https://example.com", is_descriptive=True),
            LinkAudit(page=0, index=1, link_text="click here", destination="https://example.com", is_descriptive=False),
            LinkAudit(page=1, index=0, link_text=None, destination="https://example.com"),
        ]

        result = ContentAuditResult(
            images=images,
            tables=tables,
            forms=forms,
            links=links,
            total_images=3,
            total_tables=2,
            total_form_fields=2,
            total_links=3,
        )

        # Test basic counts
        assert result.total_images == 3
        assert result.total_tables == 2
        assert result.total_form_fields == 2
        assert result.total_links == 3


class TestNonDescriptivePatterns:
    """Tests for non-descriptive link text patterns."""

    def test_patterns_exist(self):
        """Test that NON_DESCRIPTIVE_PATTERNS constant exists."""
        from inspekt.services.pdf_content_auditor import NON_DESCRIPTIVE_PATTERNS

        assert NON_DESCRIPTIVE_PATTERNS is not None
        assert len(NON_DESCRIPTIVE_PATTERNS) > 0

    def test_patterns_are_regex(self):
        """Test that patterns are valid regex strings."""
        import re
        from inspekt.services.pdf_content_auditor import NON_DESCRIPTIVE_PATTERNS

        for pattern in NON_DESCRIPTIVE_PATTERNS:
            # Should not raise
            re.compile(pattern, re.IGNORECASE)


class TestPDFContentAuditor:
    """Unit tests for PDFContentAuditor class."""

    def test_initialization(self):
        """Test PDFContentAuditor initialization."""
        from inspekt.services.pdf_content_auditor import PDFContentAuditor
        from pathlib import Path

        # Should initialize
        auditor = PDFContentAuditor("test.pdf")
        assert auditor.pdf_path == Path("test.pdf")
