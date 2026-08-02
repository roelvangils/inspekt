"""
Unified navigation service for CLI, MCP, and API.

This module provides a single source of truth for browser navigation logic,
used by all interfaces (CLI commands, MCP tools, HTTP API endpoints).

ARCHITECTURE:
-------------
1. PRIMARY: Bridge-based navigation (via browser extension)
   - Works on all platforms
   - Uses WebSocket to talk to content script → background script → chrome.tabs.update()
   - Chrome: Uses hybrid event+polling detection for reliability
   - Firefox: Uses polling-only detection (events unreliable in Firefox)

2. FALLBACK: AppleScript-based navigation (macOS only)
   - Automatically activated if bridge navigation fails
   - Uses osascript to directly control Safari/Chrome/Firefox/Brave/Edge
   - Requires Automation permission in System Settings

This fallback mechanism ensures navigation works even if:
- The browser extension isn't loaded
- The WebSocket connection is unstable
- The bridge server is unavailable
"""

from __future__ import annotations

import logging
import platform

import aiohttp

from inspekt.config import get_bridge_port

logger = logging.getLogger(__name__)


async def navigate(
    url: str,
    wait_for: str | None = None,
    timeout: int = 30,
    use_applescript_fallback: bool = True,
) -> dict:
    """
    Navigate browser to a URL.

    This is the single source of truth for navigation logic.
    Called by MCP tools, CLI handlers, and API endpoints.

    Args:
        url: Target URL (must start with http:// or https://)
        wait_for: Wait condition - 'load' (DOMContentLoaded) or 'networkidle' (no network activity)
        timeout: Timeout in seconds (default 30)
        use_applescript_fallback: If True and on macOS, try AppleScript when bridge fails (default True)

    Returns:
        dict with keys:
            - success: bool - Whether navigation succeeded
            - url: str - Final URL after navigation (may differ due to redirects)
            - title: str - Page title
            - message: str - Success or error message
    """
    # Validate URL
    if not url.startswith(("http://", "https://")):
        return {
            "success": False,
            "url": url,
            "title": "",
            "message": "URL must start with http:// or https://",
        }

    # Try bridge-based navigation first
    result = await _navigate_via_bridge(url, wait_for, timeout)

    # If failed and on macOS, try AppleScript fallback
    if not result["success"] and use_applescript_fallback and platform.system() == "Darwin":
        logger.info("Bridge navigation failed, trying AppleScript fallback…")

        try:
            from inspekt.services.applescript_navigation import navigate_applescript

            applescript_result = navigate_applescript(url)

            if applescript_result["success"]:
                logger.info("AppleScript fallback succeeded")
                return applescript_result
            else:
                # AppleScript also failed, return original bridge error
                # (it's usually more informative)
                logger.warning(f"AppleScript fallback also failed: {applescript_result['message']}")
        except ImportError:
            logger.warning("AppleScript navigation module not available")
        except Exception as e:
            logger.warning(f"AppleScript fallback error: {e}")

    return result


async def _navigate_via_bridge(
    url: str,
    wait_for: str | None,
    timeout: int,
) -> dict:
    """
    Navigate browser to URL using the bridge WebSocket/HTTP mechanism.

    This is the primary navigation method that works through the browser extension.

    Args:
        url: Target URL
        wait_for: Wait condition ('load' or 'networkidle')
        timeout: Timeout in seconds

    Returns:
        dict with success, url, title, message
    """
    bridge_port = get_bridge_port()
    logger.info(f"Navigating to {url} (timeout={timeout}s, wait_for={wait_for})")

    try:
        async with aiohttp.ClientSession() as session, session.post(
            f"http://127.0.0.1:{bridge_port}/navigate",
            json={
                "url": url,
                "waitFor": wait_for,
                "timeout": timeout,
            },
            timeout=aiohttp.ClientTimeout(total=timeout + 5),
        ) as response:
            result = await response.json()

        if result.get("ok"):
            final_url = result.get("url", url)
            title = result.get("title", "")
            logger.info(f"Navigation successful: {final_url}")
            return {
                "success": True,
                "url": final_url,
                "title": title,
                "message": "Navigation successful",
            }
        else:
            error_msg = result.get("error", "Unknown error")
            logger.warning(f"Navigation failed: {error_msg}")
            return {
                "success": False,
                "url": result.get("url", url),
                "title": result.get("title", ""),
                "message": f"Navigation failed: {error_msg}",
            }

    except aiohttp.ClientError as e:
        logger.error(f"Bridge connection error during navigation: {e}")
        return {
            "success": False,
            "url": url,
            "title": "",
            "message": f"Bridge connection error: {e}. Is 'inspekt start' running?",
        }
    except TimeoutError:
        logger.error(f"Navigation timed out after {timeout}s")
        return {
            "success": False,
            "url": url,
            "title": "",
            "message": f"Navigation timed out after {timeout}s",
        }
    except Exception as e:
        logger.error(f"Unexpected navigation error: {e}")
        return {
            "success": False,
            "url": url,
            "title": "",
            "message": f"Error: {e!s}",
        }
