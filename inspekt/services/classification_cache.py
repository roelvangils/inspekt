"""
Classification Cache for Image Categorization.

Caches CLIP and OCR classification results to avoid reprocessing
the same images repeatedly. Uses content-based hashing to ensure
cache hits even when files are renamed or moved.

Cache location: ~/.cache/inspekt/classification/

Usage:
    from inspekt.services.classification_cache import get_classification_cache

    cache = get_classification_cache()

    # Check cache before classifying
    cached = cache.get(image_path)
    if cached:
        return cached

    # After classification, store result
    cache.set(image_path, result)
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inspekt.services.image_classifier import ClassificationResult

logger = logging.getLogger(__name__)

# Default cache TTL: 30 days
DEFAULT_TTL_DAYS = 30

# How many bytes to read for content hashing (64KB is fast but catches changes)
HASH_CHUNK_SIZE = 65536

# Current cache format version - increment when cache format changes
# This ensures old cache entries are invalidated when the format changes
CURRENT_CACHE_VERSION = 1


@dataclass
class CachedClassification:
    """
    Cached classification result with metadata.

    Stored as JSON in the cache directory.
    """

    # Cache metadata
    image_hash: str
    file_size: int
    classified_at: str  # ISO format timestamp

    # Classification result
    category: str
    confidence: float
    method: str

    # Optional fields (must come after required fields)
    ocr_text: str | None = None
    cache_version: int = 1  # For future cache format changes

    def is_expired(self, ttl_days: int = DEFAULT_TTL_DAYS) -> bool:
        """Check if this cache entry has expired."""
        try:
            classified_time = datetime.fromisoformat(self.classified_at)
            expiry_time = classified_time + timedelta(days=ttl_days)
            return datetime.now() > expiry_time
        except (ValueError, TypeError):
            return True  # Invalid timestamp = expired

    def to_classification_result(self) -> "ClassificationResult":
        """Convert cached data back to ClassificationResult."""
        from inspekt.services.image_classifier import (
            ClassificationResult,
            ImageCategory,
        )

        return ClassificationResult(
            category=ImageCategory(self.category),
            confidence=self.confidence,
            method=f"{self.method} (cached)",
            ocr_text=self.ocr_text,
        )


class ClassificationCache:
    """
    Cache for image classification results.

    Uses content-based hashing (SHA256 of first 64KB + file size) to
    identify images. This ensures the same image gets the same cache
    key regardless of filename or location.
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        ttl_days: int = DEFAULT_TTL_DAYS,
    ):
        """
        Initialize the classification cache.

        Args:
            cache_dir: Custom cache directory. Defaults to ~/.cache/inspekt/classification/
            ttl_days: Time-to-live for cache entries in days (default: 30)
        """
        if cache_dir is None:
            self.cache_dir = Path.home() / ".cache" / "inspekt" / "classification"
        else:
            self.cache_dir = cache_dir

        self.ttl_days = ttl_days
        self._ensure_cache_dir()

    def _ensure_cache_dir(self) -> None:
        """Create cache directory if it doesn't exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _compute_image_hash(self, file_path: Path) -> str:
        """
        Compute a content-based hash for an image file.

        Uses SHA256 of the first 64KB + file size for speed while
        still detecting content changes.

        Args:
            file_path: Path to the image file

        Returns:
            Hex string hash (first 32 chars of SHA256)
        """
        hasher = hashlib.sha256()

        # Include file size in hash to catch truncation/corruption
        file_size = file_path.stat().st_size
        hasher.update(str(file_size).encode())

        # Hash first chunk of file content
        with open(file_path, "rb") as f:
            chunk = f.read(HASH_CHUNK_SIZE)
            hasher.update(chunk)

        # Return first 32 chars (128 bits) - enough for uniqueness
        return hasher.hexdigest()[:32]

    @staticmethod
    def compute_bytes_hash(image_bytes: bytes) -> str:
        """
        Compute a content-based hash for image bytes.

        Uses SHA256 of the first 64KB + size for consistency with file hashing.

        Args:
            image_bytes: Raw image bytes

        Returns:
            Hex string hash (first 32 chars of SHA256)
        """
        hasher = hashlib.sha256()

        # Include size in hash
        hasher.update(str(len(image_bytes)).encode())

        # Hash first chunk (or all if smaller)
        chunk = image_bytes[:HASH_CHUNK_SIZE]
        hasher.update(chunk)

        return hasher.hexdigest()[:32]

    def get_by_bytes(self, image_bytes: bytes) -> "ClassificationResult | None":
        """
        Get cached classification result for image bytes.

        Args:
            image_bytes: Raw image bytes

        Returns:
            ClassificationResult if cached and valid, None otherwise
        """
        try:
            image_hash = self.compute_bytes_hash(image_bytes)
            cache_path = self._get_cache_path(image_hash)

            if not cache_path.exists():
                return None

            # Load cached data
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            cached = CachedClassification(**data)

            # Check cache version - invalidate if format changed
            if cached.cache_version != CURRENT_CACHE_VERSION:
                logger.debug(f"Cache version mismatch for bytes hash {image_hash[:8]}…")
                cache_path.unlink(missing_ok=True)
                return None

            # Check if expired
            if cached.is_expired(self.ttl_days):
                logger.debug(f"Cache expired for bytes hash {image_hash[:8]}…")
                cache_path.unlink(missing_ok=True)
                return None

            # Verify size matches (in case of hash collision)
            if cached.file_size != len(image_bytes):
                logger.debug(f"Size mismatch for bytes hash {image_hash[:8]}..., invalidating cache")
                cache_path.unlink(missing_ok=True)
                return None

            logger.debug(f"Cache hit for bytes hash {image_hash[:8]}…")
            return cached.to_classification_result()

        except Exception as e:
            logger.debug(f"Cache read error for bytes: {e}")
            return None

    def set_by_bytes(
        self,
        image_bytes: bytes,
        result: "ClassificationResult",
    ) -> bool:
        """
        Store classification result in cache by image bytes.

        Args:
            image_bytes: Raw image bytes
            result: Classification result to cache

        Returns:
            True if cached successfully, False otherwise
        """
        try:
            image_hash = self.compute_bytes_hash(image_bytes)
            cache_path = self._get_cache_path(image_hash)

            # Strip "(cached)" suffix from method if present
            method = result.method
            if method.endswith(" (cached)"):
                method = method[:-9]

            cached = CachedClassification(
                image_hash=image_hash,
                file_size=len(image_bytes),
                classified_at=datetime.now().isoformat(),
                category=result.category.value,
                confidence=result.confidence,
                method=method,
                ocr_text=result.ocr_text,
            )

            # Write atomically (write to temp, then rename)
            temp_path = cache_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(asdict(cached), f, indent=2)

            temp_path.rename(cache_path)
            logger.debug(f"Cached classification for bytes hash {image_hash[:8]}…")
            return True

        except Exception as e:
            logger.debug(f"Cache write error for bytes: {e}")
            return False

    def _get_cache_path(self, image_hash: str) -> Path:
        """Get the cache file path for a given hash."""
        return self.cache_dir / f"{image_hash}.json"

    def get(self, file_path: Path | str) -> "ClassificationResult | None":
        """
        Get cached classification result for an image.

        Args:
            file_path: Path to the image file

        Returns:
            ClassificationResult if cached and valid, None otherwise
        """
        file_path = Path(file_path)

        if not file_path.exists():
            return None

        try:
            image_hash = self._compute_image_hash(file_path)
            cache_path = self._get_cache_path(image_hash)

            if not cache_path.exists():
                return None

            # Load cached data
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            cached = CachedClassification(**data)

            # Check cache version - invalidate if format changed
            if cached.cache_version != CURRENT_CACHE_VERSION:
                logger.debug(f"Cache version mismatch for {file_path.name} (v{cached.cache_version} != v{CURRENT_CACHE_VERSION}), invalidating")
                cache_path.unlink(missing_ok=True)
                return None

            # Check if expired
            if cached.is_expired(self.ttl_days):
                logger.debug(f"Cache expired for {file_path.name}")
                cache_path.unlink(missing_ok=True)
                return None

            # Verify file size matches (in case of hash collision)
            current_size = file_path.stat().st_size
            if cached.file_size != current_size:
                logger.debug(f"File size mismatch for {file_path.name}, invalidating cache")
                cache_path.unlink(missing_ok=True)
                return None

            logger.debug(f"Cache hit for {file_path.name}")
            return cached.to_classification_result()

        except Exception as e:
            logger.debug(f"Cache read error for {file_path}: {e}")
            return None

    def set(
        self,
        file_path: Path | str,
        result: "ClassificationResult",
    ) -> bool:
        """
        Store classification result in cache.

        Args:
            file_path: Path to the image file
            result: Classification result to cache

        Returns:
            True if cached successfully, False otherwise
        """
        file_path = Path(file_path)

        if not file_path.exists():
            return False

        try:
            image_hash = self._compute_image_hash(file_path)
            cache_path = self._get_cache_path(image_hash)

            # Strip "(cached)" suffix from method if present
            method = result.method
            if method.endswith(" (cached)"):
                method = method[:-9]

            cached = CachedClassification(
                image_hash=image_hash,
                file_size=file_path.stat().st_size,
                classified_at=datetime.now().isoformat(),
                category=result.category.value,
                confidence=result.confidence,
                method=method,
                ocr_text=result.ocr_text,
            )

            # Write atomically (write to temp, then rename)
            temp_path = cache_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(asdict(cached), f, indent=2)

            temp_path.rename(cache_path)
            logger.debug(f"Cached classification for {file_path.name}")
            return True

        except Exception as e:
            logger.debug(f"Cache write error for {file_path}: {e}")
            return False

    def invalidate(self, file_path: Path | str) -> bool:
        """
        Invalidate (delete) cache entry for a specific file.

        Args:
            file_path: Path to the image file

        Returns:
            True if entry was deleted, False if not found
        """
        file_path = Path(file_path)

        if not file_path.exists():
            return False

        try:
            image_hash = self._compute_image_hash(file_path)
            cache_path = self._get_cache_path(image_hash)

            if cache_path.exists():
                cache_path.unlink()
                return True
            return False

        except Exception:
            return False

    def clear(self) -> int:
        """
        Clear all cached classifications.

        Returns:
            Number of cache entries deleted
        """
        if not self.cache_dir.exists():
            return 0

        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
                count += 1
            except Exception:
                pass

        return count

    def cleanup_expired(self) -> int:
        """
        Remove all expired cache entries.

        Returns:
            Number of expired entries deleted
        """
        if not self.cache_dir.exists():
            return 0

        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                cached = CachedClassification(**data)
                if cached.is_expired(self.ttl_days):
                    cache_file.unlink()
                    count += 1
            except Exception:
                # Invalid cache file, delete it
                try:
                    cache_file.unlink()
                    count += 1
                except Exception:
                    pass

        return count

    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with count, size, and cache directory info
        """
        if not self.cache_dir.exists():
            return {
                "count": 0,
                "total_size": 0,
                "total_size_kb": 0,
                "cache_dir": str(self.cache_dir),
                "ttl_days": self.ttl_days,
            }

        files = list(self.cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in files if f.is_file())

        # Count expired entries
        expired_count = 0
        for cache_file in files:
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cached = CachedClassification(**data)
                if cached.is_expired(self.ttl_days):
                    expired_count += 1
            except Exception:
                expired_count += 1

        return {
            "count": len(files),
            "expired_count": expired_count,
            "valid_count": len(files) - expired_count,
            "total_size": total_size,
            "total_size_kb": round(total_size / 1024, 2),
            "cache_dir": str(self.cache_dir),
            "ttl_days": self.ttl_days,
        }


# ═══════════════════════════════════════════════════════════════
# Singleton Instance
# ═══════════════════════════════════════════════════════════════
_classification_cache: ClassificationCache | None = None


def get_classification_cache(
    ttl_days: int = DEFAULT_TTL_DAYS,
) -> ClassificationCache:
    """
    Get the shared classification cache instance.

    Args:
        ttl_days: Time-to-live for cache entries (default: 30 days)

    Returns:
        ClassificationCache instance
    """
    global _classification_cache

    if _classification_cache is None:
        _classification_cache = ClassificationCache(ttl_days=ttl_days)

    return _classification_cache


def clear_classification_cache() -> int:
    """
    Clear all cached classifications.

    Convenience function that gets the cache and clears it.

    Returns:
        Number of entries deleted
    """
    cache = get_classification_cache()
    return cache.clear()


# ═══════════════════════════════════════════════════════════════
# Alt-Text Cache
# ═══════════════════════════════════════════════════════════════
@dataclass
class CachedAltText:
    """
    Cached AI-generated alt text with metadata.

    Stored as JSON in the cache directory.
    """

    image_hash: str
    category: str  # ImageCategory value
    alt_text: str
    generated_at: str  # ISO format timestamp
    cache_version: int = 1

    def is_expired(self, ttl_days: int = DEFAULT_TTL_DAYS) -> bool:
        """Check if this cache entry has expired."""
        try:
            generated_time = datetime.fromisoformat(self.generated_at)
            expiry_time = generated_time + timedelta(days=ttl_days)
            return datetime.now() > expiry_time
        except (ValueError, TypeError):
            return True


class AltTextCache:
    """
    Cache for AI-generated alt text suggestions.

    Uses content-based hashing + category as the cache key.
    This means the same image with the same category will get
    the same cached alt text, even if the document context varies.
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        ttl_days: int = DEFAULT_TTL_DAYS,
    ):
        """
        Initialize the alt-text cache.

        Args:
            cache_dir: Custom cache directory. Defaults to ~/.cache/inspekt/alt-text/
            ttl_days: Time-to-live for cache entries in days (default: 30)
        """
        if cache_dir is None:
            self.cache_dir = Path.home() / ".cache" / "inspekt" / "alt-text"
        else:
            self.cache_dir = cache_dir

        self.ttl_days = ttl_days
        self._ensure_cache_dir()

    def _ensure_cache_dir(self) -> None:
        """Create cache directory if it doesn't exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, image_hash: str, category: str) -> str:
        """Generate cache key from image hash and category."""
        # Combine hash and category for unique key
        combined = f"{image_hash}_{category}"
        return hashlib.sha256(combined.encode()).hexdigest()[:32]

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get the cache file path for a given key."""
        return self.cache_dir / f"{cache_key}.json"

    def get(self, image_bytes: bytes, category: str) -> str | None:
        """
        Get cached alt text for an image and category.

        Args:
            image_bytes: Raw image bytes
            category: ImageCategory value string

        Returns:
            Cached alt text or None if not found/expired
        """
        try:
            image_hash = ClassificationCache.compute_bytes_hash(image_bytes)
            cache_key = self._get_cache_key(image_hash, category)
            cache_path = self._get_cache_path(cache_key)

            if not cache_path.exists():
                return None

            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            cached = CachedAltText(**data)

            # Check if expired
            if cached.is_expired(self.ttl_days):
                logger.debug(f"Alt-text cache expired for {image_hash[:8]}…")
                cache_path.unlink(missing_ok=True)
                return None

            logger.debug(f"Alt-text cache hit for {image_hash[:8]}... ({category})")
            return cached.alt_text

        except Exception as e:
            logger.debug(f"Alt-text cache read error: {e}")
            return None

    def set(self, image_bytes: bytes, category: str, alt_text: str) -> bool:
        """
        Store alt text in cache.

        Args:
            image_bytes: Raw image bytes
            category: ImageCategory value string
            alt_text: Generated alt text to cache

        Returns:
            True if cached successfully, False otherwise
        """
        try:
            image_hash = ClassificationCache.compute_bytes_hash(image_bytes)
            cache_key = self._get_cache_key(image_hash, category)
            cache_path = self._get_cache_path(cache_key)

            cached = CachedAltText(
                image_hash=image_hash,
                category=category,
                alt_text=alt_text,
                generated_at=datetime.now().isoformat(),
            )

            # Write atomically
            temp_path = cache_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(asdict(cached), f, indent=2)

            temp_path.rename(cache_path)
            logger.debug(f"Cached alt-text for {image_hash[:8]}... ({category})")
            return True

        except Exception as e:
            logger.debug(f"Alt-text cache write error: {e}")
            return False

    def clear(self) -> int:
        """Clear all cached alt texts."""
        if not self.cache_dir.exists():
            return 0

        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
                count += 1
            except Exception:
                pass

        return count

    def get_stats(self) -> dict:
        """Get cache statistics."""
        if not self.cache_dir.exists():
            return {
                "count": 0,
                "total_size": 0,
                "cache_dir": str(self.cache_dir),
            }

        files = list(self.cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in files if f.is_file())

        return {
            "count": len(files),
            "total_size": total_size,
            "total_size_kb": round(total_size / 1024, 2),
            "cache_dir": str(self.cache_dir),
            "ttl_days": self.ttl_days,
        }


# Singleton instance for alt-text cache
_alt_text_cache: AltTextCache | None = None


def get_alt_text_cache(ttl_days: int = DEFAULT_TTL_DAYS) -> AltTextCache:
    """
    Get the shared alt-text cache instance.

    Args:
        ttl_days: Time-to-live for cache entries (default: 30 days)

    Returns:
        AltTextCache instance
    """
    global _alt_text_cache

    if _alt_text_cache is None:
        _alt_text_cache = AltTextCache(ttl_days=ttl_days)

    return _alt_text_cache
