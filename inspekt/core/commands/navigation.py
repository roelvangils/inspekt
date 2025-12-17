"""
Navigation command definitions.

Commands for browser navigation:
- navigate_to_url: Navigate to a URL
- go_back: Go back in browser history
- go_forward: Go forward in browser history
- reload_page: Reload the current page
"""

from inspekt.core.commands.base import Category, CommandDefinition, EmptyParams
from inspekt.core.schemas.navigation import (
    NavigateParams,
    NavigateResponse,
    ReloadParams,
)

# === Navigate to URL ===

navigate_to_url = CommandDefinition(
    id="navigate_to_url",
    name="Navigate to URL",
    category=Category.NAVIGATION,
    description="""Navigate to a URL in the browser with full JavaScript execution.

Use this instead of HTTP fetch when you need:
- Dynamic content rendered by JavaScript
- Authentication state from browser cookies
- Interaction with the page after loading

Supports wait conditions for reliable page loading.""",
    params_schema=NavigateParams,
    response_schema=NavigateResponse,
    handler="inspekt.core.handlers.navigation.navigate_to_url",
    cli_name="open",
    cli_aliases=["nav", "goto"],
    api_path="/navigation/open",
    api_method="POST",
    examples=[
        "inspekt open https://example.com",
        "inspekt open https://example.com --wait load",
    ],
)

# === Go Back ===

go_back = CommandDefinition(
    id="go_back",
    name="Go Back",
    category=Category.NAVIGATION,
    description="Navigate back to the previous page in browser history.",
    params_schema=EmptyParams,
    response_schema=NavigateResponse,
    handler="inspekt.core.handlers.navigation.go_back",
    cli_name="back",
    cli_aliases=["previous"],
    api_path="/navigation/back",
    api_method="POST",
    examples=["inspekt back"],
)

# === Go Forward ===

go_forward = CommandDefinition(
    id="go_forward",
    name="Go Forward",
    category=Category.NAVIGATION,
    description="Navigate forward to the next page in browser history.",
    params_schema=EmptyParams,
    response_schema=NavigateResponse,
    handler="inspekt.core.handlers.navigation.go_forward",
    cli_name="forward",
    api_path="/navigation/forward",
    api_method="POST",
    examples=["inspekt forward"],
)

# === Reload Page ===

reload_page = CommandDefinition(
    id="reload_page",
    name="Reload Page",
    category=Category.NAVIGATION,
    description="""Reload the current page in the browser.

Use --hard to bypass cache and do a full reload.""",
    params_schema=ReloadParams,
    response_schema=NavigateResponse,
    handler="inspekt.core.handlers.navigation.reload_page",
    cli_name="reload",
    cli_aliases=["refresh"],
    api_path="/navigation/reload",
    api_method="POST",
    examples=[
        "inspekt reload",
        "inspekt reload --hard",
    ],
)

# All navigation commands
NAVIGATION_COMMANDS = [
    navigate_to_url,
    go_back,
    go_forward,
    reload_page,
]
