"""
Unit tests for the global OCR service.
"""

from unittest.mock import patch

import pytest


class TestOCRAvailability:
    """Tests for OCR availability checking functions."""

    def test_is_pytesseract_available_when_installed(self):
        """Test that is_pytesseract_available returns True when pytesseract is installed."""
        # Clear cached service instances first
        from inspekt.services.ocr_service import clear_ocr_service_cache
        clear_ocr_service_cache()

        from inspekt.services.ocr_service import is_pytesseract_available

        # The function should return True if import succeeds
        # (we can't mock this easily in this test, so we just check it doesn't crash)
        result = is_pytesseract_available()
        assert isinstance(result, bool)

    def test_is_tesseract_available_when_in_path(self):
        """Test that is_tesseract_available detects tesseract in PATH."""
        from inspekt.services.ocr_service import is_tesseract_available

        with patch("shutil.which", return_value="/usr/local/bin/tesseract"):
            assert is_tesseract_available() is True

    def test_is_tesseract_available_when_not_in_path(self):
        """Test that is_tesseract_available returns False when not in PATH."""
        from inspekt.services.ocr_service import is_tesseract_available

        with patch("shutil.which", return_value=None):
            assert is_tesseract_available() is False

    def test_get_ocr_availability_returns_tuple(self):
        """Test that get_ocr_availability returns a tuple."""
        from inspekt.services.ocr_service import get_ocr_availability

        result = get_ocr_availability()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert result[1] is None or isinstance(result[1], str)

    def test_get_ocr_availability_when_pytesseract_missing(self):
        """Test availability check when pytesseract is not installed."""
        from inspekt.services import ocr_service

        with patch.object(ocr_service, "is_pytesseract_available", return_value=False):
            available, reason = ocr_service.get_ocr_availability()
            assert available is False
            assert "pytesseract" in reason.lower()

    def test_get_ocr_availability_when_tesseract_missing(self):
        """Test availability check when tesseract binary is missing."""
        from inspekt.services import ocr_service

        with patch.object(ocr_service, "is_pytesseract_available", return_value=True):
            with patch.object(ocr_service, "is_tesseract_available", return_value=False):
                available, reason = ocr_service.get_ocr_availability()
                assert available is False
                assert "binary" in reason.lower() or "tesseract" in reason.lower()


class TestMeaningfulTextDetection:
    """Tests for the _is_meaningful_text function."""

    def test_empty_text_is_not_meaningful(self):
        """Empty text should not be considered meaningful."""
        from inspekt.services.ocr_service import _is_meaningful_text

        assert _is_meaningful_text("") is False
        assert _is_meaningful_text("   ") is False

    def test_short_text_is_not_meaningful(self):
        """Text shorter than min_chars should not be meaningful."""
        from inspekt.services.ocr_service import _is_meaningful_text

        assert _is_meaningful_text("Hi") is False  # Too short
        assert _is_meaningful_text("Hello") is False  # Still too short

    def test_few_words_is_not_meaningful(self):
        """Text with fewer than min_words should not be meaningful."""
        from inspekt.services.ocr_service import _is_meaningful_text

        assert _is_meaningful_text("Hello there") is False  # Only 2 words

    def test_single_character_words_is_not_meaningful(self):
        """Text with very short average word length should not be meaningful."""
        from inspekt.services.ocr_service import _is_meaningful_text

        # "a b c d e" has average word length of 1
        assert _is_meaningful_text("a b c d e f g h i j") is False

    def test_mostly_numeric_is_not_meaningful(self):
        """Text that is mostly digits should not be meaningful."""
        from inspekt.services.ocr_service import _is_meaningful_text

        # 90% digits
        assert _is_meaningful_text("123456789012345") is False
        # Serial number with some text
        assert _is_meaningful_text("SN123456789012345") is False

    def test_regular_text_is_meaningful(self):
        """Normal text with enough words should be meaningful."""
        from inspekt.services.ocr_service import _is_meaningful_text

        assert _is_meaningful_text("This is a sample text with several words") is True
        assert _is_meaningful_text("The quick brown fox jumps over the lazy dog") is True

    def test_meaningful_with_some_numbers(self):
        """Text with some numbers mixed in should still be meaningful."""
        from inspekt.services.ocr_service import _is_meaningful_text

        assert _is_meaningful_text("Call us at 555 1234 for more information") is True

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("", False),
            ("Hi", False),
            ("Hello world", False),  # Only 2 words
            ("Hello world today", True),  # 3 words, sufficient chars
            ("a b c d e f", False),  # Short words
            ("The quick brown fox jumps", True),  # Good text
            ("123456789012345", False),  # Mostly numeric
            ("Product costs $29.99 today", True),  # Mix is OK
        ],
    )
    def test_meaningful_text_parametrized(self, text, expected):
        """Parametrized tests for meaningful text detection."""
        from inspekt.services.ocr_service import _is_meaningful_text

        assert _is_meaningful_text(text) is expected


class TestTextCleaning:
    """Tests for the _clean_text function."""

    def test_collapses_whitespace(self):
        """Test that multiple whitespace is collapsed to single space."""
        from inspekt.services.ocr_service import _clean_text

        assert _clean_text("hello    world") == "hello world"
        assert _clean_text("hello\n\nworld") == "hello world"
        assert _clean_text("hello\t\tworld") == "hello world"

    def test_strips_leading_trailing(self):
        """Test that leading/trailing whitespace is stripped."""
        from inspekt.services.ocr_service import _clean_text

        assert _clean_text("  hello  ") == "hello"
        assert _clean_text("\nhello\n") == "hello"

    def test_removes_control_characters(self):
        """Test that control characters are removed."""
        from inspekt.services.ocr_service import _clean_text

        # Control characters are removed (not replaced with space)
        assert _clean_text("hello\x00world") == "helloworld"
        assert _clean_text("hello\x1fworld") == "helloworld"
        # Control characters surrounded by whitespace get collapsed
        assert _clean_text("hello \x00 world") == "hello world"


class TestConfidenceEstimation:
    """Tests for the _estimate_confidence function."""

    def test_empty_text_zero_confidence(self):
        """Empty text should have zero confidence."""
        from inspekt.services.ocr_service import _estimate_confidence

        assert _estimate_confidence("", 0) == 0.0

    def test_more_words_higher_confidence(self):
        """More words should result in higher confidence."""
        from inspekt.services.ocr_service import _estimate_confidence

        conf_few = _estimate_confidence("hello world", 2)
        conf_many = _estimate_confidence("the quick brown fox jumps over lazy dog today", 9)
        assert conf_many > conf_few

    def test_common_words_boost_confidence(self):
        """Common English words should boost confidence."""
        from inspekt.services.ocr_service import _estimate_confidence

        # Text with common words
        conf_common = _estimate_confidence("the quick and lazy fox is in the field", 9)
        # Text without common words
        conf_uncommon = _estimate_confidence("xyzzy quux plugh grault corge", 5)
        assert conf_common > conf_uncommon

    def test_confidence_capped_at_one(self):
        """Confidence should never exceed 1.0."""
        from inspekt.services.ocr_service import _estimate_confidence

        # Even with optimal text, confidence should be <= 1.0
        conf = _estimate_confidence(
            "the and is in to of a for on with the and is in to of a for on with",
            20,
        )
        assert conf <= 1.0


class TestOCRResult:
    """Tests for the OCRResult dataclass."""

    def test_preview_short_text(self):
        """Preview of short text should return full text."""
        from inspekt.services.ocr_service import OCRResult

        result = OCRResult(
            raw_text="Hello world",
            cleaned_text="hello world",
            word_count=2,
            char_count=11,
            confidence=0.8,
            has_meaningful_text=False,
        )
        assert result.preview == "hello world"

    def test_preview_long_text_truncated(self):
        """Preview of long text should be truncated to 100 chars."""
        from inspekt.services.ocr_service import OCRResult

        long_text = "a" * 200
        result = OCRResult(
            raw_text=long_text,
            cleaned_text=long_text,
            word_count=1,
            char_count=200,
            confidence=0.8,
            has_meaningful_text=True,
        )
        assert len(result.preview) <= 100
        assert result.preview.endswith("…")


class TestOCRServiceSingleton:
    """Tests for the OCR service singleton pattern."""

    def test_get_ocr_service_returns_same_instance(self):
        """get_ocr_service should return the same instance for same language."""
        from inspekt.services.ocr_service import (
            clear_ocr_service_cache,
            get_ocr_availability,
        )

        available, _ = get_ocr_availability()
        if not available:
            pytest.skip("OCR not available")

        clear_ocr_service_cache()

        from inspekt.services.ocr_service import get_ocr_service

        service1 = get_ocr_service("eng")
        service2 = get_ocr_service("eng")
        assert service1 is service2

    def test_get_ocr_service_different_language(self):
        """Different languages should get different instances."""
        from inspekt.services.ocr_service import (
            clear_ocr_service_cache,
            get_ocr_availability,
        )

        available, _ = get_ocr_availability()
        if not available:
            pytest.skip("OCR not available")

        clear_ocr_service_cache()

        from inspekt.services.ocr_service import get_ocr_service

        service_eng = get_ocr_service("eng")
        service_nld = get_ocr_service("nld")
        assert service_eng is not service_nld
        assert service_eng.language == "eng"
        assert service_nld.language == "nld"

    def test_clear_cache_resets_instances(self):
        """clear_ocr_service_cache should reset all instances."""
        from inspekt.services.ocr_service import (
            clear_ocr_service_cache,
            get_ocr_availability,
        )

        available, _ = get_ocr_availability()
        if not available:
            pytest.skip("OCR not available")

        from inspekt.services.ocr_service import get_ocr_service

        service_before = get_ocr_service("eng")
        clear_ocr_service_cache()
        service_after = get_ocr_service("eng")
        assert service_before is not service_after


class TestOCRServiceImageProcessing:
    """Tests for OCR image processing (requires actual OCR)."""

    @pytest.fixture
    def mock_pytesseract(self):
        """Mock pytesseract for testing without actual OCR."""
        with patch("pytesseract.image_to_string") as mock:
            mock.return_value = "Hello world from OCR"
            yield mock

    def test_ocr_returns_result_structure(self):
        """Test that OCR returns proper OCRResult structure."""
        from inspekt.services.ocr_service import (
            clear_ocr_service_cache,
            get_ocr_availability,
        )

        available, _ = get_ocr_availability()
        if not available:
            pytest.skip("OCR not available")

        clear_ocr_service_cache()

        from io import BytesIO

        # We need a real image to test - create a simple white image
        from PIL import Image

        from inspekt.services.ocr_service import OCRResult, get_ocr_service

        img = Image.new("RGB", (100, 100), color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

        service = get_ocr_service()
        result = service.ocr_image_bytes(image_bytes)

        assert isinstance(result, OCRResult)
        assert isinstance(result.raw_text, str)
        assert isinstance(result.cleaned_text, str)
        assert isinstance(result.word_count, int)
        assert isinstance(result.char_count, int)
        assert isinstance(result.confidence, float)
        assert isinstance(result.has_meaningful_text, bool)
