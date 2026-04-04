"""
Navigation command schemas.

Input/output models for navigation commands:
- navigate_to_url
- go_back / go_forward / reload_page
- get_sitemap
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class NavigateParams(BaseModel):
    """Parameters for navigate_to_url command."""

    url: str = Field(
        ...,
        description="The URL to navigate to (must start with http:// or https://)",
    )
    wait_for: Optional[Literal["load", "networkidle"]] = Field(
        default=None,
        description="Wait condition: 'load' (DOMContentLoaded), 'networkidle' (no network activity)",
    )
    timeout: Optional[int] = Field(
        default=30,
        description="Navigation timeout in seconds",
    )


class ReloadParams(BaseModel):
    """Parameters for reload_page command."""

    hard: bool = Field(
        default=False,
        description="Hard reload (bypass cache)",
    )


class NavigateResponse(BaseModel):
    """Response from navigation commands."""

    success: bool = Field(
        ...,
        description="Whether the navigation succeeded",
    )
    url: str = Field(
        default="",
        description="The final URL after navigation (may differ due to redirects)",
    )
    title: str = Field(
        default="",
        description="Page title",
    )
    message: Optional[str] = Field(
        default=None,
        description="Success or error message",
    )


# ── Sitemap schemas ──────────────────────────────────────────────────


class SitemapParams(BaseModel):
    """Parameters for get_sitemap command."""

    url: Optional[str] = Field(
        default=None,
        description="Site URL or direct sitemap URL. If omitted, uses the current page's origin.",
    )
    lang: Optional[str] = Field(
        default=None,
        description="Filter by language code (e.g., 'nl', 'en', 'fr')",
    )
    refresh: bool = Field(
        default=False,
        description="Force re-fetch, bypassing cache",
    )


class SitemapEntryItem(BaseModel):
    """A single URL entry in the sitemap response."""

    index: int = Field(description="1-based index for use with --open")
    url: str = Field(description="Full URL")
    title: str = Field(default="", description="Page title (if fetched)")
    lastmod: str = Field(default="", description="Last modified date (ISO 8601)")
    path: str = Field(default="", description="URL path relative to origin")


class SitemapResponse(BaseModel):
    """Response from get_sitemap command."""

    success: bool = Field(description="Whether the sitemap was found and parsed")
    origin: str = Field(default="", description="Site origin")
    source_url: str = Field(default="", description="Sitemap URL(s) that were fetched")
    total_urls: int = Field(default=0, description="Total number of URLs in sitemap")
    languages: list[str] = Field(default_factory=list, description="Detected language codes")
    entries: list[SitemapEntryItem] = Field(default_factory=list, description="Sitemap entries")
    message: Optional[str] = Field(default=None, description="Status or error message")
