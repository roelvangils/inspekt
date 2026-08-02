"""AppleScript-based navigation fallback for macOS.

This module provides a fallback mechanism for browser navigation when the
extension-based bridge fails. It uses AppleScript to directly control
Safari, Chrome, Firefox, Brave, and Edge browsers.

WHEN IS THIS USED?
------------------
This module is called automatically by inspekt/services/navigation.py when:
1. Bridge-based navigation fails (extension not loaded, WebSocket issues, etc.)
2. Running on macOS (Darwin)

HOW IT WORKS:
-------------
1. Get the active browser from bridge status (which browser has the extension connected)
2. Generate browser-specific AppleScript to set the URL
3. Execute via osascript and return the result

REQUIREMENTS:
-------------
- macOS only (uses osascript)
- Browser must be running
- Terminal/Claude Code must have Automation permission for the browser
  (System Settings > Privacy & Security > Automation)

Note: Firefox has limited AppleScript support - it can only "open location",
not set URL on existing tab like Chromium browsers.
"""

from __future__ import annotations

import logging
import platform
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


def get_active_browser() -> str | None:
    """
    Get the most recently active browser from bridge status.

    Returns:
        Browser name (Chrome, Safari, Firefox, Edge, Brave) or None
    """
    try:
        from inspekt.client import BridgeClient

        client = BridgeClient()
        status = client.get_status()
        browsers = status.get("browsers", [])

        # Find most recently active browser
        for b in browsers:
            if b.get("is_most_recent"):
                return b.get("browser_name")

        # Fallback to first browser if none marked as most recent
        return browsers[0].get("browser_name") if browsers else None
    except Exception as e:
        logger.debug(f"Could not get active browser from bridge: {e}")
        return None


def navigate_applescript(url: str, browser_name: str | None = None) -> dict:
    """
    Navigate to URL using AppleScript (macOS only).

    This function uses AppleScript to control the browser directly,
    bypassing the extension-based bridge. It's used as a fallback
    when the bridge-based navigation fails.

    Args:
        url: URL to navigate to (must start with http:// or https://)
        browser_name: Browser to target. If None, auto-detects from bridge status.

    Returns:
        dict with keys:
            - success: bool - Whether navigation succeeded
            - url: str - The URL that was navigated to
            - title: str - Page title (if available)
            - message: str - Success or error message
    """
    # Check platform
    if platform.system() != "Darwin":
        return {
            "success": False,
            "url": url,
            "title": "",
            "message": "AppleScript fallback only available on macOS",
        }

    # Validate URL
    if not url.startswith(("http://", "https://")):
        return {
            "success": False,
            "url": url,
            "title": "",
            "message": "URL must start with http:// or https://",
        }

    # Auto-detect browser if not specified
    if browser_name is None:
        browser_name = get_active_browser()
        logger.info(f"Auto-detected browser: {browser_name}")

    if browser_name is None:
        return {
            "success": False,
            "url": url,
            "title": "",
            "message": "Could not determine active browser. Is a browser connected to Inspekt?",
        }

    # Map browser names to AppleScript app names
    app_names = {
        "Chrome": "Google Chrome",
        "Firefox": "Firefox",
        "Safari": "Safari",
        "Brave": "Brave Browser",
        "Edge": "Microsoft Edge",
    }

    app_name = app_names.get(browser_name, browser_name)

    # Escape URL for AppleScript (handle special characters)
    safe_url = url.replace('"', '\\"')

    # Build browser-specific AppleScript
    if browser_name == "Safari":
        script = f'''
        tell application "Safari"
            activate
            if (count of windows) = 0 then
                make new document with properties {{URL:"{safe_url}"}}
            else
                set URL of current tab of front window to "{safe_url}"
            end if
            delay 1
            return title of current tab of front window
        end tell
        '''
    elif browser_name == "Firefox":
        # Firefox has limited AppleScript support - use open location
        script = f'''
        tell application "Firefox"
            activate
            open location "{safe_url}"
            delay 2
            return "Navigation initiated"
        end tell
        '''
    else:
        # Chromium-based browsers (Chrome, Brave, Edge)
        script = f'''
        tell application "{app_name}"
            activate
            if (count of windows) = 0 then
                make new window
            end if
            set URL of active tab of front window to "{safe_url}"
            delay 1
            return title of active tab of front window
        end tell
        '''

    logger.info(f"Executing AppleScript navigation to {url} in {browser_name}")

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=15,  # Allow time for page to start loading
        )

        if result.returncode == 0:
            title = result.stdout.strip()
            logger.info(f"AppleScript navigation successful: {title}")
            return {
                "success": True,
                "url": url,
                "title": title,
                "message": f"Navigation successful (AppleScript → {browser_name})",
            }
        else:
            error_msg = result.stderr.strip()
            logger.warning(f"AppleScript navigation failed: {error_msg}")

            # Provide helpful error messages for common issues
            if "not running" in error_msg.lower():
                error_msg = f"{browser_name} is not running. Please open the browser first."
            elif "not allowed" in error_msg.lower() or "-1743" in error_msg:
                error_msg = (
                    f"Automation permission denied. Please allow Terminal/Claude "
                    f"to control {browser_name} in System Settings > Privacy & Security > Automation."
                )

            return {
                "success": False,
                "url": url,
                "title": "",
                "message": f"AppleScript error: {error_msg}",
            }

    except subprocess.TimeoutExpired:
        logger.error("AppleScript navigation timed out")
        return {
            "success": False,
            "url": url,
            "title": "",
            "message": "AppleScript timed out waiting for browser response",
        }
    except FileNotFoundError:
        logger.error("osascript not found")
        return {
            "success": False,
            "url": url,
            "title": "",
            "message": "osascript command not found (is this macOS?)",
        }
    except Exception as e:
        logger.error(f"AppleScript navigation error: {e}")
        return {
            "success": False,
            "url": url,
            "title": "",
            "message": f"AppleScript error: {e!s}",
        }


def is_applescript_available() -> bool:
    """Check if AppleScript is available on this system."""
    if platform.system() != "Darwin":
        return False

    try:
        result = subprocess.run(
            ["osascript", "-e", 'return "ok"'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False
