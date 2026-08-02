"""
HTML Image Optimization Service for Inspekt.

Processes HTML content with embedded base64 images:
- Resizes images to their displayed width (1x, not retina)
- Converts JPG/JPEG to WebP at configurable quality
- Optimizes PNG with oxipng

This is designed for use with SingleFile output where images are
embedded as data URIs.
"""

from __future__ import annotations

import base64
import io
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PIL import Image

from inspekt.services.image_optimizer import is_oxipng_installed, optimize_png_data

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class ImageOptimizationStats:
    """Statistics from image optimization."""

    total_images: int = 0
    optimized_images: int = 0
    resized_images: int = 0
    converted_to_webp: int = 0
    optimized_png: int = 0
    skipped_images: int = 0
    original_size: int = 0
    optimized_size: int = 0

    @property
    def savings_bytes(self) -> int:
        return self.original_size - self.optimized_size

    @property
    def savings_percent(self) -> float:
        if self.original_size == 0:
            return 0.0
        return (self.savings_bytes / self.original_size) * 100


def parse_data_uri(data_uri: str) -> tuple[str, bytes] | None:
    """
    Parse a data URI into mime type and decoded bytes.

    Args:
        data_uri: Data URI string (e.g., "data:image/jpeg;base64,…")

    Returns:
        Tuple of (mime_type, bytes) or None if parsing fails
    """
    # Match data:image/TYPE;base64,DATA
    match = re.match(r"data:image/([^;,]+)(?:;base64)?,(.+)", data_uri, re.DOTALL)
    if not match:
        return None

    image_type = match.group(1).lower()
    data_part = match.group(2)

    # Normalize image type
    if image_type == "jpg":
        image_type = "jpeg"

    try:
        image_bytes = base64.b64decode(data_part)
        return (f"image/{image_type}", image_bytes)
    except Exception:
        return None


def encode_data_uri(mime_type: str, data: bytes) -> str:
    """
    Encode bytes as a data URI.

    Args:
        mime_type: MIME type (e.g., "image/webp")
        data: Raw image bytes

    Returns:
        Data URI string
    """
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{b64}"


def extract_displayed_width(img_tag: str) -> int | None:
    """
    Extract the displayed width from an img tag.

    Checks (in order):
    1. width attribute
    2. style="width: Npx"
    3. style="max-width: Npx"

    Args:
        img_tag: The full <img ...> tag HTML

    Returns:
        Width in pixels, or None if not found
    """
    # Check width attribute
    width_match = re.search(r'\bwidth\s*=\s*["\']?(\d+)', img_tag, re.IGNORECASE)
    if width_match:
        return int(width_match.group(1))

    # Check style attribute for width
    style_match = re.search(r'style\s*=\s*["\']([^"\']+)["\']', img_tag, re.IGNORECASE)
    if style_match:
        style = style_match.group(1)

        # Check for width: Npx
        px_match = re.search(r"\bwidth\s*:\s*(\d+)px", style, re.IGNORECASE)
        if px_match:
            return int(px_match.group(1))

        # Check for max-width: Npx
        max_match = re.search(r"\bmax-width\s*:\s*(\d+)px", style, re.IGNORECASE)
        if max_match:
            return int(max_match.group(1))

    return None


def optimize_image(
    image_bytes: bytes,
    mime_type: str,
    target_width: int | None = None,
    webp_quality: int = 30,
    optimize_png: bool = True,
) -> tuple[bytes, str]:
    """
    Optimize a single image.

    Args:
        image_bytes: Raw image bytes
        mime_type: Original MIME type
        target_width: Target width for resizing (None = no resize)
        webp_quality: Quality for WebP conversion (1-100)
        optimize_png: Whether to run oxipng on PNGs

    Returns:
        Tuple of (optimized_bytes, new_mime_type)
    """
    try:
        # Open image with Pillow
        img = Image.open(io.BytesIO(image_bytes))
        original_width, original_height = img.size

        # Resize if target width is specified and smaller than original
        if target_width and target_width < original_width:
            # Calculate new height maintaining aspect ratio
            ratio = target_width / original_width
            new_height = int(original_height * ratio)
            img = img.resize((target_width, new_height), Image.Resampling.LANCZOS)

        # Determine output format based on input
        is_jpeg = mime_type in ("image/jpeg", "image/jpg")
        is_png = mime_type == "image/png"
        is_gif = mime_type == "image/gif"
        is_webp = mime_type == "image/webp"

        # Handle transparency for format conversion
        has_transparency = img.mode in ("RGBA", "LA", "P")
        if has_transparency and img.mode == "P":
            # Check if palette has transparency
            has_transparency = "transparency" in img.info

        # Convert JPEG to WebP
        if is_jpeg:
            # Convert to RGB if needed (JPEG doesn't support alpha)
            if img.mode != "RGB":
                img = img.convert("RGB")

            output = io.BytesIO()
            img.save(output, format="WEBP", quality=webp_quality, method=6)
            return (output.getvalue(), "image/webp")

        # Optimize PNG
        if is_png:
            # Save as PNG first
            output = io.BytesIO()

            # Ensure proper mode for PNG
            if img.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                img = img.convert("RGBA" if has_transparency else "RGB")

            img.save(output, format="PNG", optimize=True)
            png_data = output.getvalue()

            # Apply oxipng if available
            if optimize_png and is_oxipng_installed():
                png_data = optimize_png_data(png_data, level=3, strip=True)

            return (png_data, "image/png")

        # For GIF, WebP, and others - just resize if needed, keep format
        if is_gif:
            output = io.BytesIO()
            img.save(output, format="GIF")
            return (output.getvalue(), "image/gif")

        if is_webp:
            output = io.BytesIO()
            img.save(output, format="WEBP", quality=webp_quality, method=6)
            return (output.getvalue(), "image/webp")

        # Unknown format - return original
        return (image_bytes, mime_type)

    except Exception:
        # On any error, return original unchanged
        return (image_bytes, mime_type)


def optimize_html_images(
    html_content: str,
    webp_quality: int = 30,
    optimize_png: bool = True,
    resize_to_displayed: bool = True,
    min_size_bytes: int = 1024,
    on_progress: Callable[[int, int, str], None] | None = None,
    debug: bool = False,
) -> tuple[str, ImageOptimizationStats]:
    """
    Optimize all embedded images in HTML content.

    Args:
        html_content: HTML string with embedded base64 images
        webp_quality: Quality for WebP conversion (1-100, default: 30)
        optimize_png: Whether to optimize PNGs with oxipng
        resize_to_displayed: Whether to resize images to displayed width
        min_size_bytes: Minimum image size to optimize (skip tiny images)
        on_progress: Optional callback(current, total, status)
        debug: Whether to print debug information

    Returns:
        Tuple of (optimized_html, stats)
    """
    stats = ImageOptimizationStats()

    # Find all img tags with data URIs
    # Pattern matches <img ... src="data:image/…" ...>
    img_pattern = re.compile(
        r'(<img\s[^>]*?src\s*=\s*["\'])(data:image/[^"\']+)(["\'][^>]*>)',
        re.IGNORECASE | re.DOTALL,
    )

    matches = list(img_pattern.finditer(html_content))
    stats.total_images = len(matches)

    if stats.total_images == 0:
        return (html_content, stats)

    # Process each image
    replacements: list[tuple[int, int, str]] = []

    for i, match in enumerate(matches):
        if on_progress:
            on_progress(i + 1, stats.total_images, "Processing images")

        full_match = match.group(0)
        prefix = match.group(1)  # <img ... src="
        data_uri = match.group(2)  # data:image/...
        suffix = match.group(3)  # ">...

        # Parse the data URI
        parsed = parse_data_uri(data_uri)
        if parsed is None:
            stats.skipped_images += 1
            continue

        mime_type, image_bytes = parsed
        original_len = len(image_bytes)

        # Skip tiny images (icons, spacers)
        if original_len < min_size_bytes:
            stats.skipped_images += 1
            continue

        stats.original_size += original_len

        # Get displayed width if we should resize
        target_width = None
        if resize_to_displayed:
            target_width = extract_displayed_width(full_match)

        # Optimize the image
        optimized_bytes, new_mime_type = optimize_image(
            image_bytes,
            mime_type,
            target_width=target_width,
            webp_quality=webp_quality,
            optimize_png=optimize_png,
        )

        optimized_len = len(optimized_bytes)
        stats.optimized_size += optimized_len

        # Track what was done
        if target_width and optimized_len < original_len:
            stats.resized_images += 1

        if new_mime_type == "image/webp" and mime_type != "image/webp":
            stats.converted_to_webp += 1

        if mime_type == "image/png" and optimize_png:
            stats.optimized_png += 1

        # Only replace if we actually saved space
        if optimized_len < original_len:
            stats.optimized_images += 1
            new_data_uri = encode_data_uri(new_mime_type, optimized_bytes)
            new_tag = f"{prefix}{new_data_uri}{suffix}"

            # Store replacement (position, length, new content)
            replacements.append((match.start(), match.end(), new_tag))

            if debug:
                savings = original_len - optimized_len
                print(
                    f"  Image {i + 1}: {original_len:,} → {optimized_len:,} bytes "
                    f"(-{savings:,}, {savings / original_len * 100:.1f}%)"
                )
        else:
            stats.skipped_images += 1
            # Keep original size in stats
            stats.optimized_size = stats.optimized_size - optimized_len + original_len

    # Apply replacements in reverse order to preserve positions
    result = html_content
    for start, end, new_content in reversed(replacements):
        result = result[:start] + new_content + result[end:]

    return (result, stats)
