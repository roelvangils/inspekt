"""
Image metadata service for Inspekt.

Provides embedding and reading of metadata in PNG and JPEG screenshot files.
Uses PNG tEXt chunks and JPEG EXIF UserComment fields.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from inspekt.services.formatting_utils import format_filesize

# Pillow is optional - check before importing
_PILLOW_AVAILABLE = False
try:
    import warnings

    from PIL import Image
    from PIL.PngImagePlugin import PngInfo

    # Increase pixel limit for large screenshots (default ~89M is too low for full-page captures)
    # 300 million pixels allows for very large screenshots while still protecting against actual bombs
    # E.g., 16384px page at 4x DPR = ~268M pixels
    Image.MAX_IMAGE_PIXELS = 300_000_000

    # Suppress the decompression bomb warning since we've set our own limit
    warnings.filterwarnings("ignore", category=Image.DecompressionBombWarning)

    _PILLOW_AVAILABLE = True
except ImportError:
    Image = None  # type: ignore
    PngInfo = None  # type: ignore

if TYPE_CHECKING:
    from typing import Any


def is_pillow_installed() -> bool:
    """
    Check if Pillow is available.

    Returns:
        True if Pillow is installed, False otherwise
    """
    return _PILLOW_AVAILABLE


# Metadata keys for screenshots (kebab-case with inspekt: namespace)
METADATA_KEYS = {
    # Core
    "source_url": "inspekt:source-url",
    "timestamp": "inspekt:capture-timestamp",
    "tool": "inspekt:tool",
    "tool_version": "inspekt:tool-version",
    # Screenshot target
    "target": "inspekt:target",
    "selector": "inspekt:selector",
    "element_tag": "inspekt:element-tag",
    # Image properties
    "dpr": "inspekt:device-pixel-ratio",
    "original_width": "inspekt:original-width",
    "original_height": "inspekt:original-height",
    "file_size": "inspekt:file-size",
    "compression_ratio": "inspekt:compression-ratio",
    "redacted": "inspekt:redacted",
    # Page context
    "page_title": "inspekt:page-title",
    "page_language": "inspekt:page-language",
    # Media queries
    "prefers_color_scheme": "inspekt:prefers-color-scheme",
    "prefers_contrast": "inspekt:prefers-contrast",
    "prefers_reduced_motion": "inspekt:prefers-reduced-motion",
    "prefers_reduced_transparency": "inspekt:prefers-reduced-transparency",
    "forced_colors": "inspekt:forced-colors",
    # Browser
    "browser_version": "inspekt:browser-version",
    "user_agent": "inspekt:user-agent",
    "window_width": "inspekt:window-width",
    "window_height": "inspekt:window-height",
    "viewport_width": "inspekt:viewport-width",
    "viewport_height": "inspekt:viewport-height",
    # Environment
    "captured_by": "inspekt:captured-by",
    "hostname": "inspekt:hostname",
    "operating_system": "inspekt:operating-system",
    "timezone": "inspekt:timezone",
}


def get_inspekt_version() -> str:
    """Get the current inspekt version from pyproject.toml."""
    try:
        from importlib.metadata import version
        return version("inspekt")
    except Exception:
        return "unknown"


def get_username() -> str:
    """Get the current username (cross-platform)."""
    import getpass
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def get_os_info() -> str:
    """
    Get operating system name and version.

    Returns:
        String like "macOS 14.2.1", "Windows 11", or "Linux 6.1.0"
    """
    import platform

    system = platform.system()

    if system == "Darwin":
        # macOS - get the marketing version
        mac_ver = platform.mac_ver()[0]
        return f"macOS {mac_ver}" if mac_ver else "macOS"
    elif system == "Windows":
        # Windows - get version like "10" or "11"
        win_ver = platform.win32_ver()[0]
        return f"Windows {win_ver}" if win_ver else "Windows"
    elif system == "Linux":
        # Linux - try to get distribution info
        try:
            # Python 3.10+ has platform.freedesktop_os_release()
            if hasattr(platform, "freedesktop_os_release"):
                info = platform.freedesktop_os_release()
                name = info.get("NAME", "Linux")
                version = info.get("VERSION_ID", "")
                return f"{name} {version}".strip()
        except Exception:
            pass
        # Fallback to kernel version
        return f"Linux {platform.release()}"
    else:
        return f"{system} {platform.release()}"


def get_hostname() -> str:
    """Get the machine hostname."""
    import socket
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


def get_timezone() -> str:
    """
    Get the local timezone name.

    Returns:
        Timezone string like "Europe/Brussels" or "UTC+01:00"
    """
    try:
        # Python 3.9+ approach
        from datetime import datetime

        # Try to get the IANA timezone name
        local_tz = datetime.now().astimezone().tzinfo
        if hasattr(local_tz, 'key'):
            return local_tz.key

        # Fallback to UTC offset format
        offset = datetime.now().astimezone().strftime('%z')
        return f"UTC{offset[:3]}:{offset[3:]}"
    except Exception:
        try:
            # Alternative: use time module
            import time
            return time.tzname[time.daylight] if time.daylight else time.tzname[0]
        except Exception:
            return "unknown"


def create_metadata(
    source_url: str | None = None,
    target: str = "unknown",
    selector: str | None = None,
    element_tag: str | None = None,
    dpr: int = 1,
    redacted: bool = False,
    # Image dimensions
    original_width: int | None = None,
    original_height: int | None = None,
    file_size: int | None = None,
    compression_ratio: float | None = None,
    # Page context
    page_title: str | None = None,
    page_language: str | None = None,
    # Media queries
    prefers_color_scheme: str | None = None,
    prefers_contrast: str | None = None,
    prefers_reduced_motion: str | None = None,
    prefers_reduced_transparency: str | None = None,
    forced_colors: str | None = None,
    # Browser info
    browser_version: str | None = None,
    user_agent: str | None = None,
    window_width: int | None = None,
    window_height: int | None = None,
    viewport_width: int | None = None,
    viewport_height: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, str]:
    """
    Create a metadata dictionary for a screenshot.

    Args:
        source_url: The URL of the page that was captured
        target: Screenshot target type (element, viewport, page)
        selector: CSS selector used to capture the element
        element_tag: HTML tag name of the captured element
        dpr: Device pixel ratio used for capture
        redacted: Whether the screenshot contains redacted sensitive data
        original_width: Original image width before any processing
        original_height: Original image height before any processing
        file_size: File size in bytes
        compression_ratio: Compression ratio as percentage
        page_title: Document title
        page_language: Document language (from lang attr or navigator.language)
        prefers_color_scheme: User color scheme preference (light/dark)
        prefers_contrast: User contrast preference (no-preference/more/less)
        prefers_reduced_motion: User motion preference (no-preference/reduce)
        prefers_reduced_transparency: User transparency preference
        forced_colors: Forced colors mode (none/active)
        browser_version: Chrome/browser version string
        user_agent: Full user agent string
        window_width: Browser window outer width
        window_height: Browser window outer height
        viewport_width: Viewport inner width
        viewport_height: Viewport inner height
        extra: Additional metadata key-value pairs

    Returns:
        Dictionary of metadata key-value pairs
    """
    # Core metadata (always included)
    metadata = {
        METADATA_KEYS["timestamp"]: datetime.now(UTC).isoformat(),
        METADATA_KEYS["tool"]: "inspekt",
        METADATA_KEYS["tool_version"]: get_inspekt_version(),
        METADATA_KEYS["target"]: target,
        METADATA_KEYS["dpr"]: str(dpr),
        # Environment (automatic)
        METADATA_KEYS["captured_by"]: get_username(),
        METADATA_KEYS["hostname"]: get_hostname(),
        METADATA_KEYS["operating_system"]: get_os_info(),
        METADATA_KEYS["timezone"]: get_timezone(),
    }

    # Source URL
    if source_url:
        metadata[METADATA_KEYS["source_url"]] = source_url

    # Screenshot target details
    if selector:
        metadata[METADATA_KEYS["selector"]] = selector

    if element_tag:
        metadata[METADATA_KEYS["element_tag"]] = element_tag

    if redacted:
        metadata[METADATA_KEYS["redacted"]] = "true"

    # Image dimensions
    if original_width is not None:
        metadata[METADATA_KEYS["original_width"]] = str(original_width)

    if original_height is not None:
        metadata[METADATA_KEYS["original_height"]] = str(original_height)

    if file_size is not None:
        metadata[METADATA_KEYS["file_size"]] = str(file_size)

    if compression_ratio is not None:
        metadata[METADATA_KEYS["compression_ratio"]] = f"{compression_ratio:.1f}"

    # Page context
    if page_title:
        metadata[METADATA_KEYS["page_title"]] = page_title

    if page_language:
        metadata[METADATA_KEYS["page_language"]] = page_language

    # Media queries
    if prefers_color_scheme:
        metadata[METADATA_KEYS["prefers_color_scheme"]] = prefers_color_scheme

    if prefers_contrast:
        metadata[METADATA_KEYS["prefers_contrast"]] = prefers_contrast

    if prefers_reduced_motion:
        metadata[METADATA_KEYS["prefers_reduced_motion"]] = prefers_reduced_motion

    if prefers_reduced_transparency:
        metadata[METADATA_KEYS["prefers_reduced_transparency"]] = prefers_reduced_transparency

    if forced_colors:
        metadata[METADATA_KEYS["forced_colors"]] = forced_colors

    # Browser info
    if browser_version:
        metadata[METADATA_KEYS["browser_version"]] = browser_version

    if user_agent:
        metadata[METADATA_KEYS["user_agent"]] = user_agent

    if window_width is not None:
        metadata[METADATA_KEYS["window_width"]] = str(window_width)

    if window_height is not None:
        metadata[METADATA_KEYS["window_height"]] = str(window_height)

    if viewport_width is not None:
        metadata[METADATA_KEYS["viewport_width"]] = str(viewport_width)

    if viewport_height is not None:
        metadata[METADATA_KEYS["viewport_height"]] = str(viewport_height)

    # Add any extra metadata
    if extra:
        for key, value in extra.items():
            metadata[f"inspekt:{key}"] = str(value)

    return metadata


def add_png_metadata(file_path: Path, metadata: dict[str, str]) -> None:
    """
    Add metadata to a PNG file using tEXt chunks.

    The metadata is preserved when viewing file properties in most
    operating systems and image viewers.

    Args:
        file_path: Path to the PNG file
        metadata: Dictionary of metadata key-value pairs

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file is not a PNG
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if file_path.suffix.lower() != ".png":
        raise ValueError(f"Expected PNG file, got: {file_path.suffix}")

    # Open image and create PngInfo
    with Image.open(file_path) as img:
        pnginfo = PngInfo()

        # Preserve any existing text chunks
        if hasattr(img, "text"):
            for key, value in img.text.items():
                if key not in metadata:
                    pnginfo.add_text(key, value)

        # Add new metadata
        for key, value in metadata.items():
            pnginfo.add_text(key, value)

        # Save with metadata
        # Need to save to buffer first, then write to file
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", pnginfo=pnginfo)
        buffer.seek(0)

    # Write buffer to file
    with open(file_path, "wb") as f:
        f.write(buffer.getvalue())


def add_jpeg_metadata(file_path: Path, metadata: dict[str, str]) -> None:
    """
    Add metadata to a JPEG file using EXIF UserComment field.

    Since JPEG has limited text metadata support, we store metadata
    as a JSON string in the UserComment EXIF field.

    Args:
        file_path: Path to the JPEG file
        metadata: Dictionary of metadata key-value pairs

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file is not a JPEG
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if file_path.suffix.lower() not in (".jpg", ".jpeg"):
        raise ValueError(f"Expected JPEG file, got: {file_path.suffix}")

    # JPEG EXIF handling is complex without piexif
    # For now, we'll use XMP sidecar approach or skip
    # This is a simplified implementation using Pillow's limited EXIF support
    try:
        with Image.open(file_path) as img:
            # Get existing EXIF or create new
            exif = img.getexif()

            # UserComment tag (0x9286) - store JSON metadata
            # Note: This requires proper encoding
            user_comment = json.dumps(metadata, ensure_ascii=False)

            # Tag 0x9286 is UserComment in EXIF IFD
            # We need to write to the EXIF IFD, not main IFD
            # For simplicity, we'll use ImageDescription (0x010E) which is main IFD
            exif[0x010E] = user_comment  # ImageDescription

            # Save with EXIF
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", exif=exif, quality=95)
            buffer.seek(0)

        # Write buffer to file
        with open(file_path, "wb") as f:
            f.write(buffer.getvalue())

    except Exception as e:
        # JPEG EXIF writing can be finicky, log warning but don't fail
        import click
        click.echo(f"Warning: Could not add metadata to JPEG: {e}", err=True)


def add_metadata(file_path: Path, metadata: dict[str, str]) -> None:
    """
    Add metadata to an image file (PNG or JPEG).

    Automatically detects file format and uses appropriate method.

    Args:
        file_path: Path to the image file
        metadata: Dictionary of metadata key-value pairs

    Raises:
        ImportError: If Pillow is not installed
    """
    if not is_pillow_installed():
        raise ImportError("Pillow is required for metadata embedding. Install with: pip install Pillow")

    file_path = Path(file_path)
    suffix = file_path.suffix.lower()

    if suffix == ".png":
        add_png_metadata(file_path, metadata)
    elif suffix in (".jpg", ".jpeg"):
        add_jpeg_metadata(file_path, metadata)
    elif suffix == ".webp":
        # WebP metadata support is limited in Pillow
        # Could implement via XMP sidecar in future
        pass
    else:
        raise ValueError(f"Unsupported image format: {suffix}")


def read_png_metadata(file_path: Path) -> dict[str, str]:
    """
    Read metadata from a PNG file.

    Args:
        file_path: Path to the PNG file

    Returns:
        Dictionary of metadata key-value pairs (only Inspekt keys)

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    with Image.open(file_path) as img:
        metadata = {}

        if hasattr(img, "text"):
            for key, value in img.text.items():
                # Only return Inspekt metadata (lowercase namespace)
                if key.startswith("inspekt:"):
                    metadata[key] = value

        return metadata


def read_jpeg_metadata(file_path: Path) -> dict[str, str]:
    """
    Read metadata from a JPEG file.

    Args:
        file_path: Path to the JPEG file

    Returns:
        Dictionary of metadata key-value pairs (only Inspekt keys)
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    try:
        with Image.open(file_path) as img:
            exif = img.getexif()

            # Check ImageDescription (0x010E) for our JSON
            if 0x010E in exif:
                try:
                    data = json.loads(exif[0x010E])
                    return {k: v for k, v in data.items() if k.startswith("inspekt:")}
                except json.JSONDecodeError:
                    pass

            return {}
    except Exception:
        return {}


def read_metadata(file_path: Path) -> dict[str, str]:
    """
    Read Inspekt metadata from an image file.

    Args:
        file_path: Path to the image file

    Returns:
        Dictionary of Inspekt metadata key-value pairs
    """
    file_path = Path(file_path)
    suffix = file_path.suffix.lower()

    if suffix == ".png":
        return read_png_metadata(file_path)
    elif suffix in (".jpg", ".jpeg"):
        return read_jpeg_metadata(file_path)
    else:
        return {}


def format_metadata_display(metadata: dict[str, str]) -> str:
    """
    Format metadata for CLI display.

    Args:
        metadata: Dictionary of metadata key-value pairs

    Returns:
        Formatted string for display
    """
    if not metadata:
        return "No Inspekt metadata found"

    lines = []

    # Organized display sections with (key, display_name) tuples
    sections = {
        "Core": [
            (METADATA_KEYS["source_url"], "Source URL"),
            (METADATA_KEYS["timestamp"], "Captured"),
            (METADATA_KEYS["tool"], "Tool"),
            (METADATA_KEYS["tool_version"], "Version"),
        ],
        "Screenshot": [
            (METADATA_KEYS["target"], "Target"),
            (METADATA_KEYS["selector"], "Selector"),
            (METADATA_KEYS["element_tag"], "Element"),
            (METADATA_KEYS["dpr"], "DPR"),
            (METADATA_KEYS["redacted"], "Redacted"),
        ],
        "Image": [
            (METADATA_KEYS["original_width"], "Original Width"),
            (METADATA_KEYS["original_height"], "Original Height"),
            (METADATA_KEYS["file_size"], "File Size"),
            (METADATA_KEYS["compression_ratio"], "Compression"),
        ],
        "Page": [
            (METADATA_KEYS["page_title"], "Page Title"),
            (METADATA_KEYS["page_language"], "Language"),
        ],
        "Media Queries": [
            (METADATA_KEYS["prefers_color_scheme"], "Color Scheme"),
            (METADATA_KEYS["prefers_contrast"], "Contrast"),
            (METADATA_KEYS["prefers_reduced_motion"], "Reduced Motion"),
            (METADATA_KEYS["prefers_reduced_transparency"], "Reduced Transparency"),
            (METADATA_KEYS["forced_colors"], "Forced Colors"),
        ],
        "Browser": [
            (METADATA_KEYS["browser_version"], "Browser Version"),
            (METADATA_KEYS["user_agent"], "User Agent"),
            (METADATA_KEYS["window_width"], "Window Width"),
            (METADATA_KEYS["window_height"], "Window Height"),
            (METADATA_KEYS["viewport_width"], "Viewport Width"),
            (METADATA_KEYS["viewport_height"], "Viewport Height"),
        ],
        "Environment": [
            (METADATA_KEYS["captured_by"], "Captured By"),
            (METADATA_KEYS["hostname"], "Hostname"),
            (METADATA_KEYS["operating_system"], "OS"),
            (METADATA_KEYS["timezone"], "Timezone"),
        ],
    }

    # Track which keys we've displayed
    displayed_keys = set()

    for _section_name, fields in sections.items():
        section_lines = []
        for key, display_name in fields:
            if key in metadata:
                value = metadata[key]
                displayed_keys.add(key)

                # Format special values
                if key == METADATA_KEYS["timestamp"]:
                    try:
                        dt = datetime.fromisoformat(value)
                        value = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                    except ValueError:
                        pass
                elif key == METADATA_KEYS["file_size"]:
                    # Format file size as human readable
                    try:
                        size = int(value)
                        value = format_filesize(size)
                    except ValueError:
                        pass
                elif key == METADATA_KEYS["compression_ratio"]:
                    value = f"{value}%"

                section_lines.append(f"  {display_name}: {value}")

        if section_lines:
            lines.extend(section_lines)

    # Add any extra metadata not in predefined sections
    for key, value in metadata.items():
        if key.startswith("inspekt:") and key not in displayed_keys:
            display_key = key.replace("inspekt:", "").replace("-", " ").title()
            lines.append(f"  {display_key}: {value}")

    return "\n".join(lines)
