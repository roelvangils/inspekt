"""
Storage API endpoints - Manage unified browser storage (cookies, localStorage, sessionStorage).

This module provides HTTP API endpoints for unified storage management:
- GET /api/storage?types=cookies,local,session - List all storage items
- GET /api/storage/{key}?type=cookies|local|session - Get a specific item by key
- POST /api/storage - Set a storage item
- DELETE /api/storage/{key}?type=cookies|local|session - Delete a specific item
- DELETE /api/storage?types=cookies,local,session - Clear all items

Supports:
  - cookies: Browser cookies (via chrome.cookies API or document.cookie fallback)
  - local: localStorage
  - session: sessionStorage
"""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from inspekt.app.api.models import CommandResponse
from inspekt.services.bridge_executor import get_executor
from inspekt.services.script_loader import ScriptLoader

router = APIRouter()


# Request Models
class SetStorageRequest(BaseModel):
    """Request model for setting storage items."""

    key: str = Field(..., description="Storage key / cookie name")
    value: str = Field(..., description="Storage value / cookie value")
    type: Literal["cookies", "local", "session"] = Field(
        "local", description="Storage type (default: local)"
    )

    # Cookie-specific options (only used when type="cookies")
    max_age: int | None = Field(None, description="Cookie max age in seconds (cookies only)")
    expires: str | None = Field(None, description="Cookie expiration date (cookies only)")
    path: str = Field("/", description="Cookie path (cookies only, default: /)")
    domain: str | None = Field(None, description="Cookie domain (cookies only)")
    secure: bool = Field(False, description="Secure flag - HTTPS only (cookies only)")
    same_site: Literal["Strict", "Lax", "None"] | None = Field(
        None, description="SameSite attribute (cookies only)"
    )


# Response Models
class StorageListResponse(BaseModel):
    """Response model for listing storage items."""

    ok: bool = Field(..., description="Whether the command executed successfully")
    result: dict[str, Any] | None = Field(None, description="Storage data")
    error: str | None = Field(None, description="Error message if ok=False")


class StorageGetResponse(BaseModel):
    """Response model for getting a specific storage item."""

    ok: bool = Field(..., description="Whether the command executed successfully")
    result: dict[str, Any] | None = Field(None, description="Storage item data")
    error: str | None = Field(None, description="Error message if ok=False")


# Helper Functions
def _execute_unified_storage_action(
    types: list[str],
    action: str,
    key: str = "",
    value: str = "",
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Helper function to execute unified storage actions."""
    executor = get_executor()
    loader = ScriptLoader()

    # Load the unified storage script
    try:
        script = loader.load_script_sync("storage_unified.js")
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Script not found: {e!s}")

    # Replace placeholders
    code = script.replace("ACTION_PLACEHOLDER", action)
    code = code.replace("TYPES_PLACEHOLDER", json.dumps(types))
    code = code.replace("KEY_PLACEHOLDER", key)
    code = code.replace("VALUE_PLACEHOLDER", value)
    code = code.replace("OPTIONS_PLACEHOLDER", json.dumps(options if options else {}))

    result = executor.execute(code, timeout=60.0)

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error"))

    response = result.get("result", {})

    if not response.get("ok"):
        raise HTTPException(status_code=400, detail=response.get("error", "Unknown error"))

    return response


def _parse_types_param(types_str: str | None, default: list[str] | None = None) -> list[str]:
    """Parse comma-separated types string into list."""
    if not types_str:
        return default or ["cookies", "local", "session"]

    if types_str == "all":
        return ["cookies", "local", "session"]

    # Split by comma and clean up
    return [t.strip() for t in types_str.split(",") if t.strip() in ["cookies", "local", "session"]]


# Endpoints
@router.get("", response_model=StorageListResponse)
@router.get("/", response_model=StorageListResponse)
def list_storage(
    types: str | None = Query(
        None,
        description="Comma-separated storage types: cookies,local,session or 'all' (default: all)",
    ),
    type: Literal["local", "session", "cookies", "all"] | None = Query(
        None, description="[DEPRECATED] Single storage type - use 'types' instead"
    ),
):
    """
    List all storage items across specified storage types.

    Mirrors 'inspekt storage list --json' CLI command.

    Query Parameters:
        types: Comma-separated list - "cookies,local,session" or "all" (default: all)
        type: [DEPRECATED] Single type - "local", "session", "cookies", or "all" (use 'types' instead)

    Returns:
        Unified storage data with items grouped by storage type, plus metadata.

    Example response (all types):
    ```json
    {
        "ok": true,
        "result": {
            "origin": "https://example.com",
            "hostname": "example.com",
            "timestamp": "2025-11-15T10:30:00.000Z",
            "storage": {
                "cookies": {
                    "ok": true,
                    "count": 3,
                    "items": [...],
                    "apiUsed": "chrome.cookies"
                },
                "localStorage": {
                    "ok": true,
                    "count": 5,
                    "items": {...}
                },
                "sessionStorage": {
                    "ok": true,
                    "count": 2,
                    "items": {...}
                }
            },
            "totals": {
                "totalItems": 10,
                "totalSize": 2048,
                "byType": {
                    "cookies": 3,
                    "localStorage": 5,
                    "sessionStorage": 2
                }
            }
        }
    }
    ```
    """
    try:
        # Handle legacy 'type' parameter (backward compatibility)
        if type and not types:
            if type == "all":
                types_list = ["cookies", "local", "session"]
            else:
                types_list = [type]
        else:
            types_list = _parse_types_param(types)

        response = _execute_unified_storage_action(types_list, "list")

        return {
            "ok": True,
            "result": response,
            "error": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{key}", response_model=StorageGetResponse)
def get_storage(
    key: str,
    type: Literal["cookies", "local", "session"] = Query("local", description="Storage type"),
):
    """
    Get the value of a specific storage item.

    Mirrors 'inspekt storage get <key> --json' CLI command.

    Path Parameters:
        key: Storage key / cookie name to retrieve

    Query Parameters:
        type: Storage type - "cookies", "local", or "session" (default: local)

    Returns:
        Storage key, value, and whether it exists.

    Example response:
    ```json
    {
        "ok": true,
        "result": {
            "origin": "https://example.com",
            "hostname": "example.com",
            "storage": {
                "localStorage": {
                    "ok": true,
                    "key": "user_token",
                    "value": "abc123",
                    "exists": true
                }
            }
        }
    }
    ```
    """
    try:
        response = _execute_unified_storage_action([type], "get", key=key)

        # Check if item exists in the response
        storage_key = (
            "cookies"
            if type == "cookies"
            else "localStorage"
            if type == "local"
            else "sessionStorage"
        )
        storage_result = response.get("storage", {}).get(storage_key, {})

        if not storage_result.get("exists"):
            storage_name = (
                "cookies"
                if type == "cookies"
                else ("localStorage" if type == "local" else "sessionStorage")
            )
            raise HTTPException(status_code=404, detail=f"Key not found in {storage_name}: {key}")

        return {
            "ok": True,
            "result": response,
            "error": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=CommandResponse)
@router.post("/", response_model=CommandResponse)
def set_storage(request: SetStorageRequest):
    """
    Set a storage item (localStorage, sessionStorage, or cookie).

    Mirrors 'inspekt storage set' CLI command.

    Request Body:
        key: Storage key / cookie name
        value: Storage value / cookie value
        type: Storage type - "cookies", "local", or "session" (default: local)

        Cookie-specific options (only used when type="cookies"):
        - max_age: Cookie max age in seconds
        - expires: Cookie expiration date
        - path: Cookie path (default: "/")
        - domain: Cookie domain
        - secure: Secure flag (HTTPS only)
        - same_site: SameSite attribute ("Strict", "Lax", or "None")

    Examples:
        - localStorage: `{"key": "user_token", "value": "abc123", "type": "local"}`
        - sessionStorage: `{"key": "temp_data", "value": "xyz", "type": "session"}`
        - Cookie (basic): `{"key": "session_id", "value": "abc123", "type": "cookies"}`
        - Cookie (secure): `{"key": "auth_token", "value": "xyz", "type": "cookies", "secure": true, "max_age": 3600}`

    Returns:
        Confirmation of set operation.

    Example response:
    ```json
    {
        "ok": true,
        "result": {
            "origin": "https://example.com",
            "storage": {
                "cookies": {
                    "ok": true,
                    "key": "session_id",
                    "value": "abc123"
                }
            }
        }
    }
    ```
    """
    try:
        # Build options for cookies
        options = {}
        if request.type == "cookies":
            options["path"] = request.path
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

        response = _execute_unified_storage_action(
            [request.type], "set", key=request.key, value=request.value, options=options
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


@router.delete("/{key}", response_model=CommandResponse)
def delete_storage(
    key: str,
    type: Literal["cookies", "local", "session"] = Query("local", description="Storage type"),
):
    """
    Delete a specific storage item or cookie.

    Mirrors 'inspekt storage delete <key>' CLI command.

    Path Parameters:
        key: Storage key / cookie name to delete

    Query Parameters:
        type: Storage type - "cookies", "local", or "session" (default: local)

    Examples:
        - DELETE /api/storage/user_token?type=local
        - DELETE /api/storage/session_id?type=cookies

    Returns:
        Confirmation of deletion.

    Example response:
    ```json
    {
        "ok": true,
        "result": {
            "origin": "https://example.com",
            "storage": {
                "localStorage": {
                    "ok": true,
                    "key": "user_token"
                }
            }
        }
    }
    ```
    """
    try:
        response = _execute_unified_storage_action([type], "delete", key=key)

        return {
            "ok": True,
            "result": response,
            "error": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("", response_model=CommandResponse)
@router.delete("/", response_model=CommandResponse)
def clear_storage(
    types: str | None = Query(
        None,
        description="Comma-separated storage types: cookies,local,session or 'all' (default: all)",
    ),
    type: Literal["local", "session", "cookies", "all"] | None = Query(
        None, description="[DEPRECATED] Single storage type - use 'types' instead"
    ),
):
    """
    Clear all storage items across specified storage types.

    Mirrors 'inspekt storage clear' CLI command.

    Query Parameters:
        types: Comma-separated list - "cookies,local,session" or "all" (default: all)
        type: [DEPRECATED] Single type - "local", "session", "cookies", or "all" (use 'types' instead)

    Examples:
        - DELETE /api/storage?types=local
        - DELETE /api/storage?types=cookies,session
        - DELETE /api/storage?types=all

    Returns:
        Number of items deleted per storage type.

    Example response (all types):
    ```json
    {
        "ok": true,
        "result": {
            "origin": "https://example.com",
            "storage": {
                "cookies": {
                    "ok": true,
                    "deleted": 3
                },
                "localStorage": {
                    "ok": true,
                    "deleted": 5
                },
                "sessionStorage": {
                    "ok": true,
                    "deleted": 2
                }
            }
        }
    }
    ```
    """
    try:
        # Handle legacy 'type' parameter (backward compatibility)
        if type and not types:
            if type == "all":
                types_list = ["cookies", "local", "session"]
            else:
                types_list = [type]
        else:
            types_list = _parse_types_param(types)

        response = _execute_unified_storage_action(types_list, "clear")

        return {
            "ok": True,
            "result": response,
            "error": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
