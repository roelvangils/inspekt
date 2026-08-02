"""
Image caching service for article extraction.

Provides:
- Download images from URLs
- Cache images permanently at ~/.cache/inspekt/images/
- Hash-based filename generation to avoid collisions
- Graceful failure handling
"""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import urlparse

from inspekt.services import http_client

if TYPE_CHECKING:
    from collections.abc import Callable


class ImageCache:
    """Manages image downloading and caching."""

    # Valid image extensions to preserve
    VALID_EXTENSIONS: ClassVar[set[str]] = {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".svg",
        ".avif",
    }

    def __init__(self, cache_dir: Path | None = None):
        """
        Initialize the image cache.

        Args:
            cache_dir: Custom cache directory. Defaults to ~/.cache/inspekt/images/
        """
        if cache_dir is None:
            self.cache_dir = Path.home() / ".cache" / "inspekt" / "images"
        else:
            self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cache_path(self, url: str) -> Path:
        """
        Generate cache file path from URL using hash.

        Uses SHA256 hash of the URL (first 16 chars) to create a deterministic
        filename that avoids collisions and filesystem issues with special characters.

        Args:
            url: The image URL

        Returns:
            Path to the cached file location
        """
        # Extract extension from URL
        parsed = urlparse(url)
        path = parsed.path
        extension = Path(path).suffix.lower()

        # Normalize extension - use .jpg as default for unknown types
        if extension not in self.VALID_EXTENSIONS:
            extension = ".jpg"

        # Generate hash-based filename
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        return self.cache_dir / f"{url_hash}{extension}"

    def is_cached(self, url: str) -> bool:
        """
        Check if an image URL is already cached.

        Args:
            url: The image URL

        Returns:
            True if the image is cached, False otherwise
        """
        return self.get_cache_path(url).exists()

    def get_or_download(self, url: str, timeout: float = 10.0) -> Path | None:
        """
        Get cached image or download if not cached.

        Args:
            url: The image URL to fetch
            timeout: Download timeout in seconds

        Returns:
            Path to cached file, or None if download failed
        """
        cache_path = self.get_cache_path(url)

        # Return cached version if exists
        if cache_path.exists():
            return cache_path

        # Skip data URLs - they're already embedded
        if url.startswith("data:"):
            return None

        try:
            response = http_client.get(
                url,
                timeout=timeout,
                stream=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
            )
            response.raise_for_status()

            # Write to cache
            with open(cache_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            return cache_path
        except Exception:
            # Return None on any failure - caller handles gracefully
            return None

    def download_batch(
        self,
        urls: list[str],
        on_progress: Callable[[str, bool, int, int], None] | None = None,
        max_workers: int = 5,
    ) -> dict[str, Path | None]:
        """
        Download multiple images concurrently.

        Args:
            urls: List of image URLs to download
            on_progress: Optional callback(url, success, current, total)
            max_workers: Maximum concurrent downloads

        Returns:
            Dictionary mapping URL to cached Path (or None if failed)
        """
        results: dict[str, Path | None] = {}
        total = len(urls)

        if not urls:
            return results

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(self.get_or_download, url): url for url in urls}

            for i, future in enumerate(as_completed(future_to_url), 1):
                url = future_to_url[future]
                try:
                    results[url] = future.result()
                    success = results[url] is not None
                except Exception:
                    results[url] = None
                    success = False

                if on_progress:
                    on_progress(url, success, i, total)

        return results

    def get_cache_stats(self) -> dict:
        """
        Get statistics about the image cache.

        Returns:
            Dictionary with count, total_size, and cache_dir
        """
        if not self.cache_dir.exists():
            return {"count": 0, "total_size": 0, "cache_dir": str(self.cache_dir)}

        files = list(self.cache_dir.glob("*"))
        total_size = sum(f.stat().st_size for f in files if f.is_file())

        return {
            "count": len(files),
            "total_size": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "cache_dir": str(self.cache_dir),
        }

    def clear_cache(self) -> int:
        """
        Clear all cached images.

        Returns:
            Number of files deleted
        """
        if not self.cache_dir.exists():
            return 0

        count = 0
        for f in self.cache_dir.glob("*"):
            if f.is_file():
                f.unlink()
                count += 1

        return count


def get_image_cache() -> ImageCache:
    """
    Get the default image cache instance.

    Returns:
        ImageCache instance with default cache directory
    """
    return ImageCache()
