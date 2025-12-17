"""
Inspection command schemas.

Input/output models for inspection commands:
- get_page_info
- take_screenshot
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class GetPageInfoResponse(BaseModel):
    """Response from get_page_info command (lightweight page info)."""

    success: bool = Field(..., description="Whether operation succeeded")
    url: str = Field(..., description="Current page URL")
    title: str = Field(..., description="Page title")
    viewport_width: int = Field(..., description="Viewport width in pixels")
    viewport_height: int = Field(..., description="Viewport height in pixels")
    scroll_x: int = Field(..., description="Horizontal scroll position")
    scroll_y: int = Field(..., description="Vertical scroll position")


class TakeScreenshotParams(BaseModel):
    """Parameters for take_screenshot command."""

    target: Optional[Literal["viewport", "page", "element"]] = Field(
        default="viewport",
        description="Screenshot target: viewport (visible area), page (full page), or element",
    )
    selector: Optional[str] = Field(
        default=None,
        description="CSS selector for element screenshot (required if target='element')",
    )
    format: Optional[Literal["png", "jpeg"]] = Field(
        default="png", description="Image format"
    )
    quality: Optional[int] = Field(
        default=90, description="JPEG quality (1-100, ignored for PNG)"
    )


class TakeScreenshotResponse(BaseModel):
    """Response from take_screenshot command."""

    success: bool = Field(..., description="Whether screenshot succeeded")
    data: Optional[str] = Field(default=None, description="Base64-encoded image data")
    format: str = Field(..., description="Image format (png or jpeg)")
    width: int = Field(..., description="Image width in pixels")
    height: int = Field(..., description="Image height in pixels")
    message: Optional[str] = Field(default=None, description="Success or error message")
