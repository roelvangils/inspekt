"""Display API endpoints — zoom and viewport control."""


from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================

class ZoomSetRequest(BaseModel):
    """Request body for POST /zoom."""
    level: int | None = Field(default=None, description="Zoom percentage (25–500)")
    action: str | None = Field(default=None, description="Action: in, out, reset")


class ViewportSetRequest(BaseModel):
    """Request body for POST /viewport."""
    width: int = Field(..., description="Viewport width in pixels", ge=320, le=3840)
    height: int | None = Field(default=None, description="Viewport height in pixels", ge=240, le=2160)
    auto_height: bool = Field(default=False, description="Auto-fill display height (VM only)")


# ============================================================================
# Zoom Endpoints
# ============================================================================

@router.get("/zoom")
async def get_zoom():
    """Get the current browser zoom level."""
    from inspekt.core.commands.base import EmptyParams
    from inspekt.core.handlers.display import get_zoom as _get_zoom

    result = await _get_zoom(EmptyParams())
    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)
    return {
        "ok": True,
        "zoom": result.zoom,
        "percentage": result.percentage,
        "wcag_note": result.wcag_note,
    }


@router.post("/zoom")
async def set_zoom(request: ZoomSetRequest):
    """Set the browser zoom level. Accepts a percentage or action (in/out/reset)."""
    from inspekt.core.handlers.display import set_zoom as _set_zoom
    from inspekt.core.schemas.display import ZoomSetParams

    params = ZoomSetParams(level=request.level, action=request.action)
    result = await _set_zoom(params)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)
    return {
        "ok": True,
        "zoom": result.zoom,
        "percentage": result.percentage,
        "previous_zoom": result.previous_zoom,
        "wcag_note": result.wcag_note,
    }


# ============================================================================
# Viewport Endpoints
# ============================================================================

@router.get("/viewport")
async def get_viewport():
    """Get the current browser viewport dimensions."""
    from inspekt.core.commands.base import EmptyParams
    from inspekt.core.handlers.display import get_viewport as _get_viewport

    result = await _get_viewport(EmptyParams())
    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)
    return {
        "ok": True,
        "width": result.width,
        "height": result.height,
    }


@router.post("/viewport")
async def set_viewport(request: ViewportSetRequest):
    """Set the browser viewport dimensions."""
    from inspekt.core.handlers.display import set_viewport as _set_viewport
    from inspekt.core.schemas.display import ViewportSetParams

    params = ViewportSetParams(width=request.width, height=request.height, auto_height=request.auto_height)
    result = await _set_viewport(params)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)
    return {
        "ok": True,
        "width": result.width,
        "height": result.height,
        "previous_width": result.previous_width,
        "previous_height": result.previous_height,
    }
