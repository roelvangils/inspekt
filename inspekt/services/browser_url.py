"""
Shared utilities for resolving the current page URL from the browser.

Provides consistent error handling and internal URL detection across
all CLI commands and MCP handlers that need the current page's URL.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Schemes and hostnames that indicate internal/non-web pages
_INTERNAL_SCHEMES = {"inspekt", "chrome", "chrome-error", "about", "data", "blob", "file"}
_INTERNAL_HOSTS = {"inspekt", "localhost"}


class BrowserURLError(Exception):
    """Raised when the browser URL cannot be retrieved."""
    pass


class InternalURLError(Exception):
    """Raised when the browser is on an internal/non-web page."""
    pass


def _validate_url(url: str) -> None:
    """Check if a URL is a real website. Raises InternalURLError if not."""
    parsed = urlparse(url)
    if parsed.scheme in _INTERNAL_SCHEMES or parsed.hostname in _INTERNAL_HOSTS:
        raise InternalURLError("This command requires a real website (http/https)")


def _execute_and_extract(js_expression: str) -> str:
    """Execute a JS expression via the bridge and extract the string result."""
    from inspekt.services.bridge_executor import get_executor

    executor = get_executor()
    result = executor.execute(js_expression, timeout=5.0)

    if not result.get("ok"):
        raise BrowserURLError(
            f"Could not get current page URL: {result.get('error')}"
        )

    value = result.get("result", "")
    if isinstance(value, dict):
        value = value.get("result", "")

    value = str(value)
    if not value or value == "null":
        raise BrowserURLError("No page loaded in the browser")

    return value


def resolve_origin(override_url: str | None = None) -> str:
    """
    Get the origin (scheme://host) from the browser or an override URL.

    Raises:
        BrowserURLError: If the URL can't be retrieved
        InternalURLError: If the browser is on an internal page
    """
    if override_url:
        parsed = urlparse(override_url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return f"https://{override_url}"

    origin = _execute_and_extract("window.location.origin")
    _validate_url(origin)
    return origin


def resolve_url(override_url: str | None = None) -> str:
    """
    Get the full href from the browser or an override URL.

    Raises:
        BrowserURLError: If the URL can't be retrieved
        InternalURLError: If the browser is on an internal page
    """
    if override_url:
        parsed = urlparse(override_url)
        if parsed.scheme and parsed.netloc:
            return override_url
        return f"https://{override_url}"

    url = _execute_and_extract("window.location.href")
    _validate_url(url)
    return url
