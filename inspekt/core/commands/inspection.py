"""
Inspection command definitions.

Commands for inspecting web page state:
- get_page_info: Get lightweight page metadata
- take_screenshot: Capture page screenshots
"""

from inspekt.core.commands.base import Category, CommandDefinition, EmptyParams
from inspekt.core.schemas.inspection import (
    GetPageInfoResponse,
    TakeScreenshotParams,
    TakeScreenshotResponse,
)

# === Get Page Info ===

get_page_info = CommandDefinition(
    id="get_page_info",
    name="Get Page Info",
    category=Category.INSPECTION,
    description="""Get lightweight current page information.

Returns essential page state:
- URL and title
- Viewport dimensions (width/height)
- Scroll position (x/y)

This is a fast, low-overhead command ideal for:
- Status checks before other operations
- Verifying navigation completed
- Getting context for AI analysis""",
    params_schema=EmptyParams,
    response_schema=GetPageInfoResponse,
    handler="inspekt.core.handlers.inspection.get_page_info",
    cli_name="info",
    cli_group="page",  # inspekt page info
    api_path="/inspection/info",
    api_method="GET",
    examples=["inspekt page info"],
)

# === Take Screenshot ===

take_screenshot = CommandDefinition(
    id="take_screenshot",
    name="Take Screenshot",
    category=Category.INSPECTION,
    description="""Capture a screenshot of the browser viewport, full page, or element.

Screenshot targets:
- viewport: Visible browser area (default, fastest)
- page: Full scrollable page (stitched screenshots)
- element: Specific element by CSS selector

Output formats:
- png: Lossless, larger files (default)
- jpeg: Lossy compression, smaller files

Returns base64-encoded image data that can be:
- Saved to file
- Embedded in HTML/markdown
- Analyzed by vision models""",
    params_schema=TakeScreenshotParams,
    response_schema=TakeScreenshotResponse,
    handler="inspekt.core.handlers.inspection.take_screenshot",
    cli_name="screenshot",
    api_path="/inspection/screenshot",
    api_method="POST",
    examples=[
        "inspekt screenshot",
        "inspekt screenshot --target page",
        "inspekt screenshot --target element --selector '.main-content'",
        "inspekt screenshot --format jpeg --quality 80",
    ],
)

# All inspection commands
INSPECTION_COMMANDS = [
    get_page_info,
    take_screenshot,
]
