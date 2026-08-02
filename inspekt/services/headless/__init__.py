"""
Headless browser infrastructure for Inspekt.

This module provides a command-agnostic API for running browser operations
in headless Chrome, with optional session mirroring from a live browser.

Main interface:
    HeadlessContext - Async context manager for headless browser operations

Example usage:
    async with HeadlessContext(url="https://example.com", mirror_session=True) as ctx:
        # Run accessibility tests
        results = await ctx.execute_script(axe_script)

        # Take screenshots
        image = await ctx.screenshot(selector=".hero", isolate=True)

        # Extract content
        html = await ctx.get_html()
"""

from inspekt.services.headless.cdp import CDPClient, CDPSession
from inspekt.services.headless.chrome import HeadlessChrome
from inspekt.services.headless.context import HeadlessContext
from inspekt.services.headless.pool import (
    HeadlessChromePool,
    PooledHeadlessContext,
    get_pooled_chrome,
)
from inspekt.services.headless.state import BrowserState, StateMirror

__all__ = [
    "HeadlessContext",
    "BrowserState",
    "StateMirror",
    "HeadlessChrome",
    "CDPClient",
    "CDPSession",
    "HeadlessChromePool",
    "PooledHeadlessContext",
    "get_pooled_chrome",
]
