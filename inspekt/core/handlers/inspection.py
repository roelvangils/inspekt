"""
Inspection command handlers.

Implements: get_page_info, take_screenshot
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from inspekt.core.commands.base import EmptyParams
from inspekt.core.schemas.inspection import (
    GetPageInfoResponse,
    TakeScreenshotParams,
    TakeScreenshotResponse,
)

if TYPE_CHECKING:
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


async def get_page_info(params: EmptyParams) -> GetPageInfoResponse:
    """
    Get lightweight current page information.

    Returns URL, title, viewport dimensions, and scroll position.
    This is a fast operation suitable for frequent status checks.
    """
    executor = get_executor()

    try:
        code = """
        ({
            url: window.location.href,
            title: document.title,
            viewport_width: window.innerWidth,
            viewport_height: window.innerHeight,
            scroll_x: window.scrollX,
            scroll_y: window.scrollY
        })
        """

        result = await asyncio.to_thread(executor.execute, code, 5.0)

        if result.get("ok"):
            data = result.get("result", {})
            return GetPageInfoResponse(
                success=True,
                url=data.get("url", ""),
                title=data.get("title", ""),
                viewport_width=int(data.get("viewport_width", 0)),
                viewport_height=int(data.get("viewport_height", 0)),
                scroll_x=int(data.get("scroll_x", 0)),
                scroll_y=int(data.get("scroll_y", 0)),
            )
        else:
            return GetPageInfoResponse(
                success=False,
                url="",
                title="",
                viewport_width=0,
                viewport_height=0,
                scroll_x=0,
                scroll_y=0,
            )

    except Exception as e:
        logger.error(f"Get page info error: {e}")
        return GetPageInfoResponse(
            success=False,
            url="",
            title="",
            viewport_width=0,
            viewport_height=0,
            scroll_x=0,
            scroll_y=0,
        )


async def take_screenshot(params: TakeScreenshotParams) -> TakeScreenshotResponse:
    """
    Take a screenshot of the viewport, full page, or specific element.

    Captures the current visual state of the page. Returns base64-encoded
    image data suitable for embedding or saving.
    """
    executor = get_executor()
    script_loader = get_script_loader()

    try:
        # Load screenshot script
        try:
            script = await script_loader.load_script_async("screenshot_unified.js")
        except FileNotFoundError:
            return TakeScreenshotResponse(
                success=False,
                data=None,
                format=params.format or "png",
                width=0,
                height=0,
                message="Screenshot script not available",
            )

        # Substitute placeholders
        script = script_loader.substitute_placeholders(
            script,
            {
                "TARGET": params.target or "viewport",
                "SELECTOR": params.selector or "",
                "FORMAT": params.format or "png",
                "QUALITY": params.quality or 90,
            },
        )

        result = await asyncio.to_thread(executor.execute, script, 30.0)

        if result.get("ok"):
            data = result.get("result", {})
            return TakeScreenshotResponse(
                success=True,
                data=data.get("data"),
                format=data.get("format", params.format or "png"),
                width=data.get("width", 0),
                height=data.get("height", 0),
                message="Screenshot captured",
            )
        else:
            return TakeScreenshotResponse(
                success=False,
                data=None,
                format=params.format or "png",
                width=0,
                height=0,
                message=result.get("error", "Screenshot failed"),
            )

    except Exception as e:
        logger.error(f"Screenshot error: {e}")
        return TakeScreenshotResponse(
            success=False,
            data=None,
            format=params.format or "png",
            width=0,
            height=0,
            message=f"Error: {str(e)}",
        )
