"""
Interaction API endpoints - Click, type, paste, and wait operations.

This module provides HTTP API endpoints for browser interaction:
- POST /api/interaction/click - Click on elements
- POST /api/interaction/double-click - Double-click on elements
- POST /api/interaction/right-click - Right-click (context menu) on elements
- POST /api/interaction/type - Type text character by character
- POST /api/interaction/paste - Paste text instantly
- POST /api/interaction/wait - Wait for elements or conditions
"""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from inspekt.app.api.dependencies import get_bridge_client
from inspekt.app.api.models import CommandResponse
from inspekt.config import get_typing_config
from inspekt.services.script_loader import ScriptLoader

router = APIRouter()


# Request Models
class ClickRequest(BaseModel):
    """Request model for clicking elements."""

    selector: str = Field(
        ..., description="CSS selector of element to click (use '$0' for inspected element)"
    )


class TypeRequest(BaseModel):
    """Request model for typing text."""

    text: str = Field(..., description="Text to type")
    selector: str | None = Field(None, description="CSS selector to focus before typing")
    speed: int | None = Field(
        None,
        description="Typing speed in characters per second (omit for fastest, 0 for human-like)",
    )
    clear: bool = Field(True, description="Clear existing text before typing")


class PasteRequest(BaseModel):
    """Request model for pasting text."""

    text: str = Field(..., description="Text to paste")
    selector: str | None = Field(None, description="CSS selector to focus before pasting")
    clear: bool = Field(True, description="Clear existing text before pasting")


class WaitRequest(BaseModel):
    """Request model for waiting operations."""

    selector: str = Field(..., description="CSS selector of element to wait for")
    timeout: int = Field(30, description="Timeout in seconds", ge=1, le=300)
    wait_type: Literal["exists", "visible", "hidden", "text"] = Field(
        "exists", description="Type of wait condition"
    )
    text: str | None = Field(None, description="Text to wait for (only for wait_type='text')")


# Helper Functions
def _send_text_api(text: str, selector: str | None, delay_ms: int, clear: bool = True) -> dict[str, Any]:
    """Helper function to send text to browser via API."""
    client = get_bridge_client()

    # Focus the element first if selector provided
    if selector:
        focus_code = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (!el) {{
                return {{ error: 'Element not found: {selector}' }};
            }}
            el.focus();
            return {{ ok: true }};
        }})()
        """
        result = client.execute(focus_code, timeout=60.0)
        if not result.get("ok") or result.get("result", {}).get("error"):
            error = result.get("error") or result.get("result", {}).get("error", "Unknown error")
            raise HTTPException(status_code=400, detail=f"Error focusing element: {error}")

    # Load and execute the send_keys script
    script_loader = ScriptLoader()
    try:
        script = script_loader.load_script_sync("send_keys.js")
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Script not found: {str(e)}")

    # Get typing configuration
    typing_config = get_typing_config()
    typo_rate = typing_config["human-like-typo-rate"]

    # Replace placeholders with properly escaped values
    code = script.replace("TEXT_PLACEHOLDER", json.dumps(text))
    code = code.replace("DELAY_PLACEHOLDER", str(delay_ms))
    code = code.replace("CLEAR_PLACEHOLDER", "true" if clear else "false")
    code = code.replace("TYPO_RATE_PLACEHOLDER", str(typo_rate))

    # Calculate timeout based on text length and delay
    if delay_ms == -1:
        # Human mode: estimate 300ms per char
        estimated_time = len(text) * 0.3
    elif delay_ms == 0:
        # Fast mode: minimal time
        estimated_time = len(text) * 0.05
    else:
        # Custom speed: calculate from delay
        estimated_time = len(text) * delay_ms / 1000.0

    # Add buffer and enforce minimum
    timeout = max(estimated_time + 10, 60.0)

    result = client.execute(code, timeout=timeout)

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error"))

    response = result.get("result", {})
    if response.get("error"):
        raise HTTPException(status_code=400, detail=response.get("error"))

    return response


def _perform_click_api(selector: str, click_type: str) -> dict[str, Any]:
    """Helper function to perform click actions via API."""
    client = get_bridge_client()

    # Load the click script
    script_loader = ScriptLoader()
    try:
        script = script_loader.load_script_sync("click_element.js")
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Script not found: {str(e)}")

    # Replace placeholders with properly escaped values
    code = script.replace("'SELECTOR_PLACEHOLDER'", json.dumps(selector))
    code = code.replace("'CLICK_TYPE_PLACEHOLDER'", json.dumps(click_type))

    result = client.execute(code, timeout=60.0)

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error"))

    response = result.get("result", {})

    if response.get("error"):
        raise HTTPException(status_code=400, detail=response.get("error"))

    return response


# Endpoints
@router.post("/click", response_model=CommandResponse)
def click_element(request: ClickRequest):
    """
    Click on an element.

    Mirrors 'inspekt click' CLI command.

    Examples:
        - Click stored element: `{"selector": "$0"}`
        - Click specific element: `{"selector": "button#submit"}`
    """
    try:
        response = _perform_click_api(request.selector, "click")
        return {
            "ok": True,
            "result": response,
            "error": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/double-click", response_model=CommandResponse)
def double_click_element(request: ClickRequest):
    """
    Double-click on an element.

    Mirrors 'inspekt double-click' CLI command.

    Examples:
        - Double-click element: `{"selector": "div.item"}`
    """
    try:
        response = _perform_click_api(request.selector, "dblclick")
        return {
            "ok": True,
            "result": response,
            "error": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/right-click", response_model=CommandResponse)
def right_click_element(request: ClickRequest):
    """
    Right-click (context menu) on an element.

    Mirrors 'inspekt right-click' CLI command.

    Examples:
        - Right-click element: `{"selector": "a.download-link"}`
    """
    try:
        response = _perform_click_api(request.selector, "contextmenu")
        return {
            "ok": True,
            "result": response,
            "error": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/type", response_model=CommandResponse)
def type_text(request: TypeRequest):
    """
    Type text character by character into the browser.

    Mirrors 'inspekt type' CLI command.

    By default, clears any existing text and types as fast as possible.
    Use speed parameter to control typing rate and clear=false to append.

    Examples:
        - Type at maximum speed: `{"text": "Hello World"}`
        - Human-like typing: `{"text": "Hello", "speed": 0}`
        - Type at 10 chars/sec: `{"text": "test@example.com", "speed": 10}`
        - Type without clearing: `{"text": "append this", "clear": false}`
        - Type into specific field: `{"text": "password", "selector": "input[type=password]"}`
    """
    try:
        # Calculate delay in milliseconds from speed
        if request.speed == 0:
            # Special case: 0 means human-like typing
            delay_ms = -1
        elif request.speed:
            delay_ms = int(1000 / request.speed)
        else:
            delay_ms = 0  # Fastest (no delay)

        response = _send_text_api(request.text, request.selector, delay_ms, request.clear)

        return {
            "ok": True,
            "result": response,
            "error": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/paste", response_model=CommandResponse)
def paste_text(request: PasteRequest):
    """
    Paste text instantly into the browser.

    Mirrors 'inspekt paste' CLI command.

    By default, clears any existing text before pasting.
    This is equivalent to type with maximum speed.

    Examples:
        - Paste text: `{"text": "Hello World"}`
        - Paste without clearing: `{"text": "append this", "clear": false}`
        - Paste into specific field: `{"text": "test@example.com", "selector": "input[type=email]"}`
    """
    try:
        response = _send_text_api(request.text, request.selector, 0, request.clear)

        return {
            "ok": True,
            "result": response,
            "error": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/wait", response_model=CommandResponse)
def wait_for_element(request: WaitRequest):
    """
    Wait for an element to appear, be visible, hidden, or contain text.

    Mirrors 'inspekt wait' CLI command.

    By default, waits for element to exist in the DOM.

    Examples:
        - Wait for element: `{"selector": "button#submit"}`
        - Wait to be visible: `{"selector": ".modal", "wait_type": "visible"}`
        - Wait to be hidden: `{"selector": ".loading-spinner", "wait_type": "hidden"}`
        - Wait for text: `{"selector": "h1", "wait_type": "text", "text": "Success"}`
        - Custom timeout: `{"selector": "div.result", "timeout": 10}`
    """
    client = get_bridge_client()

    # Load the wait script
    script_loader = ScriptLoader()
    try:
        script = script_loader.load_script_sync("wait_for.js")
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Script not found: {str(e)}")

    # Replace placeholders with properly escaped values
    timeout_ms = request.timeout * 1000

    code = script.replace("'SELECTOR_PLACEHOLDER'", json.dumps(request.selector))
    code = code.replace("'WAIT_TYPE_PLACEHOLDER'", json.dumps(request.wait_type))
    code = code.replace("'TEXT_PLACEHOLDER'", json.dumps(request.text or ""))
    code = code.replace("TIMEOUT_PLACEHOLDER", str(timeout_ms))

    try:
        # Use longer timeout for the request (add 5 seconds buffer)
        result = client.execute(code, timeout=request.timeout + 5)

        if not result.get("ok"):
            raise HTTPException(status_code=500, detail=result.get("error"))

        response = result.get("result", {})

        if response.get("error"):
            raise HTTPException(status_code=400, detail=response.get("error"))

        if response.get("timeout"):
            raise HTTPException(
                status_code=408, detail=response.get("message", "Operation timed out")
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
