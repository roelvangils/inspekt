"""Browser control API endpoints.

This module provides HTTP API endpoints for browser-level operations
that use AppleScript on macOS to control browser windows and tabs.

- POST /api/browser/activate-tab - Activate a browser tab by URL
- GET /api/browser/platform - Check if platform supports browser activation
"""

from __future__ import annotations

import platform

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from inspekt.services.applescript_utils import (
    activate_browser_tab,
    is_browser_supported,
)

router = APIRouter()


class ActivateTabRequest(BaseModel):
    """Request model for activating a browser tab."""

    browser_name: str = Field(..., description="Browser name (Safari, Chrome, Brave, Edge)")
    url: str = Field(..., description="URL of the tab to activate (uses 'contains' matching)")


class ActivateTabResponse(BaseModel):
    """Response model for activate tab."""

    ok: bool
    message: str | None = None
    error: str | None = None


class PlatformResponse(BaseModel):
    """Response model for platform check."""

    is_macos: bool
    platform: str
    supports_activation: bool


@router.get("/platform", response_model=PlatformResponse)
def check_platform():
    """Check if the current platform supports browser tab activation.

    Browser tab activation using AppleScript is only supported on macOS.
    Use this endpoint to conditionally show/hide activation UI.
    """
    is_macos = platform.system() == "Darwin"
    return PlatformResponse(
        is_macos=is_macos,
        platform=platform.system(),
        supports_activation=is_macos,
    )


@router.post("/activate-tab", response_model=ActivateTabResponse)
def activate_tab(request: ActivateTabRequest):
    """Activate a browser tab by bringing it to the foreground.

    Uses AppleScript on macOS to find and activate the tab matching the URL.
    The URL matching uses 'contains' semantics, so partial URLs work.

    Supported browsers:
    - Safari (full support)
    - Chrome (full support)
    - Brave (full support)
    - Edge (full support)
    - Firefox (NOT supported - no AppleScript tab API)

    Examples:
        - Activate Safari tab: `{"browser_name": "Safari", "url": "github.com"}`
        - Activate Chrome tab: `{"browser_name": "Chrome", "url": "localhost:8000"}`
    """
    # Check platform
    if platform.system() != "Darwin":
        raise HTTPException(
            status_code=501,
            detail="Tab activation is only supported on macOS",
        )

    # Check browser support
    if not is_browser_supported(request.browser_name):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported browser: {request.browser_name}. "
            "Supported browsers: Safari, Chrome, Brave, Edge",
        )

    # Execute activation
    result = activate_browser_tab(request.browser_name, request.url)

    if not result.ok:
        # Map error codes to HTTP status codes
        error_code = result.error_code

        if error_code == -600:
            # Application not running
            raise HTTPException(
                status_code=503,
                detail=f"{request.browser_name} is not running",
            )
        elif error_code == -1728:
            # Invalid reference (tab not found)
            raise HTTPException(
                status_code=404,
                detail=f"Tab not found with URL containing: {request.url}",
            )
        elif "Tab not found" in (result.error or ""):
            raise HTTPException(
                status_code=404,
                detail=f"Tab not found with URL containing: {request.url}",
            )
        else:
            # Other errors
            return ActivateTabResponse(
                ok=False,
                error=result.error or "Unknown error",
            )

    return ActivateTabResponse(
        ok=True,
        message=f"Activated {request.browser_name} tab",
    )
