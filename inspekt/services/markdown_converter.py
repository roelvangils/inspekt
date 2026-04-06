"""
HTML to Markdown conversion for article extraction.

Provides:
- Convert Readability HTML output to clean Markdown
- Extract and track image URLs for caching
- Generate YAML frontmatter from article metadata
- Post-processing filters to remove unwanted content
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import yaml
from bs4 import BeautifulSoup
from markdownify import MarkdownConverter

# Cache for loaded filters
_filters_cache: list[str] | None = None


class ArticleMarkdownConverter(MarkdownConverter):
    """
    Custom Markdown converter that tracks images.

    Extends markdownify's MarkdownConverter to collect all image URLs
    encountered during conversion for optional caching.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.images: list[dict[str, str]] = []

    def convert_img(self, el, text, parent_tags=None):
        """
        Convert image element, tracking URL and alt text.

        Overrides parent to collect image metadata before conversion.
        """
        src = el.get("src", "")
        alt = el.get("alt", "")

        if src:
            self.images.append(
                {
                    "src": src,
                    "alt": alt,
                }
            )

        return super().convert_img(el, text, parent_tags=parent_tags)


def convert_html_to_markdown(
    html_content: str,
    base_url: str | None = None,
    strip_tags: list[str] | None = None,
) -> tuple[str, list[dict[str, str]]]:
    """
    Convert HTML content to Markdown.

    Args:
        html_content: HTML string to convert
        base_url: Base URL for resolving relative image URLs
        strip_tags: Additional tags to strip (default strips script, style, noscript)

    Returns:
        Tuple of (markdown_content, list_of_images)
        Each image is a dict with 'src' and 'alt' keys
    """
    # Parse HTML to normalize and clean
    soup = BeautifulSoup(html_content, "html.parser")

    # Resolve relative URLs if base_url provided
    if base_url:
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src and not src.startswith(("http://", "https://", "data:", "//")):
                img["src"] = urljoin(base_url, src)
        # Also resolve srcset if present
        for img in soup.find_all("img"):
            srcset = img.get("srcset", "")
            if srcset:
                # Parse srcset and resolve each URL
                parts = []
                for part in srcset.split(","):
                    part = part.strip()
                    if not part:
                        continue
                    tokens = part.split()
                    if tokens:
                        url = tokens[0]
                        if not url.startswith(("http://", "https://", "data:", "//")):
                            tokens[0] = urljoin(base_url, url)
                        parts.append(" ".join(tokens))
                if parts:
                    img["srcset"] = ", ".join(parts)

    # Remove unwanted elements
    default_strip = ["script", "style", "noscript", "iframe", "form"]
    tags_to_remove = default_strip + (strip_tags or [])
    for tag in soup.find_all(tags_to_remove):
        tag.decompose()

    # Create custom converter to track images
    converter = ArticleMarkdownConverter(
        heading_style="atx",
        bullets="-",
        strong_em_symbol="*",
        sub_symbol="",
        sup_symbol="",
    )

    # Convert to markdown
    markdown = converter.convert(str(soup))

    # Clean up excessive whitespace
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    markdown = re.sub(r"[ \t]+\n", "\n", markdown)  # Trailing whitespace
    markdown = markdown.strip()

    return markdown, converter.images


def generate_frontmatter(article_data: dict[str, Any]) -> str:
    """
    Generate YAML frontmatter from article metadata.

    Args:
        article_data: Dictionary with title, byline, url, lang, siteName, publishedDate

    Returns:
        YAML frontmatter string (including --- delimiters)
    """
    frontmatter: dict[str, Any] = {}

    # Map article fields to frontmatter fields
    field_mapping = {
        "title": "title",
        "byline": "author",
        "publishedDate": "date",
        "url": "url",
        "siteName": "site",
        "lang": "lang",
    }

    for source_key, target_key in field_mapping.items():
        value = article_data.get(source_key)
        if value:
            # Clean up the value
            if isinstance(value, str):
                value = value.strip()
            if value:  # Skip empty strings after stripping
                frontmatter[target_key] = value

    if not frontmatter:
        return ""

    # Generate YAML with proper formatting
    yaml_content = yaml.dump(
        frontmatter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=1000,  # Prevent line wrapping in long URLs
    )

    return f"---\n{yaml_content}---\n\n"


def convert_frontmatter_to_h1(markdown: str) -> str:
    """
    Convert YAML frontmatter to an H1 heading with the title.

    Takes markdown with YAML frontmatter and returns markdown with
    the frontmatter stripped and an H1 heading with the title instead.

    Args:
        markdown: Markdown content starting with YAML frontmatter

    Returns:
        Markdown with frontmatter replaced by H1 title heading
    """
    if not markdown.startswith("---\n"):
        return markdown

    # Find the closing ---
    end_marker = markdown.find("\n---\n", 4)
    if end_marker == -1:
        return markdown

    # Extract frontmatter YAML
    frontmatter_yaml = markdown[4:end_marker]
    body = markdown[end_marker + 5:].lstrip()

    # Parse YAML to get title
    try:
        frontmatter_data = yaml.safe_load(frontmatter_yaml)
        title = frontmatter_data.get("title", "").strip() if frontmatter_data else ""
    except yaml.YAMLError:
        title = ""

    # Return with H1 title or just body
    if title:
        return f"# {title}\n\n{body}"
    return body


def replace_image_urls(markdown: str, url_mapping: dict[str, str]) -> str:
    """
    Replace image URLs in markdown with local paths.

    Args:
        markdown: Markdown content with remote image URLs
        url_mapping: Dictionary mapping remote URLs to local paths

    Returns:
        Markdown with replaced image URLs
    """
    result = markdown
    for remote_url, local_path in url_mapping.items():
        if remote_url and local_path:
            result = result.replace(remote_url, local_path)
    return result


def flatten_inline_markdown(markdown: str) -> str:
    """
    Strip inline markdown formatting, keeping only the text content.

    Designed for text-to-speech preparation where markdown syntax
    would be read aloud incorrectly.

    Removes:
    - Links: [text](url) → text
    - Bold: **text** or __text__ → text
    - Italic: *text* or _text_ → text
    - Code: `text` → text
    - Strikethrough: ~~text~~ → text

    Preserves:
    - Headings (# syntax)
    - Paragraphs and line breaks
    - Lists (bullet points and numbers)

    Args:
        markdown: Markdown content with inline formatting

    Returns:
        Plain text with inline formatting removed
    """
    import re

    # Remove links but keep text: [text](url) → text
    markdown = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', markdown)

    # Remove reference-style links: [text][ref] → text
    markdown = re.sub(r'\[([^\]]+)\]\[[^\]]*\]', r'\1', markdown)

    # Remove bold: **text** or __text__ → text
    markdown = re.sub(r'\*\*([^*]+)\*\*', r'\1', markdown)
    markdown = re.sub(r'__([^_]+)__', r'\1', markdown)

    # Remove italic: *text* or _text_ → text (careful not to match bold)
    markdown = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'\1', markdown)
    markdown = re.sub(r'(?<!_)_([^_]+)_(?!_)', r'\1', markdown)

    # Remove inline code: `text` → text
    markdown = re.sub(r'`([^`]+)`', r'\1', markdown)

    # Remove strikethrough: ~~text~~ → text
    markdown = re.sub(r'~~([^~]+)~~', r'\1', markdown)

    return markdown


def strip_images(markdown: str) -> str:
    """
    Remove all images from markdown content.

    Removes:
    - Inline images: ![alt](url)
    - Reference-style images: ![alt][ref]
    - Image reference definitions: [ref]: url

    Args:
        markdown: Markdown content with images

    Returns:
        Markdown with all images removed
    """
    import re

    # Remove inline images: ![alt text](url "optional title")
    markdown = re.sub(r'!\[[^\]]*\]\([^)]+\)\s*', '', markdown)

    # Remove reference-style images: ![alt text][ref]
    markdown = re.sub(r'!\[[^\]]*\]\[[^\]]*\]\s*', '', markdown)

    # Remove image reference definitions: [ref]: url
    markdown = re.sub(r'^\[[^\]]+\]:\s+\S+.*$\n?', '', markdown, flags=re.MULTILINE)

    # Clean up extra blank lines (more than 2 consecutive)
    markdown = re.sub(r'\n{3,}', '\n\n', markdown)

    return markdown.strip()


def load_extract_filters() -> list[str]:
    """
    Load extraction filters from YAML file.

    Filters are cached after first load.

    Returns:
        List of filter patterns (supports * and ? wildcards)
    """
    global _filters_cache

    if _filters_cache is not None:
        return _filters_cache

    filters_path = Path(__file__).parent.parent / "data" / "extract_filters.yaml"

    if not filters_path.exists():
        _filters_cache = []
        return _filters_cache

    try:
        with open(filters_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            _filters_cache = data.get("filters", []) if data else []
    except Exception:
        _filters_cache = []

    return _filters_cache


def apply_extract_filters(markdown: str) -> str:
    """
    Apply post-processing filters to remove unwanted content.

    Filters are loaded from inspekt/data/extract_filters.yaml.
    Patterns support wildcards (* and ?) and are case-insensitive.

    Args:
        markdown: Markdown content to filter

    Returns:
        Filtered markdown content
    """
    filters = load_extract_filters()

    if not filters:
        return markdown

    lines = markdown.split("\n")
    filtered_lines = []

    for line in lines:
        line_stripped = line.strip()

        # Skip empty lines (keep them)
        if not line_stripped:
            filtered_lines.append(line)
            continue

        # Remove single-character lines (almost always artifacts like orphaned ">" or "*")
        if len(line_stripped) == 1:
            continue

        # Normalize whitespace for matching (NBSP → space, etc.)
        # This ensures patterns with regular spaces match non-breaking spaces
        line_normalized = line_stripped.replace("\xa0", " ")  # NBSP
        line_normalized = line_normalized.replace("\u2007", " ")  # Figure space
        line_normalized = line_normalized.replace("\u202f", " ")  # Narrow NBSP

        # Check if line matches any filter pattern
        should_remove = False
        for pattern in filters:
            # Normalize pattern too (in case it has NBSP from YAML)
            pattern_normalized = pattern.replace("\xa0", " ")
            pattern_normalized = pattern_normalized.replace("\u2007", " ")
            pattern_normalized = pattern_normalized.replace("\u202f", " ")
            # fnmatch is case-sensitive, so lowercase both
            if fnmatch.fnmatch(line_normalized.lower(), pattern_normalized.lower()):
                should_remove = True
                break

        if not should_remove:
            filtered_lines.append(line)

    result = "\n".join(filtered_lines)

    # Clean up multiple consecutive blank lines that may result from filtering
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result


def clean_trailing_content(markdown: str) -> str:
    """
    Clean up trailing content in extracted markdown.

    This performs two operations:
    1. Strips all empty trailing lines
    2. Recursively strips orphaned headings (lines starting with #) from the end.
       Orphaned headings typically come from callout blocks or sidebars
       that have a heading but no content following it.

    Args:
        markdown: Markdown content to clean

    Returns:
        Cleaned markdown content
    """
    # Strip trailing whitespace/empty lines
    markdown = markdown.rstrip()

    # Recursively remove orphaned headings from the end
    lines = markdown.split("\n")
    changed = True
    while changed and lines:
        changed = False
        last_line = lines[-1].strip()
        if last_line.startswith("#"):
            # Remove the orphaned heading
            lines.pop()
            changed = True
            # Strip any trailing empty lines after removing the heading
            while lines and not lines[-1].strip():
                lines.pop()

    return "\n".join(lines)


def reload_extract_filters() -> list[str]:
    """
    Force reload of extraction filters from disk.

    Useful if the filters file has been modified.

    Returns:
        Newly loaded list of filter patterns
    """
    global _filters_cache
    _filters_cache = None
    return load_extract_filters()
