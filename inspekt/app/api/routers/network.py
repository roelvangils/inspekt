"""Network API endpoints for inspecting page network requests.

This router provides endpoints for extracting network request information
from the browser using the Performance API.

Note: Uses Performance API which has limitations:
- No HTTP status codes
- No request/response headers
- Buffer limit of ~150-250 entries
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from inspekt.app.api.dependencies import get_bridge_client
from inspekt.services.script_loader import ScriptLoader

router = APIRouter()


class NetworkEntry(BaseModel):
    """A single network request entry."""
    index: int
    url: str
    name: str
    domain: str
    path: str
    type: str
    initiatorType: str
    external: bool
    transferSize: int
    encodedSize: int
    decodedSize: int
    timing: dict
    startTime: int
    protocol: str
    cached: bool


class NetworkSummary(BaseModel):
    """Summary statistics for network requests."""
    totalRequests: int
    totalTransferSize: int
    totalDecodedSize: int
    byType: dict
    byDomain: dict
    averageDuration: int
    slowestRequest: Optional[dict]
    largestRequest: Optional[dict]
    cachedRequests: int
    externalRequests: int


class NetworkResponse(BaseModel):
    """Response model for network requests."""
    ok: bool = True
    url: str
    timestamp: str
    entries: list
    summary: dict


def _get_network_data():
    """Execute the network script and return the data."""
    client = get_bridge_client()
    loader = ScriptLoader()

    try:
        code = loader.load_script_sync("get_network.js")
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Script not found: {e}")

    try:
        result = client.execute(code, timeout=30.0)

        if not result.get("ok"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to get network data"))

        data = result.get("result", {})

        if data.get("error"):
            raise HTTPException(status_code=500, detail=data["error"])

        return data

    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Bridge server connection error: {str(e)}")
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Request timeout: {str(e)}")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"Error getting network data: {str(e)}")


@router.get("/", response_model=NetworkResponse)
def get_network_requests(
    type: Optional[str] = Query(None, description="Filter by resource type (script, stylesheet, fetch, image, font, etc.)"),
    external_only: bool = Query(False, description="Only return external requests"),
    sort: str = Query("start", description="Sort by: start, time, size, name, type"),
    limit: Optional[int] = Query(None, description="Limit number of results"),
):
    """
    Get all network requests from the current page.

    Returns network request information captured by the Performance API,
    including timing, size, and type information for each resource.

    Args:
        type: Filter by resource type (script, stylesheet, fetch, image, font, etc.)
        external_only: Only return requests to external domains
        sort: Sort field (start, time, size, name, type)
        limit: Maximum number of entries to return

    Returns:
        NetworkResponse with entries and summary statistics

    Examples:
        ```bash
        # Get all network requests
        curl http://localhost:8767/api/network/

        # Get only scripts
        curl "http://localhost:8767/api/network/?type=script"

        # Get external requests sorted by size
        curl "http://localhost:8767/api/network/?external_only=true&sort=size"

        # Get top 10 slowest requests
        curl "http://localhost:8767/api/network/?sort=time&limit=10"
        ```
    """
    data = _get_network_data()
    entries = data.get("entries", [])
    summary = data.get("summary", {})

    # Filter by type
    if type:
        entries = [e for e in entries if e["type"] == type]
        # Update summary counts
        summary["totalRequests"] = len(entries)
        summary["totalTransferSize"] = sum(e["transferSize"] for e in entries)

    # Filter external only
    if external_only:
        entries = [e for e in entries if e["external"]]

    # Sort entries
    sort_keys = {
        "start": lambda e: e["startTime"],
        "time": lambda e: -e["timing"]["total"],
        "size": lambda e: -e["transferSize"],
        "name": lambda e: e["name"].lower(),
        "type": lambda e: e["type"],
    }

    if sort in sort_keys:
        entries = sorted(entries, key=sort_keys[sort])

    # Apply limit
    if limit:
        entries = entries[:limit]

    return {
        "ok": True,
        "url": data.get("url"),
        "timestamp": data.get("timestamp"),
        "entries": entries,
        "summary": summary,
    }


@router.get("/scripts")
def get_script_requests(
    external_only: bool = Query(False, description="Only return external requests"),
    sort: str = Query("start", description="Sort by: start, time, size, name"),
    limit: Optional[int] = Query(None, description="Limit number of results"),
):
    """
    Get only JavaScript resources.

    Filters network requests to show only script (.js) resources.
    """
    return get_network_requests(type="script", external_only=external_only, sort=sort, limit=limit)


@router.get("/stylesheets")
def get_stylesheet_requests(
    external_only: bool = Query(False, description="Only return external requests"),
    sort: str = Query("start", description="Sort by: start, time, size, name"),
    limit: Optional[int] = Query(None, description="Limit number of results"),
):
    """
    Get only CSS resources.

    Filters network requests to show only stylesheet (.css) resources.
    """
    return get_network_requests(type="stylesheet", external_only=external_only, sort=sort, limit=limit)


@router.get("/fetch")
def get_fetch_requests(
    external_only: bool = Query(False, description="Only return external requests"),
    sort: str = Query("start", description="Sort by: start, time, size, name"),
    limit: Optional[int] = Query(None, description="Limit number of results"),
):
    """
    Get only fetch/XHR requests.

    Filters network requests to show only fetch and XHR API calls.
    """
    return get_network_requests(type="fetch", external_only=external_only, sort=sort, limit=limit)


@router.get("/images")
def get_image_requests(
    external_only: bool = Query(False, description="Only return external requests"),
    sort: str = Query("start", description="Sort by: start, time, size, name"),
    limit: Optional[int] = Query(None, description="Limit number of results"),
):
    """
    Get only image resources.

    Filters network requests to show only image resources (png, jpg, gif, webp, etc.).
    """
    return get_network_requests(type="image", external_only=external_only, sort=sort, limit=limit)


@router.get("/fonts")
def get_font_requests(
    external_only: bool = Query(False, description="Only return external requests"),
    sort: str = Query("start", description="Sort by: start, time, size, name"),
    limit: Optional[int] = Query(None, description="Limit number of results"),
):
    """
    Get only font resources.

    Filters network requests to show only font resources (woff, woff2, ttf, etc.).
    """
    return get_network_requests(type="font", external_only=external_only, sort=sort, limit=limit)


@router.get("/summary")
def get_network_summary():
    """
    Get summary statistics for network requests.

    Returns aggregate statistics including total requests, sizes,
    breakdown by type and domain, and slowest/largest resources.

    Examples:
        ```bash
        curl http://localhost:8767/api/network/summary
        ```
    """
    data = _get_network_data()

    return {
        "ok": True,
        "url": data.get("url"),
        "timestamp": data.get("timestamp"),
        "summary": data.get("summary", {}),
    }


def _get_har_data():
    """Get HAR data from DevTools via bridge server."""
    import requests as http_requests

    try:
        response = http_requests.get(
            "http://127.0.0.1:8765/network/har",
            timeout=20.0
        )
        return response.json()
    except http_requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail="Bridge server not running. Start it with: inspekt start"
        )
    except http_requests.exceptions.Timeout:
        raise HTTPException(
            status_code=504,
            detail="HAR request timed out. Is DevTools open?"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/har")
def get_har_data(
    type: Optional[str] = Query(None, description="Filter by resource type"),
    external_only: bool = Query(False, description="Only return external requests"),
    errors_only: bool = Query(False, description="Only return failed requests (4xx/5xx)"),
    sort: str = Query("start", description="Sort by: start, time, size, name, type, status"),
    limit: Optional[int] = Query(None, description="Limit number of results"),
    raw: bool = Query(False, description="Return raw HAR format"),
):
    """
    Get full network data from DevTools (HAR format).

    This endpoint requires Chrome DevTools to be open (F12) for the active tab.
    It provides complete network data including HTTP status codes, headers,
    and detailed timing information.

    Args:
        type: Filter by resource type (script, stylesheet, fetch, image, font, document)
        external_only: Only return requests to external domains
        errors_only: Only return failed requests (4xx/5xx status codes)
        sort: Sort field (start, time, size, name, type, status)
        limit: Maximum number of entries to return
        raw: Return raw HAR format (for import into other tools)

    Returns:
        HAR data with entries and summary statistics

    Examples:
        ```bash
        # Get full HAR data
        curl http://localhost:8767/api/network/har

        # Get only scripts
        curl "http://localhost:8767/api/network/har?type=script"

        # Get failed requests
        curl "http://localhost:8767/api/network/har?errors_only=true"

        # Get raw HAR for export
        curl "http://localhost:8767/api/network/har?raw=true"
        ```
    """
    data = _get_har_data()

    if not data.get("ok", False):
        raise HTTPException(
            status_code=503,
            detail=data.get("error", "Failed to get HAR data. Is DevTools open?")
        )

    # If raw HAR requested, return as-is
    if raw:
        return data.get("rawHAR", data)

    entries = data.get("entries", [])
    summary = data.get("summary", {})

    # Filter by type
    if type:
        entries = [e for e in entries if e.get("type") == type]

    # Filter errors only
    if errors_only:
        entries = [e for e in entries if e.get("status", 0) >= 400]

    # Filter external only
    if external_only:
        domain = None
        for e in entries:
            if e.get("type") == "document":
                domain = e.get("domain")
                break
        if domain:
            entries = [e for e in entries if e.get("domain") != domain]

    # Sort entries
    sort_keys = {
        "start": lambda e: e.get("startedDateTime", ""),
        "time": lambda e: -(e.get("timing", {}).get("total", 0) if isinstance(e.get("timing"), dict) else 0),
        "size": lambda e: -e.get("transferSize", 0),
        "name": lambda e: e.get("name", "").lower(),
        "type": lambda e: e.get("type", ""),
        "status": lambda e: e.get("status", 0),
    }

    if sort in sort_keys:
        entries = sorted(entries, key=sort_keys[sort])

    # Apply limit
    if limit:
        entries = entries[:limit]

    # Update summary for filtered results
    if type or external_only or errors_only:
        summary["totalRequests"] = len(entries)
        summary["totalTransferSize"] = sum(e.get("transferSize", 0) for e in entries)

    return {
        "ok": True,
        "source": "devtools",
        "url": data.get("url"),
        "timestamp": data.get("timestamp"),
        "entries": entries,
        "summary": summary,
    }
