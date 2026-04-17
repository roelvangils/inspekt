"""
PDF Report Template Renderer.

Renders PDF accessibility reports from JSON data using Jinja2 templates.
This module provides the bridge between the data layer (JSON) and the
presentation layer (HTML).

Custom Jinja2 filters handle formatting of dates, file sizes, percentages,
and other derived values that don't need to be stored in the JSON.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from inspekt.services.pdf_report_data import PDFReportData


def get_template_dir() -> Path:
    """Get the path to the templates directory."""
    return Path(__file__).parent.parent / "templates"


def create_jinja_environment() -> Environment:
    """
    Create a Jinja2 environment with custom filters.

    Returns:
        Configured Jinja2 Environment
    """
    env = Environment(
        loader=FileSystemLoader(get_template_dir()),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Register custom filters
    env.filters["format_date"] = format_date_filter
    env.filters["format_file_size"] = format_file_size_filter
    env.filters["format_percent"] = format_percent_filter
    env.filters["truncate_text"] = truncate_text_filter
    env.filters["status_icon"] = status_icon_filter
    env.filters["severity_class"] = severity_class_filter

    return env


# =============================================================================
# Custom Jinja2 Filters
# =============================================================================


def format_date_filter(iso_date: str | None) -> str:
    """
    Convert ISO date to human-readable format.

    Args:
        iso_date: ISO format date string (e.g., "2025-03-25T18:41:31")

    Returns:
        Human-readable date (e.g., "March 25, 2025 at 6:41 PM")
    """
    if not iso_date:
        return "Unknown"

    try:
        # Handle various ISO formats
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))

        # Format: "March 25, 2025 at 6:41 PM"
        formatted = dt.strftime("%B %d, %Y at %I:%M %p")

        # Remove leading zeros from day and hour
        formatted = re.sub(r"(\w+) 0(\d),", r"\1 \2,", formatted)
        formatted = re.sub(r"at 0(\d):", r"at \1:", formatted)

        return formatted
    except (ValueError, TypeError):
        return iso_date or "Unknown"


def format_file_size_filter(size_bytes: int | None) -> str:
    """
    Convert bytes to human-readable file size.

    Args:
        size_bytes: File size in bytes

    Returns:
        Human-readable size (e.g., "1.5 MB")
    """
    if size_bytes is None or size_bytes < 0:
        return "Unknown"

    if size_bytes == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    size = float(size_bytes)

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.1f} {units[unit_index]}"


def format_percent_filter(value: float | None, decimals: int = 0) -> str:
    """
    Format a decimal value as a percentage.

    Args:
        value: Decimal value (0-1) or percentage (0-100)
        decimals: Number of decimal places

    Returns:
        Formatted percentage string
    """
    if value is None:
        return "N/A"

    # If value is between 0 and 1, treat as decimal
    if 0 <= value <= 1:
        value = value * 100

    if decimals == 0:
        return f"{int(value)}%"
    else:
        return f"{value:.{decimals}f}%"


def truncate_text_filter(text: str | None, length: int = 50, suffix: str = "…") -> str:
    """
    Truncate text to a maximum length.

    Args:
        text: Text to truncate
        length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated text
    """
    if not text:
        return ""

    if len(text) <= length:
        return text

    return text[:length - len(suffix)] + suffix


def status_icon_filter(status: str) -> str:
    """
    Convert status to Unicode icon.

    Args:
        status: Status string (pass, fail, warn, skip)

    Returns:
        Unicode icon character
    """
    icons = {
        "pass": "\u2713",  # ✓
        "fail": "\u2717",  # ✗
        "warn": "\u26A0",  # ⚠
        "skip": "\u2014",  # —
    }
    return icons.get(status.lower(), "\u2014")


def severity_class_filter(severity: str) -> str:
    """
    Convert severity to CSS class name.

    Args:
        severity: Severity string

    Returns:
        CSS class name
    """
    return f"severity-{severity.lower()}"


# =============================================================================
# Report Rendering Functions
# =============================================================================


def render_html_report(
    report_data: PDFReportData | dict[str, Any],
    template_name: str = "pdf_report.html",
) -> str:
    """
    Render an HTML report from report data.

    Args:
        report_data: PDFReportData instance or dict from JSON
        template_name: Name of the Jinja2 template file

    Returns:
        Rendered HTML string
    """
    env = create_jinja_environment()
    template = env.get_template(template_name)

    # Convert to dict if needed
    if isinstance(report_data, PDFReportData):
        data = report_data.to_dict()
    else:
        data = report_data

    # Flatten for template access
    # Template can access metadata.title, score.grade, etc.
    return template.render(**data)


def render_html_from_json(json_path: Path | str, resolve_assets: bool = True) -> str:
    """
    Render an HTML report from a JSON file.

    This is the key function that enables generating HTML reports
    from previously saved JSON data.

    Args:
        json_path: Path to the JSON report file
        resolve_assets: If True, resolve asset references to base64

    Returns:
        Rendered HTML string
    """
    json_path = Path(json_path)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Resolve external asset references if an asset manifest exists
    if resolve_assets and data.get("asset_manifest"):
        data = resolve_asset_references(data, json_path.parent)

    return render_html_report(data)


def render_html_from_json_string(json_str: str) -> str:
    """
    Render an HTML report from a JSON string.

    Args:
        json_str: JSON string containing report data

    Returns:
        Rendered HTML string
    """
    data = json.loads(json_str)
    return render_html_report(data)


# =============================================================================
# JSON Export Function
# =============================================================================


def export_json_report(
    report_data: PDFReportData,
    output_path: Path | str | None = None,
    indent: int = 2,
) -> str:
    """
    Export report data to JSON.

    Args:
        report_data: PDFReportData instance
        output_path: Optional path to save the JSON file
        indent: JSON indentation (default 2)

    Returns:
        JSON string
    """
    json_str = report_data.to_json(indent=indent)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_str, encoding="utf-8")

    return json_str


# =============================================================================
# Asset Resolution Functions (NEW in v2.0)
# =============================================================================


def resolve_asset_references(
    data: dict[str, Any],
    base_path: Path,
) -> dict[str, Any]:
    """
    Resolve external asset references to base64-encoded data.

    When loading a JSON report that has external assets (stored in a
    separate assets directory), this function reads those files and
    converts them to base64 so the HTML can be self-contained.

    Args:
        data: Report data dictionary
        base_path: Directory containing the JSON file

    Returns:
        Updated data dictionary with resolved assets
    """
    import base64
    import logging

    logger = logging.getLogger(__name__)

    manifest = data.get("asset_manifest")
    if not manifest:
        return data

    assets_dir = base_path / manifest.get("assets_directory", "")
    asset_map: dict[str, str] = {}

    # Build asset_id -> base64 mapping
    for asset in manifest.get("assets", []):
        asset_id = asset.get("asset_id")
        filename = asset.get("filename")

        if not asset_id or not filename:
            continue

        asset_path = assets_dir / filename
        if asset_path.exists():
            try:
                with open(asset_path, "rb") as f:
                    asset_map[asset_id] = base64.b64encode(f.read()).decode("ascii")
            except Exception as e:
                logger.warning(f"Failed to read asset {filename}: {e}")
        else:
            logger.warning(f"Asset file not found: {asset_path}")

    # Resolve asset references in the data
    data = _resolve_assets_in_dict(data, asset_map)

    return data


def _resolve_assets_in_dict(obj: Any, asset_map: dict[str, str]) -> Any:
    """
    Recursively resolve asset_id references in a dictionary.

    Looks for objects with:
    - asset_id field but no *_base64 field
    - Adds the corresponding *_base64 field from asset_map

    Args:
        obj: Object to process (dict, list, or primitive)
        asset_map: Mapping of asset_id -> base64 data

    Returns:
        Processed object with resolved assets
    """
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            result[key] = _resolve_assets_in_dict(value, asset_map)

        # Check if this dict has an asset_id that needs resolving
        asset_id = result.get("asset_id")
        if asset_id and asset_id in asset_map:
            # Determine which base64 field to populate
            if "image_base64" in obj:
                result["image_base64"] = asset_map[asset_id]
            elif "screenshot_base64" in obj:
                result["screenshot_base64"] = asset_map[asset_id]
            # Generic fallback - if neither exists, add image_base64
            elif not any(k.endswith("_base64") for k in obj if obj.get(k)):
                result["image_base64"] = asset_map[asset_id]

        return result

    elif isinstance(obj, list):
        return [_resolve_assets_in_dict(item, asset_map) for item in obj]

    else:
        return obj


def export_json_with_assets(
    report_data: PDFReportData,
    output_path: Path | str,
    image_size_threshold: int = 50 * 1024,  # 50KB
    indent: int = 2,
) -> tuple[Path, Path | None]:
    """
    Export report data to JSON with external assets for large images.

    Images larger than the threshold are saved to an external directory
    and referenced via asset_id. Smaller images remain base64-encoded.

    Args:
        report_data: PDFReportData instance
        output_path: Path for the JSON file
        image_size_threshold: Size threshold in bytes for external storage
        indent: JSON indentation

    Returns:
        Tuple of (json_path, assets_dir_path or None)
    """
    import base64
    import hashlib

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict for manipulation
    data = report_data.to_dict()

    # Track extracted assets
    assets = []
    assets_dir = output_path.parent / f"{output_path.stem}_assets"
    total_size = 0

    def extract_large_images(obj: Any, path_prefix: str = "") -> Any:
        """Extract large base64 images to external files."""
        nonlocal total_size

        if isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                new_path = f"{path_prefix}.{key}" if path_prefix else key

                # Check for base64 image fields
                if key.endswith("_base64") and isinstance(value, str) and len(value) > 100:
                    # Decode to check size
                    try:
                        decoded = base64.b64decode(value)
                        if len(decoded) > image_size_threshold:
                            # Save externally
                            asset_id = f"{path_prefix.replace('.', '_')}_{hashlib.md5(value[:100].encode()).hexdigest()[:8]}"
                            filename = f"{asset_id}.png"

                            # Create assets dir if needed
                            assets_dir.mkdir(parents=True, exist_ok=True)
                            asset_path = assets_dir / filename
                            asset_path.write_bytes(decoded)

                            # Track asset
                            assets.append({
                                "asset_id": asset_id,
                                "filename": filename,
                                "asset_type": _infer_asset_type(path_prefix),
                                "file_size": len(decoded),
                            })
                            total_size += len(decoded)

                            # Replace base64 with None, add asset_id
                            result[key] = None
                            result["asset_id"] = asset_id
                            continue
                    except Exception:
                        pass  # Keep as base64 if decode fails

                result[key] = extract_large_images(value, new_path)
            return result

        elif isinstance(obj, list):
            return [
                extract_large_images(item, f"{path_prefix}[{i}]")
                for i, item in enumerate(obj)
            ]

        else:
            return obj

    # Extract large images
    data = extract_large_images(data)

    # Add asset manifest if any assets were extracted
    if assets:
        data["asset_manifest"] = {
            "assets_directory": assets_dir.name,
            "total_size": total_size,
            "assets": assets,
        }

    # Write JSON
    json_str = json.dumps(data, indent=indent, default=str)
    output_path.write_text(json_str, encoding="utf-8")

    return output_path, assets_dir if assets else None


def _infer_asset_type(path: str) -> str:
    """Infer asset type from the JSON path."""
    path_lower = path.lower()
    if "cover" in path_lower:
        return "cover"
    elif "contrast" in path_lower:
        return "contrast"
    elif "screenshot" in path_lower:
        return "issue_screenshot"
    elif "thumbnail" in path_lower:
        return "thumbnail"
    elif "lightbox" in path_lower:
        return "lightbox"
    else:
        return "image"
