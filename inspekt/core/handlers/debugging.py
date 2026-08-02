"""
Debugging command handlers.

Implements: get_console_logs, clear_console_logs
"""

from __future__ import annotations

import logging

from inspekt.core.commands.base import EmptyParams
from inspekt.core.schemas.debugging import (
    ClearConsoleLogsResponse,
    ConsoleEntry,
    GetConsoleLogsParams,
    GetConsoleLogsResponse,
)

logger = logging.getLogger(__name__)


async def get_console_logs(params: GetConsoleLogsParams) -> GetConsoleLogsResponse:
    """
    Get captured browser console messages.

    Returns console.log, console.error, console.warn, console.info, and
    console.debug messages that were captured since the page loaded.
    """
    import requests as http_requests

    try:
        # Get console logs from bridge server
        response = http_requests.get(
            "http://127.0.0.1:8765/console/logs",
            timeout=15.0,
        )
        data = response.json()

        if not data.get("ok", False):
            return GetConsoleLogsResponse(
                success=False,
                entries=[],
                count=0,
                hooked=False,
                message=data.get("error", "Failed to get console logs"),
            )

        entries = data.get("entries", [])
        hooked = data.get("hooked", False)

        # Filter by level if specified
        if params.level and params.level != "all":
            entries = [e for e in entries if e.get("level") == params.level]

        # Apply limit
        if params.limit and params.limit > 0:
            entries = entries[-params.limit :]  # Get most recent

        # Convert to Pydantic models
        console_entries = [
            ConsoleEntry(
                level=e.get("level", "log"),
                timestamp=e.get("timestamp", ""),
                message=e.get("message", ""),
            )
            for e in entries
        ]

        return GetConsoleLogsResponse(
            success=True,
            entries=console_entries,
            count=len(console_entries),
            hooked=hooked,
            message=f"Retrieved {len(console_entries)} console entries",
        )

    except http_requests.exceptions.ConnectionError:
        return GetConsoleLogsResponse(
            success=False,
            entries=[],
            count=0,
            hooked=False,
            message="Bridge server not running. Start it with: inspekt start",
        )
    except http_requests.exceptions.Timeout:
        return GetConsoleLogsResponse(
            success=False,
            entries=[],
            count=0,
            hooked=False,
            message="Console logs request timed out",
        )
    except Exception as e:
        logger.error(f"Get console logs error: {e}")
        return GetConsoleLogsResponse(
            success=False,
            entries=[],
            count=0,
            hooked=False,
            message=f"Error: {e!s}",
        )


async def clear_console_logs(params: EmptyParams) -> ClearConsoleLogsResponse:
    """
    Clear the browser console message buffer.

    Removes all captured console messages from the browser's buffer.
    """
    import requests as http_requests

    try:
        # Clear console logs via bridge server
        response = http_requests.post(
            "http://127.0.0.1:8765/console/clear",
            timeout=15.0,
        )
        data = response.json()

        if not data.get("ok", False):
            return ClearConsoleLogsResponse(
                success=False,
                message=data.get("error", "Failed to clear console logs"),
            )

        return ClearConsoleLogsResponse(
            success=True,
            message="Console buffer cleared",
        )

    except http_requests.exceptions.ConnectionError:
        return ClearConsoleLogsResponse(
            success=False,
            message="Bridge server not running. Start it with: inspekt start",
        )
    except http_requests.exceptions.Timeout:
        return ClearConsoleLogsResponse(
            success=False,
            message="Clear console logs request timed out",
        )
    except Exception as e:
        logger.error(f"Clear console logs error: {e}")
        return ClearConsoleLogsResponse(
            success=False,
            message=f"Error: {e!s}",
        )
