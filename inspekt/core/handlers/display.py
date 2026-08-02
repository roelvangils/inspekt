"""
Display command handlers.

Implements: get_zoom, set_zoom, get_viewport, set_viewport.

Dispatches to either:
- VM control server (when INSPEKT_RESTRICTED=1, i.e., running inside the VM)
- Browser extension bridge + AppleScript (regular macOS browser)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request

from inspekt.core.commands.base import EmptyParams
from inspekt.core.schemas.display import (
    ViewportResponse,
    ViewportSetParams,
    ZoomResponse,
    ZoomSetParams,
    get_wcag_note,
    next_zoom_step,
    previous_zoom_step,
)

logger = logging.getLogger(__name__)

# VM control server port (matches vm/control-server.py)
VM_CONTROL_PORT = 8888

# VM overlay-bus WebSocket port (matches vm/servers/overlay-bus-server.py)
VM_OVERLAY_BUS_PORT = 8890


def _is_vm() -> bool:
    """Check if running inside the Inspekt VM."""
    return os.environ.get("INSPEKT_RESTRICTED") == "1"


def _vm_request(method: str, path: str, data: dict | None = None) -> dict:
    """Make an HTTP request to the VM control server."""
    url = f"http://localhost:{VM_CONTROL_PORT}{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, method=method)
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"VM control server unavailable: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _get_executor():
    """Get the bridge executor for regular browser communication."""
    from inspekt.services.bridge_executor import BridgeExecutor

    return BridgeExecutor()


# ============================================================================
# Zoom Handlers
# ============================================================================

# JavaScript to get zoom level via extension bridge (same pattern as control-server.py)
_GET_ZOOM_JS = """
(function() {
    return new Promise((resolve) => {
        const rid = 'zoom_' + Date.now();
        function handler(e) {
            if (e.data && e.data.type === 'INSPEKT_ZOOM_LEVEL_RESPONSE' && e.data.requestId === rid) {
                window.removeEventListener('message', handler);
                resolve(e.data.response);
            }
        }
        window.addEventListener('message', handler);
        window.postMessage({ type: 'INSPEKT_GET_ZOOM_LEVEL', source: 'inspekt-page', requestId: rid }, '*');
        setTimeout(() => { window.removeEventListener('message', handler); resolve({ ok: false, error: 'timeout' }); }, 3000);
    });
})()
"""


def _set_zoom_js(zoom_factor: float) -> str:
    """Generate JavaScript to set zoom level via extension bridge."""
    return f"""
(function() {{
    return new Promise((resolve) => {{
        const rid = 'zoom_' + Date.now();
        function handler(e) {{
            if (e.data && e.data.type === 'INSPEKT_ZOOM_SET_RESPONSE' && e.data.requestId === rid) {{
                window.removeEventListener('message', handler);
                resolve(e.data.response);
            }}
        }}
        window.addEventListener('message', handler);
        window.postMessage({{ type: 'INSPEKT_SET_ZOOM_LEVEL', source: 'inspekt-page', requestId: rid, zoomFactor: {zoom_factor} }}, '*');
        setTimeout(() => {{ window.removeEventListener('message', handler); resolve({{ ok: false, error: 'timeout' }}); }}, 3000);
    }});
}})()
"""


def _make_zoom_response(
    success: bool,
    zoom: float = 1.0,
    previous_zoom: float | None = None,
    message: str | None = None,
    error: str | None = None,
) -> ZoomResponse:
    """Build a ZoomResponse with derived fields."""
    percentage = round(zoom * 100)
    return ZoomResponse(
        success=success,
        zoom=zoom,
        percentage=percentage,
        wcag_note=get_wcag_note(zoom) if success else None,
        previous_zoom=previous_zoom,
        message=message or error,
    )


async def get_zoom(params: EmptyParams) -> ZoomResponse:
    """Get the current browser zoom level."""
    if _is_vm():
        result = await asyncio.to_thread(_vm_request, "GET", "/zoom")
        if result.get("ok"):
            zoom = result.get("zoom", 1.0)
            return _make_zoom_response(True, zoom=zoom, message=f"Zoom: {round(zoom * 100)}%")
        return _make_zoom_response(False, error=result.get("error", "Failed to get zoom"))

    # Regular browser: use extension bridge
    executor = _get_executor()
    try:
        result = await asyncio.to_thread(executor.execute, _GET_ZOOM_JS, 5.0)
        if result.get("ok"):
            data = result.get("result", {})
            if isinstance(data, dict) and data.get("ok"):
                zoom = data.get("zoomFactor", 1.0)
                return _make_zoom_response(True, zoom=zoom, message=f"Zoom: {round(zoom * 100)}%")
            return _make_zoom_response(False, error=data.get("error", "Extension did not respond"))
        return _make_zoom_response(False, error=result.get("error", "Bridge execution failed"))
    except Exception as e:
        return _make_zoom_response(False, error=str(e))


async def set_zoom(params: ZoomSetParams) -> ZoomResponse:
    """Set the browser zoom level."""
    # First, get current zoom to determine previous and for step calculations
    current_response = await get_zoom(EmptyParams())
    current_zoom = current_response.zoom if current_response.success else 1.0

    # Determine target zoom factor
    if params.action == "reset":
        target_factor = 1.0
    elif params.action == "in":
        target_factor = next_zoom_step(current_zoom)
    elif params.action == "out":
        target_factor = previous_zoom_step(current_zoom)
    elif params.level is not None:
        target_factor = params.level / 100.0
        if target_factor < 0.25 or target_factor > 5.0:
            return _make_zoom_response(
                False, zoom=current_zoom, error="Zoom level must be between 25% and 500%"
            )
    else:
        return _make_zoom_response(
            False, zoom=current_zoom, error="Provide a zoom level or action (in/out/reset)"
        )

    # Apply zoom
    if _is_vm():
        result = await asyncio.to_thread(_vm_request, "POST", "/zoom", {"level": target_factor})
        if result.get("ok"):
            return _make_zoom_response(
                True,
                zoom=target_factor,
                previous_zoom=current_zoom,
                message=f"Zoom: {round(current_zoom * 100)}% → {round(target_factor * 100)}%",
            )
        return _make_zoom_response(
            False, zoom=current_zoom, error=result.get("error", "Failed to set zoom")
        )

    # Regular browser: use extension bridge
    executor = _get_executor()
    try:
        js = _set_zoom_js(target_factor)
        result = await asyncio.to_thread(executor.execute, js, 5.0)
        if result.get("ok"):
            data = result.get("result", {})
            if isinstance(data, dict) and data.get("ok"):
                return _make_zoom_response(
                    True,
                    zoom=target_factor,
                    previous_zoom=current_zoom,
                    message=f"Zoom: {round(current_zoom * 100)}% → {round(target_factor * 100)}%",
                )
            return _make_zoom_response(
                False, zoom=current_zoom, error=data.get("error", "Extension did not respond")
            )
        return _make_zoom_response(
            False, zoom=current_zoom, error=result.get("error", "Bridge execution failed")
        )
    except Exception as e:
        return _make_zoom_response(False, zoom=current_zoom, error=str(e))


# ============================================================================
# Viewport Handlers
# ============================================================================

# JavaScript to get current viewport dimensions
_GET_VIEWPORT_JS = """
(function() {
    return { width: window.innerWidth, height: window.innerHeight };
})()
"""


def _make_viewport_response(
    success: bool,
    width: int = 0,
    height: int = 0,
    previous_width: int | None = None,
    previous_height: int | None = None,
    message: str | None = None,
    error: str | None = None,
) -> ViewportResponse:
    """Build a ViewportResponse."""
    return ViewportResponse(
        success=success,
        width=width,
        height=height,
        previous_width=previous_width,
        previous_height=previous_height,
        message=message or error,
    )


async def get_viewport(params: EmptyParams) -> ViewportResponse:
    """Get the current browser viewport dimensions."""
    if _is_vm():
        result = await asyncio.to_thread(_vm_request, "GET", "/resolution")
        if result.get("ok"):
            w, h = result.get("width", 0), result.get("height", 0)
            return _make_viewport_response(True, width=w, height=h, message=f"Viewport: {w} × {h}")
        return _make_viewport_response(False, error=result.get("error", "Failed to get resolution"))

    # Regular browser: query via JS
    executor = _get_executor()
    try:
        result = await asyncio.to_thread(executor.execute, _GET_VIEWPORT_JS, 5.0)
        if result.get("ok"):
            data = result.get("result", {})
            w, h = data.get("width", 0), data.get("height", 0)
            return _make_viewport_response(True, width=w, height=h, message=f"Viewport: {w} × {h}")
        return _make_viewport_response(False, error=result.get("error", "Bridge execution failed"))
    except Exception as e:
        return _make_viewport_response(False, error=str(e))


async def set_viewport(params: ViewportSetParams) -> ViewportResponse:
    """Set the browser viewport dimensions."""
    # Get current dimensions first
    current = await get_viewport(EmptyParams())
    prev_w = current.width if current.success else None
    prev_h = current.height if current.success else None

    target_width = params.width
    target_height = params.height

    if _is_vm():
        # auto_height: keep current display height (already fetched via get_viewport above)
        h = target_height or (prev_h if prev_h else 900)

        result = await asyncio.to_thread(
            _vm_request, "POST", "/resize", {"width": target_width, "height": h}
        )
        if result.get("ok"):
            return _make_viewport_response(
                True,
                width=target_width,
                height=h,
                previous_width=prev_w,
                previous_height=prev_h,
                message=f"Viewport: {prev_w}×{prev_h} → {target_width}×{h}",
            )
        return _make_viewport_response(
            False,
            width=prev_w or 0,
            height=prev_h or 0,
            error=result.get("error", "Failed to resize"),
        )

    # Regular browser: AppleScript on macOS
    import platform

    if platform.system() != "Darwin":
        return _make_viewport_response(
            False,
            width=prev_w or 0,
            height=prev_h or 0,
            error="Viewport resize requires macOS (uses AppleScript). On other platforms, use the Inspekt VM.",
        )

    from inspekt.services.applescript_utils import resize_browser_window

    # auto_height on macOS: keep current height
    h = target_height or (prev_h if prev_h else 900)
    ok = await asyncio.to_thread(resize_browser_window, target_width, h)

    if ok:
        # Re-read actual viewport after resize (AppleScript chrome offsets mean it may differ slightly)
        await asyncio.sleep(0.3)
        actual = await get_viewport(EmptyParams())
        actual_w = actual.width if actual.success else target_width
        actual_h = actual.height if actual.success else h
        return _make_viewport_response(
            True,
            width=actual_w,
            height=actual_h,
            previous_width=prev_w,
            previous_height=prev_h,
            message=f"Viewport: {prev_w}×{prev_h} → {actual_w}×{actual_h}",
        )
    return _make_viewport_response(
        False,
        width=prev_w or 0,
        height=prev_h or 0,
        error="AppleScript window resize failed. Is the browser running and in focus?",
    )
