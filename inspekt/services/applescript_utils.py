"""AppleScript utilities for browser tab activation on macOS.

This module provides a robust, reusable AppleScript execution framework
for activating browser tabs by URL.
"""

from __future__ import annotations

import logging
import platform
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

logger = logging.getLogger(__name__)


class BrowserType(Enum):
    """Supported browser types for AppleScript automation."""

    SAFARI = "Safari"
    CHROME = "Chrome"
    BRAVE = "Brave"
    EDGE = "Edge"
    UNSUPPORTED = "Unsupported"


@dataclass
class AppleScriptResult:
    """Result of AppleScript execution."""

    ok: bool
    output: str | None = None
    error: str | None = None
    error_code: int | None = None


class AppleScriptError(Exception):
    """Base exception for AppleScript errors."""

    pass


class BrowserNotRunningError(AppleScriptError):
    """Browser application is not running."""

    pass


class TabNotFoundError(AppleScriptError):
    """Tab with specified URL was not found."""

    pass


class UnsupportedBrowserError(AppleScriptError):
    """Browser does not support AppleScript tab activation."""

    pass


class UnsupportedPlatformError(AppleScriptError):
    """Platform does not support AppleScript (not macOS)."""

    pass


class AppleScriptExecutor:
    """Executes AppleScript commands via osascript."""

    @staticmethod
    def is_macos() -> bool:
        """Check if running on macOS."""
        return platform.system() == "Darwin"

    @staticmethod
    def sanitize_input(text: str) -> str:
        """Sanitize input for safe AppleScript string interpolation.

        Escapes backslashes and double quotes, removes control characters.
        """
        # Remove control characters
        text = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text)
        # Escape backslashes first, then double quotes
        text = text.replace("\\", "\\\\")
        text = text.replace('"', '\\"')
        return text

    def execute(self, script: str, timeout: float = 10.0) -> AppleScriptResult:
        """Execute an AppleScript and return the result.

        Args:
            script: The AppleScript code to execute
            timeout: Timeout in seconds (default 10)

        Returns:
            AppleScriptResult with ok, output, error, and error_code
        """
        if not self.is_macos():
            return AppleScriptResult(
                ok=False,
                error="AppleScript is only supported on macOS",
                error_code=-1,
            )

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() or "AppleScript execution failed"
                error_code = self._parse_error_code(error_msg)
                return AppleScriptResult(
                    ok=False,
                    error=error_msg,
                    error_code=error_code,
                )

            output = result.stdout.strip()

            # Check for explicit error returns from our scripts
            if output.startswith("ERROR:"):
                return AppleScriptResult(
                    ok=False,
                    error=output[6:].strip(),
                    error_code=-1,
                )

            return AppleScriptResult(ok=True, output=output)

        except subprocess.TimeoutExpired:
            return AppleScriptResult(
                ok=False,
                error="AppleScript execution timed out",
                error_code=-1712,
            )
        except FileNotFoundError:
            return AppleScriptResult(
                ok=False,
                error="osascript not found - this feature requires macOS",
                error_code=-1,
            )
        except Exception as e:
            return AppleScriptResult(
                ok=False,
                error=str(e),
                error_code=-1,
            )

    @staticmethod
    def _parse_error_code(error_message: str) -> int | None:
        """Parse AppleScript error code from error message."""
        # Look for patterns like "(-600)" or "error number -600"
        match = re.search(r"\((-?\d+)\)|error\s+(?:number\s+)?(-?\d+)", error_message)
        if match:
            code = match.group(1) or match.group(2)
            return int(code)
        return None


class BrowserAppleScriptTemplates:
    """AppleScript templates for browser tab activation."""

    # App name mappings for Chromium browsers
    CHROMIUM_APP_NAMES: ClassVar[dict[str, str]] = {
        "Chrome": "Google Chrome",
        "Brave": "Brave Browser",
        "Edge": "Microsoft Edge",
    }

    @classmethod
    def get_browser_type(cls, browser_name: str) -> BrowserType:
        """Determine browser type from browser name string."""
        name_lower = browser_name.lower()

        if "safari" in name_lower:
            return BrowserType.SAFARI
        elif "chrome" in name_lower or "chromium" in name_lower:
            return BrowserType.CHROME
        elif "brave" in name_lower:
            return BrowserType.BRAVE
        elif "edge" in name_lower:
            return BrowserType.EDGE
        else:
            return BrowserType.UNSUPPORTED

    @classmethod
    def get_app_name(cls, browser_type: BrowserType) -> str:
        """Get the application name for AppleScript."""
        if browser_type == BrowserType.SAFARI:
            return "Safari"
        elif browser_type in cls.CHROMIUM_APP_NAMES:
            return cls.CHROMIUM_APP_NAMES.get(browser_type.value, browser_type.value)
        else:
            return browser_type.value

    @classmethod
    def safari_activate_tab(cls, url: str) -> str:
        """Generate AppleScript to activate Safari tab by URL."""
        safe_url = AppleScriptExecutor.sanitize_input(url)
        return f'''
tell application "Safari"
    activate
    set foundTab to false
    repeat with w in windows
        repeat with t in tabs of w
            if URL of t contains "{safe_url}" then
                set current tab of w to t
                set index of w to 1
                set foundTab to true
                exit repeat
            end if
        end repeat
        if foundTab then exit repeat
    end repeat
    if foundTab then
        "OK"
    else
        "ERROR:Tab not found"
    end if
end tell
'''

    @classmethod
    def chromium_activate_tab(cls, app_name: str, url: str) -> str:
        """Generate AppleScript to activate Chromium-based browser tab by URL."""
        safe_url = AppleScriptExecutor.sanitize_input(url)
        return f'''
tell application "{app_name}"
    activate
    set foundTab to false
    repeat with w in windows
        set tabIndex to 0
        repeat with t in tabs of w
            set tabIndex to tabIndex + 1
            if URL of t contains "{safe_url}" then
                set active tab index of w to tabIndex
                set index of w to 1
                set foundTab to true
                exit repeat
            end if
        end repeat
        if foundTab then exit repeat
    end repeat
    if foundTab then
        "OK"
    else
        "ERROR:Tab not found"
    end if
end tell
'''

    @classmethod
    def generate_activate_tab_script(cls, browser_name: str, url: str) -> str:
        """Generate the appropriate AppleScript for the given browser.

        Args:
            browser_name: Browser name (e.g., "Safari", "Chrome", "Brave Browser")
            url: URL to match (uses 'contains' matching)

        Returns:
            AppleScript code string

        Raises:
            UnsupportedBrowserError: If browser doesn't support AppleScript
        """
        browser_type = cls.get_browser_type(browser_name)

        if browser_type == BrowserType.UNSUPPORTED:
            raise UnsupportedBrowserError(
                f"Browser '{browser_name}' does not support AppleScript tab activation. "
                "Supported browsers: Safari, Chrome, Brave, Edge"
            )

        if browser_type == BrowserType.SAFARI:
            return cls.safari_activate_tab(url)
        else:
            # Chromium-based browsers
            app_name = cls.get_app_name(browser_type)
            return cls.chromium_activate_tab(app_name, url)


def activate_browser_tab(browser_name: str, url: str) -> AppleScriptResult:
    """Activate a browser tab by URL.

    This is the main entry point for tab activation.

    Args:
        browser_name: Browser name (e.g., "Safari", "Chrome", "Brave")
        url: URL to match (uses 'contains' matching)

    Returns:
        AppleScriptResult with ok=True on success, or error details on failure
    """
    executor = AppleScriptExecutor()

    if not executor.is_macos():
        return AppleScriptResult(
            ok=False,
            error="Tab activation is only supported on macOS",
            error_code=-1,
        )

    try:
        script = BrowserAppleScriptTemplates.generate_activate_tab_script(
            browser_name, url
        )
    except UnsupportedBrowserError as e:
        return AppleScriptResult(ok=False, error=str(e), error_code=-1)

    result = executor.execute(script)

    # Log the result
    if result.ok:
        logger.debug(f"Successfully activated {browser_name} tab for URL: {url}")
    else:
        logger.warning(f"Failed to activate {browser_name} tab: {result.error}")

    return result


def is_browser_supported(browser_name: str) -> bool:
    """Check if a browser supports AppleScript tab activation."""
    browser_type = BrowserAppleScriptTemplates.get_browser_type(browser_name)
    return browser_type != BrowserType.UNSUPPORTED


def focus_browser_window(browser_name: str = "Chrome") -> AppleScriptResult:
    """Focus a browser window (bring to front).

    This is a simpler version that just activates the browser application
    without looking for a specific tab. Useful for starting recordings.

    Args:
        browser_name: Browser name (e.g., "Chrome", "Brave", "Safari")

    Returns:
        AppleScriptResult with ok=True on success, or error details on failure
    """
    executor = AppleScriptExecutor()

    if not executor.is_macos():
        return AppleScriptResult(
            ok=False,
            error="Browser focus is only supported on macOS",
            error_code=-1,
        )

    # Get the app name for AppleScript
    browser_type = BrowserAppleScriptTemplates.get_browser_type(browser_name)
    if browser_type == BrowserType.UNSUPPORTED:
        return AppleScriptResult(
            ok=False,
            error=f"Browser '{browser_name}' is not supported",
            error_code=-1,
        )

    app_name = BrowserAppleScriptTemplates.get_app_name(browser_type)

    # Simple script to just activate the browser
    script = f'''
tell application "{app_name}"
    activate
end tell
"OK"
'''

    result = executor.execute(script, timeout=5.0)

    if result.ok:
        logger.debug(f"Successfully focused {app_name}")
    else:
        logger.warning(f"Failed to focus {app_name}: {result.error}")

    return result


def resize_browser_window(
    viewport_width: int,
    viewport_height: int,
    browser_name: str = "Chrome",
) -> bool:
    """Resize the browser window to achieve a specific viewport size on macOS.

    This uses AppleScript to set the window bounds. The function calculates
    the window chrome (toolbar, scrollbar) offsets to achieve the desired
    viewport dimensions.

    Args:
        viewport_width: Target viewport width in pixels
        viewport_height: Target viewport height in pixels
        browser_name: Browser name (e.g., "Chrome", "Brave", "Safari")

    Returns:
        True if resize succeeded, False otherwise
    """
    executor = AppleScriptExecutor()

    if not executor.is_macos():
        logger.debug("Window resize is only supported on macOS")
        return False

    # Get the app name for AppleScript
    browser_type = BrowserAppleScriptTemplates.get_browser_type(browser_name)
    if browser_type == BrowserType.UNSUPPORTED:
        logger.warning(f"Browser '{browser_name}' is not supported for resize")
        return False

    app_name = BrowserAppleScriptTemplates.get_app_name(browser_type)

    # Issue 17: Get screen bounds dynamically via AppleScript
    screen_script = '''
tell application "Finder"
    set screenBounds to bounds of window of desktop
    return screenBounds
end tell
'''
    screen_result = executor.execute(screen_script, timeout=3.0)

    # Default screen size if we can't get it
    screen_width = 1920
    screen_height = 1080
    menu_bar_height = 25  # Default menu bar height

    if screen_result.ok and screen_result.output:
        try:
            # Parse "0, 0, 1920, 1080" format
            parts = screen_result.output.strip().split(", ")
            if len(parts) >= 4:
                screen_width = int(parts[2])
                screen_height = int(parts[3])
                logger.debug(f"Screen size: {screen_width}×{screen_height}")
        except (ValueError, IndexError):
            logger.debug("Could not parse screen bounds, using defaults")

    # Issue 16: Window chrome offsets (estimated)
    # These account for toolbar height, scrollbar width, and window borders
    # Note: These are approximate - the calibration loop in record.py handles exact sizing
    if browser_type == BrowserType.SAFARI:
        toolbar_height = 75  # Safari's toolbar is slightly shorter
        extra_width = 0  # Safari doesn't have permanent scrollbar
    else:
        toolbar_height = 88  # Chrome/Brave/Edge toolbar height
        extra_width = 16  # Scrollbar + border width

    # Calculate window dimensions
    window_width = viewport_width + extra_width
    window_height = viewport_height + toolbar_height

    # Issue 17: Check if window will fit on screen
    if window_width > screen_width or (window_height + menu_bar_height) > screen_height:
        logger.warning(
            f"Window size {window_width}×{window_height} exceeds screen bounds "
            f"{screen_width}×{screen_height - menu_bar_height}. Window may be clipped."
        )
        # Don't return False - let the resize proceed and be clipped
        # The caller can verify the actual viewport size and recalibrate if needed

    # Calculate position - try to fit on primary screen
    # Start from left edge, below menu bar
    x1 = 0
    y1 = menu_bar_height
    x2 = min(window_width, screen_width)
    y2 = min(window_height + menu_bar_height, screen_height)

    # AppleScript to resize the window
    script = f'''
tell application "{app_name}"
    activate
    if (count of windows) > 0 then
        set bounds of front window to {{{x1}, {y1}, {x2}, {y2}}}
        return "OK"
    else
        return "NO_WINDOW"
    end if
end tell
'''

    result = executor.execute(script, timeout=5.0)

    if result.ok and result.output and "OK" in result.output:
        logger.debug(f"Successfully resized {app_name} to {viewport_width}×{viewport_height}")
        return True
    else:
        logger.warning(f"Failed to resize {app_name}: {result.error or result.output}")
        return False
