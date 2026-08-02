"""
Network inspection command handlers.

Implements: get_network_requests, get_har
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import requests as http_requests

from inspekt.config import get_bridge_port
from inspekt.core.schemas.network import (
    GetHARParams,
    GetHARResponse,
    GetNetworkRequestsParams,
    GetNetworkRequestsResponse,
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


async def get_network_requests(params: GetNetworkRequestsParams) -> GetNetworkRequestsResponse:
    """
    Get network requests from the current page using Performance API.

    Returns detailed information about all resources loaded by the page,
    including timing, size, and type information.

    Note: Uses Performance API which has limitations:
    - No HTTP status codes
    - No request/response headers
    - Buffer limit of ~150-250 entries
    """
    executor = get_executor()
    script_loader = get_script_loader()

    try:
        # Load the get_network.js script
        script = await script_loader.load_script_async("get_network.js")

        result = await asyncio.to_thread(executor.execute, script, 30.0)

        if result.get("ok"):
            data = result.get("result", {})

            if data.get("error"):
                return GetNetworkRequestsResponse(
                    success=False,
                    url="",
                    timestamp="",
                    entries=[],
                    summary={},
                    message=data["error"],
                )

            entries = data.get("entries", [])
            summary = data.get("summary", {})

            # Filter by type if specified
            if params.resource_type:
                entries = [e for e in entries if e.get("type") == params.resource_type]
                # Update summary counts
                summary["totalRequests"] = len(entries)
                summary["totalTransferSize"] = sum(e.get("transferSize", 0) for e in entries)

            # Filter external only
            if params.external_only:
                entries = [e for e in entries if e.get("external")]

            # Sort entries
            sort_keys = {
                "start": lambda e: e.get("startTime", 0),
                "time": lambda e: -e.get("timing", {}).get("total", 0),
                "size": lambda e: -e.get("transferSize", 0),
                "name": lambda e: e.get("name", "").lower(),
                "type": lambda e: e.get("type", ""),
            }

            sort_by = params.sort_by or "start"
            if sort_by in sort_keys:
                entries = sorted(entries, key=sort_keys[sort_by])

            # Apply limit
            if params.limit:
                entries = entries[: params.limit]

            return GetNetworkRequestsResponse(
                success=True,
                url=data.get("url", ""),
                timestamp=data.get("timestamp", ""),
                entries=entries,
                summary=summary,
                message=f"Found {len(entries)} network requests",
            )
        else:
            return GetNetworkRequestsResponse(
                success=False,
                url="",
                timestamp="",
                entries=[],
                summary={},
                message=result.get("error", "Failed to get network data"),
            )

    except Exception as e:
        logger.error(f"Get network requests error: {e}")
        return GetNetworkRequestsResponse(
            success=False,
            url="",
            timestamp="",
            entries=[],
            summary={},
            message=f"Error: {e!s}",
        )


async def get_har(params: GetHARParams) -> GetHARResponse:
    """
    Get full network data from DevTools (HAR format).

    This tool requires Chrome DevTools to be open (F12) for the active tab.
    It provides complete network data including:
    - HTTP status codes (200, 404, 500, etc.)
    - Request and response headers
    - Full timing breakdown
    - Initiator information

    If DevTools is not open, returns an error with a hint to use
    get_network_requests instead.
    """
    try:
        # Get HAR data from bridge server (which gets it from DevTools)
        bridge_port = get_bridge_port()
        response = http_requests.get(
            f"http://127.0.0.1:{bridge_port}/network/har",
            timeout=20.0,
        )
        data = response.json()

        if not data.get("ok", False):
            return GetHARResponse(
                success=False,
                source="devtools",
                url="",
                timestamp="",
                entries=[],
                summary={},
                message=data.get("error", "Failed to get HAR data. Is DevTools open (F12)?"),
            )

        entries = data.get("entries", [])
        summary = data.get("summary", {})

        # Filter by type if specified
        if params.resource_type:
            entries = [e for e in entries if e.get("type") == params.resource_type]

        # Filter errors only (4xx/5xx status)
        if params.errors_only:
            entries = [e for e in entries if e.get("status", 0) >= 400]

        # Sort entries
        sort_keys = {
            "start": lambda e: e.get("startTime", 0),
            "time": lambda e: -e.get("time", 0),
            "size": lambda e: -e.get("bodySize", 0),
            "name": lambda e: e.get("url", "").lower(),
            "type": lambda e: e.get("type", ""),
            "status": lambda e: -e.get("status", 0),
        }

        sort_by = params.sort_by or "start"
        if sort_by in sort_keys:
            entries = sorted(entries, key=sort_keys[sort_by])

        # Apply limit
        if params.limit:
            entries = entries[: params.limit]

        return GetHARResponse(
            success=True,
            source="devtools",
            url=data.get("url", ""),
            timestamp=data.get("timestamp", ""),
            entries=entries,
            summary=summary,
            message=f"Found {len(entries)} HAR entries",
        )

    except http_requests.exceptions.ConnectionError:
        return GetHARResponse(
            success=False,
            source="devtools",
            url="",
            timestamp="",
            entries=[],
            summary={},
            message="Bridge server not running. Start it with: inspekt start",
        )
    except http_requests.exceptions.Timeout:
        return GetHARResponse(
            success=False,
            source="devtools",
            url="",
            timestamp="",
            entries=[],
            summary={},
            message="HAR request timed out",
        )
    except Exception as e:
        logger.error(f"Get HAR error: {e}")
        return GetHARResponse(
            success=False,
            source="devtools",
            url="",
            timestamp="",
            entries=[],
            summary={},
            message=f"Error: {e!s}",
        )
