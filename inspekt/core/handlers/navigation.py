"""
Navigation command handlers.

Implements: navigate_to_url, go_back, go_forward, reload_page,
            scroll_to_top, scroll_to_bottom, page_up, page_down
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from inspekt.core.commands.base import EmptyParams
from inspekt.core.schemas.navigation import (
    NavigateParams,
    NavigateResponse,
    ReloadParams,
)

if TYPE_CHECKING:
    from inspekt.services.bridge_executor import BridgeExecutor

logger = logging.getLogger(__name__)


def get_executor() -> BridgeExecutor:
    """Get the bridge executor instance."""
    from inspekt.services.bridge_executor import BridgeExecutor

    return BridgeExecutor()


async def navigate_to_url(params: NavigateParams) -> NavigateResponse:
    """
    Navigate to a URL in the browser.

    Uses the unified navigation service which calls chrome.tabs.update()
    via the bridge's /navigate endpoint. This properly handles navigation
    without destroying the JavaScript execution context.

    Supports wait conditions for page load:
    - 'load': Wait for DOMContentLoaded
    - 'networkidle': Wait for network to be idle
    """
    from inspekt.services.navigation import navigate

    logger.info(f"[navigate_to_url] Navigating to: {params.url}")

    result = await navigate(
        url=params.url,
        wait_for=params.wait_for,
        timeout=params.timeout or 30,
    )

    return NavigateResponse(**result)


async def go_back(params: EmptyParams) -> NavigateResponse:
    """Navigate browser history backward."""
    executor = get_executor()

    try:
        code = """
        (async () => {
            window.history.back();
            await new Promise(resolve => setTimeout(resolve, 500));
            return {
                url: window.location.href,
                title: document.title
            };
        })()
        """

        result = await asyncio.to_thread(executor.execute, code, 10.0)

        if result.get("ok"):
            data = result.get("result", {})
            return NavigateResponse(
                success=True,
                url=data.get("url", ""),
                title=data.get("title", ""),
                message="Navigated back",
            )
        else:
            return NavigateResponse(
                success=False,
                url="",
                title="",
                message=f"Failed to go back: {result.get('error', 'Unknown error')}",
            )

    except Exception as e:
        logger.error(f"Go back error: {e}")
        return NavigateResponse(
            success=False,
            url="",
            title="",
            message=f"Error: {str(e)}",
        )


async def go_forward(params: EmptyParams) -> NavigateResponse:
    """Navigate browser history forward."""
    executor = get_executor()

    try:
        code = """
        (async () => {
            window.history.forward();
            await new Promise(resolve => setTimeout(resolve, 500));
            return {
                url: window.location.href,
                title: document.title
            };
        })()
        """

        result = await asyncio.to_thread(executor.execute, code, 10.0)

        if result.get("ok"):
            data = result.get("result", {})
            return NavigateResponse(
                success=True,
                url=data.get("url", ""),
                title=data.get("title", ""),
                message="Navigated forward",
            )
        else:
            return NavigateResponse(
                success=False,
                url="",
                title="",
                message=f"Failed to go forward: {result.get('error', 'Unknown error')}",
            )

    except Exception as e:
        logger.error(f"Go forward error: {e}")
        return NavigateResponse(
            success=False,
            url="",
            title="",
            message=f"Error: {str(e)}",
        )


async def reload_page(params: ReloadParams) -> NavigateResponse:
    """Reload the current page."""
    executor = get_executor()

    try:
        hard_reload = "true" if params.hard else "false"
        code = f"""
        (async () => {{
            window.location.reload({hard_reload});
            await new Promise(resolve => setTimeout(resolve, 500));
            return {{
                url: window.location.href,
                title: document.title
            }};
        }})()
        """

        result = await asyncio.to_thread(executor.execute, code, 10.0)

        if result.get("ok"):
            data = result.get("result", {})
            return NavigateResponse(
                success=True,
                url=data.get("url", ""),
                title=data.get("title", ""),
                message="Page reloaded" + (" (hard)" if params.hard else ""),
            )
        else:
            return NavigateResponse(
                success=False,
                url="",
                title="",
                message=f"Failed to reload: {result.get('error', 'Unknown error')}",
            )

    except Exception as e:
        logger.error(f"Reload error: {e}")
        return NavigateResponse(
            success=False,
            url="",
            title="",
            message=f"Error: {str(e)}",
        )


async def scroll_to_top(params: EmptyParams) -> NavigateResponse:
    """Scroll to the top of the page."""
    executor = get_executor()

    try:
        code = """
        (function() {
            window.scrollTo({ top: 0, behavior: 'instant' });
            return {
                url: window.location.href,
                title: document.title
            };
        })()
        """

        result = await asyncio.to_thread(executor.execute, code, 5.0)

        if result.get("ok"):
            data = result.get("result", {})
            return NavigateResponse(
                success=True,
                url=data.get("url", ""),
                title=data.get("title", ""),
                message="Scrolled to top",
            )
        else:
            return NavigateResponse(
                success=False,
                url="",
                title="",
                message=f"Failed to scroll: {result.get('error', 'Unknown error')}",
            )

    except Exception as e:
        logger.error(f"Scroll to top error: {e}")
        return NavigateResponse(
            success=False,
            url="",
            title="",
            message=f"Error: {str(e)}",
        )


async def scroll_to_bottom(params: EmptyParams) -> NavigateResponse:
    """Scroll to the bottom of the page."""
    executor = get_executor()

    try:
        code = """
        (function() {
            window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' });
            return {
                url: window.location.href,
                title: document.title
            };
        })()
        """

        result = await asyncio.to_thread(executor.execute, code, 5.0)

        if result.get("ok"):
            data = result.get("result", {})
            return NavigateResponse(
                success=True,
                url=data.get("url", ""),
                title=data.get("title", ""),
                message="Scrolled to bottom",
            )
        else:
            return NavigateResponse(
                success=False,
                url="",
                title="",
                message=f"Failed to scroll: {result.get('error', 'Unknown error')}",
            )

    except Exception as e:
        logger.error(f"Scroll to bottom error: {e}")
        return NavigateResponse(
            success=False,
            url="",
            title="",
            message=f"Error: {str(e)}",
        )


async def page_up(params: EmptyParams) -> NavigateResponse:
    """Scroll up by one viewport height."""
    executor = get_executor()

    try:
        code = """
        (function() {
            window.scrollBy({ top: -window.innerHeight, behavior: 'instant' });
            return {
                url: window.location.href,
                title: document.title
            };
        })()
        """

        result = await asyncio.to_thread(executor.execute, code, 5.0)

        if result.get("ok"):
            data = result.get("result", {})
            return NavigateResponse(
                success=True,
                url=data.get("url", ""),
                title=data.get("title", ""),
                message="Scrolled up one page",
            )
        else:
            return NavigateResponse(
                success=False,
                url="",
                title="",
                message=f"Failed to scroll: {result.get('error', 'Unknown error')}",
            )

    except Exception as e:
        logger.error(f"Page up error: {e}")
        return NavigateResponse(
            success=False,
            url="",
            title="",
            message=f"Error: {str(e)}",
        )


async def page_down(params: EmptyParams) -> NavigateResponse:
    """Scroll down by one viewport height."""
    executor = get_executor()

    try:
        code = """
        (function() {
            window.scrollBy({ top: window.innerHeight, behavior: 'instant' });
            return {
                url: window.location.href,
                title: document.title
            };
        })()
        """

        result = await asyncio.to_thread(executor.execute, code, 5.0)

        if result.get("ok"):
            data = result.get("result", {})
            return NavigateResponse(
                success=True,
                url=data.get("url", ""),
                title=data.get("title", ""),
                message="Scrolled down one page",
            )
        else:
            return NavigateResponse(
                success=False,
                url="",
                title="",
                message=f"Failed to scroll: {result.get('error', 'Unknown error')}",
            )

    except Exception as e:
        logger.error(f"Page down error: {e}")
        return NavigateResponse(
            success=False,
            url="",
            title="",
            message=f"Error: {str(e)}",
        )


# ── Sitemap handler ──────────────────────────────────────────────────


async def get_sitemap(params: "SitemapParams") -> "SitemapResponse":
    """
    Fetch and return a site's sitemap with page titles.

    Auto-discovers the sitemap via robots.txt, fetches all entries
    (flattening sitemap indexes), enriches with page titles, and
    returns structured data. Results are cached for 1 hour.
    """
    from urllib.parse import urlparse

    from inspekt.core.schemas.navigation import SitemapEntryItem, SitemapResponse
    from inspekt.services.sitemap_service import (
        detect_site_name,
        discover_sitemap,
        fetch_sitemap,
        fetch_titles,
        load_from_cache,
        save_to_cache,
        strip_site_name,
    )

    # Determine origin
    from inspekt.services.browser_url import BrowserURLError, InternalURLError, resolve_origin

    try:
        origin = await asyncio.to_thread(resolve_origin, params.url)
    except (BrowserURLError, InternalURLError) as e:
        return SitemapResponse(success=False, message=str(e))

    # Check cache
    sitemap_result = None
    if not params.refresh:
        sitemap_result = load_from_cache(origin)

    # Fetch if no cache
    if sitemap_result is None:
        sitemap_urls, discovery_method = discover_sitemap(origin)
        if not sitemap_urls:
            return SitemapResponse(
                success=False, origin=origin, message="No sitemap found"
            )

        sitemap_result = fetch_sitemap(sitemap_urls[0], flatten=True)
        seen = {e.loc for e in sitemap_result.entries}
        for extra_url in sitemap_urls[1:]:
            extra = fetch_sitemap(extra_url, flatten=True)
            for entry in extra.entries:
                if entry.loc not in seen:
                    sitemap_result.entries.append(entry)
                    seen.add(entry.loc)

        if len(sitemap_urls) > 1:
            sitemap_result.source_url = f"{sitemap_urls[0]} (+{len(sitemap_urls) - 1} more)"

        sitemap_result.discovered_via = discovery_method
        sitemap_result.origin = origin

        # Fetch titles
        if sitemap_result.entries:
            await asyncio.to_thread(
                fetch_titles, sitemap_result.entries, 30, 10.0
            )

            site_name = detect_site_name(sitemap_result.entries)
            if site_name:
                for entry in sitemap_result.entries:
                    if entry.title:
                        entry.title = strip_site_name(entry.title, site_name)

        save_to_cache(sitemap_result)

    # Apply language filter
    entries = sitemap_result.entries
    if params.lang:
        lang_prefix = f"/{params.lang.strip('/')}/"
        entries = [e for e in entries if lang_prefix in urlparse(e.loc).path]

    # Detect languages
    from inspekt.services.sitemap_service import detect_languages
    languages = sorted(detect_languages(sitemap_result.entries))

    # Build response
    items = []
    for i, entry in enumerate(entries, 1):
        parsed = urlparse(entry.loc)
        items.append(SitemapEntryItem(
            index=i,
            url=entry.loc,
            title=entry.title,
            lastmod=entry.lastmod,
            path=parsed.path or "/",
        ))

    return SitemapResponse(
        success=True,
        origin=sitemap_result.origin,
        source_url=sitemap_result.source_url,
        total_urls=len(items),
        languages=languages,
        entries=items,
    )
