"""
Navigation command handlers.

Implements: navigate_to_url, go_back, go_forward, reload_page
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

    Supports wait conditions for page load:
    - 'load': Wait for DOMContentLoaded
    - 'networkidle': Wait for network to be idle
    """
    executor = get_executor()

    try:
        # Validate URL
        if not params.url.startswith(("http://", "https://")):
            return NavigateResponse(
                success=False,
                url=params.url,
                title="",
                message="URL must start with http:// or https://",
            )

        import json

        wait_code = ""
        if params.wait_for == "load":
            wait_code = "await new Promise(resolve => { if (document.readyState === 'complete') resolve(); else window.addEventListener('load', resolve); });"
        elif params.wait_for == "networkidle":
            wait_code = "await new Promise(resolve => setTimeout(resolve, 2000));"

        code = f"""
        (async () => {{
            window.location.href = {json.dumps(params.url)};
            {wait_code}
            return {{
                url: window.location.href,
                title: document.title
            }};
        }})()
        """

        result = await asyncio.to_thread(
            executor.execute, code, float(params.timeout or 30)
        )

        if result.get("ok"):
            data = result.get("result", {})
            return NavigateResponse(
                success=True,
                url=data.get("url", params.url),
                title=data.get("title", ""),
                message="Navigation successful",
            )
        else:
            return NavigateResponse(
                success=False,
                url=params.url,
                title="",
                message=f"Navigation failed: {result.get('error', 'Unknown error')}",
            )

    except Exception as e:
        logger.error(f"Navigation error: {e}")
        return NavigateResponse(
            success=False,
            url=params.url,
            title="",
            message=f"Error: {str(e)}",
        )


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
