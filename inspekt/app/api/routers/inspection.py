"""
Inspection API endpoints - Inspect elements and capture screenshots.

This module provides HTTP API endpoints for element inspection:
- POST /api/inspection/inspect - Select and inspect elements
- GET /api/inspection/inspected - View inspected element details
- POST /api/inspection/screenshot - Capture element screenshots
"""

from __future__ import annotations

import base64
import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from inspekt.app.api.dependencies import get_bridge_client
from inspekt.app.api.models import CommandResponse
from inspekt.services.script_loader import ScriptLoader

router = APIRouter()


# Request Models
class InspectRequest(BaseModel):
    """Request model for inspecting elements."""

    selector: str = Field(..., description="CSS selector of element to inspect")


class ScreenshotRequest(BaseModel):
    """Request model for taking screenshots."""

    selector: str = Field(
        ...,
        description="CSS selector of element to screenshot (use '$0' for inspected element)",
    )


# Response Models
class ScreenshotResponse(BaseModel):
    """Response model for screenshot operations."""

    ok: bool = Field(..., description="Whether the command executed successfully")
    result: dict[str, Any] | None = Field(None, description="Screenshot data")
    error: str | None = Field(None, description="Error message if ok=False")


# Endpoints
@router.post("/inspect", response_model=CommandResponse)
def inspect_element(request: InspectRequest):
    """
    Select an element and show its details.

    Mirrors 'zen inspect' CLI command.

    This endpoint marks an element for inspection and returns its details.
    The element is also highlighted briefly in the browser.

    Examples:
        - Inspect element: `{"selector": "h1"}`
        - Inspect by ID: `{"selector": "#header"}`
        - Inspect by class: `{"selector": ".main-content"}`
    """
    client = get_bridge_client()

    # Mark the element and get details
    mark_code = f"""
    (function() {{
        const el = document.querySelector('{request.selector}');
        if (!el) {{
            return {{ error: 'Element not found: {request.selector}' }};
        }}

        // Store reference
        window.__ZEN_INSPECTED_ELEMENT__ = el;

        // Highlight it briefly
        const originalOutline = el.style.outline;
        el.style.outline = '3px solid #0066ff';
        setTimeout(() => {{
            el.style.outline = originalOutline;
        }}, 1000);

        return {{ ok: true, message: 'Element marked for inspection' }};
    }})()
    """

    try:
        result = client.execute(mark_code, timeout=60.0)

        if not result.get("ok"):
            raise HTTPException(status_code=500, detail=result.get("error"))

        response = result.get("result", {})
        if response.get("error"):
            raise HTTPException(status_code=400, detail=response.get("error"))

        # Now get the element details
        script_loader = ScriptLoader()
        try:
            details_code = script_loader.load_script_sync("get_inspected.js")
        except FileNotFoundError as e:
            raise HTTPException(status_code=500, detail=f"Script not found: {str(e)}")

        details_result = client.execute(details_code, timeout=60.0)

        if not details_result.get("ok"):
            raise HTTPException(status_code=500, detail=details_result.get("error"))

        details_response = details_result.get("result", {})
        if details_response.get("error"):
            raise HTTPException(status_code=400, detail=details_response.get("error"))

        return {
            "ok": True,
            "result": details_response,
            "error": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inspected", response_model=CommandResponse)
def get_inspected_element():
    """
    Get information about the currently inspected element.

    Mirrors 'inspekt inspected' CLI command.

    Shows details about the element from DevTools inspection or from 'inspect' endpoint.

    To capture element from DevTools:
        1. Right-click element → Inspect
        2. In DevTools Console: zenStore()
        3. Call: GET /api/inspection/inspected

    Or select programmatically:
        POST /api/inspection/inspect {"selector": "h1"}
        GET /api/inspection/inspected
    """
    client = get_bridge_client()
    loader = ScriptLoader()

    # Load the get_inspected.js script
    try:
        code = loader.load_script_sync("get_inspected.js")
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Script not found: {str(e)}")

    try:
        result = client.execute(code, timeout=60.0)

        if not result.get("ok"):
            raise HTTPException(status_code=500, detail=result.get("error"))

        response = result.get("result", {})
        if response.get("error"):
            raise HTTPException(
                status_code=400,
                detail=f"{response.get('error')}. {response.get('hint', '')}".strip(),
            )

        return {
            "ok": True,
            "result": response,
            "error": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/screenshot", response_model=ScreenshotResponse)
def screenshot_element(request: ScreenshotRequest):
    """
    Take a screenshot of a specific element.

    Mirrors 'zen screenshot' CLI command.

    Captures a DOM element and returns it as a base64-encoded PNG image.
    Use '$0' to screenshot the currently inspected element.

    Examples:
        - Screenshot element: `{"selector": "#main"}`
        - Screenshot inspected: `{"selector": "$0"}`
        - Screenshot by class: `{"selector": ".hero-section"}`

    Returns:
        Response with screenshot data including:
        - dataUrl: Base64-encoded image data URL (data:image/png;base64,...)
        - width: Image width in pixels
        - height: Image height in pixels
    """
    client = get_bridge_client()
    loader = ScriptLoader()

    # Load screenshot script
    try:
        script = loader.load_script_sync("screenshot_element.js")
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Script not found: {str(e)}")

    # Replace selector placeholder with properly escaped value
    code = script.replace("SELECTOR_PLACEHOLDER", json.dumps(request.selector))

    try:
        result = client.execute(code, timeout=60.0)

        if not result.get("ok"):
            raise HTTPException(status_code=500, detail=result.get("error"))

        response = result.get("result", {})
        if response.get("error"):
            detail = response.get("error")
            if response.get("details"):
                detail += f" - {response.get('details')}"
            raise HTTPException(status_code=400, detail=detail)

        # Verify we got the data URL
        data_url = response.get("dataUrl")
        if not data_url:
            raise HTTPException(status_code=500, detail="No image data received")

        return {
            "ok": True,
            "result": response,
            "error": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
