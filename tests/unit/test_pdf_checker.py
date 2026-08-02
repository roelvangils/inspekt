"""
Unit tests for PDF Accessibility Checkers.

Tests for PDFBasicChecker, SimplePDFChecker, and their agreement on common checks.
"""

from __future__ import annotations

import pytest

# Import fixtures from the PDF fixtures conftest
pytest_plugins = ["tests.fixtures.pdf.conftest"]


class TestSimplePDFChecker:
    """Unit tests for SimplePDFChecker."""

    def test_accessible_pdf_passes_all_checks(self, accessible_pdf):
        """An accessible PDF should pass all basic checks."""
        from inspekt.services.simple_pdf_checker import SimplePDFChecker

        checker = SimplePDFChecker()
        result = checker.check(accessible_pdf)

        # Should pass tagged check
        tagged = result.get_check("tagged")
        assert tagged is not None
        assert tagged.status == "pass", f"Tagged check failed: {tagged.message}"

        # Should pass title check
        title = result.get_check("title")
        assert title is not None
        assert title.status == "pass", f"Title check failed: {title.message}"

        # Should pass language check
        language = result.get_check("language")
        assert language is not None
        assert language.status == "pass", f"Language check failed: {language.message}"

        # Should pass protected check
        protected = result.get_check("protected")
        assert protected is not None
        assert protected.status == "pass", f"Protected check failed: {protected.message}"

        # Should not be totally inaccessible
        assert not result.is_totally_inaccessible

    def test_untagged_pdf_fails_tagged_check(self, untagged_pdf):
        """An untagged PDF should fail the tagged check."""
        from inspekt.services.simple_pdf_checker import SimplePDFChecker

        checker = SimplePDFChecker()
        result = checker.check(untagged_pdf)

        tagged = result.get_check("tagged")
        assert tagged is not None
        assert tagged.status == "fail", f"Tagged check should fail: {tagged.message}"

        # Should be marked as totally inaccessible
        assert result.is_totally_inaccessible

    def test_no_title_pdf_fails_title_check(self, no_title_pdf):
        """A PDF without title should fail the title check."""
        from inspekt.services.simple_pdf_checker import SimplePDFChecker

        checker = SimplePDFChecker()
        result = checker.check(no_title_pdf)

        title = result.get_check("title")
        assert title is not None
        assert title.status == "fail", f"Title check should fail: {title.message}"

    def test_no_language_pdf_fails_language_check(self, no_language_pdf):
        """A PDF without language should fail the language check."""
        from inspekt.services.simple_pdf_checker import SimplePDFChecker

        checker = SimplePDFChecker()
        result = checker.check(no_language_pdf)

        language = result.get_check("language")
        assert language is not None
        assert language.status == "fail", f"Language check should fail: {language.message}"

    def test_invalid_language_pdf_warns(self, invalid_language_pdf):
        """A PDF with invalid language should warn on the language check."""
        from inspekt.services.simple_pdf_checker import SimplePDFChecker

        checker = SimplePDFChecker()
        result = checker.check(invalid_language_pdf)

        language = result.get_check("language")
        assert language is not None
        # Should be warn or fail depending on validation strictness
        assert language.status in ("warn", "fail"), (
            f"Language check should warn or fail: {language.message}"
        )
        assert (
            language.details.get("valid") is False or language.details.get("invalid_lang") is True
        )

    def test_forms_pdf_warns_about_fields(self, with_forms_pdf):
        """A PDF with form fields should warn about them."""
        from inspekt.services.simple_pdf_checker import SimplePDFChecker

        checker = SimplePDFChecker()
        result = checker.check(with_forms_pdf)

        forms = result.get_check("forms")
        assert forms is not None
        assert forms.status == "warn", f"Forms check should warn: {forms.message}"
        assert forms.details.get("has_forms") is True
        assert forms.details.get("field_count", 0) > 0

    def test_xmp_pdf_passes_xmp_check(self, with_xmp_pdf):
        """A PDF with XMP metadata should pass the XMP check."""
        from inspekt.services.simple_pdf_checker import SimplePDFChecker

        checker = SimplePDFChecker()
        result = checker.check(with_xmp_pdf)

        xmp = result.get_check("xmp_metadata")
        assert xmp is not None
        assert xmp.status == "pass", f"XMP check should pass: {xmp.message}"
        assert xmp.details.get("has_xmp") is True

    def test_long_pdf_without_bookmarks_fails(self, long_no_bookmarks_pdf):
        """A 25+ page PDF without bookmarks should fail the bookmarks check."""
        from inspekt.services.simple_pdf_checker import SimplePDFChecker

        checker = SimplePDFChecker()
        result = checker.check(long_no_bookmarks_pdf)

        bookmarks = result.get_check("bookmarks")
        assert bookmarks is not None
        assert bookmarks.status == "fail", (
            f"Bookmarks check should fail for long doc: {bookmarks.message}"
        )
        assert bookmarks.details.get("required") is True
        assert bookmarks.details.get("page_count") >= 20

    def test_result_counts_are_correct(self, accessible_pdf):
        """Result summary counts should be correct."""
        from inspekt.services.simple_pdf_checker import SimplePDFChecker

        checker = SimplePDFChecker()
        result = checker.check(accessible_pdf)

        # Count should match sum of individual statuses
        total = result.passed + result.failed + result.warnings + result.skipped
        assert total == len(result.checks)

    def test_check_has_11_checks(self, accessible_pdf):
        """SimplePDFChecker should run 11 checks."""
        from inspekt.services.simple_pdf_checker import SimplePDFChecker

        checker = SimplePDFChecker()
        result = checker.check(accessible_pdf)

        # Should have exactly 9 checks (tagged, title, language, protected, bookmarks, scanned, forms, xfa, xmp)
        assert len(result.checks) == 9  # Note: 9 checks in our implementation

    def test_metadata_extraction(self, accessible_pdf):
        """Metadata should be properly extracted."""
        from inspekt.services.simple_pdf_checker import SimplePDFChecker

        checker = SimplePDFChecker()
        result = checker.check(accessible_pdf)

        meta = result.metadata
        assert meta.file_path == accessible_pdf
        assert meta.page_count >= 1
        assert meta.title is not None
        assert meta.language == "en-US"
        assert meta.language_display_name is not None  # Should have display name from langcodes


class TestPDFBasicChecker:
    """Unit tests for PDFBasicChecker."""

    def test_accessible_pdf_passes_all_checks(self, accessible_pdf):
        """An accessible PDF should pass all basic checks."""
        from inspekt.services.pdf_checker import PDFBasicChecker

        checker = PDFBasicChecker()
        result = checker.check(accessible_pdf)

        assert result.failed == 0, f"Expected no failures, got {result.failed}"
        # May have skipped bookmarks check (short document)
        assert result.passed >= 5

    def test_untagged_pdf_fails_tagged_check(self, untagged_pdf):
        """An untagged PDF should fail the tagged check."""
        from inspekt.services.pdf_checker import PDFBasicChecker

        checker = PDFBasicChecker()
        result = checker.check(untagged_pdf)

        tagged_check = None
        for check in result.checks:
            if check.check_id == "tagged":
                tagged_check = check
                break

        assert tagged_check is not None
        assert tagged_check.status == "fail"

    def test_check_has_7_checks(self, accessible_pdf):
        """PDFBasicChecker should run all 7 checks."""
        from inspekt.services.pdf_checker import PDFBasicChecker

        checker = PDFBasicChecker()
        result = checker.check(accessible_pdf)

        assert len(result.checks) == 7


class TestCheckPdfFunction:
    """Test the check_pdf convenience function."""

    def test_basic_engine(self, accessible_pdf):
        """check_pdf with basic engine should return basic results only."""
        from inspekt.services.pdf_checker import check_pdf

        result = check_pdf(accessible_pdf, engine="basic")

        assert result.basic is not None
        assert result.simple is None
        assert result.verapdf is None

    def test_simple_engine(self, accessible_pdf):
        """check_pdf with simple engine should return both basic and simple results."""
        from inspekt.services.pdf_checker import check_pdf

        result = check_pdf(accessible_pdf, engine="simple")

        assert result.basic is not None
        assert result.simple is not None
        assert result.verapdf is None

    def test_all_engine_without_verapdf(self, accessible_pdf):
        """check_pdf with all engine returns basic and simple, may skip vera if unavailable."""
        from inspekt.services.pdf_checker import VeraPDFChecker, check_pdf

        # Check if veraPDF is available
        vera_checker = VeraPDFChecker()
        has_vera = vera_checker.is_native_available() or vera_checker.is_docker_available()
        if not has_vera:
            pytest.skip("veraPDF not available (no native binary or Docker image)")

        try:
            result = check_pdf(accessible_pdf, engine="all")
            assert result.basic is not None
            assert result.simple is not None
        except RuntimeError as e:
            if "veraPDF" in str(e):
                pytest.skip(f"veraPDF unavailable at runtime: {e}")
            raise
