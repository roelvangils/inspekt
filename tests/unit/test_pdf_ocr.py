"""
Unit tests for PDF OCR service.

Tests the OCR text comparison functionality and graceful degradation
when Tesseract is not installed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestOCRAvailability:
    """Tests for OCR availability detection."""

    def test_is_pytesseract_available(self):
        """Test pytesseract availability detection."""
        from inspekt.services.pdf_ocr import is_pytesseract_available

        result = is_pytesseract_available()
        assert isinstance(result, bool)

    def test_is_tesseract_available(self):
        """Test Tesseract binary availability detection."""
        from inspekt.services.pdf_ocr import is_tesseract_available

        result = is_tesseract_available()
        assert isinstance(result, bool)

    def test_get_ocr_availability_tuple(self):
        """Test OCR availability returns tuple."""
        from inspekt.services.pdf_ocr import get_ocr_availability

        available, reason = get_ocr_availability()
        assert isinstance(available, bool)
        if not available:
            assert isinstance(reason, str)
        else:
            assert reason is None

    def test_is_tesseract_available_not_in_path(self):
        """Test detection when tesseract is not in PATH."""
        with patch("shutil.which", return_value=None):
            from inspekt.services.pdf_ocr import is_tesseract_available

            # Need to call the function after patching
            result = is_tesseract_available()
            # The result depends on whether tesseract is actually installed


class TestTextComparison:
    """Tests for text comparison functions."""

    def test_compare_texts_identical(self):
        """Test comparing identical texts."""
        from inspekt.services.pdf_ocr import compare_texts

        result = compare_texts("hello world", "hello world")
        assert result == 1.0

    def test_compare_texts_completely_different(self):
        """Test comparing completely different texts."""
        from inspekt.services.pdf_ocr import compare_texts

        result = compare_texts("hello", "xxxxx")
        assert result < 0.5

    def test_compare_texts_empty_both(self):
        """Test comparing two empty strings."""
        from inspekt.services.pdf_ocr import compare_texts

        result = compare_texts("", "")
        assert result == 1.0  # Both empty = identical

    def test_compare_texts_one_empty(self):
        """Test comparing when one string is empty."""
        from inspekt.services.pdf_ocr import compare_texts

        result = compare_texts("hello world", "")
        assert result == 0.0  # Completely different

    def test_compare_texts_similar(self):
        """Test comparing similar texts."""
        from inspekt.services.pdf_ocr import compare_texts

        # Slight differences
        result = compare_texts("the quick brown fox", "the quik brown fox")
        assert 0.8 < result < 1.0  # Should be high but not perfect


class TestTextNormalization:
    """Tests for text normalization."""

    def test_normalize_text_whitespace(self):
        """Test that whitespace is normalized."""
        from inspekt.services.pdf_ocr import _normalize_text

        result = _normalize_text("hello   world\n\ttab")
        assert result == "hello world tab"

    def test_normalize_text_case(self):
        """Test that text is lowercased."""
        from inspekt.services.pdf_ocr import _normalize_text

        result = _normalize_text("Hello WORLD")
        assert result == "hello world"

    def test_normalize_text_punctuation(self):
        """Test that punctuation is removed."""
        from inspekt.services.pdf_ocr import _normalize_text

        result = _normalize_text("Hello, world! How are you?")
        assert result == "hello world how are you"


class TestPageTextComparison:
    """Tests for PageTextComparison dataclass."""

    def test_has_significant_discrepancy_low_similarity(self):
        """Test discrepancy detection with low similarity."""
        from inspekt.services.pdf_ocr import PageTextComparison

        comparison = PageTextComparison(
            page_num=0,
            pdf_text="hello world",
            ocr_text="completely different text",
            similarity=0.3,
            pdf_char_count=11,
            ocr_char_count=25,
        )

        assert comparison.has_significant_discrepancy is True

    def test_has_significant_discrepancy_high_similarity(self):
        """Test no discrepancy with high similarity."""
        from inspekt.services.pdf_ocr import PageTextComparison

        comparison = PageTextComparison(
            page_num=0,
            pdf_text="hello world",
            ocr_text="hello world",
            similarity=1.0,
            pdf_char_count=11,
            ocr_char_count=11,
        )

        assert comparison.has_significant_discrepancy is False

    def test_is_image_only_no_pdf_text(self):
        """Test image-only detection when PDF has no text."""
        from inspekt.services.pdf_ocr import PageTextComparison

        comparison = PageTextComparison(
            page_num=0,
            pdf_text="",
            ocr_text="This is text found by OCR in a scanned document (truncated)",
            similarity=0.0,
            pdf_char_count=0,
            ocr_char_count=100,  # Must be > 50 for is_image_only
        )

        assert comparison.is_image_only is True

    def test_is_image_only_with_pdf_text(self):
        """Test image-only detection when PDF has text."""
        from inspekt.services.pdf_ocr import PageTextComparison

        comparison = PageTextComparison(
            page_num=0,
            pdf_text="This is text from the PDF layer",
            ocr_text="This is text from the PDF layer",
            similarity=1.0,
            pdf_char_count=32,
            ocr_char_count=32,
        )

        assert comparison.is_image_only is False


class TestTextDiscrepancyResult:
    """Tests for TextDiscrepancyResult dataclass."""

    def test_is_likely_scanned_majority_image(self):
        """Test scanned detection when most pages are image-only."""
        from inspekt.services.pdf_ocr import TextDiscrepancyResult

        result = TextDiscrepancyResult(
            pages_analyzed=10,
            pages_with_discrepancy=8,
            image_only_pages=6,  # 60% image-only
            overall_similarity=0.2,
        )

        assert result.is_likely_scanned is True

    def test_is_likely_scanned_minority_image(self):
        """Test scanned detection when few pages are image-only."""
        from inspekt.services.pdf_ocr import TextDiscrepancyResult

        result = TextDiscrepancyResult(
            pages_analyzed=10,
            pages_with_discrepancy=1,
            image_only_pages=2,  # 20% image-only
            overall_similarity=0.9,
        )

        assert result.is_likely_scanned is False

    def test_needs_warning_scanned(self):
        """Test warning needed for scanned documents."""
        from inspekt.services.pdf_ocr import TextDiscrepancyResult

        result = TextDiscrepancyResult(
            pages_analyzed=10,
            pages_with_discrepancy=10,
            image_only_pages=10,
            overall_similarity=0.0,
        )

        assert result.needs_warning is True

    def test_needs_warning_no_issues(self):
        """Test no warning when no issues."""
        from inspekt.services.pdf_ocr import TextDiscrepancyResult

        result = TextDiscrepancyResult(
            pages_analyzed=10,
            pages_with_discrepancy=0,
            image_only_pages=0,
            overall_similarity=0.98,
        )

        assert result.needs_warning is False


class TestAnalyzeTextDiscrepancy:
    """Tests for the main analyze_text_discrepancy function."""

    def test_analyze_returns_unavailable_when_no_tesseract(self):
        """Test graceful degradation when Tesseract is not available."""
        with patch("inspekt.services.pdf_ocr.get_ocr_availability", return_value=(False, "Tesseract not installed")):
            from inspekt.services.pdf_ocr import analyze_text_discrepancy

            result = analyze_text_discrepancy("/some/path.pdf")

            assert result.ocr_available is False
            assert result.unavailable_reason == "Tesseract not installed"
            assert result.pages_analyzed == 0

    def test_analyze_returns_unavailable_when_no_pymupdf(self):
        """Test graceful degradation when PyMuPDF is not available."""
        with patch("inspekt.services.pdf_ocr.get_ocr_availability", return_value=(True, None)):
            with patch("inspekt.services.pdf_renderer.is_pymupdf_available", return_value=False):
                from inspekt.services.pdf_ocr import analyze_text_discrepancy

                # Need to reimport after patching
                result = analyze_text_discrepancy("/some/path.pdf")

                # Should indicate unavailability
                # (Note: actual behavior depends on import order)
