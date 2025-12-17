"""
Storage command handlers.

Implements: get_selected_text, get_cookies, set_cookie
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from inspekt.core.commands.base import EmptyParams
from inspekt.core.schemas.storage import (
    CookieInfo,
    GetCookiesResponse,
    GetSelectedTextParams,
    GetSelectedTextResponse,
    SetCookieParams,
    SetCookieResponse,
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


async def get_selected_text(params: GetSelectedTextParams) -> GetSelectedTextResponse:
    """
    Get the currently selected text from the page.

    Returns the selection in the requested format (text, HTML, or markdown).
    """
    executor = get_executor()
    script_loader = get_script_loader()

    try:
        # Load get_selection.js script
        script = await script_loader.load_script_async("get_selection.js")

        result = await asyncio.to_thread(executor.execute, script, 5.0)

        if result.get("ok"):
            data = result.get("result", {})
            content_format = params.format or "text"

            # Extract content based on format
            content = data.get(content_format, data.get("text", ""))

            return GetSelectedTextResponse(
                success=True,
                content=content,
                format=content_format,
                length=len(content),
            )
        else:
            return GetSelectedTextResponse(
                success=False,
                content="",
                format=params.format or "text",
                length=0,
            )

    except Exception as e:
        logger.error(f"Get selected text error: {e}")
        return GetSelectedTextResponse(
            success=False,
            content="",
            format=params.format or "text",
            length=0,
        )


async def get_cookies(params: EmptyParams) -> GetCookiesResponse:
    """
    Get all cookies for the current page.

    Returns detailed cookie information including security attributes.
    """
    executor = get_executor()
    script_loader = get_script_loader()

    try:
        # Load cookies.js script
        script = await script_loader.load_script_async("cookies.js")

        result = await asyncio.to_thread(executor.execute, script, 10.0)

        if result.get("ok"):
            data = result.get("result", {})
            cookies_data = data.get("cookies", [])

            # Convert to Pydantic models
            cookies = [
                CookieInfo(
                    name=cookie.get("name", ""),
                    value=cookie.get("value", ""),
                    domain=cookie.get("domain", ""),
                    path=cookie.get("path", "/"),
                    secure=cookie.get("secure", False),
                    httpOnly=cookie.get("httpOnly", False),
                    sameSite=cookie.get("sameSite"),
                    expires=cookie.get("expires"),
                    session=cookie.get("session", True),
                    size=cookie.get("size", 0),
                    party=cookie.get("party"),
                )
                for cookie in cookies_data
            ]

            return GetCookiesResponse(
                success=True,
                cookies=cookies,
                count=len(cookies),
            )
        else:
            return GetCookiesResponse(success=False, cookies=[], count=0)

    except Exception as e:
        logger.error(f"Get cookies error: {e}")
        return GetCookiesResponse(success=False, cookies=[], count=0)


async def set_cookie(params: SetCookieParams) -> SetCookieResponse:
    """
    Set a cookie with the specified attributes.

    Creates or updates a cookie with full control over security attributes.
    """
    executor = get_executor()

    try:
        # Build cookie string
        cookie_parts = [f"{params.name}={params.value}"]

        if params.domain:
            cookie_parts.append(f"domain={params.domain}")
        if params.path:
            cookie_parts.append(f"path={params.path}")
        if params.secure:
            cookie_parts.append("secure")
        if params.sameSite:
            cookie_parts.append(f"samesite={params.sameSite}")
        if params.expires:
            cookie_parts.append(f"expires={params.expires}")

        cookie_string = "; ".join(cookie_parts)

        code = f"""
        (function() {{
            document.cookie = {json.dumps(cookie_string)};
            return {{ success: true }};
        }})()
        """

        result = await asyncio.to_thread(executor.execute, code, 5.0)

        if result.get("ok"):
            return SetCookieResponse(success=True, message="Cookie set successfully")
        else:
            return SetCookieResponse(
                success=False, message=result.get("error", "Failed to set cookie")
            )

    except Exception as e:
        logger.error(f"Set cookie error: {e}")
        return SetCookieResponse(success=False, message=f"Error: {str(e)}")
