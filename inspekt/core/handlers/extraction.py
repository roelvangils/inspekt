"""
Extraction command handlers.

Implements: extract_links, extract_outline, extract_page_info, extract_article
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from inspekt.core.schemas.extraction import (
    ExtractArticleResponse,
    ExtractLinksParams,
    ExtractLinksResponse,
    ExtractOutlineResponse,
    LinkInfo,
    OutlineItem,
    PageInfoResponse,
)

if TYPE_CHECKING:
    from inspekt.core.commands.base import EmptyParams
    from inspekt.services.bridge_executor import BridgeExecutor
    from inspekt.services.script_loader import ScriptLoader

logger = logging.getLogger(__name__)


def get_executor() -> BridgeExecutor:
    """Get the bridge executor instance."""
    from inspekt.services.bridge_executor import BridgeExecutor

    return BridgeExecutor()


def get_script_loader() -> ScriptLoader:
    """Get the script loader instance."""
    from inspekt.services.script_loader import ScriptLoader

    return ScriptLoader()


async def extract_links(params: ExtractLinksParams) -> ExtractLinksResponse:
    """
    Extract all links from the current page.

    Returns structured data including link text, URLs, and link types.
    """
    executor = get_executor()
    script_loader = get_script_loader()

    try:
        # Load the extract_links.js script
        script = await script_loader.load_script_async("extract_links.js")

        result = await asyncio.to_thread(executor.execute, script, 15.0)

        if result.get("ok"):
            links_data = result.get("result", [])

            # Filter by type if requested
            if params.filter_type and params.filter_type != "all":
                links_data = [
                    link for link in links_data if link.get("type") == params.filter_type
                ]

            # Filter anchors if not included
            if not params.include_anchors:
                links_data = [
                    link for link in links_data if link.get("type") != "anchor"
                ]

            # Convert to Pydantic models
            links = [
                LinkInfo(
                    url=link.get("url", ""),
                    text=link.get("text", ""),
                    title=link.get("title"),
                    type=link.get("type", "internal"),
                )
                for link in links_data
            ]

            return ExtractLinksResponse(
                success=True,
                links=links,
                count=len(links),
                message=f"Found {len(links)} links",
            )
        else:
            return ExtractLinksResponse(
                success=False,
                links=[],
                count=0,
                message=f"Failed to extract links: {result.get('error', 'Unknown error')}",
            )

    except Exception as e:
        logger.error(f"Extract links error: {e}")
        return ExtractLinksResponse(
            success=False,
            links=[],
            count=0,
            message=f"Error: {e!s}",
        )


async def extract_outline(params: EmptyParams) -> ExtractOutlineResponse:
    """
    Extract the heading hierarchy (H1-H6) from the current page.

    Creates a structured outline of the page content.
    """
    executor = get_executor()
    script_loader = get_script_loader()

    try:
        # Load the extract_outline.js script
        script = await script_loader.load_script_async("extract_outline.js")

        result = await asyncio.to_thread(executor.execute, script, 15.0)

        if result.get("ok"):
            result_data = result.get("result", {})
            # The script returns {"headings": [...]}
            outline_data = (
                result_data.get("headings", []) if isinstance(result_data, dict) else []
            )

            # Convert to Pydantic models
            outline = [
                OutlineItem(
                    level=item.get("level", 1),
                    text=item.get("text", ""),
                    id=item.get("id"),
                )
                for item in outline_data
            ]

            return ExtractOutlineResponse(
                success=True,
                outline=outline,
                count=len(outline),
                message=f"Found {len(outline)} headings",
            )
        else:
            return ExtractOutlineResponse(
                success=False,
                outline=[],
                count=0,
                message=f"Failed to extract outline: {result.get('error', 'Unknown error')}",
            )

    except Exception as e:
        logger.error(f"Extract outline error: {e}")
        return ExtractOutlineResponse(
            success=False,
            outline=[],
            count=0,
            message=f"Error: {e!s}",
        )


async def extract_page_info(params: EmptyParams) -> PageInfoResponse:
    """
    Extract comprehensive metadata from the current page.

    Includes title, description, Open Graph tags, meta tags, and more.
    """
    executor = get_executor()
    script_loader = get_script_loader()

    try:
        # Load extended_info.js script
        script = await script_loader.load_script_async("extended_info.js")

        result = await asyncio.to_thread(executor.execute, script, 15.0)

        if result.get("ok"):
            data = result.get("result", {})

            return PageInfoResponse(
                success=True,
                url=data.get("url", ""),
                title=data.get("title", ""),
                description=data.get("description"),
                language=data.get("language"),
                author=data.get("author"),
                keywords=data.get("keywords"),
                og_title=data.get("og_title"),
                og_description=data.get("og_description"),
                og_image=data.get("og_image"),
                canonical_url=data.get("canonical_url"),
                viewport_width=data.get("viewport_width", 0),
                viewport_height=data.get("viewport_height", 0),
                message="Page info extracted successfully",
            )
        else:
            return PageInfoResponse(
                success=False,
                url="",
                title="",
                viewport_width=0,
                viewport_height=0,
                message=f"Failed to extract page info: {result.get('error', 'Unknown error')}",
            )

    except Exception as e:
        logger.error(f"Extract page info error: {e}")
        return PageInfoResponse(
            success=False,
            url="",
            title="",
            viewport_width=0,
            viewport_height=0,
            message=f"Error: {e!s}",
        )


async def extract_article(params: EmptyParams) -> ExtractArticleResponse:
    """
    Extract the main article content using Mozilla Readability algorithm.

    Removes navigation, ads, and clutter to return clean article text.
    """
    executor = get_executor()
    script_loader = get_script_loader()

    try:
        # Load extract_article.js script
        script = await script_loader.load_script_async("extract_article.js")

        result = await asyncio.to_thread(executor.execute, script, 15.0)

        if result.get("ok"):
            data = result.get("result", {})
            content = data.get("textContent", "")

            return ExtractArticleResponse(
                success=True,
                title=data.get("title"),
                byline=data.get("byline"),
                content=content,
                excerpt=data.get("excerpt"),
                length=len(content),
                message="Article extracted successfully",
            )
        else:
            return ExtractArticleResponse(
                success=False,
                content="",
                length=0,
                message=f"Failed to extract article: {result.get('error', 'Unknown error')}",
            )

    except Exception as e:
        logger.error(f"Extract article error: {e}")
        return ExtractArticleResponse(
            success=False,
            content="",
            length=0,
            message=f"Error: {e!s}",
        )
