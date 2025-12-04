"""Plugin Management API endpoints.

This module provides HTTP API endpoints for managing custom JavaScript plugins
(bookmarklets) for browser automation.

Plugins are stored in SQLite and can be executed via CLI, API, or MCP tools.
"""

import json
from typing import Any

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from inspekt.services.plugin_service import get_plugin_service

router = APIRouter()

# Bridge server configuration
BRIDGE_HTTP_HOST = "127.0.0.1"
BRIDGE_HTTP_PORT = 8765


# ============================================================================
# Request/Response Models
# ============================================================================


class PluginCreateRequest(BaseModel):
    """Request model for creating a plugin."""

    name: str = Field(..., min_length=1, max_length=100, description="Plugin name")
    code: str = Field("", description="JavaScript code (can be empty, edit later)")
    description: str | None = Field(None, description="Plugin description")
    category: str | None = Field(None, description="Category for filtering")
    tags: list[str] | None = Field(None, description="List of tags")
    returns_data: bool = Field(False, description="Whether plugin returns JSON data")
    timeout: int = Field(30, ge=1, le=300, description="Execution timeout in seconds")
    mcp_exposed: bool = Field(False, description="Expose as MCP tool")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Text Spacing Bookmarklet",
                "code": "(function(){...})();",
                "description": "Tests WCAG 1.4.12 text spacing requirements",
                "category": "a11y",
                "tags": ["wcag", "visual"],
                "mcp_exposed": True,
            }
        }
    }


class PluginFromBookmarkletRequest(BaseModel):
    """Request model for creating a plugin from bookmarklet URL."""

    bookmarklet: str = Field(..., description="Bookmarklet URL or code")
    name: str = Field(..., min_length=1, max_length=100, description="Plugin name")
    description: str | None = Field(None, description="Plugin description")
    category: str | None = Field(None, description="Category for filtering")
    tags: list[str] | None = Field(None, description="List of tags")
    returns_data: bool = Field(False, description="Whether plugin returns JSON data")
    mcp_exposed: bool = Field(False, description="Expose as MCP tool")

    model_config = {
        "json_schema_extra": {
            "example": {
                "bookmarklet": "javascript:(function(){alert('Hello')})();",
                "name": "Hello World",
                "category": "utility",
            }
        }
    }


class PluginUpdateRequest(BaseModel):
    """Request model for updating a plugin."""

    name: str | None = Field(None, min_length=1, max_length=100, description="New name")
    code: str | None = Field(None, min_length=1, description="New JavaScript code")
    description: str | None = Field(None, description="New description")
    credits: str | None = Field(None, description="Original author/source attribution")
    category: str | None = Field(None, description="New category")
    tags: list[str] | None = Field(None, description="New tags")
    returns_data: bool | None = Field(None, description="Returns data flag")
    timeout: int | None = Field(None, ge=1, le=300, description="New timeout")
    mcp_exposed: bool | None = Field(None, description="MCP exposure flag")
    unload_mode: str | None = Field(None, description="Unload behavior: 'toggle', 'custom', or 'none'")
    unload_code: str | None = Field(None, description="Custom unload JavaScript code")


class PluginTestRequest(BaseModel):
    """Request model for testing arbitrary code."""

    code: str = Field(..., min_length=1, description="JavaScript code to test")
    timeout: float = Field(30.0, ge=1, le=300, description="Execution timeout")
    capture_console: bool = Field(True, description="Capture console output")
    browser_index: int | None = Field(None, description="Target browser index (0-based)")


class PluginImportRequest(BaseModel):
    """Request model for importing plugins."""

    data: dict[str, Any] = Field(..., description="Export data with plugins array")
    conflict_mode: str = Field(
        "skip",
        description="How to handle conflicts: 'skip' or 'replace'",
    )


class PluginResponse(BaseModel):
    """Response model for plugin operations."""

    ok: bool
    plugin: dict | None = None
    warnings: list[str] | None = None
    error: str | None = None


class PluginListResponse(BaseModel):
    """Response model for list plugins operation."""

    ok: bool
    plugins: list[dict] | None = None
    count: int | None = None
    error: str | None = None


class PluginRunResponse(BaseModel):
    """Response model for plugin execution."""

    ok: bool
    result: Any | None = None
    console_output: list[dict] | None = None
    execution_time_ms: int | None = None
    error: str | None = None


class PluginExportResponse(BaseModel):
    """Response model for export operation."""

    ok: bool
    data: dict | None = None
    count: int | None = None
    error: str | None = None


class PluginImportResponse(BaseModel):
    """Response model for import operation."""

    ok: bool
    imported: int | None = None
    skipped: int | None = None
    total: int | None = None
    errors: list[str] | None = None
    error: str | None = None


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("", response_model=PluginListResponse)
def list_plugins(category: str | None = None, mcp_only: bool = False):
    """
    List all plugins with optional filtering.

    Args:
        category: Filter by category
        mcp_only: Only return MCP-exposed plugins

    Returns:
        List of plugin objects

    Examples:
        ```bash
        curl http://localhost:8000/api/plugins
        curl http://localhost:8000/api/plugins?category=a11y
        curl http://localhost:8000/api/plugins?mcp_only=true
        ```
    """
    try:
        plugin_service = get_plugin_service()
        plugins = plugin_service.list_plugins(category=category, mcp_only=mcp_only)
        return {"ok": True, "plugins": plugins, "count": len(plugins)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
def get_categories():
    """
    Get all unique plugin categories.

    Returns:
        List of category strings

    Examples:
        ```bash
        curl http://localhost:8000/api/plugins/categories
        ```
    """
    try:
        plugin_service = get_plugin_service()
        categories = plugin_service.get_categories()
        return {"ok": True, "categories": categories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tags")
def get_tags():
    """
    Get all unique plugin tags.

    Returns:
        List of tag strings

    Examples:
        ```bash
        curl http://localhost:8000/api/plugins/tags
        ```
    """
    try:
        plugin_service = get_plugin_service()
        tags = plugin_service.get_all_tags()
        return {"ok": True, "tags": tags}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export", response_model=PluginExportResponse)
def export_plugins(ids: str | None = None):
    """
    Export plugins to JSON format.

    Args:
        ids: Comma-separated list of plugin IDs to export (all if not specified)

    Returns:
        Export data with plugins array

    Examples:
        ```bash
        curl http://localhost:8000/api/plugins/export
        curl http://localhost:8000/api/plugins/export?ids=text-spacing,focus-order
        ```
    """
    try:
        plugin_service = get_plugin_service()
        plugin_ids = ids.split(",") if ids else None
        result = plugin_service.export_plugins(plugin_ids)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{plugin_id}", response_model=PluginResponse)
def get_plugin(plugin_id: str):
    """
    Get a single plugin by ID.

    Args:
        plugin_id: Plugin slug ID

    Returns:
        Plugin object

    Examples:
        ```bash
        curl http://localhost:8000/api/plugins/text-spacing
        ```
    """
    try:
        plugin_service = get_plugin_service()
        plugin = plugin_service.get_plugin(plugin_id)

        if not plugin:
            raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

        return {"ok": True, "plugin": plugin}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=PluginResponse)
def create_plugin(request: PluginCreateRequest):
    """
    Create a new plugin.

    Args:
        request: Plugin data

    Returns:
        Created plugin object

    Examples:
        ```bash
        curl -X POST http://localhost:8000/api/plugins \\
          -H "Content-Type: application/json" \\
          -d '{
            "name": "Dark Mode",
            "code": "(function(){document.body.classList.toggle(\"dark\")})();",
            "category": "utility"
          }'
        ```
    """
    try:
        plugin_service = get_plugin_service()
        result = plugin_service.add_plugin(
            name=request.name,
            code=request.code,
            description=request.description,
            category=request.category,
            tags=request.tags,
            returns_data=request.returns_data,
            timeout=request.timeout,
            mcp_exposed=request.mcp_exposed,
        )

        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error"))

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/from-bookmarklet", response_model=PluginResponse)
def create_from_bookmarklet(request: PluginFromBookmarkletRequest):
    """
    Create a plugin from a bookmarklet URL or code.

    Automatically parses and extracts JavaScript from bookmarklet format.

    Args:
        request: Bookmarklet data with name

    Returns:
        Created plugin object with parsing warnings

    Examples:
        ```bash
        curl -X POST http://localhost:8000/api/plugins/from-bookmarklet \\
          -H "Content-Type: application/json" \\
          -d '{
            "bookmarklet": "javascript:(function(){alert(1)})();",
            "name": "Alert Test"
          }'
        ```
    """
    try:
        plugin_service = get_plugin_service()
        result = plugin_service.add_from_bookmarklet(
            bookmarklet=request.bookmarklet,
            name=request.name,
            description=request.description,
            category=request.category,
            tags=request.tags,
            returns_data=request.returns_data,
            mcp_exposed=request.mcp_exposed,
        )

        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error"))

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{plugin_id}", response_model=PluginResponse)
def update_plugin(plugin_id: str, request: PluginUpdateRequest):
    """
    Update an existing plugin.

    Args:
        plugin_id: Plugin slug ID
        request: Fields to update

    Returns:
        Updated plugin object

    Examples:
        ```bash
        curl -X PUT http://localhost:8000/api/plugins/dark-mode \\
          -H "Content-Type: application/json" \\
          -d '{"description": "Updated description"}'
        ```
    """
    try:
        plugin_service = get_plugin_service()

        # Build updates dict from non-None values
        updates = {k: v for k, v in request.model_dump().items() if v is not None}

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = plugin_service.update_plugin(plugin_id, **updates)

        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error"))

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{plugin_id}")
def delete_plugin(plugin_id: str):
    """
    Delete a plugin.

    Args:
        plugin_id: Plugin slug ID

    Returns:
        Deletion confirmation

    Examples:
        ```bash
        curl -X DELETE http://localhost:8000/api/plugins/dark-mode
        ```
    """
    try:
        plugin_service = get_plugin_service()
        result = plugin_service.delete_plugin(plugin_id)

        if not result.get("ok"):
            raise HTTPException(status_code=404, detail=result.get("error"))

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{plugin_id}/run", response_model=PluginRunResponse)
def run_plugin(plugin_id: str, capture_console: bool = True):
    """
    Execute a plugin in the browser.

    Args:
        plugin_id: Plugin slug ID
        capture_console: Whether to capture console output

    Returns:
        Execution result with optional console output

    Examples:
        ```bash
        curl -X POST http://localhost:8000/api/plugins/text-spacing/run
        curl -X POST "http://localhost:8000/api/plugins/text-spacing/run?capture_console=true"
        ```
    """
    try:
        plugin_service = get_plugin_service()
        plugin = plugin_service.get_plugin(plugin_id)

        if not plugin:
            raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

        result = _execute_plugin_code(
            code=plugin["code"],
            timeout=plugin["timeout"],
            capture_console=capture_console,
            returns_data=plugin["returns_data"],
        )

        # Update run count
        plugin_service.increment_run_count(plugin_id)

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{plugin_id}/unload", response_model=PluginRunResponse)
def unload_plugin(plugin_id: str, capture_console: bool = True):
    """
    Unload/reverse a plugin's effects.

    Behavior depends on the plugin's unload_mode:
    - 'toggle': Re-runs the plugin code (for toggle-style plugins)
    - 'custom': Runs the custom unload_code
    - 'none': Returns error (plugin doesn't support unloading)

    Args:
        plugin_id: Plugin slug ID
        capture_console: Whether to capture console output

    Returns:
        Execution result with optional console output

    Examples:
        ```bash
        curl -X POST http://localhost:8000/api/plugins/text-spacing/unload
        ```
    """
    try:
        plugin_service = get_plugin_service()
        plugin = plugin_service.get_plugin(plugin_id)

        if not plugin:
            raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

        unload_mode = plugin.get("unload_mode", "none")

        if unload_mode == "none":
            return {
                "ok": False,
                "error": f"Plugin '{plugin['name']}' does not support unloading",
            }

        # Determine which code to run
        if unload_mode == "toggle":
            code_to_run = plugin["code"]
        elif unload_mode == "custom":
            code_to_run = plugin.get("unload_code")
            if not code_to_run:
                return {
                    "ok": False,
                    "error": f"Plugin '{plugin['name']}' has custom unload mode but no unload code",
                }
        else:
            return {
                "ok": False,
                "error": f"Unknown unload mode: {unload_mode}",
            }

        result = _execute_plugin_code(
            code=code_to_run,
            timeout=plugin["timeout"],
            capture_console=capture_console,
            returns_data=plugin["returns_data"],
        )

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test", response_model=PluginRunResponse)
def test_code(request: PluginTestRequest):
    """
    Test arbitrary JavaScript code without saving.

    Args:
        request: Code and execution settings

    Returns:
        Execution result with optional console output

    Examples:
        ```bash
        curl -X POST http://localhost:8000/api/plugins/test \\
          -H "Content-Type: application/json" \\
          -d '{"code": "console.log(\"test\"); return {tested: true};"}'
        ```
    """
    try:
        result = _execute_plugin_code(
            code=request.code,
            timeout=request.timeout,
            capture_console=request.capture_console,
            returns_data=True,  # Always capture return value for tests
            browser_index=request.browser_index,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import", response_model=PluginImportResponse)
def import_plugins(request: PluginImportRequest):
    """
    Import plugins from JSON data.

    Args:
        request: Export data with conflict handling mode

    Returns:
        Import results with counts

    Examples:
        ```bash
        curl -X POST http://localhost:8000/api/plugins/import \\
          -H "Content-Type: application/json" \\
          -d '{
            "data": {"version": "1.0", "plugins": [...]},
            "conflict_mode": "skip"
          }'
        ```
    """
    try:
        plugin_service = get_plugin_service()
        result = plugin_service.import_plugins(
            data=request.data,
            conflict_mode=request.conflict_mode,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Helper Functions
# ============================================================================


def _execute_plugin_code(
    code: str,
    timeout: float = 30.0,
    capture_console: bool = True,
    returns_data: bool = False,
    browser_index: int | None = None,
) -> dict[str, Any]:
    """
    Execute JavaScript code in the browser via the bridge.

    Args:
        code: JavaScript code to execute
        timeout: Execution timeout in seconds
        capture_console: Whether to capture console output
        returns_data: Whether to capture return value
        browser_index: Target browser index (0-based), or None for default

    Returns:
        Execution result dict
    """
    import time

    start_time = time.time()
    console_output: list[dict] = []

    try:
        # Clear console before execution if capturing
        if capture_console:
            try:
                requests.post(
                    f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/console/clear",
                    timeout=5.0,
                )
            except requests.exceptions.RequestException:
                pass  # Console clear is optional

        # Execute code via bridge
        payload = {"code": code, "timeout": timeout}
        if browser_index is not None:
            payload["browser_index"] = browser_index

        response = requests.post(
            f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/run",
            json=payload,
            timeout=timeout + 5,
        )

        execution_time_ms = int((time.time() - start_time) * 1000)

        if response.status_code != 200:
            return {
                "ok": False,
                "error": f"Bridge returned HTTP {response.status_code}",
                "execution_time_ms": execution_time_ms,
            }

        result_data = response.json()

        # Capture console output if requested
        if capture_console:
            try:
                console_response = requests.get(
                    f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/console/logs",
                    timeout=5.0,
                )
                if console_response.status_code == 200:
                    console_data = console_response.json()
                    console_output = console_data.get("entries", [])
            except requests.exceptions.RequestException:
                pass  # Console capture is optional

        if not result_data.get("ok"):
            return {
                "ok": False,
                "error": result_data.get("error", "Execution failed"),
                "console_output": console_output if capture_console else None,
                "execution_time_ms": execution_time_ms,
            }

        return {
            "ok": True,
            "result": result_data.get("result") if returns_data else None,
            "console_output": console_output if capture_console else None,
            "execution_time_ms": execution_time_ms,
        }

    except requests.exceptions.ConnectionError:
        return {
            "ok": False,
            "error": "Could not connect to bridge server. Ensure server is running: inspekt start",
        }
    except requests.exceptions.Timeout:
        return {
            "ok": False,
            "error": f"Execution timed out after {timeout} seconds",
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }
