"""
Global OCR Service for Inspekt.

Provides a reusable OCR service wrapping pytesseract for text extraction
from images. Used by both image classification and PDF processing.

Features:
- Singleton pattern for efficient reuse
- Meaningful text detection with configurable thresholds
- Graceful degradation when Tesseract is unavailable

Usage:
    from inspekt.services.ocr_service import get_ocr_service, get_ocr_availability

    # Check if OCR is available
    available, reason = get_ocr_availability()
    if not available:
        print(f"OCR unavailable: {reason}")
        return

    # Get the service and perform OCR
    ocr = get_ocr_service()
    result = ocr.ocr_file("/path/to/image.png")
    if result.has_meaningful_text:
        print(f"Found text: {result.cleaned_text}")
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image as PILImage

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Thresholds for "Meaningful Text" Detection
# ═══════════════════════════════════════════════════════════════
MIN_WORDS = 3  # Filter single-word artifacts
MIN_CHARACTERS = 15  # Ensure enough content
MIN_AVG_WORD_LENGTH = 2.5  # Filter random character noise
MAX_NUMERIC_RATIO = 0.80  # Filter serial numbers/captchas


# ═══════════════════════════════════════════════════════════════
# Availability Checks
# ═══════════════════════════════════════════════════════════════
def is_pytesseract_available() -> bool:
    """
    Check if the pytesseract library is installed.

    Returns:
        True if pytesseract can be imported, False otherwise.
    """
    try:
        import pytesseract  # noqa: F401

        return True
    except ImportError:
        return False


def is_tesseract_available() -> bool:
    """
    Check if Tesseract OCR is installed on the system.

    Returns:
        True if tesseract binary is found in PATH, False otherwise.
    """
    return shutil.which("tesseract") is not None


def get_ocr_availability() -> tuple[bool, str | None]:
    """
    Check OCR availability and return status with reason if unavailable.

    Returns:
        Tuple of (is_available, reason_if_unavailable)
    """
    if not is_pytesseract_available():
        return (False, "pytesseract library not installed (pip install pytesseract)")

    if not is_tesseract_available():
        return (False, "Tesseract OCR binary not found in PATH (brew install tesseract)")

    return (True, None)


# ═══════════════════════════════════════════════════════════════
# OCR Result
# ═══════════════════════════════════════════════════════════════
@dataclass
class OCRResult:
    """
    Result of OCR text extraction from an image.

    Attributes:
        raw_text: The raw text extracted by Tesseract.
        cleaned_text: Normalized text with excess whitespace removed.
        word_count: Number of words detected.
        char_count: Number of characters in cleaned text.
        confidence: Estimated confidence (0.0-1.0) based on text quality.
        has_meaningful_text: Whether the text passes the "meaningful" thresholds.
    """

    raw_text: str
    cleaned_text: str
    word_count: int
    char_count: int
    confidence: float  # 0.0-1.0
    has_meaningful_text: bool

    @property
    def preview(self) -> str:
        """Get a short preview of the extracted text (max 100 chars)."""
        if len(self.cleaned_text) <= 100:
            return self.cleaned_text
        return self.cleaned_text[:97] + "…"


# ═══════════════════════════════════════════════════════════════
# Text Processing Helpers
# ═══════════════════════════════════════════════════════════════
def _clean_text(text: str) -> str:
    """
    Clean and normalize OCR text.

    - Collapse multiple whitespace to single spaces
    - Strip leading/trailing whitespace
    - Remove control characters
    """
    # Remove control characters except newlines
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_meaningful_text(
    text: str,
    min_words: int = MIN_WORDS,
    min_chars: int = MIN_CHARACTERS,
    min_avg_word_length: float = MIN_AVG_WORD_LENGTH,
    max_numeric_ratio: float = MAX_NUMERIC_RATIO,
) -> bool:
    """
    Determine if extracted text is "meaningful" (not noise/artifacts).

    Args:
        text: The cleaned text to evaluate.
        min_words: Minimum number of words required.
        min_chars: Minimum number of characters required.
        min_avg_word_length: Minimum average word length.
        max_numeric_ratio: Maximum ratio of digits to total chars.

    Returns:
        True if text passes all thresholds, False otherwise.
    """
    if not text:
        return False

    # Character count check
    if len(text) < min_chars:
        return False

    # Word count check
    words = text.split()
    if len(words) < min_words:
        return False

    # Average word length check (filters "a b c d e f" noise)
    avg_word_length = sum(len(w) for w in words) / len(words)
    if avg_word_length < min_avg_word_length:
        return False

    # Numeric ratio check (filters "123456789" serial numbers)
    digit_count = sum(1 for c in text if c.isdigit())
    return not (len(text) > 0 and digit_count / len(text) > max_numeric_ratio)


def _estimate_confidence(text: str, word_count: int) -> float:
    """
    Estimate OCR confidence based on text characteristics.

    This is a heuristic since pytesseract doesn't always provide
    reliable confidence scores for the full text.

    Args:
        text: The cleaned text.
        word_count: Number of words.

    Returns:
        Confidence score from 0.0 to 1.0.
    """
    if not text or word_count == 0:
        return 0.0

    # Start with base confidence
    confidence = 0.5

    # More words generally means better detection
    if word_count >= 10:
        confidence += 0.2
    elif word_count >= 5:
        confidence += 0.1

    # Longer average word length is a good sign
    avg_word_length = len(text.replace(" ", "")) / word_count
    if avg_word_length >= 4:
        confidence += 0.15
    elif avg_word_length >= 3:
        confidence += 0.1

    # Presence of common English words boosts confidence
    common_words = {"the", "and", "is", "in", "to", "of", "a", "for", "on", "with"}
    words_lower = set(text.lower().split())
    common_matches = len(words_lower & common_words)
    if common_matches >= 3:
        confidence += 0.15
    elif common_matches >= 1:
        confidence += 0.05

    return min(confidence, 1.0)


# ═══════════════════════════════════════════════════════════════
# OCR Service Class
# ═══════════════════════════════════════════════════════════════
class OCRService:
    """
    Singleton OCR service wrapping pytesseract.

    Provides methods to extract text from images in various formats:
    - Raw bytes
    - PIL Image objects
    - File paths

    The service automatically checks for Tesseract availability and
    provides meaningful error messages when unavailable.
    """

    def __init__(self, language: str = "eng"):
        """
        Initialize the OCR service.

        Args:
            language: Tesseract language code (default: "eng" for English).
                      Use "nld" for Dutch, "fra" for French, etc.
                      Multiple languages: "eng+nld+fra"

        Raises:
            ImportError: If pytesseract is not installed.
            RuntimeError: If Tesseract binary is not available.
        """
        available, reason = get_ocr_availability()
        if not available:
            if "pytesseract" in (reason or ""):
                raise ImportError(reason)
            else:
                raise RuntimeError(reason)

        self.language = language
        self._pytesseract = None  # Lazy import

    def _get_pytesseract(self):
        """Lazy import of pytesseract."""
        if self._pytesseract is None:
            import pytesseract

            self._pytesseract = pytesseract
        return self._pytesseract

    def ocr_image_bytes(self, image_bytes: bytes) -> OCRResult:
        """
        Perform OCR on image bytes.

        Args:
            image_bytes: Raw image data (PNG, JPEG, etc.)

        Returns:
            OCRResult with extracted text and metadata.
        """
        from PIL import Image

        image = Image.open(BytesIO(image_bytes))
        return self.ocr_pil_image(image)

    def ocr_pil_image(self, image: PILImage.Image) -> OCRResult:
        """
        Perform OCR on a PIL Image object.

        Args:
            image: PIL Image object.

        Returns:
            OCRResult with extracted text and metadata.
        """
        pytesseract = self._get_pytesseract()

        try:
            raw_text = pytesseract.image_to_string(image, lang=self.language)
        except Exception as e:
            logger.warning(f"OCR failed: {e}")
            return OCRResult(
                raw_text="",
                cleaned_text="",
                word_count=0,
                char_count=0,
                confidence=0.0,
                has_meaningful_text=False,
            )

        cleaned_text = _clean_text(raw_text)
        words = cleaned_text.split()
        word_count = len(words)
        char_count = len(cleaned_text)

        has_meaningful = _is_meaningful_text(cleaned_text)
        confidence = _estimate_confidence(cleaned_text, word_count)

        return OCRResult(
            raw_text=raw_text,
            cleaned_text=cleaned_text,
            word_count=word_count,
            char_count=char_count,
            confidence=confidence,
            has_meaningful_text=has_meaningful,
        )

    def ocr_file(self, file_path: Path | str) -> OCRResult:
        """
        Perform OCR on an image file.

        Args:
            file_path: Path to the image file.

        Returns:
            OCRResult with extracted text and metadata.
        """
        from PIL import Image

        path = Path(file_path)
        with Image.open(path) as image:
            return self.ocr_pil_image(image)


# ═══════════════════════════════════════════════════════════════
# Singleton Instance
# ═══════════════════════════════════════════════════════════════
_ocr_service_instances: dict[str, OCRService] = {}


def get_ocr_service(language: str = "eng") -> OCRService:
    """
    Get the shared OCR service instance for a given language.

    This function implements a singleton pattern per language to avoid
    re-initializing Tesseract for each OCR operation.

    Args:
        language: Tesseract language code (default: "eng").

    Returns:
        OCRService instance.

    Raises:
        ImportError: If pytesseract is not installed.
        RuntimeError: If Tesseract binary is not available.
    """
    global _ocr_service_instances

    if language not in _ocr_service_instances:
        _ocr_service_instances[language] = OCRService(language)

    return _ocr_service_instances[language]


def clear_ocr_service_cache() -> None:
    """
    Clear the OCR service singleton cache.

    Useful for testing or when you need to reinitialize
    the service with different settings.
    """
    global _ocr_service_instances
    _ocr_service_instances.clear()
