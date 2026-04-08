"""
Cookies API endpoints - Manage browser cookies.

⚠ DEPRECATED: This API endpoint group is deprecated and will be removed in v2.0.0
   Use '/api/storage' with type parameter instead.

Migration guide:
  GET  /api/cookies              → GET  /api/storage?types=cookies
  GET  /api/cookies/{name}       → GET  /api/storage/{name}?type=cookies
  POST /api/cookies              → POST /api/storage (with type: "cookies")
  DELETE /api/cookies/{name}     → DELETE /api/storage/{name}?type=cookies
  DELETE /api/cookies            → DELETE /api/storage?types=cookies

This module provides HTTP API endpoints for cookie management:
- GET /api/cookies - List all cookies for the current page
- GET /api/cookies/{name} - Get a specific cookie by name
- POST /api/cookies - Set a cookie with various options
- DELETE /api/cookies/{name} - Delete a specific cookie
- DELETE /api/cookies - Clear all cookies
"""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from inspekt.app.api.dependencies import get_bridge_client
from inspekt.app.api.models import CommandResponse
from inspekt.services.bridge_executor import get_executor
from inspekt.services.script_loader import ScriptLoader

router = APIRouter()


def _add_deprecation_headers(response: Response):
    """Add deprecation warning headers to API responses."""
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Wed, 01 Jan 2026 00:00:00 GMT"
    response.headers["Link"] = '</api/storage>; rel="alternate"'
    response.headers["Warning"] = '299 - "This API endpoint is deprecated. Use /api/storage instead."'


# Request Models
class SetCookieRequest(BaseModel):
    """Request model for setting cookies."""

    name: str = Field(..., description="Cookie name")
    value: str = Field(..., description="Cookie value")
    max_age: int | None = Field(None, description="Max age in seconds")
    expires: str | None = Field(
        None, description="Expiration date (e.g., 'Wed, 21 Oct 2025 07:28:00 GMT')"
    )
    path: str = Field("/", description="Cookie path")
    domain: str | None = Field(None, description="Cookie domain")
    secure: bool = Field(False, description="Secure flag (HTTPS only)")
    same_site: Literal["Strict", "Lax", "None"] | None = Field(None, description="SameSite attribute")


# Response Models
class CookieDetail(BaseModel):
    """Detailed cookie information from chrome.cookies API."""

    name: str = Field(..., description="Cookie name")
    value: str = Field(..., description="Cookie value")
    domain: str = Field(..., description="Cookie domain")
    path: str = Field(..., description="Cookie path")
    expires: str | None = Field(None, description="Expiration date in ISO format")
    size: int = Field(..., description="Cookie size in bytes (name + value length)")
    type: str = Field(..., description="Cookie type: 'session' or 'persistent'")
    party: str = Field(..., description="Cookie party: 'first-party' or 'third-party'")
    secure: bool = Field(False, description="Secure flag (HTTPS only)")
    httpOnly: bool = Field(False, description="HttpOnly flag (not accessible via JavaScript)")
    sameSite: str | None = Field(None, description="SameSite attribute")
    session: bool = Field(..., description="Whether this is a session cookie")
    hostOnly: bool | None = Field(None, description="Whether cookie is host-only")
    storeId: str | None = Field(None, description="Cookie store ID")


class CookieListResult(BaseModel):
    """Result data for cookie list operation."""

    action: str = Field(..., description="Action performed ('list')")
    count: int = Field(..., description="Number of cookies")
    cookies: list[CookieDetail] | dict[str, str] = Field(
        ..., description="Cookie data - enhanced (array) or legacy (dict)"
    )
    apiUsed: str = Field(..., description="API used: 'chrome.cookies' or 'document.cookie'")
    origin: str = Field(..., description="Page origin")
    hostname: str = Field(..., description="Page hostname")


class CookiesListResponse(BaseModel):
    """Response model for listing cookies."""

    ok: bool = Field(..., description="Whether the command executed successfully")
    result: CookieListResult | None = Field(None, description="Cookies data")
    error: str | None = Field(None, description="Error message if ok=False")


class CookieGetResponse(BaseModel):
    """Response model for getting a specific cookie."""

    ok: bool = Field(..., description="Whether the command executed successfully")
    result: dict[str, Any] | None = Field(None, description="Cookie data")
    error: str | None = Field(None, description="Error message if ok=False")


# Helper Function
def _execute_cookie_action(
    action: str,
    cookie_name: str = "",
    cookie_value: str = "",
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Helper function to execute cookie actions."""
    executor = get_executor()
    loader = ScriptLoader()

    # Load the cookies script
    try:
        script = loader.load_script_sync("cookies.js")
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Script not found: {str(e)}")

    # Replace placeholders
    options_json = json.dumps(options if options else {})
    code = script.replace("ACTION_PLACEHOLDER", action)
    code = code.replace("NAME_PLACEHOLDER", cookie_name)
    code = code.replace("VALUE_PLACEHOLDER", cookie_value)
    code = code.replace("OPTIONS_PLACEHOLDER", options_json)

    result = executor.execute(code, timeout=60.0)

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error"))

    response = result.get("result", {})

    if response.get("error"):
        raise HTTPException(status_code=400, detail=response.get("error"))

    return response


# Endpoints
@router.get("", response_model=CookiesListResponse)
@router.get("/", response_model=CookiesListResponse)
def list_cookies(response: Response):
    """
    List all cookies for the current page.

    Mirrors 'inspekt cookies list --json' CLI command.

    Returns:
        Cookie data with comprehensive metadata (when extension is active)
        or basic name/value pairs (fallback mode).

    Example response (enhanced mode via chrome.cookies API):
    ```json
    {
        "ok": true,
        "result": {
            "action": "list",
            "count": 2,
            "cookies": [
                {
                    "name": "session_id",
                    "value": "abc123",
                    "domain": "example.com",
                    "path": "/",
                    "expires": "2025-10-21T07:28:00.000Z",
                    "size": 16,
                    "type": "persistent",
                    "party": "first-party",
                    "secure": true,
                    "httpOnly": true,
                    "sameSite": "Lax",
                    "session": false,
                    "hostOnly": true
                }
            ],
            "apiUsed": "chrome.cookies",
            "origin": "https://example.com",
            "hostname": "example.com"
        }
    }
    ```

    Example response (fallback mode via document.cookie):
    ```json
    {
        "ok": true,
        "result": {
            "action": "list",
            "count": 2,
            "cookies": {
                "session_id": "abc123",
                "user_pref": "dark"
            },
            "apiUsed": "document.cookie",
            "origin": "https://example.com",
            "hostname": "example.com"
        }
    }
    ```
    """
    _add_deprecation_headers(response)
    try:
        result = _execute_cookie_action("list")
        return {
            "ok": True,
            "result": result,
            "error": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{name}", response_model=CookieGetResponse)
def get_cookie(name: str, response: Response):
    """
    Get the value of a specific cookie.

    Mirrors 'inspekt cookies get <name> --json' CLI command.

    Args:
        name: Cookie name to retrieve

    Returns:
        Cookie name, value, and whether it exists.

    Example response:
    ```json
    {
        "ok": true,
        "result": {
            "name": "session_id",
            "value": "abc123",
            "exists": true
        }
    }
    ```
    """
    _add_deprecation_headers(response)
    try:
        result = _execute_cookie_action("get", cookie_name=name)

        # If cookie doesn't exist, return 404
        if not result.get("exists"):
            raise HTTPException(status_code=404, detail=f"Cookie not found: {name}")

        return {
            "ok": True,
            "result": result,
            "error": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=CommandResponse)
@router.post("/", response_model=CommandResponse)
def set_cookie(request: SetCookieRequest, response: Response):
    """
    Set a cookie with various options.

    Mirrors 'inspekt cookies set' CLI command.

    Examples:
        - Basic cookie: `{"name": "session_id", "value": "abc123"}`
        - With max age: `{"name": "token", "value": "xyz", "max_age": 3600}`
        - With options: `{"name": "user_pref", "value": "dark", "path": "/", "secure": true}`
        - SameSite: `{"name": "tracking", "value": "123", "same_site": "Lax"}`

    Cookie options:
        - max_age: Lifetime in seconds
        - expires: Expiration date string
        - path: Cookie path (default: "/")
        - domain: Cookie domain
        - secure: HTTPS only
        - same_site: "Strict", "Lax", or "None"
    """
    _add_deprecation_headers(response)
    try:
        options: dict[str, Any] = {"path": request.path}

        if request.max_age is not None:
            options["maxAge"] = request.max_age
        if request.expires:
            options["expires"] = request.expires
        if request.domain:
            options["domain"] = request.domain
        if request.secure:
            options["secure"] = True
        if request.same_site:
            options["sameSite"] = request.same_site

        result = _execute_cookie_action(
            "set", cookie_name=request.name, cookie_value=request.value, options=options
        )

        return {
            "ok": True,
            "result": result,
            "error": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{name}", response_model=CommandResponse)
def delete_cookie(name: str, response: Response):
    """
    Delete a specific cookie.

    Mirrors 'inspekt cookies delete <name>' CLI command.

    Args:
        name: Cookie name to delete

    Example:
        DELETE /api/cookies/session_id

    Returns:
        Confirmation of deletion.
    """
    _add_deprecation_headers(response)
    try:
        result = _execute_cookie_action("delete", cookie_name=name)

        return {
            "ok": True,
            "result": result,
            "error": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("", response_model=CommandResponse)
@router.delete("/", response_model=CommandResponse)
def clear_cookies(response: Response):
    """
    Clear all cookies for the current page.

    Mirrors 'inspekt cookies clear' CLI command.

    Deletes all cookies associated with the current domain.

    Returns:
        Number of cookies deleted.

    Example response:
    ```json
    {
        "ok": true,
        "result": {
            "deleted": 5
        }
    }
    ```
    """
    _add_deprecation_headers(response)
    try:
        result = _execute_cookie_action("clear")

        return {
            "ok": True,
            "result": result,
            "error": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
