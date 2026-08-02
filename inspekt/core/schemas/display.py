"""
Display command schemas.

Input/output models for display commands:
- get_zoom / set_zoom: Browser zoom level
- get_viewport / set_viewport: Browser viewport dimensions
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

# ============================================================================
# Zoom Schemas
# ============================================================================

# Predefined zoom steps (matching control-panel.html ZOOM_STEPS)
ZOOM_STEPS = [0.25, 0.33, 0.5, 0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0, 5.0]

# WCAG guidance for zoom levels
ZOOM_WCAG_NOTES = {
    0.25: "Minimum zoom level",
    0.5: "Good for seeing the full layout at a glance",
    1.0: "Default zoom level",
    1.5: "Common accessibility zoom level",
    2.0: "WCAG 1.4.4 requires content to be usable at 200% zoom",
    3.0: "Tests extreme zoom for low-vision users",
    4.0: "WCAG 1.4.10 requires content reflow at 400% zoom",
    5.0: "Maximum zoom level",
}


def get_wcag_note(zoom_factor: float) -> str | None:
    """Get WCAG guidance note for a zoom level, if any."""
    return ZOOM_WCAG_NOTES.get(zoom_factor)


def next_zoom_step(current: float) -> float:
    """Get the next zoom step above current level."""
    for step in ZOOM_STEPS:
        if step > current + 0.001:  # Small epsilon for float comparison
            return step
    return ZOOM_STEPS[-1]


def previous_zoom_step(current: float) -> float:
    """Get the next zoom step below current level."""
    for step in reversed(ZOOM_STEPS):
        if step < current - 0.001:
            return step
    return ZOOM_STEPS[0]


class ZoomSetParams(BaseModel):
    """Parameters for set_zoom command."""

    level: int | None = Field(
        default=None,
        description="Zoom level as percentage (e.g., 150 for 150%). Range: 25–500.",
    )
    action: Literal["in", "out", "reset"] | None = Field(
        default=None,
        description="Zoom action: 'in' (next step), 'out' (previous step), 'reset' (100%)",
    )


class ZoomResponse(BaseModel):
    """Response from zoom commands (get and set)."""

    success: bool = Field(
        ...,
        description="Whether the operation succeeded",
    )
    zoom: float = Field(
        default=1.0,
        description="Current zoom factor (e.g., 1.5 for 150%)",
    )
    percentage: int = Field(
        default=100,
        description="Current zoom as percentage (e.g., 150)",
    )
    wcag_note: str | None = Field(
        default=None,
        description="WCAG guidance for the current zoom level, if applicable",
    )
    previous_zoom: float | None = Field(
        default=None,
        description="Previous zoom factor before change (only for set operations)",
    )
    message: str | None = Field(
        default=None,
        description="Success or error message",
    )


# ============================================================================
# Viewport Schemas
# ============================================================================

# Named viewport presets
VIEWPORT_PRESETS = {
    "mobile": (375, None, "iPhone SE / small mobile"),
    "tablet": (768, None, "iPad portrait / tablet"),
    "desktop": (1280, None, "Standard desktop"),
    "wide": (1920, None, "Full HD / wide desktop"),
}


class ViewportSetParams(BaseModel):
    """Parameters for set_viewport command."""

    width: int = Field(
        ...,
        description="Viewport width in pixels (min: 320, max: 3840)",
        ge=320,
        le=3840,
    )
    height: int | None = Field(
        default=None,
        description="Viewport height in pixels (min: 240, max: 2160). If omitted, only width changes.",
        ge=240,
        le=2160,
    )
    auto_height: bool = Field(
        default=False,
        description="Automatically set height to fill available display (VM only). Overrides height.",
    )


class ViewportResponse(BaseModel):
    """Response from viewport commands (get and set)."""

    success: bool = Field(
        ...,
        description="Whether the operation succeeded",
    )
    width: int = Field(
        default=0,
        description="Current viewport width in pixels",
    )
    height: int = Field(
        default=0,
        description="Current viewport height in pixels",
    )
    previous_width: int | None = Field(
        default=None,
        description="Previous viewport width (only for set operations)",
    )
    previous_height: int | None = Field(
        default=None,
        description="Previous viewport height (only for set operations)",
    )
    message: str | None = Field(
        default=None,
        description="Success or error message",
    )
