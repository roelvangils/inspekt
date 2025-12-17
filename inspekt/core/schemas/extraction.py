"""
Extraction command schemas.

Input/output models for extraction commands:
- extract_links
- extract_outline
- extract_page_info
- extract_article
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# === Link Extraction ===


class ExtractLinksParams(BaseModel):
    """Parameters for extract_links command."""

    filter_type: Optional[Literal["all", "internal", "external"]] = Field(
        default="all",
        description="Filter links by type: all, internal, or external",
    )
    include_anchors: Optional[bool] = Field(
        default=True,
        description="Include same-page anchor links (#section)",
    )


class LinkInfo(BaseModel):
    """Information about a single link."""

    url: str = Field(..., description="The link URL (absolute)")
    text: str = Field(..., description="Link text content")
    title: Optional[str] = Field(default=None, description="Link title attribute")
    type: Literal["internal", "external", "anchor"] = Field(
        ..., description="Link type classification"
    )


class ExtractLinksResponse(BaseModel):
    """Response from extract_links command."""

    success: bool = Field(..., description="Whether extraction succeeded")
    links: list[LinkInfo] = Field(default_factory=list, description="List of extracted links")
    count: int = Field(default=0, description="Total number of links found")
    message: Optional[str] = Field(default=None, description="Status message")


# === Outline Extraction ===


class OutlineItem(BaseModel):
    """A heading in the page outline."""

    level: int = Field(..., description="Heading level (1-6)")
    text: str = Field(..., description="Heading text content")
    id: Optional[str] = Field(default=None, description="Element ID if present")


class ExtractOutlineResponse(BaseModel):
    """Response from extract_outline command."""

    success: bool = Field(..., description="Whether extraction succeeded")
    outline: list[OutlineItem] = Field(default_factory=list, description="Page heading hierarchy")
    count: int = Field(default=0, description="Total number of headings")
    message: Optional[str] = Field(default=None, description="Status message")


# === Page Info Extraction ===


class PageInfoResponse(BaseModel):
    """Response from extract_page_info command."""

    success: bool = Field(..., description="Whether extraction succeeded")
    url: str = Field(default="", description="Page URL")
    title: str = Field(default="", description="Page title")
    description: Optional[str] = Field(default=None, description="Meta description")
    language: Optional[str] = Field(default=None, description="Page language (ISO 639-1 code)")
    author: Optional[str] = Field(default=None, description="Author from meta tags")
    keywords: Optional[list[str]] = Field(default=None, description="Meta keywords")
    og_title: Optional[str] = Field(default=None, description="Open Graph title")
    og_description: Optional[str] = Field(default=None, description="Open Graph description")
    og_image: Optional[str] = Field(default=None, description="Open Graph image URL")
    canonical_url: Optional[str] = Field(default=None, description="Canonical URL")
    viewport_width: int = Field(default=0, description="Viewport width in pixels")
    viewport_height: int = Field(default=0, description="Viewport height in pixels")
    message: Optional[str] = Field(default=None, description="Status message")


# === Article Extraction ===


class ExtractArticleResponse(BaseModel):
    """Response from extract_article command."""

    success: bool = Field(..., description="Whether extraction succeeded")
    title: Optional[str] = Field(default=None, description="Article title")
    byline: Optional[str] = Field(default=None, description="Article author/byline")
    content: str = Field(default="", description="Extracted article content (plain text)")
    excerpt: Optional[str] = Field(default=None, description="Article excerpt/summary")
    length: int = Field(default=0, description="Content length in characters")
    message: Optional[str] = Field(default=None, description="Status message")
