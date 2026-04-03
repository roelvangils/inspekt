"""
Display command definitions.

Commands for browser display control:
- zoom: Get/set browser zoom level (in, out, reset, arbitrary %)
- viewport: Get/set browser viewport dimensions
"""

from inspekt.core.commands.base import (
    Category,
    CommandDefinition,
    EmptyParams,
    SubcommandDefinition,
)
from inspekt.core.schemas.display import (
    ViewportResponse,
    ViewportSetParams,
    ZoomResponse,
    ZoomSetParams,
)

# === Zoom (get) ===

get_zoom = CommandDefinition(
    id="get_zoom",
    name="Get Zoom Level",
    category=Category.INSPECTION,
    description="""Get the current browser zoom level.

Returns the zoom factor (e.g., 1.5) and percentage (e.g., 150%).
Also provides WCAG guidance when the zoom level corresponds to
a WCAG success criterion threshold.""",
    params_schema=EmptyParams,
    response_schema=ZoomResponse,
    handler="inspekt.core.handlers.display.get_zoom",
    cli_name="zoom",
    cli_hidden=True,  # The CLI group handles this
    api_path="/display/zoom",
    api_method="GET",
    examples=["inspekt zoom"],
)

# === Zoom (set) ===

set_zoom = CommandDefinition(
    id="set_zoom",
    name="Set Zoom Level",
    category=Category.INSPECTION,
    description="""Set the browser zoom level.

Accepts a percentage (25–500) or an action:
- **in**: Step to the next predefined zoom level
- **out**: Step to the previous predefined zoom level
- **reset**: Return to 100%

Predefined zoom steps: 25%, 33%, 50%, 67%, 75%, 80%, 90%, 100%,
110%, 125%, 150%, 175%, 200%, 250%, 300%, 400%, 500%.

WCAG accessibility testing shortcuts:
- 200% tests WCAG 1.4.4 (Resize Text)
- 400% tests WCAG 1.4.10 (Reflow)""",
    params_schema=ZoomSetParams,
    response_schema=ZoomResponse,
    handler="inspekt.core.handlers.display.set_zoom",
    cli_name="zoom set",
    cli_hidden=True,  # The CLI group handles this
    api_path="/display/zoom",
    api_method="POST",
    examples=[
        "inspekt zoom 150",
        "inspekt zoom in",
        "inspekt zoom out",
        "inspekt zoom reset",
        "inspekt zoom --wcag",
    ],
)

# === Zoom Group (for CLI/dashboard) ===

zoom_group = CommandDefinition(
    id="zoom_group",
    name="Zoom",
    category=Category.INSPECTION,
    description="""Get or set browser zoom level.

Without arguments, shows the current zoom level.
With a number, sets the zoom to that percentage.

Subcommands: in, out, reset.""",
    params_schema=EmptyParams,
    response_schema=ZoomResponse,
    handler=None,
    cli_name="zoom",
    api_path=None,
    mcp_enabled_default=False,
    is_group=True,
    subcommands=[
        SubcommandDefinition(
            name="in",
            description="Zoom in to the next predefined level",
            params_schema=EmptyParams,
            examples=["inspekt zoom in"],
        ),
        SubcommandDefinition(
            name="out",
            description="Zoom out to the previous predefined level",
            params_schema=EmptyParams,
            examples=["inspekt zoom out"],
        ),
        SubcommandDefinition(
            name="reset",
            description="Reset zoom to 100%",
            params_schema=EmptyParams,
            examples=["inspekt zoom reset"],
        ),
    ],
    examples=[
        "inspekt zoom",
        "inspekt zoom 150",
        "inspekt zoom in",
        "inspekt zoom out",
        "inspekt zoom reset",
        "inspekt zoom --wcag",
    ],
)

# === Viewport (get) ===

get_viewport = CommandDefinition(
    id="get_viewport",
    name="Get Viewport Size",
    category=Category.INSPECTION,
    description="""Get the current browser viewport dimensions.

Returns width and height in CSS pixels.
In the VM, returns the X display resolution.
On macOS, returns window.innerWidth/innerHeight.""",
    params_schema=EmptyParams,
    response_schema=ViewportResponse,
    handler="inspekt.core.handlers.display.get_viewport",
    cli_name="viewport",
    cli_hidden=True,  # The CLI command handles this
    api_path="/display/viewport",
    api_method="GET",
    examples=["inspekt viewport"],
)

# === Viewport (set) ===

set_viewport = CommandDefinition(
    id="set_viewport",
    name="Set Viewport Size",
    category=Category.INSPECTION,
    description="""Set the browser viewport dimensions.

Resizes the browser window to achieve the specified viewport width
(and optionally height) in CSS pixels.

On macOS: uses AppleScript to resize the browser window.
In the VM: changes the X display resolution.

Named presets: mobile (375px), tablet (768px),
desktop (1280px), wide (1920px).

Use "auto" as height to fill the available display (VM only).
Use "wider" / "narrower" subcommands for relative adjustments.""",
    params_schema=ViewportSetParams,
    response_schema=ViewportResponse,
    handler="inspekt.core.handlers.display.set_viewport",
    cli_name="viewport set",
    cli_hidden=True,  # The CLI group handles this
    api_path="/display/viewport",
    api_method="POST",
    examples=[
        "inspekt viewport 1024",
        "inspekt viewport 1024 768",
        "inspekt viewport 1024 auto",
        "inspekt viewport mobile",
        "inspekt viewport tablet",
        "inspekt viewport wider",
        "inspekt viewport narrower 50",
    ],
)

# === Viewport Group (for CLI/dashboard) ===

viewport_group = CommandDefinition(
    id="viewport_group",
    name="Viewport",
    category=Category.INSPECTION,
    description="""Get or set browser viewport dimensions.

Without arguments, shows the current viewport size.
With a number, sets the width. With two numbers, sets width and height.

Subcommands: mobile, tablet, desktop, wide, wider, narrower.""",
    params_schema=EmptyParams,
    response_schema=ViewportResponse,
    handler=None,
    cli_name="viewport",
    api_path=None,
    mcp_enabled_default=False,
    is_group=True,
    subcommands=[
        SubcommandDefinition(
            name="mobile",
            description="Set viewport to 375px (iPhone SE)",
            params_schema=EmptyParams,
            examples=["inspekt viewport mobile"],
        ),
        SubcommandDefinition(
            name="tablet",
            description="Set viewport to 768px (iPad portrait)",
            params_schema=EmptyParams,
            examples=["inspekt viewport tablet"],
        ),
        SubcommandDefinition(
            name="desktop",
            description="Set viewport to 1280px (standard desktop)",
            params_schema=EmptyParams,
            examples=["inspekt viewport desktop"],
        ),
        SubcommandDefinition(
            name="wide",
            description="Set viewport to 1920px (Full HD)",
            params_schema=EmptyParams,
            examples=["inspekt viewport wide"],
        ),
        SubcommandDefinition(
            name="wider",
            description="Grow viewport width by N pixels (default: 100)",
            params_schema=EmptyParams,
            examples=["inspekt viewport wider", "inspekt viewport wider 50"],
        ),
        SubcommandDefinition(
            name="narrower",
            description="Shrink viewport width by N pixels (default: 100)",
            params_schema=EmptyParams,
            examples=["inspekt viewport narrower", "inspekt viewport narrower 50"],
        ),
        SubcommandDefinition(
            name="fit",
            description="Fit viewport to VNC canvas size (VM only)",
            params_schema=EmptyParams,
            examples=["inspekt viewport fit"],
        ),
    ],
    examples=[
        "inspekt viewport",
        "inspekt viewport 1024",
        "inspekt viewport 1024 768",
        "inspekt viewport 1024 auto",
        "inspekt viewport mobile",
        "inspekt viewport wider",
        "inspekt viewport fit",
    ],
)


# All display commands
DISPLAY_COMMANDS = [
    get_zoom,
    set_zoom,
    zoom_group,
    get_viewport,
    set_viewport,
    viewport_group,
]
