"""
Image grid composition for pseudo-state screenshots.

Creates a labeled grid of screenshots showing an element in different CSS states.
"""

from __future__ import annotations

import io

# Pillow is optional - check before importing
_PILLOW_AVAILABLE = False
try:
    from PIL import Image, ImageDraw, ImageFont

    _PILLOW_AVAILABLE = True
except ImportError:
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore
    ImageFont = None  # type: ignore



def is_pillow_installed() -> bool:
    """Check if Pillow is available."""
    return _PILLOW_AVAILABLE


def compose_state_grid(
    screenshots: list[tuple[str, bytes]],
    columns: int = 2,
    label_height: int = 28,
    padding: int = 12,
    cell_padding: int = 8,
    background_color: str = "#f8f9fa",
    label_color: str = "#495057",
    border_color: str = "#dee2e6",
    border_width: int = 1,
) -> bytes:
    """
    Compose a grid of labeled screenshots.

    Args:
        screenshots: List of (label, image_bytes) tuples
        columns: Number of columns in grid (default: 2)
        label_height: Height of label area below each image
        padding: Padding around the entire grid
        cell_padding: Padding inside each cell around the image
        background_color: Grid background color (hex)
        label_color: Label text color (hex)
        border_color: Border around each screenshot (hex)
        border_width: Border width in pixels

    Returns:
        Composed grid image as PNG bytes

    Raises:
        ImportError: If Pillow is not installed
        ValueError: If screenshots list is empty
    """
    if not is_pillow_installed():
        raise ImportError(
            "Pillow is required for grid composition. Install with: pip install Pillow"
        )

    if not screenshots:
        raise ValueError("At least one screenshot is required")

    # Load all images and find max dimensions
    images: list[tuple[str, Image.Image]] = []
    max_width = 0
    max_height = 0

    for label, img_bytes in screenshots:
        img = Image.open(io.BytesIO(img_bytes))
        # Convert to RGB if necessary (handles RGBA, P, etc.)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        images.append((label, img))
        max_width = max(max_width, img.width)
        max_height = max(max_height, img.height)

    # Calculate grid dimensions
    num_images = len(images)
    rows = (num_images + columns - 1) // columns  # Ceiling division

    # Cell dimensions include the image area + padding + border + label
    cell_width = max_width + cell_padding * 2 + border_width * 2
    cell_height = max_height + cell_padding * 2 + border_width * 2 + label_height

    # Grid dimensions
    grid_width = columns * cell_width + padding * 2 + (columns - 1) * padding
    grid_height = rows * cell_height + padding * 2 + (rows - 1) * padding

    # Create grid canvas
    grid = Image.new("RGB", (grid_width, grid_height), background_color)
    draw = ImageDraw.Draw(grid)

    # Try to load a nice font, fall back to default
    font = _get_font(size=13)

    # Place each image in grid
    for i, (label, img) in enumerate(images):
        row = i // columns
        col = i % columns

        # Calculate cell position (top-left of the cell)
        cell_x = padding + col * (cell_width + padding)
        cell_y = padding + row * (cell_height + padding)

        # Draw cell background (white) with border
        cell_bg_rect = [
            cell_x,
            cell_y,
            cell_x + cell_width,
            cell_y + cell_height - label_height,
        ]
        draw.rectangle(cell_bg_rect, fill="#ffffff", outline=border_color, width=border_width)

        # Center image within cell
        img_x = cell_x + cell_padding + border_width + (max_width - img.width) // 2
        img_y = cell_y + cell_padding + border_width + (max_height - img.height) // 2

        # Paste image (handle transparency)
        if img.mode == "RGBA":
            grid.paste(img, (img_x, img_y), img)
        else:
            grid.paste(img, (img_x, img_y))

        # Draw label centered below the cell
        label_y = cell_y + cell_height - label_height + 6

        # Get text bounding box for centering
        bbox = draw.textbbox((0, 0), label, font=font)
        text_width = bbox[2] - bbox[0]
        label_x = cell_x + (cell_width - text_width) // 2

        draw.text((label_x, label_y), label, fill=label_color, font=font)

    # Close source images to free memory
    for _, img in images:
        img.close()

    # Export as PNG
    output = io.BytesIO()
    grid.save(output, format="PNG", optimize=True)
    output.seek(0)

    return output.getvalue()


def _get_font(size: int = 13) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    Get a font for labels, trying system fonts first.

    Args:
        size: Font size in points

    Returns:
        PIL font object
    """
    # Try common system font locations
    font_candidates = [
        # macOS
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText.ttf",
        "/Library/Fonts/Arial.ttf",
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        # Windows
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ]

    for font_path in font_candidates:
        try:
            return ImageFont.truetype(font_path, size)
        except OSError:
            continue

    # Fallback to default bitmap font
    return ImageFont.load_default()


def generate_state_filename_suffix(states: tuple[str, ...]) -> str:
    """
    Generate filename suffix for state grid screenshot.

    Args:
        states: Tuple of states (excluding 'normal')

    Returns:
        Suffix like "_hover" or "_states"
    """
    if len(states) == 1:
        return f"_{states[0]}"
    else:
        return "_states"
