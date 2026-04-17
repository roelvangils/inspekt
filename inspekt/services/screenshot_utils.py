"""
Shared utilities for screenshot commands.

Provides common functionality used across node, viewport, and page screenshot modes.
"""

import base64
import re
import sys
from datetime import datetime
from pathlib import Path

import click

from inspekt.app.cli import icons


def slugify(text: str, max_length: int = 50) -> str:
    """
    Convert text to a URL/filename-safe slug.

    Args:
        text: Text to slugify (e.g., page title)
        max_length: Maximum length of the slug (default: 50)

    Returns:
        Lowercase slug with hyphens (e.g., "my-page-title")

    Examples:
        "Hello World!" -> "hello-world"
        "My Page — Special" -> "my-page-special"
        "   Spaces   " -> "spaces"
    """
    if not text:
        return "untitled"

    # Lowercase
    slug = text.lower()
    # Replace common separators with hyphens
    slug = re.sub(r"[\s_—–]+", "-", slug)
    # Remove non-alphanumeric characters (except hyphens)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    # Remove consecutive hyphens
    slug = re.sub(r"-+", "-", slug)
    # Strip leading/trailing hyphens
    slug = slug.strip("-")
    # Truncate to max_length, avoiding cutting in the middle of a word
    if len(slug) > max_length:
        slug = slug[:max_length].rsplit("-", 1)[0]

    return slug or "untitled"


def generate_screenshot_filename(
    mode: str,
    page_title: str | None = None,
    format: str = "png",
) -> str:
    """
    Generate an auto-generated filename for screenshots.

    Args:
        mode: Screenshot mode ("node", "viewport", "page")
        page_title: Page title to include in filename
        format: Image format extension

    Returns:
        Generated filename like "20251223124851_viewport_my-page.png"
    """
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    title_slug = slugify(page_title) if page_title else "untitled"

    if mode == "page":
        # Full page: YYYYMMDDHHMMSS_[TITLE].png
        return f"{timestamp}_{title_slug}.{format}"
    elif mode == "viewport":
        # Viewport: YYYYMMDDHHMMSS_viewport_[TITLE].png
        return f"{timestamp}_viewport_{title_slug}.{format}"
    else:
        # Node mode handled separately (uses tag name)
        return f"{timestamp}_{title_slug}.{format}"


def get_screenshot_output_path(
    output: str | None,
    mode: str,
    page_title: str | None = None,
    format: str = "png",
) -> tuple[Path, bool]:
    """
    Get the output path for a screenshot, auto-generating if needed.

    Args:
        output: User-provided output path (may be None)
        mode: Screenshot mode ("viewport", "page")
        page_title: Page title for auto-generated filename
        format: Image format extension

    Returns:
        Tuple of (output_path, auto_generated)
    """
    if output:
        return Path(output), False

    # Auto-generate filename
    from inspekt.config import get_paths_config

    filename = generate_screenshot_filename(mode, page_title, format)
    paths = get_paths_config()
    output_path = paths["screenshots"] / filename

    return output_path, True


def decode_data_url(data_url: str) -> bytes:
    """
    Extract and decode base64 image data from a data URL.

    Args:
        data_url: Data URL string (e.g., "data:image/png;base64,…")

    Returns:
        Decoded image bytes

    Raises:
        ValueError: If data URL is empty or decoding fails
    """
    if not data_url:
        raise ValueError("No image data received from Chrome")

    # Extract base64 portion after comma
    if "," in data_url:
        base64_data = data_url.split(",", 1)[1]
    else:
        base64_data = data_url

    try:
        image_data = base64.b64decode(base64_data)
    except Exception as e:
        raise ValueError(f"Failed to decode image data: {e}")

    if len(image_data) == 0:
        raise ValueError("Received empty image data from Chrome")

    return image_data


def validate_screenshot_options(
    clipboard: bool,
    open_after: bool,
    reveal_after: bool,
    json_output: bool = False,
    output: str | None = None,
    allow_auto_filename: bool = False,
) -> None:
    """
    Validate mutually exclusive screenshot options.

    Args:
        clipboard: Whether to copy to clipboard
        open_after: Whether to open file after saving
        reveal_after: Whether to reveal file in explorer
        json_output: Whether JSON output mode is enabled
        output: Output file path
        allow_auto_filename: Whether auto-generated filename is allowed (default: False)

    Raises:
        SystemExit: If validation fails
    """
    if clipboard and (open_after or reveal_after):
        click.echo("Error: --clipboard cannot be used with --open or --reveal", err=True)
        sys.exit(1)

    if json_output and (open_after or reveal_after or clipboard):
        click.echo("Error: --json cannot be used with --open, --reveal, or --clipboard", err=True)
        sys.exit(1)

    if not clipboard and not output and not allow_auto_filename:
        click.echo("Error: Either --output or --clipboard is required", err=True)
        sys.exit(1)


def display_adjustment_feedback(
    response: dict,
    quiet: bool = False,
    json_output: bool = False,
) -> None:
    """
    Display feedback about zoom and selection adjustments made before capture.

    Args:
        response: Response dict from Chrome containing adjustment info
        quiet: Suppress output if True
        json_output: Suppress output if True (JSON mode)
    """
    if quiet or json_output:
        return

    # Zoom reset feedback
    if response.get("zoomWasReset"):
        original_zoom = response.get("originalZoom", 1.0)
        zoom_percent = int(original_zoom * 100)
        # Use zoom-out icon if reducing, zoom-in if increasing
        zoom_icon = "\uf532" if original_zoom > 1.0 else "\uf531"
        click.echo(click.style(f"{zoom_icon}  ", fg="blue") + f"Resetting zoom level from {zoom_percent}% to 100%…")

    # Selection cleared feedback
    if response.get("selectionCleared"):
        click.echo(click.style("\U000F09A9  ", fg="blue") + "Clearing text selection…")


def display_capture_feedback(
    mode: str,
    selector: str | None = None,
    quiet: bool = False,
    json_output: bool = False,
) -> None:
    """
    Display feedback about the capture action.

    Args:
        mode: Screenshot mode ("node", "viewport", "page")
        selector: CSS selector for node mode
        quiet: Suppress output if True
        json_output: Suppress output if True (JSON mode)
    """
    if quiet or json_output:
        return

    if mode == "node":
        if selector:
            click.echo(click.style("\ueada  ", fg="blue") + f"Capturing element: {selector}")
        else:
            click.echo(icons.camera("Capturing currently inspected element…"))
    elif mode == "viewport":
        click.echo(click.style("\ueada  ", fg="blue") + "Capturing viewport…")
    elif mode == "page":
        click.echo(click.style("\ueada  ", fg="blue") + "Capturing full page (debugger will attach briefly)…")


def display_restoration_feedback(
    response: dict,
    quiet: bool = False,
    json_output: bool = False,
) -> None:
    """
    Display feedback about zoom/selection being restored after capture.

    Args:
        response: Response dict from Chrome containing restoration info
        quiet: Suppress output if True
        json_output: Suppress output if True (JSON mode)
    """
    if quiet or json_output:
        return

    zoom_restored = response.get("zoomWasReset")
    selection_restored = response.get("selectionCleared")

    if zoom_restored and selection_restored:
        click.echo(icons.info("Zoom level and text selection restored"))
    elif zoom_restored:
        click.echo(icons.info("Zoom level restored"))
    elif selection_restored:
        click.echo(icons.info("Text selection restored"))


def display_dimension_warning(
    width: int | None,
    height: int | None,
    quiet: bool = False,
    json_output: bool = False,
) -> None:
    """
    Display warning for unusually large dimensions.

    Args:
        width: Image width in pixels
        height: Image height in pixels
        quiet: Suppress output if True
        json_output: Suppress output if True (JSON mode)
    """
    if quiet or json_output:
        return

    if width and height and (width > 10000 or height > 10000):
        click.echo(
            f"Note: Large dimensions ({width}x{height}px) may result in large file sizes.",
            err=True,
        )
