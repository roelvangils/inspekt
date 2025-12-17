"""
Extraction command definitions.

Commands for extracting data from web pages:
- extract_links: Extract all links
- extract_outline: Extract heading hierarchy
- extract_page_info: Extract page metadata
- extract_article: Extract article content
"""

from inspekt.core.commands.base import Category, CommandDefinition, EmptyParams
from inspekt.core.schemas.extraction import (
    ExtractArticleResponse,
    ExtractLinksParams,
    ExtractLinksResponse,
    ExtractOutlineResponse,
    PageInfoResponse,
)

# === Extract Links ===

extract_links = CommandDefinition(
    id="extract_links",
    name="Extract Links",
    category=Category.EXTRACTION,
    description="""Extract all links from the current page.

Returns structured data including link text, URLs, and link types
(internal, external, anchor). Uses the live DOM, so it sees
JavaScript-rendered content that simple HTML parsing would miss.

Can filter by link type and include/exclude anchor links.""",
    params_schema=ExtractLinksParams,
    response_schema=ExtractLinksResponse,
    handler="inspekt.core.handlers.extraction.extract_links",
    cli_name="links",
    api_path="/extraction/links",
    api_method="GET",
    examples=[
        "inspekt links",
        "inspekt links --filter external",
        "inspekt links --no-anchors",
    ],
)

# === Extract Outline ===

extract_outline = CommandDefinition(
    id="extract_outline",
    name="Extract Outline",
    category=Category.EXTRACTION,
    description="""Extract the heading hierarchy (H1-H6) from the current page.

Creates a structured outline of the page content. Useful for:
- Understanding page structure
- Accessibility auditing (heading hierarchy)
- Content summarization""",
    params_schema=EmptyParams,
    response_schema=ExtractOutlineResponse,
    handler="inspekt.core.handlers.extraction.extract_outline",
    cli_name="outline",
    api_path="/extraction/outline",
    api_method="GET",
    examples=["inspekt outline"],
)

# === Extract Page Info ===

extract_page_info = CommandDefinition(
    id="extract_page_info",
    name="Extract Page Info",
    category=Category.EXTRACTION,
    description="""Extract comprehensive metadata from the current page.

Includes:
- Title, description, language
- Open Graph tags (og:title, og:description, og:image)
- Author, keywords
- Canonical URL
- Viewport dimensions""",
    params_schema=EmptyParams,
    response_schema=PageInfoResponse,
    handler="inspekt.core.handlers.extraction.extract_page_info",
    cli_name="info",
    cli_group="page",  # inspekt page info
    api_path="/extraction/info",
    api_method="GET",
    examples=["inspekt info"],
)

# === Extract Article ===

extract_article = CommandDefinition(
    id="extract_article",
    name="Extract Article",
    category=Category.EXTRACTION,
    description="""Extract the main article content using Mozilla Readability algorithm.

Removes navigation, ads, sidebars, and other clutter to return clean,
readable article text. Best for:
- News articles
- Blog posts
- Long-form content

Returns title, byline, content, and excerpt.""",
    params_schema=EmptyParams,
    response_schema=ExtractArticleResponse,
    handler="inspekt.core.handlers.extraction.extract_article",
    cli_name="article",
    api_path="/extraction/article",
    api_method="GET",
    examples=["inspekt article"],
)

# All extraction commands
EXTRACTION_COMMANDS = [
    extract_links,
    extract_outline,
    extract_page_info,
    extract_article,
]
