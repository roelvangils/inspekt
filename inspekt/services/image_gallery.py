"""
Image Gallery HTML Generator for Inspekt.

Generates a self-contained, accessible HTML gallery page with:
- Responsive grid of thumbnail cards
- Lightbox modal with keyboard navigation
- Image metadata display (filename, dimensions, alt text)
- Dark mode support (system preference + manual toggle)
- WCAG 2.1 AA compliant accessibility
"""

from __future__ import annotations

import base64
import html
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class GalleryImage:
    """Data for a single image in the gallery."""

    filename: str
    file_path: Path
    thumbnail_path: Path | None
    width: int
    height: int
    file_size: int  # bytes
    alt: str
    title: str
    original_url: str
    is_optimized: bool = False
    svg_content: str | None = None  # SVG source code (for code preview)
    # When set, the card's <img> uses this as src instead of the sibling
    # thumbnail file (e.g. a "data:image/webp;base64,…" URI for self-contained
    # galleries shipped as zips to a host machine).
    thumbnail_data_uri: str | None = None
    # When set, the lightbox's data-full-src points at this value instead of
    # the sibling filename — used to reference publicly-reachable originals
    # by absolute URL so they don't need bundling.
    full_src_override: str | None = None
    # Accessibility context (populated by the JS extractor). These feed the
    # per-card accessible-name line and the _compute_acc_hints heuristics.
    source_type: str = "img"  # "img" | "css-background"
    accessible_name: str = ""
    accessible_name_source: str = "alt attribute"
    is_linked: bool = False
    link_href: str = ""
    nearest_heading_text: str = ""


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return html.escape(text) if text else ""


def _format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


_PLACEHOLDER_NAMES = {
    "placeholder", "untitled", "image", "img", "photo", "picture",
    "banner", "graphic", "thumbnail", "icon",
}
_REDUNDANT_PREFIXES = ("image of", "picture of", "photo of", "graphic of", "image showing", "photo showing")
_CLICK_WORDS_RE = re.compile(r"\b(?:click|tap|press)\b", re.IGNORECASE)
_URL_RE = re.compile(r"https?://|\bwww\.", re.IGNORECASE)
_DIMENSIONS_RE = re.compile(r"\b\d+\s*[x×]\s*\d+\b|\b\d+\s*px\b", re.IGNORECASE)
_NUMERIC_ID_RE = re.compile(r"^(?:#?\d+|(?:item|asset)[-_]\d+)$", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<\w+[\s/>]")
_ENCODED_CHARS_RE = re.compile(r"&(?:[a-z]+|#\d+);|\n")
_COPYRIGHT_RE = re.compile(r"[©®™]|\(c\)", re.IGNORECASE)
_LOGO_RE = re.compile(r"\blogo\b", re.IGNORECASE)


def _compute_acc_hints(img: GalleryImage) -> list[str]:
    """
    Return human-readable accessibility hints for an image's accessible name.

    Each hint is a short HTML-safe fragment. Hints are ordered by structural
    issues first (missing alt, decorative in link, css-background) followed
    by name-quality issues (length, placeholders, HTML, encoding, etc.).
    Empty names only trigger structural hints — name-quality rules require
    non-empty content to avoid spamming decorative images.
    """
    hints: list[str] = []
    name = img.accessible_name or ""
    stripped = name.strip()
    src_type = img.source_type
    name_source = img.accessible_name_source

    # Structural — apply regardless of name emptiness.

    if name_source == "missing alt attribute" and src_type != "css-background":
        hints.append("Image has no <code>alt</code> attribute.")

    if img.is_linked and name_source == "empty alt (decorative)":
        hints.append("Decorative image inside a link — the link has no accessible name.")

    if src_type == "css-background":
        hints.append("CSS background image — cannot receive an accessible name via markup.")

    # Name-quality heuristics — require a non-empty trimmed name.
    if not stripped:
        return hints

    # H18 — irregular spacing (check original vs. trimmed, and internal doubles).
    if name != stripped or "  " in stripped:
        hints.append("Name has irregular spacing.")

    # H5 — very short.
    if len(stripped) < 3:
        hints.append("Name is very short.")

    # H6 — too long.
    if len(stripped) > 80:
        hints.append("Name should be under 80 characters.")

    # H7 — redundant "image of" / "photo of" / "picture of" prefix.
    lower = stripped.lower()
    if any(lower.startswith(prefix) for prefix in _REDUNDANT_PREFIXES):
        hints.append("Name starts with a redundant prefix (e.g. &ldquo;Image of&hellip;&rdquo;).")

    # H8 — generic placeholder.
    if lower in _PLACEHOLDER_NAMES:
        hints.append("Name is a generic placeholder.")

    # H11 — copyright / trademark symbols.
    if _COPYRIGHT_RE.search(stripped):
        hints.append("Name contains copyright or trademark symbols.")

    # H12 — raw HTML tags in the name.
    if _HTML_TAG_RE.search(stripped):
        hints.append("Name contains HTML tags.")

    # H13 — HTML-encoded characters or stray newlines (check raw, not stripped).
    if _ENCODED_CHARS_RE.search(name):
        hints.append("Name contains encoded characters or line breaks.")

    # H14 — all caps (ignore short abbreviations like FAQ/PDF/SVG — require 4+ letters).
    letters = [c for c in stripped if c.isalpha()]
    if len(letters) >= 4 and all(c.isupper() for c in letters):
        hints.append("Name is in all caps.")

    # H15 — linked logo.
    if img.is_linked and _LOGO_RE.search(stripped):
        hints.append("Logo inside a link — ensure the name describes where the link goes, not just the logo.")

    # H16 — URL in the accessible name.
    if _URL_RE.search(stripped):
        hints.append("Name contains a URL.")

    # H17 — numeric ID (pure digits, #123, item-45, asset_67).
    if _NUMERIC_ID_RE.match(stripped):
        hints.append("Name looks like a numeric ID.")

    # H19 — dimensions in the name.
    if _DIMENSIONS_RE.search(stripped):
        hints.append("Name contains image dimensions.")

    # H20 — interaction instructions baked into the name.
    if _CLICK_WORDS_RE.search(stripped):
        hints.append("Name contains interaction instructions.")

    return hints


def generate_gallery_html(
    images: list[GalleryImage],
    page_title: str,
    page_url: str,
    output_dir: Path,
    generated_at: str | None = None,
) -> str:
    """
    Generate accessible HTML gallery with lightbox.

    Args:
        images: List of GalleryImage objects
        page_title: Title of the source page
        page_url: URL of the source page
        output_dir: Directory where images are stored (for relative paths)
        generated_at: Timestamp string (default: current time)

    Returns:
        Complete HTML string for the gallery page
    """
    if generated_at is None:
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Collect unique file extensions for filter dropdown
    # Normalize jpg -> jpeg for consistency
    def normalize_ext(ext: str) -> str:
        return "jpeg" if ext == "jpg" else ext

    file_types: set[str] = set()
    any_bg = False
    for img in images:
        ext = Path(img.filename).suffix.lower().lstrip(".")
        if ext:
            file_types.add(normalize_ext(ext))
        if img.source_type == "css-background":
            any_bg = True
    any_hints = False  # set inside the card loop below when hints are emitted
    file_types_sorted = sorted(file_types)

    # Build file type options HTML
    file_type_options = ['<option value="">All types</option>']
    for ext in file_types_sorted:
        file_type_options.append(f'<option value="{ext}">{ext.upper()}</option>')
    file_type_options_html = "\n                        ".join(file_type_options)

    # Build image cards HTML
    cards_html = []
    for i, img in enumerate(images):
        # Use thumbnail if available, otherwise use full image
        # Thumbnails are in a 'thumbnails/' subdirectory
        if img.thumbnail_data_uri:
            thumb_src = img.thumbnail_data_uri
        elif img.thumbnail_path:
            thumb_src = f"thumbnails/{img.thumbnail_path.name}"
        else:
            thumb_src = img.full_src_override or img.filename
        full_src = img.full_src_override or img.filename

        # Get file extension for filtering (normalize jpg -> jpeg)
        file_ext = normalize_ext(Path(img.filename).suffix.lower().lstrip("."))

        # Format dimensions
        dimensions = f"{img.width}×{img.height}" if img.width and img.height else "Unknown"
        file_size_str = _format_file_size(img.file_size)

        # Base64 encode SVG content for code preview (avoids HTML escaping issues)
        svg_data_attr = ""
        if img.svg_content:
            svg_b64 = base64.b64encode(img.svg_content.encode("utf-8")).decode("ascii")
            svg_data_attr = f'\n                    data-svg-source="{svg_b64}"'

        # Build badge row — format is always present; source/link/hints conditional.
        badges = [f'<span class="gallery-badge badge-format">{_escape_html(file_ext.upper())}</span>']
        if img.source_type == "css-background":
            badges.append('<span class="gallery-badge badge-source" title="CSS background image">BG</span>')
        elif img.original_url.startswith("data:"):
            badges.append('<span class="gallery-badge badge-source" title="Originally a data URI">64</span>')
        if img.is_linked:
            badges.append(
                '<span class="gallery-badge badge-link" title="Wrapped in a link">↗</span>'
            )
        hints = _compute_acc_hints(img)
        if hints:
            any_hints = True
            badges.append(
                f'<span class="gallery-badge badge-hints" '
                f'aria-label="{len(hints)} accessibility hint{"s" if len(hints) != 1 else ""}" '
                f'title="{len(hints)} accessibility hint{"s" if len(hints) != 1 else ""}">'
                f'⚠ {len(hints)}</span>'
            )
        badges_html = "\n                    ".join(badges)

        # Accessible-name line. Empty name gets a warning pill so it's visible.
        if img.accessible_name:
            acc_name_display = img.accessible_name[:120] + "…" if len(img.accessible_name) > 120 else img.accessible_name
            acc_name_html = f'<span class="acc-name">{_escape_html(acc_name_display)}</span>'
        else:
            acc_name_html = '<span class="no-name">— no accessible name —</span>'
        name_source_html = f'<span class="name-source">{_escape_html(img.accessible_name_source)}</span>'

        # Hints encoded for the lightbox as JSON (lightbox JS parses and renders).
        import json as _json_mod
        hints_json = _json_mod.dumps(hints) if hints else "[]"

        cards_html.append(f"""
        <article class="gallery-card" data-index="{i}" data-ext="{file_ext}" data-width="{img.width}" data-height="{img.height}" data-source-type="{_escape_html(img.source_type)}" data-has-hints="{'1' if hints else '0'}">
            <button type="button" class="gallery-thumbnail"
                    aria-label="View {_escape_html(img.filename)} in lightbox"
                    data-full-src="{_escape_html(full_src)}"
                    data-alt="{_escape_html(img.alt)}"
                    data-title="{_escape_html(img.title)}"
                    data-width="{img.width}"
                    data-height="{img.height}"
                    data-size="{file_size_str}"
                    data-size-bytes="{img.file_size}"
                    data-url="{_escape_html(img.original_url)}"
                    data-acc-name="{_escape_html(img.accessible_name)}"
                    data-acc-name-source="{_escape_html(img.accessible_name_source)}"
                    data-hints="{_escape_html(hints_json)}"{svg_data_attr}>
                <div class="gallery-badges">
                    {badges_html}
                </div>
                <img src="{_escape_html(thumb_src)}"
                     alt="{_escape_html(img.alt) or 'Image ' + str(i + 1)}"
                     loading="lazy"
                     decoding="async">
            </button>
            <div class="gallery-card-info">
                <span class="filename" title="{_escape_html(img.filename)}">{_escape_html(img.filename)}</span>
                <div class="meta">
                    <span class="dimensions">{dimensions}</span>
                    <span class="size">{file_size_str}</span>
                </div>
                <div class="accessible-name" title="{_escape_html(img.accessible_name) or 'no accessible name'}">
                    {acc_name_html}
                    {name_source_html}
                </div>
            </div>
        </article>
        """)

    cards_joined = "\n".join(cards_html)

    # Calculate statistics
    total_size = sum(img.file_size for img in images)
    total_size_str = _format_file_size(total_size)

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Image Gallery - {_escape_html(page_title)}</title>
    <style>
        /* ═══════════════════════════════════════════════════════════════
           CSS Custom Properties (Design Tokens)
           ═══════════════════════════════════════════════════════════════ */
        :root {{
            color-scheme: light dark;

            /* Light mode colors */
            --bg-primary: #ffffff;
            --bg-secondary: #f6f8fa;
            --bg-card: #ffffff;
            --text-primary: #1f2328;
            --text-secondary: #656d76;
            --text-muted: #8b949e;
            --border-color: #d0d7de;
            --border-subtle: #e8ecf0;
            --accent: #0969da;
            --accent-hover: #0550ae;
            --shadow-sm: 0 1px 3px rgba(0,0,0,0.08);
            --shadow-md: 0 4px 12px rgba(0,0,0,0.1);
            --shadow-lg: 0 8px 24px rgba(0,0,0,0.15);

            /* Lightbox */
            --lightbox-bg: rgba(0, 0, 0, 0.92);
            --lightbox-text: #ffffff;
        }}

        /* Dark mode */
        [data-theme="dark"] {{
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --bg-card: #21262d;
            --text-primary: #e6edf3;
            --text-secondary: #8b949e;
            --text-muted: #6e7681;
            --border-color: #30363d;
            --border-subtle: #21262d;
            --accent: #58a6ff;
            --accent-hover: #79c0ff;
            --shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
            --shadow-md: 0 4px 12px rgba(0,0,0,0.4);
            --shadow-lg: 0 8px 24px rgba(0,0,0,0.5);
            --lightbox-bg: rgba(0, 0, 0, 0.95);
        }}

        /* System preference fallback */
        @media (prefers-color-scheme: dark) {{
            :root:not([data-theme="light"]) {{
                --bg-primary: #0d1117;
                --bg-secondary: #161b22;
                --bg-card: #21262d;
                --text-primary: #e6edf3;
                --text-secondary: #8b949e;
                --text-muted: #6e7681;
                --border-color: #30363d;
                --border-subtle: #21262d;
                --accent: #58a6ff;
                --accent-hover: #79c0ff;
                --shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
                --shadow-md: 0 4px 12px rgba(0,0,0,0.4);
                --shadow-lg: 0 8px 24px rgba(0,0,0,0.5);
                --lightbox-bg: rgba(0, 0, 0, 0.95);
            }}
        }}

        /* ═══════════════════════════════════════════════════════════════
           Base Styles
           ═══════════════════════════════════════════════════════════════ */
        *, *::before, *::after {{
            box-sizing: border-box;
        }}

        body {{
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, sans-serif;
            font-size: 14px;
            line-height: 1.5;
            background: var(--bg-primary);
            color: var(--text-primary);
        }}

        /* Skip link for accessibility */
        .skip-link {{
            position: absolute;
            top: -100px;
            left: 16px;
            background: var(--accent);
            color: white;
            padding: 8px 16px;
            border-radius: 4px;
            text-decoration: none;
            font-weight: 500;
            z-index: 10000;
            transition: top 0.2s;
        }}

        .skip-link:focus {{
            top: 16px;
        }}

        /* ═══════════════════════════════════════════════════════════════
           Header
           ═══════════════════════════════════════════════════════════════ */
        header {{
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            padding: 16px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
        }}

        .header-content {{
            flex: 1;
            min-width: 200px;
        }}

        header h1 {{
            margin: 0 0 4px 0;
            font-size: 1.25rem;
            font-weight: 600;
            color: var(--text-primary);
        }}

        .source-link {{
            color: var(--accent);
            text-decoration: none;
            font-size: 0.875rem;
            display: inline-block;
            max-width: 400px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}

        .source-link:hover {{
            color: var(--accent-hover);
            text-decoration: underline;
        }}

        .header-stats {{
            display: flex;
            gap: 16px;
            font-size: 0.875rem;
            color: var(--text-secondary);
        }}

        .stat {{
            display: flex;
            align-items: center;
            gap: 4px;
        }}

        .stat-value {{
            font-weight: 600;
            color: var(--text-primary);
        }}

        .theme-toggle {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 8px 12px;
            cursor: pointer;
            font-size: 1rem;
            color: var(--text-primary);
            transition: background 0.2s, border-color 0.2s;
        }}

        .theme-toggle:hover {{
            background: var(--bg-primary);
            border-color: var(--accent);
        }}

        .theme-toggle:focus-visible {{
            outline: 2px solid var(--accent);
            outline-offset: 2px;
        }}

        /* ═══════════════════════════════════════════════════════════════
           Filter Bar
           ═══════════════════════════════════════════════════════════════ */
        .filter-bar {{
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            padding: 12px 24px;
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
            align-items: center;
        }}

        .filter-group {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .filter-group label {{
            font-size: 0.875rem;
            font-weight: 500;
            color: var(--text-secondary);
            white-space: nowrap;
        }}

        .filter-group select,
        .filter-group input {{
            padding: 6px 10px;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            background: var(--bg-card);
            color: var(--text-primary);
            font-size: 0.875rem;
            min-width: 100px;
        }}

        .filter-group input[type="number"] {{
            width: 80px;
        }}

        .filter-group input[type="color"] {{
            width: 40px;
            height: 32px;
            padding: 2px;
            cursor: pointer;
            border-radius: 6px;
        }}

        .filter-group-checkbox {{
            margin-left: 8px;
        }}

        .filter-group-checkbox label {{
            display: flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
            font-size: 0.875rem;
            color: var(--text-secondary);
            white-space: nowrap;
        }}

        .filter-group-checkbox input[type="checkbox"] {{
            width: 16px;
            height: 16px;
            min-width: 16px;
            margin: 0;
            cursor: pointer;
            accent-color: var(--accent);
        }}

        .filter-group select:focus,
        .filter-group input:focus {{
            outline: 2px solid var(--accent);
            outline-offset: 1px;
            border-color: var(--accent);
        }}

        .filter-results {{
            margin-left: auto;
            font-size: 0.875rem;
            color: var(--text-muted);
        }}

        .filter-results strong {{
            color: var(--text-primary);
        }}

        .gallery-card.hidden {{
            display: none;
        }}

        /* ═══════════════════════════════════════════════════════════════
           Gallery Grid
           ═══════════════════════════════════════════════════════════════ */
        main {{
            padding: 24px;
            max-width: 1600px;
            margin: 0 auto;
        }}

        .gallery-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 20px;
        }}

        .gallery-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: var(--shadow-sm);
            transition: box-shadow 0.2s, transform 0.2s;
        }}

        .gallery-card:hover {{
            box-shadow: var(--shadow-md);
            transform: translateY(-2px);
        }}

        .gallery-thumbnail {{
            display: block;
            width: 100%;
            aspect-ratio: 4/3;
            padding: 0;
            border: none;
            background: var(--bg-secondary);
            cursor: pointer;
            overflow: hidden;
        }}

        .gallery-thumbnail:focus-visible {{
            outline: 3px solid var(--accent);
            outline-offset: -3px;
        }}

        .gallery-thumbnail img {{
            width: 100%;
            height: 100%;
            object-fit: contain;
            transition: transform 0.3s;
        }}

        .gallery-thumbnail:hover img {{
            transform: scale(1.05);
        }}

        /* SVG images get padding to prevent edge-to-edge display */
        .gallery-card[data-ext="svg"] .gallery-thumbnail img {{
            padding: 12px;
            box-sizing: border-box;
        }}

        .gallery-card-info {{
            padding: 12px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}

        .gallery-card-info .filename {{
            font-weight: 500;
            font-size: 0.875rem;
            color: var(--text-primary);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}

        .gallery-card-info .meta {{
            display: flex;
            gap: 12px;
            font-size: 0.75rem;
            color: var(--text-muted);
        }}

        .gallery-card-info .alt-text {{
            font-size: 0.75rem;
            color: var(--text-secondary);
            font-style: italic;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}

        /* Accessible-name line — replaces the plain alt display so the user
           sees both the computed name and where it came from. */
        .gallery-card-info .accessible-name {{
            font-size: 0.75rem;
            color: var(--text-secondary);
            line-height: 1.35;
            overflow: hidden;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
        }}
        .gallery-card-info .accessible-name .acc-name {{
            font-style: italic;
        }}
        .gallery-card-info .accessible-name .no-name {{
            color: #b25400;
            font-style: normal;
            font-weight: 500;
        }}
        [data-theme="dark"] .gallery-card-info .accessible-name .no-name {{
            color: #f0883e;
        }}
        .gallery-card-info .name-source {{
            display: block;
            font-size: 0.65rem;
            color: var(--text-muted);
            font-variant-numeric: tabular-nums;
        }}

        /* Image-type badges (format, source, link, hints). Copied from
           inspekt/static/gallery/gallery.css so the template stays
           self-contained for host-side downloads. */
        .gallery-badges {{
            position: absolute;
            top: 6px;
            left: 6px;
            display: flex;
            gap: 4px;
            z-index: 5;
            pointer-events: none;
            flex-wrap: wrap;
            max-width: calc(100% - 12px);
        }}
        .gallery-badge {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 2px 5px;
            font-size: 0.625rem;
            font-weight: 600;
            font-family: ui-monospace, 'SF Mono', Monaco, monospace;
            text-transform: uppercase;
            letter-spacing: 0.02em;
            border-radius: 4px;
            background: rgba(0, 0, 0, 0.6);
            color: rgba(255, 255, 255, 0.85);
            backdrop-filter: blur(4px);
            -webkit-backdrop-filter: blur(4px);
            line-height: 1;
        }}
        .gallery-badge.badge-source {{ background: rgba(100, 70, 150, 0.75); }}
        .gallery-badge.badge-format {{ background: rgba(0, 0, 0, 0.55); }}
        .gallery-badge.badge-link   {{ background: rgba(9, 105, 218, 0.75); }}
        .gallery-badge.badge-hints  {{ background: rgba(178, 84, 0, 0.85); color: #fff; }}

        .gallery-thumbnail:hover .gallery-badge {{ background: rgba(0, 0, 0, 0.8); }}
        .gallery-thumbnail:hover .gallery-badge.badge-source {{ background: rgba(100, 70, 150, 0.9); }}
        .gallery-thumbnail:hover .gallery-badge.badge-link {{ background: rgba(9, 105, 218, 0.9); }}
        .gallery-thumbnail:hover .gallery-badge.badge-hints {{ background: rgba(178, 84, 0, 1); }}

        [data-theme="dark"] .gallery-badge {{
            background: rgba(255, 255, 255, 0.15);
            color: rgba(255, 255, 255, 0.9);
        }}
        [data-theme="dark"] .gallery-badge.badge-source {{ background: rgba(150, 120, 200, 0.4); }}
        [data-theme="dark"] .gallery-badge.badge-link {{ background: rgba(88, 166, 255, 0.4); }}
        [data-theme="dark"] .gallery-badge.badge-hints {{ background: rgba(240, 136, 62, 0.5); color: #fff; }}
        [data-theme="dark"] .gallery-thumbnail:hover .gallery-badge {{ background: rgba(255, 255, 255, 0.25); }}
        [data-theme="dark"] .gallery-thumbnail:hover .gallery-badge.badge-source {{ background: rgba(150, 120, 200, 0.6); }}
        [data-theme="dark"] .gallery-thumbnail:hover .gallery-badge.badge-link {{ background: rgba(88, 166, 255, 0.6); }}
        [data-theme="dark"] .gallery-thumbnail:hover .gallery-badge.badge-hints {{ background: rgba(240, 136, 62, 0.75); }}

        /* Lightbox hints panel */
        .lightbox-hints {{
            padding: 8px 12px;
            background: rgba(178, 84, 0, 0.1);
            border-left: 3px solid #b25400;
            margin: 8px 0;
            font-size: 0.85rem;
            line-height: 1.4;
            max-height: 180px;
            overflow-y: auto;
        }}
        .lightbox-hints:empty {{ display: none; }}
        .lightbox-hints ul {{ margin: 0; padding-left: 18px; }}
        .lightbox-hints li {{ margin: 2px 0; }}
        [data-theme="dark"] .lightbox-hints {{
            background: rgba(240, 136, 62, 0.1);
            border-left-color: #f0883e;
        }}

        /* ═══════════════════════════════════════════════════════════════
           Lightbox Modal
           ═══════════════════════════════════════════════════════════════ */
        .lightbox {{
            display: none;
            position: fixed;
            inset: 0;
            background: var(--lightbox-solid-bg, #000);
            z-index: 9999;
            flex-direction: column;
            overflow: hidden;
        }}

        .lightbox.active {{
            display: flex;
        }}

        /* SVG mode: smooth background color transitions */
        .lightbox.svg-mode {{
            transition: background-color 0.3s ease;
        }}

        /* Hide backdrop blur for SVG images, show solid background instead */
        .lightbox.svg-mode .lightbox-backdrop {{
            display: none;
        }}

        /* Blurred backdrop images (two layers for crossfade) */
        .lightbox-backdrop {{
            position: absolute;
            inset: -10%;
            width: 120%;
            height: 120%;
            object-fit: cover;
            filter: blur(40px) saturate(0.4) brightness(0.8);
            z-index: 0;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.8s ease;
        }}

        .lightbox-backdrop.active {{
            opacity: 1;
        }}

        .lightbox-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 16px;
            background: rgba(0, 0, 0, 0.5);
            color: var(--lightbox-text);
            position: relative;
            z-index: 2;
        }}

        .lightbox-counter {{
            font-size: 0.875rem;
            font-weight: 500;
        }}

        .lightbox-close {{
            background: transparent;
            border: none;
            color: var(--lightbox-text);
            font-size: 1.5rem;
            cursor: pointer;
            padding: 8px;
            border-radius: 8px;
            line-height: 1;
            transition: background 0.2s;
        }}

        .lightbox-close:hover {{
            background: rgba(255, 255, 255, 0.1);
        }}

        .lightbox-close:focus-visible {{
            outline: 2px solid white;
            outline-offset: 2px;
        }}

        .lightbox-content {{
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            overflow: hidden;
            z-index: 1;
        }}

        .lightbox-image-container {{
            max-width: 90vw;
            max-height: calc(90vh - 120px);
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .lightbox-image {{
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            filter: drop-shadow(0 8px 32px rgba(0, 0, 0, 0.5));
        }}

        /* SVGs may lack intrinsic dimensions - ensure they're visible */
        .lightbox.svg-mode .lightbox-image {{
            min-width: 100px;
            min-height: 100px;
            filter: none;  /* No drop shadow for SVGs */
            transition: width 0.3s ease, height 0.3s ease, filter 0.3s ease;
            object-fit: contain;
        }}

        .lightbox-nav {{
            position: absolute;
            top: 50%;
            transform: translateY(-50%);
            background: rgba(255, 255, 255, 0.15);
            border: none;
            color: var(--lightbox-text);
            font-size: 2rem;
            padding: 16px 20px;
            cursor: pointer;
            border-radius: 8px;
            transition: background 0.2s;
        }}

        .lightbox-nav:hover {{
            background: rgba(255, 255, 255, 0.25);
        }}

        .lightbox-nav:focus-visible {{
            outline: 2px solid white;
            outline-offset: 2px;
        }}

        .lightbox-nav:disabled {{
            opacity: 0.3;
            cursor: not-allowed;
        }}

        .lightbox-prev {{
            left: 16px;
        }}

        .lightbox-next {{
            right: 16px;
        }}

        .lightbox-footer {{
            padding: 12px 16px;
            background: rgba(0, 0, 0, 0.5);
            color: var(--lightbox-text);
            position: relative;
            z-index: 2;
        }}

        .lightbox-info {{
            text-align: center;
        }}

        .lightbox-filename {{
            font-weight: 500;
            margin-bottom: 4px;
        }}

        .lightbox-meta {{
            font-size: 0.875rem;
            opacity: 0.8;
        }}

        .lightbox-alt {{
            font-size: 0.875rem;
            font-style: italic;
            margin-top: 8px;
            opacity: 0.9;
        }}

        /* ═══════════════════════════════════════════════════════════════
           SVG Preview Options
           ═══════════════════════════════════════════════════════════════ */
        .svg-options {{
            display: none;
            padding: 12px 16px;
            background: rgba(0, 0, 0, 0.6);
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            position: relative;
            z-index: 2;
        }}

        .lightbox.svg-mode .svg-options {{
            display: block;
        }}

        .svg-options-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 24px;
            justify-content: center;
            align-items: center;
        }}

        .svg-option-group {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .svg-option-label {{
            font-size: 0.75rem;
            color: rgba(255, 255, 255, 0.7);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 500;
        }}

        .svg-toggle-group {{
            display: flex;
            border-radius: 6px;
            overflow: hidden;
            background: rgba(255, 255, 255, 0.1);
        }}

        .svg-toggle {{
            padding: 6px 12px;
            font-size: 0.8125rem;
            font-weight: 500;
            background: transparent;
            border: none;
            color: rgba(255, 255, 255, 0.7);
            cursor: pointer;
            transition: background 0.15s, color 0.15s;
            white-space: nowrap;
        }}

        .svg-toggle:hover {{
            background: rgba(255, 255, 255, 0.15);
            color: rgba(255, 255, 255, 0.9);
        }}

        .svg-toggle:focus-visible {{
            outline: 2px solid white;
            outline-offset: -2px;
            z-index: 1;
            position: relative;
        }}

        .svg-toggle[aria-pressed="true"] {{
            background: rgba(255, 255, 255, 0.25);
            color: white;
        }}

        .svg-toggle + .svg-toggle {{
            border-left: 1px solid rgba(255, 255, 255, 0.1);
        }}

        /* Color swatch indicators */
        .svg-toggle .color-swatch {{
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 2px;
            vertical-align: middle;
            margin-right: 4px;
            border: 1px solid rgba(255, 255, 255, 0.3);
        }}

        .svg-toggle .color-swatch.white {{
            background: white;
        }}

        .svg-toggle .color-swatch.black {{
            background: black;
        }}

        /* SVG preview size options - use explicit dimensions for scaling up/down */
        .lightbox.svg-mode .lightbox-image.svg-size-auto {{
            width: 75vw;
            height: calc(75vh - 150px);
            max-width: 75vw;
            max-height: calc(75vh - 150px);
        }}

        .lightbox.svg-mode .lightbox-image.svg-size-50 {{
            width: 50vw;
            height: calc(50vh - 100px);
            max-width: 50vw;
            max-height: calc(50vh - 100px);
        }}

        .lightbox.svg-mode .lightbox-image.svg-size-25 {{
            width: 25vw;
            height: calc(25vh - 50px);
            max-width: 25vw;
            max-height: calc(25vh - 50px);
        }}

        .lightbox.svg-mode .lightbox-image.svg-size-original {{
            /* Original: use natural size, no scaling */
            width: auto;
            height: auto;
            max-width: 90vw;
            max-height: calc(90vh - 150px);
        }}

        /* SVG color filters - override the filter:none with color transforms */
        .lightbox.svg-mode .lightbox-image.svg-color-white {{
            filter: brightness(0) invert(1);
        }}

        .lightbox.svg-mode .lightbox-image.svg-color-black {{
            filter: brightness(0);
        }}

        /* Responsive adjustments for SVG options */
        @media (max-width: 600px) {{
            .svg-options-row {{
                gap: 12px;
            }}

            .svg-option-group {{
                flex-wrap: wrap;
                justify-content: center;
            }}

            .svg-toggle {{
                padding: 5px 10px;
                font-size: 0.75rem;
            }}
        }}

        /* ═══════════════════════════════════════════════════════════════
           SVG Code Preview
           ═══════════════════════════════════════════════════════════════ */
        .lightbox-code-container[hidden] {{
            display: none !important;
        }}

        .lightbox-code-container {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            max-width: 90vw;
            max-height: calc(90vh - 180px);
            width: 800px;
            display: flex;
            flex-direction: column;
            z-index: 10;
        }}

        .code-copy-btn {{
            position: absolute;
            top: 8px;
            right: 8px;
            background: rgba(255, 255, 255, 0.15);
            border: none;
            color: rgba(255, 255, 255, 0.8);
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 0.8125rem;
            font-weight: 500;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
            transition: background 0.15s, color 0.15s;
            z-index: 10;
        }}

        .code-copy-btn:hover {{
            background: rgba(255, 255, 255, 0.25);
            color: white;
        }}

        .code-copy-btn:focus-visible {{
            outline: 2px solid white;
            outline-offset: 2px;
        }}

        .code-copy-btn.copied {{
            background: rgba(34, 197, 94, 0.3);
            color: #4ade80;
        }}

        .lightbox-code {{
            margin: 0;
            padding: 16px;
            padding-top: 48px;
            background: rgba(0, 0, 0, 0.75) !important;
            border-radius: 8px;
            overflow: auto;
            max-height: calc(90vh - 180px);
            font-size: 0.8125rem;
            line-height: 1.6;
        }}

        /* Override Prism theme backgrounds for transparency */
        .lightbox-code,
        .lightbox-code code,
        .lightbox-code code[class*="language-"],
        .lightbox-code pre[class*="language-"] {{
            background: transparent !important;
        }}

        .lightbox-code-container {{
            background: rgba(0, 0, 0, 0.75);
            border-radius: 8px;
        }}

        /* Override Prism theme for dark lightbox */
        .lightbox-code code {{
            font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', 'Source Code Pro', monospace !important;
            font-size: 0.8125rem !important;
            white-space: pre-wrap !important;
            word-wrap: break-word !important;
            overflow-wrap: break-word !important;
        }}

        /* Dim size/colour/bg options when in code preview mode */
        .lightbox.svg-code-mode .svg-option-group:not(:first-child) {{
            opacity: 0.4;
            pointer-events: none;
        }}

        /* ═══════════════════════════════════════════════════════════════
           Footer
           ═══════════════════════════════════════════════════════════════ */
        footer {{
            text-align: center;
            padding: 24px;
            font-size: 0.75rem;
            color: var(--text-muted);
            border-top: 1px solid var(--border-subtle);
            margin-top: 24px;
        }}

        footer a {{
            color: var(--accent);
            text-decoration: none;
        }}

        footer a:hover {{
            text-decoration: underline;
        }}

        /* ═══════════════════════════════════════════════════════════════
           Responsive
           ═══════════════════════════════════════════════════════════════ */
        @media (max-width: 768px) {{
            header {{
                padding: 12px 16px;
            }}

            main {{
                padding: 16px;
            }}

            .gallery-grid {{
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: 12px;
            }}

            .header-stats {{
                flex-wrap: wrap;
                gap: 8px;
            }}

            .lightbox-nav {{
                padding: 12px 16px;
                font-size: 1.5rem;
            }}
        }}

        /* ═══════════════════════════════════════════════════════════════
           Print Styles
           ═══════════════════════════════════════════════════════════════ */
        @media print {{
            .theme-toggle,
            .lightbox {{
                display: none !important;
            }}

            body {{
                background: white;
                color: black;
            }}

            .gallery-grid {{
                grid-template-columns: repeat(4, 1fr);
            }}
        }}
    </style>
    <!-- Prism.js for SVG syntax highlighting -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism-tomorrow.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-markup.min.js"></script>
</head>
<body>
    <a href="#gallery" class="skip-link">Skip to gallery</a>

    <header>
        <div class="header-content">
            <h1>Image Gallery</h1>
            <a href="{_escape_html(page_url)}" class="source-link" target="_blank" rel="noopener">
                {_escape_html(page_title or page_url)}
            </a>
        </div>
        <div class="header-stats">
            <span class="stat">
                <span class="stat-value">{len(images)}</span> images
            </span>
            <span class="stat">
                <span class="stat-value">{total_size_str}</span> total
            </span>
        </div>
        <button type="button" class="theme-toggle" aria-label="Toggle dark mode">
            <span class="theme-icon">🌓</span>
        </button>
    </header>

    <div class="filter-bar" role="search" aria-label="Filter images">
        <div class="filter-group">
            <label for="filter-type">Type</label>
            <select id="filter-type">
                {file_type_options_html}
            </select>
        </div>
        {'''<div class="filter-group">
            <label for="filter-source">Source</label>
            <select id="filter-source">
                <option value="">All sources</option>
                <option value="img">&lt;img&gt; elements</option>
                <option value="css-background">CSS backgrounds</option>
            </select>
        </div>''' if any_bg else ''}
        <div class="filter-group">
            <label for="filter-min-width">Min. width</label>
            <input type="number" id="filter-min-width" min="0" placeholder="px">
        </div>
        <div class="filter-group">
            <label for="filter-min-height">Min. height</label>
            <input type="number" id="filter-min-height" min="0" placeholder="px">
        </div>
        <div class="filter-group">
            <label for="filter-bg-color">Background</label>
            <input type="color" id="filter-bg-color" value="#e5e5e5" title="Background color for transparent images">
        </div>
        <div class="filter-group filter-group-checkbox">
            <label for="filter-merge-duplicates">
                <input type="checkbox" id="filter-merge-duplicates">
                Merge identical images
            </label>
        </div>
        {'''<div class="filter-group filter-group-checkbox">
            <label for="filter-only-issues">
                <input type="checkbox" id="filter-only-issues">
                Only with a11y issues
            </label>
        </div>''' if any_hints else ''}
        <div class="filter-results" aria-live="polite">
            Showing <strong id="visible-count">{len(images)}</strong> of {len(images)} images
        </div>
    </div>

    <main id="gallery" tabindex="-1">
        <div class="gallery-grid" role="list" aria-label="Image gallery">
            {cards_joined}
        </div>
    </main>

    <!-- Lightbox Modal -->
    <div class="lightbox" role="dialog" aria-modal="true" aria-label="Image viewer">
        <img class="lightbox-backdrop" id="backdrop-a" src="" alt="" aria-hidden="true">
        <img class="lightbox-backdrop" id="backdrop-b" src="" alt="" aria-hidden="true">
        <div class="lightbox-header">
            <span class="lightbox-counter" aria-live="polite">1 / {len(images)}</span>
            <button type="button" class="lightbox-close" aria-label="Close lightbox">×</button>
        </div>
        <div class="lightbox-content">
            <button type="button" class="lightbox-nav lightbox-prev" aria-label="Previous image">‹</button>
            <div class="lightbox-image-container">
                <img class="lightbox-image" src="" alt="">
            </div>
            <div class="lightbox-code-container" hidden>
                <button type="button" class="code-copy-btn" aria-label="Copy SVG code to clipboard">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"/>
                        <path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"/>
                    </svg>
                    Copy
                </button>
                <pre class="lightbox-code"><code class="language-markup"></code></pre>
            </div>
            <button type="button" class="lightbox-nav lightbox-next" aria-label="Next image">›</button>
        </div>
        <div class="svg-options" role="toolbar" aria-label="SVG preview options">
            <div class="svg-options-row">
                <div class="svg-option-group" role="group" aria-labelledby="svg-preview-label">
                    <span class="svg-option-label" id="svg-preview-label">Preview</span>
                    <div class="svg-toggle-group">
                        <button type="button" class="svg-toggle" data-option="preview" data-value="image" aria-pressed="true">Image</button>
                        <button type="button" class="svg-toggle" data-option="preview" data-value="code" aria-pressed="false">Code</button>
                    </div>
                </div>
                <div class="svg-option-group" role="group" aria-labelledby="svg-size-label">
                    <span class="svg-option-label" id="svg-size-label">Size</span>
                    <div class="svg-toggle-group">
                        <button type="button" class="svg-toggle" data-option="size" data-value="auto" aria-pressed="true">Auto</button>
                        <button type="button" class="svg-toggle" data-option="size" data-value="50" aria-pressed="false">50%</button>
                        <button type="button" class="svg-toggle" data-option="size" data-value="25" aria-pressed="false">25%</button>
                        <button type="button" class="svg-toggle" data-option="size" data-value="original" aria-pressed="false">Original</button>
                    </div>
                </div>
                <div class="svg-option-group" role="group" aria-labelledby="svg-color-label">
                    <span class="svg-option-label" id="svg-color-label">Colour</span>
                    <div class="svg-toggle-group">
                        <button type="button" class="svg-toggle" data-option="color" data-value="original" aria-pressed="true">Original</button>
                        <button type="button" class="svg-toggle" data-option="color" data-value="white" aria-pressed="false"><span class="color-swatch white"></span>White</button>
                        <button type="button" class="svg-toggle" data-option="color" data-value="black" aria-pressed="false"><span class="color-swatch black"></span>Black</button>
                    </div>
                </div>
                <div class="svg-option-group" role="group" aria-labelledby="svg-bg-label">
                    <span class="svg-option-label" id="svg-bg-label">Background</span>
                    <div class="svg-toggle-group">
                        <button type="button" class="svg-toggle" data-option="bg" data-value="current" aria-pressed="true">Current</button>
                        <button type="button" class="svg-toggle" data-option="bg" data-value="white" aria-pressed="false"><span class="color-swatch white"></span>White</button>
                        <button type="button" class="svg-toggle" data-option="bg" data-value="black" aria-pressed="false"><span class="color-swatch black"></span>Black</button>
                    </div>
                </div>
            </div>
        </div>
        <div class="lightbox-footer">
            <div class="lightbox-info">
                <div class="lightbox-filename"></div>
                <div class="lightbox-meta"></div>
                <div class="lightbox-alt"></div>
                <div class="lightbox-acc-name"></div>
                <div class="lightbox-hints" aria-live="polite"></div>
            </div>
        </div>
    </div>

    <footer>
        Generated by <a href="https://github.com/roelvangils/inspekt" target="_blank" rel="noopener">Inspekt</a>
        on {_escape_html(generated_at)}
    </footer>

    <script>
        (function() {{
            // Theme toggle
            const html = document.documentElement;
            const themeToggle = document.querySelector('.theme-toggle');

            function getPreferredTheme() {{
                const stored = localStorage.getItem('inspekt-gallery-theme');
                if (stored) return stored;
                return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
            }}

            function setTheme(theme) {{
                html.setAttribute('data-theme', theme);
                localStorage.setItem('inspekt-gallery-theme', theme);
            }}

            // Initialize theme
            setTheme(getPreferredTheme());

            themeToggle.addEventListener('click', function() {{
                const current = html.getAttribute('data-theme');
                setTheme(current === 'dark' ? 'light' : 'dark');
            }});

            // Filter functionality
            const filterType = document.getElementById('filter-type');
            const filterSource = document.getElementById('filter-source');          // may be absent
            const filterMinWidth = document.getElementById('filter-min-width');
            const filterMinHeight = document.getElementById('filter-min-height');
            const filterBgColor = document.getElementById('filter-bg-color');
            const filterMergeDuplicates = document.getElementById('filter-merge-duplicates');
            const filterOnlyIssues = document.getElementById('filter-only-issues');  // may be absent
            const visibleCount = document.getElementById('visible-count');
            const cards = document.querySelectorAll('.gallery-card');
            const thumbnails = document.querySelectorAll('.gallery-thumbnail');

            // Background color for transparent images
            function applyBgColor(color) {{
                thumbnails.forEach(function(thumb) {{
                    thumb.style.backgroundColor = color;
                }});
                localStorage.setItem('inspekt-gallery-bg-color', color);
            }}

            // Initialize background color from storage or default
            const storedBgColor = localStorage.getItem('inspekt-gallery-bg-color');
            if (storedBgColor) {{
                filterBgColor.value = storedBgColor;
                applyBgColor(storedBgColor);
            }} else {{
                applyBgColor(filterBgColor.value);
            }}

            filterBgColor.addEventListener('input', function() {{
                applyBgColor(this.value);
            }});

            function applyFilters() {{
                const typeFilter = filterType.value.toLowerCase();
                const sourceFilter = filterSource ? filterSource.value : '';
                const minWidth = parseInt(filterMinWidth.value) || 0;
                const minHeight = parseInt(filterMinHeight.value) || 0;
                const mergeDuplicates = filterMergeDuplicates.checked;
                const onlyIssues = filterOnlyIssues ? filterOnlyIssues.checked : false;

                // First pass: apply basic filters (type, source, dimensions, hints)
                const basicFiltered = [];
                cards.forEach(function(card) {{
                    const ext = card.dataset.ext || '';
                    const width = parseInt(card.dataset.width) || 0;
                    const height = parseInt(card.dataset.height) || 0;
                    const src = card.dataset.sourceType || 'img';
                    const hasHints = card.dataset.hasHints === '1';

                    const matchesType = !typeFilter || ext === typeFilter;
                    const matchesSource = !sourceFilter || src === sourceFilter;
                    const matchesWidth = width >= minWidth;
                    const matchesHeight = height >= minHeight;
                    const matchesIssues = !onlyIssues || hasHints;

                    if (matchesType && matchesSource && matchesWidth && matchesHeight && matchesIssues) {{
                        basicFiltered.push(card);
                        card.classList.remove('hidden');
                    }} else {{
                        card.classList.add('hidden');
                    }}
                }});

                // Second pass: merge duplicates if enabled
                let visible = basicFiltered.length;
                if (mergeDuplicates && basicFiltered.length > 0) {{
                    // Group by lowercase filename (from .filename element's title attribute)
                    const groups = {{}};
                    basicFiltered.forEach(function(card) {{
                        const filenameEl = card.querySelector('.filename');
                        const filename = (filenameEl ? filenameEl.title : '').toLowerCase();
                        if (!groups[filename]) {{
                            groups[filename] = [];
                        }}
                        groups[filename].push(card);
                    }});

                    // For each group with duplicates, keep only the largest file
                    visible = 0;
                    Object.values(groups).forEach(function(group) {{
                        if (group.length === 1) {{
                            // Single image, already visible
                            visible++;
                            return;
                        }}
                        // Sort by file size descending (largest first)
                        group.sort(function(a, b) {{
                            const thumbA = a.querySelector('.gallery-thumbnail');
                            const thumbB = b.querySelector('.gallery-thumbnail');
                            const sizeA = parseInt(thumbA ? thumbA.dataset.sizeBytes : 0) || 0;
                            const sizeB = parseInt(thumbB ? thumbB.dataset.sizeBytes : 0) || 0;
                            return sizeB - sizeA;
                        }});
                        // Keep first (largest), hide the rest
                        visible++;
                        for (let i = 1; i < group.length; i++) {{
                            group[i].classList.add('hidden');
                        }}
                    }});
                }}

                visibleCount.textContent = visible;
            }}

            filterType.addEventListener('change', applyFilters);
            filterMinWidth.addEventListener('input', applyFilters);
            filterMinHeight.addEventListener('input', applyFilters);
            filterMergeDuplicates.addEventListener('change', applyFilters);
            if (filterSource) filterSource.addEventListener('change', applyFilters);
            if (filterOnlyIssues) filterOnlyIssues.addEventListener('change', applyFilters);

            // Lightbox functionality
            const lightbox = document.querySelector('.lightbox');
            const backdropA = document.getElementById('backdrop-a');
            const backdropB = document.getElementById('backdrop-b');
            const lightboxImage = document.querySelector('.lightbox-image');

            const lightboxCounter = document.querySelector('.lightbox-counter');
            const lightboxFilename = document.querySelector('.lightbox-filename');
            const lightboxMeta = document.querySelector('.lightbox-meta');
            const lightboxAlt = document.querySelector('.lightbox-alt');
            const lightboxAccName = document.querySelector('.lightbox-acc-name');
            const lightboxHints = document.querySelector('.lightbox-hints');
            const closeBtn = document.querySelector('.lightbox-close');
            const prevBtn = document.querySelector('.lightbox-prev');
            const nextBtn = document.querySelector('.lightbox-next');
            // thumbnails already declared above in filter section

            let currentIndex = 0;
            let lastFocusedElement = null;
            let activeBackdrop = 'a';  // Track which backdrop is currently visible
            let backdropDebounceTimer = null;  // Debounce timer for backdrop crossfade
            const BACKDROP_DEBOUNCE_MS = 150;  // Wait 150ms before updating backdrop

            // Get array of visible (non-filtered) thumbnail indices
            function getVisibleIndices() {{
                const indices = [];
                thumbnails.forEach(function(thumb, index) {{
                    const card = thumb.closest('.gallery-card');
                    if (card && !card.classList.contains('hidden')) {{
                        indices.push(index);
                    }}
                }});
                return indices;
            }}

            function updateBackdrop(imageSrc, isInitial) {{
                if (isInitial) {{
                    // Initial open: just set both to same image, show A
                    backdropA.src = imageSrc;
                    backdropB.src = imageSrc;
                    backdropA.classList.add('active');
                    backdropB.classList.remove('active');
                    activeBackdrop = 'a';
                }} else {{
                    // Navigation: crossfade between backdrops
                    if (activeBackdrop === 'a') {{
                        backdropB.src = imageSrc;
                        backdropB.classList.add('active');
                        backdropA.classList.remove('active');
                        activeBackdrop = 'b';
                    }} else {{
                        backdropA.src = imageSrc;
                        backdropA.classList.add('active');
                        backdropB.classList.remove('active');
                        activeBackdrop = 'a';
                    }}
                }}
            }}

            function updateLightbox(index, isInitial) {{
                currentIndex = index;
                const thumb = thumbnails[index];
                const card = thumb.closest('.gallery-card');
                const isSvg = card && card.dataset.ext === 'svg';

                const imageSrc = thumb.dataset.fullSrc;
                lightboxImage.src = imageSrc;

                // Toggle SVG mode (solid background instead of blur)
                if (isSvg) {{
                    lightbox.classList.add('svg-mode');
                    // Background color is applied by applySvgOptions() after this function
                }} else {{
                    lightbox.classList.remove('svg-mode');
                }}

                // Debounce backdrop crossfade to prevent stacking during rapid navigation
                if (backdropDebounceTimer) {{
                    clearTimeout(backdropDebounceTimer);
                }}

                // Only update backdrop for non-SVG images
                if (!isSvg) {{
                    if (isInitial) {{
                        // Initial open: update backdrop immediately
                        updateBackdrop(imageSrc, true);
                    }} else {{
                        // Navigation: debounce the backdrop update
                        backdropDebounceTimer = setTimeout(function() {{
                            updateBackdrop(imageSrc, false);
                        }}, BACKDROP_DEBOUNCE_MS);
                    }}
                }}

                lightboxImage.alt = thumb.dataset.alt || 'Image ' + (index + 1);

                // Update counter based on visible (filtered) images
                const visibleIndices = getVisibleIndices();
                const positionInVisible = visibleIndices.indexOf(index) + 1;
                lightboxCounter.textContent = positionInVisible + ' / ' + visibleIndices.length;

                // Extract filename from src
                const filename = thumb.dataset.fullSrc.split('/').pop();
                lightboxFilename.textContent = filename;
                lightboxMeta.textContent = thumb.dataset.width + '×' + thumb.dataset.height + ' · ' + thumb.dataset.size;
                lightboxAlt.textContent = thumb.dataset.alt ? '"' + thumb.dataset.alt + '"' : '';

                // Accessible name + source
                if (lightboxAccName) {{
                    const accName = thumb.dataset.accName || '';
                    const accSource = thumb.dataset.accNameSource || '';
                    if (accName) {{
                        lightboxAccName.innerHTML = '<span class="acc-label">Accessible name:</span> <em>' + accName.replace(/[<>&]/g, c => ({{'<':'&lt;','>':'&gt;','&':'&amp;'}}[c])) + '</em> <small>(' + accSource + ')</small>';
                    }} else if (accSource === 'none') {{
                        lightboxAccName.innerHTML = '<span class="acc-label" style="color:#f0883e">⚠ No accessible name</span>';
                    }} else {{
                        lightboxAccName.innerHTML = '<span class="acc-label" style="color:#f0883e">⚠ No accessible name (' + accSource + ')</span>';
                    }}
                }}

                // Accessibility hints
                if (lightboxHints) {{
                    let hints = [];
                    try {{ hints = JSON.parse(thumb.dataset.hints || '[]'); }} catch (_) {{}}
                    if (hints.length > 0) {{
                        lightboxHints.innerHTML = '<strong>Accessibility hints:</strong><ul>' +
                            hints.map(h => '<li>' + h + '</li>').join('') +
                            '</ul>';
                    }} else {{
                        lightboxHints.innerHTML = '';
                    }}
                }}

                // Update navigation state based on visible images
                const posIndex = visibleIndices.indexOf(index);
                prevBtn.disabled = posIndex <= 0;
                nextBtn.disabled = posIndex >= visibleIndices.length - 1;
            }}

            function openLightbox(index) {{
                lastFocusedElement = document.activeElement;
                lightbox.classList.add('active');
                document.body.style.overflow = 'hidden';
                updateLightbox(index, true);  // true = initial open
                closeBtn.focus();
            }}

            function closeLightbox() {{
                lightbox.classList.remove('active');
                lightbox.classList.remove('svg-mode');
                document.body.style.overflow = '';
                // Clear any pending backdrop update
                if (backdropDebounceTimer) {{
                    clearTimeout(backdropDebounceTimer);
                    backdropDebounceTimer = null;
                }}
                // Reset backdrop state
                backdropA.classList.remove('active');
                backdropB.classList.remove('active');
                if (lastFocusedElement) {{
                    lastFocusedElement.focus();
                }}
            }}

            function showPrev() {{
                const visibleIndices = getVisibleIndices();
                const currentPos = visibleIndices.indexOf(currentIndex);
                if (currentPos > 0) {{
                    updateLightbox(visibleIndices[currentPos - 1], false);  // false = navigation
                }}
            }}

            function showNext() {{
                const visibleIndices = getVisibleIndices();
                const currentPos = visibleIndices.indexOf(currentIndex);
                if (currentPos < visibleIndices.length - 1) {{
                    updateLightbox(visibleIndices[currentPos + 1], false);  // false = navigation
                }}
            }}

            // Event listeners
            thumbnails.forEach(function(thumb, index) {{
                thumb.addEventListener('click', function() {{
                    openLightbox(index);
                }});
            }});

            closeBtn.addEventListener('click', closeLightbox);
            prevBtn.addEventListener('click', showPrev);
            nextBtn.addEventListener('click', showNext);

            // Keyboard navigation
            document.addEventListener('keydown', function(e) {{
                if (!lightbox.classList.contains('active')) return;

                if (e.key === 'Escape') {{
                    closeLightbox();
                }} else if (e.key === 'ArrowLeft') {{
                    showPrev();
                }} else if (e.key === 'ArrowRight') {{
                    showNext();
                }}
            }});

            // Close on backdrop click
            lightbox.addEventListener('click', function(e) {{
                if (e.target === lightbox || e.target.classList.contains('lightbox-content')) {{
                    closeLightbox();
                }}
            }});

            // SVG Preview Options
            const svgToggles = document.querySelectorAll('.svg-toggle');
            const SVG_STORAGE_KEY = 'inspekt-svg-options';

            // Load saved options from localStorage or use defaults
            function loadSvgOptions() {{
                try {{
                    const saved = localStorage.getItem(SVG_STORAGE_KEY);
                    if (saved) {{
                        return JSON.parse(saved);
                    }}
                }} catch (e) {{
                    console.warn('Could not load SVG options from localStorage');
                }}
                return {{ size: 'auto', color: 'original', bg: 'current', preview: 'image' }};
            }}

            // Save options to localStorage
            function saveSvgOptions() {{
                try {{
                    localStorage.setItem(SVG_STORAGE_KEY, JSON.stringify(svgState));
                }} catch (e) {{
                    console.warn('Could not save SVG options to localStorage');
                }}
            }}

            const svgState = loadSvgOptions();

            // Code preview elements
            const codeContainer = document.querySelector('.lightbox-code-container');
            const codeElement = codeContainer.querySelector('code');
            const copyBtn = codeContainer.querySelector('.code-copy-btn');
            const imageContainer = document.querySelector('.lightbox-image-container');
            let svgCodeCache = {{}};  // Cache fetched SVG code

            // Get SVG source code - prefer embedded content, fall back to fetch
            async function getSvgCode() {{
                // Get current thumbnail's embedded SVG content
                const thumb = thumbnails[currentIndex];
                const embeddedB64 = thumb?.dataset?.svgSource;

                if (embeddedB64) {{
                    // Decode base64-encoded SVG content
                    try {{
                        return atob(embeddedB64);
                    }} catch (e) {{
                        console.warn('Failed to decode embedded SVG:', e);
                    }}
                }}

                // Fall back to fetch (only works on http://)
                const src = lightboxImage.src;
                if (svgCodeCache[src]) {{
                    return svgCodeCache[src];
                }}

                if (window.location.protocol === 'file:') {{
                    // Friendly message for large SVGs or missing content
                    return 'This SVG file is too large to embed in the gallery.\\n\\nTo view the source code, right-click the image and select "Open image in new tab", then view the page source.';
                }}

                try {{
                    const response = await fetch(src);
                    if (!response.ok) throw new Error('Failed to fetch SVG');
                    const code = await response.text();
                    svgCodeCache[src] = code;
                    return code;
                }} catch (error) {{
                    console.warn('Could not fetch SVG code:', error);
                    return '<!-- Could not load SVG source: ' + error.message + ' -->';
                }}
            }}

            // Show code preview (overlay on top of image)
            async function showCodePreview() {{
                const code = await getSvgCode();
                codeElement.textContent = code;
                if (window.Prism) {{
                    Prism.highlightElement(codeElement);
                }}
                // Keep image visible behind, show code on top
                codeContainer.hidden = false;
                lightbox.classList.add('svg-code-mode');
            }}

            // Show image preview (hide code overlay)
            function showImagePreview() {{
                codeContainer.hidden = true;
                lightbox.classList.remove('svg-code-mode');
            }}

            // Copy button functionality
            copyBtn.addEventListener('click', async function() {{
                const code = codeElement.textContent;
                try {{
                    await navigator.clipboard.writeText(code);
                    this.classList.add('copied');
                    const originalHTML = this.innerHTML;
                    this.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.75.75 0 1 1 1.06-1.06L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z"/></svg> Copied!';
                    setTimeout(() => {{
                        this.classList.remove('copied');
                        this.innerHTML = originalHTML;
                    }}, 2000);
                }} catch (err) {{
                    console.error('Failed to copy:', err);
                }}
            }});

            // Helper: check if a hex color is "light" (luminance > 0.5)
            function isLightColor(hex) {{
                // Handle shorthand and standard hex
                const cleanHex = hex.replace('#', '');
                let r, g, b;
                if (cleanHex.length === 3) {{
                    r = parseInt(cleanHex[0] + cleanHex[0], 16);
                    g = parseInt(cleanHex[1] + cleanHex[1], 16);
                    b = parseInt(cleanHex[2] + cleanHex[2], 16);
                }} else {{
                    r = parseInt(cleanHex.substring(0, 2), 16);
                    g = parseInt(cleanHex.substring(2, 4), 16);
                    b = parseInt(cleanHex.substring(4, 6), 16);
                }}
                // Relative luminance formula
                const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
                return luminance > 0.5;
            }}

            function applySvgOptions() {{
                // Remove all SVG-related classes
                lightboxImage.classList.remove(
                    'svg-size-auto', 'svg-size-50', 'svg-size-25', 'svg-size-original',
                    'svg-color-white', 'svg-color-black'
                );

                // Apply size class
                lightboxImage.classList.add('svg-size-' + svgState.size);

                // Apply color filter
                if (svgState.color === 'white') {{
                    lightboxImage.classList.add('svg-color-white');
                }} else if (svgState.color === 'black') {{
                    lightboxImage.classList.add('svg-color-black');
                }}

                // Determine the effective background color
                let effectiveBgColor;
                if (svgState.bg === 'white') {{
                    effectiveBgColor = '#ffffff';
                }} else if (svgState.bg === 'black') {{
                    effectiveBgColor = '#000000';
                }} else {{
                    effectiveBgColor = filterBgColor.value || '#e5e5e5';
                }}

                // Auto-contrast: prevent invisible images (bi-directional)
                const bgIsLight = isLightColor(effectiveBgColor);

                // If SVG color would be invisible on current background, adjust
                if (svgState.color === 'white' && bgIsLight) {{
                    // White SVG on light background → switch background to black
                    effectiveBgColor = '#000000';
                    svgState.bg = 'black';
                }} else if (svgState.color === 'black' && !bgIsLight) {{
                    // Black SVG on dark background → switch background to white
                    effectiveBgColor = '#ffffff';
                    svgState.bg = 'white';
                }} else if (svgState.color === 'original') {{
                    // For original color, check if background change would hide a white/black SVG
                    // (Can't detect original SVG color, so skip auto-adjustment)
                }} else {{
                    // Background was changed - check if SVG color needs adjustment
                    if (bgIsLight && svgState.color === 'white') {{
                        // Light bg + white SVG → switch SVG to black
                        svgState.color = 'black';
                        lightboxImage.classList.remove('svg-color-white');
                        lightboxImage.classList.add('svg-color-black');
                    }} else if (!bgIsLight && svgState.color === 'black') {{
                        // Dark bg + black SVG → switch SVG to white
                        svgState.color = 'white';
                        lightboxImage.classList.remove('svg-color-black');
                        lightboxImage.classList.add('svg-color-white');
                    }}
                }}

                // Apply the background color
                lightbox.style.setProperty('--lightbox-solid-bg', effectiveBgColor);

                // Update aria-pressed states to match current state
                svgToggles.forEach(function(toggle) {{
                    const option = toggle.dataset.option;
                    const value = toggle.dataset.value;
                    const isActive = svgState[option] === value;
                    toggle.setAttribute('aria-pressed', isActive ? 'true' : 'false');
                }});

                // Handle preview mode (image vs code)
                if (svgState.preview === 'code') {{
                    showCodePreview();
                }} else {{
                    showImagePreview();
                }}
            }}

            // Handle SVG toggle button clicks
            svgToggles.forEach(function(toggle) {{
                toggle.addEventListener('click', function() {{
                    const option = this.dataset.option;
                    const value = this.dataset.value;

                    // Update state
                    svgState[option] = value;

                    // Save to localStorage
                    saveSvgOptions();

                    // Apply the changes (also updates aria-pressed)
                    applySvgOptions();
                }});
            }});

            // Clean up SVG classes when closing lightbox (but keep saved state)
            const originalCloseLightbox = closeLightbox;
            closeLightbox = function() {{
                // Remove SVG-specific classes from image
                lightboxImage.classList.remove(
                    'svg-size-auto', 'svg-size-50', 'svg-size-25', 'svg-size-original',
                    'svg-color-white', 'svg-color-black'
                );
                // Hide code overlay
                codeContainer.hidden = true;
                lightbox.classList.remove('svg-code-mode');
                originalCloseLightbox();
            }};

            // Apply saved SVG options when opening an SVG image
            const originalUpdateLightbox = updateLightbox;
            updateLightbox = function(index, isInitial) {{
                // Reset code view when navigating
                codeContainer.hidden = true;
                imageContainer.hidden = false;
                lightbox.classList.remove('svg-code-mode');

                originalUpdateLightbox(index, isInitial);
                // If this is an SVG, apply saved options
                if (lightbox.classList.contains('svg-mode')) {{
                    applySvgOptions();
                }}
            }};

            // Trap focus in lightbox
            lightbox.addEventListener('keydown', function(e) {{
                if (e.key !== 'Tab') return;

                const focusables = lightbox.querySelectorAll('button:not([disabled])');
                const first = focusables[0];
                const last = focusables[focusables.length - 1];

                if (e.shiftKey && document.activeElement === first) {{
                    e.preventDefault();
                    last.focus();
                }} else if (!e.shiftKey && document.activeElement === last) {{
                    e.preventDefault();
                    first.focus();
                }}
            }});
        }})();
    </script>
</body>
</html>
"""
