"""
Inspection command handlers.

Implements: get_page_info, take_screenshot
"""

from __future__ import annotations

import asyncio
import json
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

        # Apply redaction if enabled (default: True)
        redact_enabled = params.redact if params.redact is not None else True
        if redact_enabled:
            try:
                redact_script = await script_loader.load_script_async("screenshot_redact.js")
                redact_options = {
                    "style": params.redact_style or "bar",
                    "scope": params.selector if params.target == "node" else None,
                }
                redact_code = redact_script.replace("OPTIONS_PLACEHOLDER", json.dumps(redact_options))
                await asyncio.to_thread(executor.execute, redact_code, 10.0)
            except FileNotFoundError:
                pass  # Redaction script not available, continue without it
            except Exception as e:
                logger.warning(f"Redaction failed, continuing without it: {e}")

        # Build options object for the script
        options = {
            "selector": params.selector or "",
            "format": params.format or "png",
            "quality": params.quality or 90,
            "margin": params.margin or 0,
            "isolate": params.isolate or False,
        }

        # Substitute placeholders
        # MODE_PLACEHOLDER is a string literal in quotes
        # OPTIONS_PLACEHOLDER is a JSON object (no quotes)
        mode = params.target or "viewport"
        script = script.replace("'MODE_PLACEHOLDER'", f"'{mode}'")
        script = script.replace("OPTIONS_PLACEHOLDER", json.dumps(options))

        result = await asyncio.to_thread(executor.execute, script, 30.0)

        if result.get("ok"):
            data = result.get("result", {})
            # Note: The screenshot script returns 'dataUrl' not 'data'
            # Extract just the base64 part, removing the data URI prefix if present
            data_url = data.get("dataUrl") or data.get("data")
            if data_url and data_url.startswith("data:"):
                # Strip the "data:image/png;base64," prefix to get raw base64
                data_url = data_url.split(",", 1)[1] if "," in data_url else data_url

            # If we got ok=True but no actual data, something went wrong
            # (e.g., element picker was cancelled or timed out)
            if not data_url:
                error_msg = data.get("error") or data.get("message") or "No screenshot data returned"
                return TakeScreenshotResponse(
                    success=False,
                    data=None,
                    format=params.format or "png",
                    width=0,
                    height=0,
                    message=error_msg,
                )

            return TakeScreenshotResponse(
                success=True,
                data=data_url,
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
            message=f"Error: {e!s}",
        )
