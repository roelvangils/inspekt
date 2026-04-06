"""
Unit tests for the classification cache service.
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestCachedClassification:
    """Tests for the CachedClassification dataclass."""

    def test_is_expired_returns_false_for_recent(self):
        """Recent cache entries should not be expired."""
        from inspekt.services.classification_cache import CachedClassification

        cached = CachedClassification(
            image_hash="abc123",
            file_size=1000,
            classified_at=datetime.now().isoformat(),
            category="photograph",
            confidence=0.9,
            method="clip",
        )
        assert cached.is_expired(ttl_days=30) is False

    def test_is_expired_returns_true_for_old(self):
        """Old cache entries should be expired."""
        from inspekt.services.classification_cache import CachedClassification

        old_date = datetime.now() - timedelta(days=60)
        cached = CachedClassification(
            image_hash="abc123",
            file_size=1000,
            classified_at=old_date.isoformat(),
            category="photograph",
            confidence=0.9,
            method="clip",
        )
        assert cached.is_expired(ttl_days=30) is True

    def test_is_expired_returns_true_for_invalid_timestamp(self):
        """Invalid timestamps should be treated as expired."""
        from inspekt.services.classification_cache import CachedClassification

        cached = CachedClassification(
            image_hash="abc123",
            file_size=1000,
            classified_at="invalid-date",
            category="photograph",
            confidence=0.9,
            method="clip",
        )
        assert cached.is_expired() is True

    def test_to_classification_result(self):
        """Should convert to ClassificationResult correctly."""
        from inspekt.services.classification_cache import CachedClassification

        cached = CachedClassification(
            image_hash="abc123",
            file_size=1000,
            classified_at=datetime.now().isoformat(),
            category="photograph",
            confidence=0.9,
            method="clip",
            ocr_text="Sample text",
        )

        result = cached.to_classification_result()

        assert result.category.value == "photograph"
        assert result.confidence == 0.9
        assert "(cached)" in result.method
        assert result.ocr_text == "Sample text"


class TestClassificationCache:
    """Tests for the ClassificationCache class."""

    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def temp_image(self, temp_cache_dir):
        """Create a temporary test image file."""
        image_path = temp_cache_dir / "test_image.png"
        # Create a minimal PNG file (1x1 pixel)
        # PNG header + IHDR + IDAT + IEND
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,  # IDAT chunk
            0x54, 0x08, 0xD7, 0x63, 0xF8, 0xFF, 0xFF, 0x3F,
            0x00, 0x05, 0xFE, 0x02, 0xFE, 0xDC, 0xCC, 0x59,
            0xE7, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,  # IEND chunk
            0x44, 0xAE, 0x42, 0x60, 0x82
        ])
        image_path.write_bytes(png_data)
        return image_path

    @pytest.fixture
    def cache(self, temp_cache_dir):
        """Create a cache instance with temp directory."""
        from inspekt.services.classification_cache import ClassificationCache

        return ClassificationCache(cache_dir=temp_cache_dir / "classification")

    @pytest.fixture
    def mock_result(self):
        """Create a mock ClassificationResult."""
        from inspekt.services.image_classifier import (
            ClassificationResult,
            ImageCategory,
        )

        return ClassificationResult(
            category=ImageCategory.PHOTOGRAPH,
            confidence=0.9,
            method="clip",
            ocr_text="Sample OCR text",
        )

    def test_cache_dir_created(self, cache):
        """Cache directory should be created on init."""
        assert cache.cache_dir.exists()

    def test_get_returns_none_for_uncached(self, cache, temp_image):
        """get() should return None for uncached images."""
        result = cache.get(temp_image)
        assert result is None

    def test_set_and_get_roundtrip(self, cache, temp_image, mock_result):
        """Should be able to set and get a cached result."""
        # Set the cache
        success = cache.set(temp_image, mock_result)
        assert success is True

        # Get the cached result
        cached = cache.get(temp_image)
        assert cached is not None
        assert cached.category.value == "photograph"
        assert cached.confidence == 0.9
        assert cached.ocr_text == "Sample OCR text"
        assert "(cached)" in cached.method

    def test_get_returns_none_for_nonexistent_file(self, cache):
        """get() should return None for files that don't exist."""
        result = cache.get(Path("/nonexistent/file.png"))
        assert result is None

    def test_set_returns_false_for_nonexistent_file(self, cache, mock_result):
        """set() should return False for files that don't exist."""
        success = cache.set(Path("/nonexistent/file.png"), mock_result)
        assert success is False

    def test_cache_invalidated_on_file_size_change(self, cache, temp_image, mock_result):
        """Cache should be invalidated if file size changes."""
        # Set the cache
        cache.set(temp_image, mock_result)

        # Verify it's cached
        assert cache.get(temp_image) is not None

        # Modify the file (change size)
        temp_image.write_bytes(temp_image.read_bytes() + b"extra data")

        # Cache should now miss
        result = cache.get(temp_image)
        assert result is None

    def test_invalidate_removes_cache_entry(self, cache, temp_image, mock_result):
        """invalidate() should remove the cache entry."""
        cache.set(temp_image, mock_result)
        assert cache.get(temp_image) is not None

        success = cache.invalidate(temp_image)
        assert success is True
        assert cache.get(temp_image) is None

    def test_invalidate_returns_false_if_not_cached(self, cache, temp_image):
        """invalidate() should return False if entry doesn't exist."""
        success = cache.invalidate(temp_image)
        assert success is False

    def test_clear_removes_all_entries(self, cache, temp_image, mock_result):
        """clear() should remove all cache entries."""
        # Create multiple cache entries
        cache.set(temp_image, mock_result)

        # Create another temp file
        temp_image2 = temp_image.parent / "test_image2.png"
        temp_image2.write_bytes(temp_image.read_bytes() + b"different")
        cache.set(temp_image2, mock_result)

        # Clear all
        deleted = cache.clear()
        assert deleted >= 1

        # Both should be gone
        assert cache.get(temp_image) is None

    def test_get_stats_returns_correct_info(self, cache, temp_image, mock_result):
        """get_stats() should return correct cache statistics."""
        cache.set(temp_image, mock_result)

        stats = cache.get_stats()
        assert stats["count"] == 1
        assert stats["valid_count"] == 1
        assert stats["expired_count"] == 0
        assert "cache_dir" in stats
        assert "ttl_days" in stats

    def test_expired_entries_not_returned(self, cache, temp_image, mock_result):
        """Expired cache entries should not be returned."""
        cache.set(temp_image, mock_result)

        # Manually expire the cache entry
        cache_files = list(cache.cache_dir.glob("*.json"))
        assert len(cache_files) == 1

        with open(cache_files[0], "r") as f:
            data = json.load(f)

        # Set classified_at to 60 days ago
        old_date = datetime.now() - timedelta(days=60)
        data["classified_at"] = old_date.isoformat()

        with open(cache_files[0], "w") as f:
            json.dump(data, f)

        # Should return None (expired)
        result = cache.get(temp_image)
        assert result is None

    def test_cleanup_expired_removes_old_entries(self, cache, temp_image, mock_result):
        """cleanup_expired() should remove expired entries."""
        cache.set(temp_image, mock_result)

        # Manually expire the cache entry
        cache_files = list(cache.cache_dir.glob("*.json"))
        with open(cache_files[0], "r") as f:
            data = json.load(f)

        old_date = datetime.now() - timedelta(days=60)
        data["classified_at"] = old_date.isoformat()

        with open(cache_files[0], "w") as f:
            json.dump(data, f)

        # Cleanup should remove it
        deleted = cache.cleanup_expired()
        assert deleted == 1
        assert len(list(cache.cache_dir.glob("*.json"))) == 0

    def test_cache_invalidated_on_version_mismatch(self, cache, temp_image, mock_result):
        """Cache should be invalidated if cache version doesn't match."""
        cache.set(temp_image, mock_result)

        # Verify it's cached
        assert cache.get(temp_image) is not None

        # Manually change the cache version to an old version
        cache_files = list(cache.cache_dir.glob("*.json"))
        with open(cache_files[0], "r") as f:
            data = json.load(f)

        data["cache_version"] = 0  # Old version

        with open(cache_files[0], "w") as f:
            json.dump(data, f)

        # Cache should now miss due to version mismatch
        result = cache.get(temp_image)
        assert result is None


class TestImageHashComputation:
    """Tests for image hash computation."""

    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_same_content_same_hash(self, temp_cache_dir):
        """Same file content should produce same hash."""
        from inspekt.services.classification_cache import ClassificationCache

        cache = ClassificationCache(cache_dir=temp_cache_dir / "cache")

        # Create two files with same content
        content = b"test image content" * 1000
        file1 = temp_cache_dir / "file1.png"
        file2 = temp_cache_dir / "file2.png"
        file1.write_bytes(content)
        file2.write_bytes(content)

        hash1 = cache._compute_image_hash(file1)
        hash2 = cache._compute_image_hash(file2)

        assert hash1 == hash2

    def test_different_content_different_hash(self, temp_cache_dir):
        """Different file content should produce different hash."""
        from inspekt.services.classification_cache import ClassificationCache

        cache = ClassificationCache(cache_dir=temp_cache_dir / "cache")

        file1 = temp_cache_dir / "file1.png"
        file2 = temp_cache_dir / "file2.png"
        file1.write_bytes(b"content A" * 1000)
        file2.write_bytes(b"content B" * 1000)

        hash1 = cache._compute_image_hash(file1)
        hash2 = cache._compute_image_hash(file2)

        assert hash1 != hash2

    def test_hash_includes_file_size(self, temp_cache_dir):
        """Hash should include file size to catch truncation."""
        from inspekt.services.classification_cache import ClassificationCache

        cache = ClassificationCache(cache_dir=temp_cache_dir / "cache")

        # Same initial bytes but different total size
        file1 = temp_cache_dir / "file1.png"
        file2 = temp_cache_dir / "file2.png"
        file1.write_bytes(b"A" * 100)
        file2.write_bytes(b"A" * 200)

        hash1 = cache._compute_image_hash(file1)
        hash2 = cache._compute_image_hash(file2)

        assert hash1 != hash2


class TestSingletonBehavior:
    """Tests for the cache singleton pattern."""

    def test_get_classification_cache_returns_same_instance(self):
        """get_classification_cache should return same instance."""
        from inspekt.services.classification_cache import get_classification_cache

        cache1 = get_classification_cache()
        cache2 = get_classification_cache()

        assert cache1 is cache2

    def test_clear_classification_cache_convenience_function(self):
        """clear_classification_cache should work."""
        from inspekt.services.classification_cache import clear_classification_cache

        # Should not raise
        count = clear_classification_cache()
        assert isinstance(count, int)
