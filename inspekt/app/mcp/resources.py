"""
MCP Resource Definitions

Implements read-only MCP resources that expose current browser state.
Resources are automatically cached and updated when content changes.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from mcp.types import Resource, TextContent, ImageContent, EmbeddedResource

from inspekt.services.bridge_executor import BridgeExecutor

logger = logging.getLogger(__name__)


class ResourceCache:
    """Simple TTL-based cache for resource data."""

    def __init__(self, ttl_seconds: int = 5):
        """
        Initialize resource cache.

        Args:
            ttl_seconds: Time-to-live for cached data in seconds (default: 5)
        """
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[Any, datetime]] = {}

    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired."""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self.ttl_seconds):
                return value
            # Expired, remove from cache
            del self._cache[key]
        return None

    def set(self, key: str, value: Any) -> None:
        """Set cached value with current timestamp."""
        self._cache[key] = (value, datetime.now())

    def invalidate(self, key: Optional[str] = None) -> None:
        """Invalidate specific key or entire cache."""
        if key:
            self._cache.pop(key, None)
        else:
            self._cache.clear()


class ResourceProvider:
    """Provides MCP resources backed by browser state."""

    def __init__(self, executor: BridgeExecutor, cache_ttl: int = 5):
        """
        Initialize resource provider.

        Args:
            executor: BridgeExecutor instance for browser communication
            cache_ttl: Cache time-to-live in seconds (default: 5)
        """
        self.executor = executor
        self.cache = ResourceCache(ttl_seconds=cache_ttl)

    async def list_resources(self) -> list[Resource]:
        """
        List all available resources.

        Returns:
            List of Resource objects describing available resources
        """
        return [
            Resource(
                uri="inspekt-mcp://current-url",
                name="Current Page URL",
                description="The URL of the currently active browser tab",
                mimeType="text/plain",
            ),
            Resource(
                uri="inspekt-mcp://page-title",
                name="Page Title",
                description="The title of the currently active browser tab",
                mimeType="text/plain",
            ),
            Resource(
                uri="inspekt-mcp://page-metadata",
                name="Page Metadata",
                description="Extended metadata about the current page (JSON)",
                mimeType="application/json",
            ),
            Resource(
                uri="inspekt-mcp://browser-info",
                name="Browser Information",
                description="Information about the connected browser (JSON)",
                mimeType="application/json",
            ),
            Resource(
                uri="inspekt-mcp://connection-status",
                name="Connection Status",
                description="Bridge server connection status and health (JSON)",
                mimeType="application/json",
            ),
        ]

    async def read_resource(self, uri: str) -> str | bytes:
        """
        Read a resource by URI.

        Args:
            uri: Resource URI (e.g., "inspekt://current-url")

        Returns:
            Resource content as string or bytes

        Raises:
            ValueError: If resource URI is not recognized
            RuntimeError: If resource cannot be read from browser
        """
        # Convert URI to string if it's a Pydantic URL object
        uri_str = str(uri)

        # Check cache first
        cached = self.cache.get(uri_str)
        if cached is not None:
            return cached

        # Fetch resource based on URI
        logger.info(f"Reading resource URI: '{uri_str}' (original type: {type(uri).__name__})")

        if uri_str == "inspekt-mcp://current-url":
            content = await self._get_current_url()
        elif uri_str == "inspekt-mcp://page-title":
            content = await self._get_page_title()
        elif uri_str == "inspekt-mcp://page-metadata":
            content = await self._get_page_metadata()
        elif uri_str == "inspekt-mcp://browser-info":
            content = await self._get_browser_info()
        elif uri_str == "inspekt-mcp://connection-status":
            content = await self._get_connection_status()
        else:
            logger.error(f"No match found for URI: '{uri_str}' (repr: {repr(uri_str)})")
            raise ValueError(f"Unknown resource URI: {uri_str}")

        # Cache and return
        self.cache.set(uri_str, content)
        return content

    # ========================================================================
    # Resource Implementations
    # ========================================================================

    async def _get_current_url(self) -> str:
        """Get current page URL."""
        from inspekt.services.browser_url import BrowserURLError, InternalURLError, resolve_url

        try:
            return await asyncio.to_thread(resolve_url)
        except (BrowserURLError, InternalURLError) as e:
            logger.error(f"Error getting current URL: {e}")
            raise RuntimeError(str(e))

    async def _get_page_title(self) -> str:
        """Get current page title."""
        try:
            result = await asyncio.to_thread(
                self.executor.execute, "document.title", 5.0
            )
            if result.get("ok"):
                return result.get("result", "")
            else:
                raise RuntimeError(f"Failed to get title: {result.get('error', 'Unknown error')}")
        except Exception as e:
            logger.error(f"Error getting page title: {e}")
            raise RuntimeError(f"Failed to read page title: {e}")

    async def _get_page_metadata(self) -> str:
        """Get extended page metadata as JSON."""
        try:
            # Execute JavaScript to gather page metadata
            code = """
            (function() {
                const getMeta = (name) => {
                    const meta = document.querySelector(`meta[name="${name}"], meta[property="${name}"]`);
                    return meta ? meta.content : null;
                };

                return {
                    url: window.location.href,
                    title: document.title,
                    description: getMeta('description'),
                    language: document.documentElement.lang || null,
                    author: getMeta('author'),
                    keywords: getMeta('keywords')?.split(',').map(k => k.trim()) || [],
                    og_title: getMeta('og:title'),
                    og_description: getMeta('og:description'),
                    og_image: getMeta('og:image'),
                    canonical_url: document.querySelector('link[rel="canonical"]')?.href || null,
                    viewport_width: window.innerWidth,
                    viewport_height: window.innerHeight,
                    scroll_x: window.scrollX,
                    scroll_y: window.scrollY,
                    timestamp: new Date().toISOString()
                };
            })()
            """
            result = await asyncio.to_thread(
                self.executor.execute, code, 10.0
            )
            if result.get("ok"):
                # Return as formatted JSON
                return json.dumps(result.get("result", {}), indent=2)
            else:
                raise RuntimeError(f"Failed to get metadata: {result.get('error', 'Unknown error')}")
        except Exception as e:
            logger.error(f"Error getting page metadata: {e}")
            raise RuntimeError(f"Failed to read page metadata: {e}")

    async def _get_browser_info(self) -> str:
        """Get browser information as JSON."""
        try:
            code = """
            (function() {
                return {
                    user_agent: navigator.userAgent,
                    platform: navigator.platform,
                    language: navigator.language,
                    languages: navigator.languages || [],
                    online: navigator.onLine,
                    cookie_enabled: navigator.cookieEnabled,
                    viewport_width: window.innerWidth,
                    viewport_height: window.innerHeight,
                    screen_width: window.screen.width,
                    screen_height: window.screen.height,
                    color_depth: window.screen.colorDepth,
                    pixel_ratio: window.devicePixelRatio || 1
                };
            })()
            """
            result = await asyncio.to_thread(
                self.executor.execute, code, 10.0
            )
            if result.get("ok"):
                return json.dumps(result.get("result", {}), indent=2)
            else:
                raise RuntimeError(f"Failed to get browser info: {result.get('error', 'Unknown error')}")
        except Exception as e:
            logger.error(f"Error getting browser info: {e}")
            raise RuntimeError(f"Failed to read browser info: {e}")

    async def _get_connection_status(self) -> str:
        """Get connection status and health information as JSON."""
        try:
            # Get bridge server status (run in thread since it's synchronous)
            bridge_connected = await asyncio.to_thread(
                self.executor.is_server_running
            )

            status = {
                "bridge_connected": bridge_connected,
                "timestamp": datetime.now().isoformat()
            }

            # Try to get additional server health info
            try:
                server_status = await asyncio.to_thread(
                    self.executor.client.get_status
                )
                if server_status:
                    status["server_info"] = server_status
            except Exception:
                pass  # Server status not critical

            return json.dumps(status, indent=2)
        except Exception as e:
            logger.error(f"Error getting connection status: {e}")
            # Even if there's an error, return what we know
            return json.dumps({
                "bridge_connected": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }, indent=2)
