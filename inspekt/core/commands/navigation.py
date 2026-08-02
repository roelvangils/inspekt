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
    SitemapParams,
    SitemapResponse,
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
    # URL scheme support
    url_scheme="open",
    url_scheme_params={
        "url": "The URL to navigate to",
        "wait": "Wait for page load (true/false)",
    },
    url_scheme_examples=[
        "inspekt://open?url=https://example.com",
        "inspekt://open?url=https://example.com&wait=true",
    ],
    url_scheme_output_mode="notification",
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
    # URL scheme support
    url_scheme="back",
    url_scheme_examples=["inspekt://back"],
    url_scheme_output_mode="notification",
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
    # URL scheme support
    url_scheme="forward",
    url_scheme_examples=["inspekt://forward"],
    url_scheme_output_mode="notification",
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
    # URL scheme support
    url_scheme="reload",
    url_scheme_examples=["inspekt://reload"],
    url_scheme_output_mode="notification",
    examples=[
        "inspekt reload",
        "inspekt reload --hard",
    ],
)

# === Scroll to Top ===

scroll_to_top = CommandDefinition(
    id="scroll_to_top",
    name="Scroll to Top",
    category=Category.NAVIGATION,
    description="Scroll to the top of the page. Equivalent to pressing Home key.",
    params_schema=EmptyParams,
    response_schema=NavigateResponse,
    handler="inspekt.core.handlers.navigation.scroll_to_top",
    cli_name="top",
    cli_aliases=["home"],
    api_path="/navigation/top",
    api_method="POST",
    # URL scheme support
    url_scheme="top",
    url_scheme_examples=["inspekt://top"],
    url_scheme_output_mode="notification",
    examples=["inspekt top"],
)

# === Scroll to Bottom ===

scroll_to_bottom = CommandDefinition(
    id="scroll_to_bottom",
    name="Scroll to Bottom",
    category=Category.NAVIGATION,
    description="Scroll to the bottom of the page. Equivalent to pressing End key.",
    params_schema=EmptyParams,
    response_schema=NavigateResponse,
    handler="inspekt.core.handlers.navigation.scroll_to_bottom",
    cli_name="bottom",
    cli_aliases=["end"],
    api_path="/navigation/bottom",
    api_method="POST",
    # URL scheme support
    url_scheme="bottom",
    url_scheme_examples=["inspekt://bottom"],
    url_scheme_output_mode="notification",
    examples=["inspekt bottom"],
)

# === Page Up ===

page_up = CommandDefinition(
    id="page_up",
    name="Page Up",
    category=Category.NAVIGATION,
    description="Scroll up by one viewport height. Equivalent to pressing Page Up key.",
    params_schema=EmptyParams,
    response_schema=NavigateResponse,
    handler="inspekt.core.handlers.navigation.page_up",
    cli_name="pageup",
    cli_aliases=["pgup"],
    api_path="/navigation/pageup",
    api_method="POST",
    # URL scheme support
    url_scheme="pageup",
    url_scheme_examples=["inspekt://pageup"],
    url_scheme_output_mode="notification",
    examples=["inspekt pageup"],
)

# === Page Down ===

page_down = CommandDefinition(
    id="page_down",
    name="Page Down",
    category=Category.NAVIGATION,
    description="Scroll down by one viewport height. Equivalent to pressing Page Down key.",
    params_schema=EmptyParams,
    response_schema=NavigateResponse,
    handler="inspekt.core.handlers.navigation.page_down",
    cli_name="pagedown",
    cli_aliases=["pgdown"],
    api_path="/navigation/pagedown",
    api_method="POST",
    # URL scheme support
    url_scheme="pagedown",
    url_scheme_examples=["inspekt://pagedown"],
    url_scheme_output_mode="notification",
    examples=["inspekt pagedown"],
)

# ── Sitemap ──────────────────────────────────────────────────────────

get_sitemap = CommandDefinition(
    id="get_sitemap",
    name="Get Sitemap",
    category=Category.NAVIGATION,
    description="""Fetch a site's sitemap and return all URLs with page titles.

Auto-discovers the sitemap via robots.txt or /sitemap.xml. Handles sitemap
index files by flattening all child sitemaps. Enriches entries with real
page titles (fetched from each page's HTML). Results are cached for 1 hour.

Use the `lang` parameter to filter multilingual sites (e.g., lang="nl" for
Dutch pages only). Use `refresh=true` to bypass the cache.

Returns structured data with each URL's title, path, and last modified date.
Use the index numbers with navigate_to_url to visit specific pages.""",
    params_schema=SitemapParams,
    response_schema=SitemapResponse,
    handler="inspekt.core.handlers.navigation.get_sitemap",
    cli_name="sitemap",
    api_path="/navigation/sitemap",
    api_method="POST",
    examples=[
        "inspekt sitemap",
        "inspekt sitemap --lang nl",
        "inspekt sitemap --json",
    ],
)

# All navigation commands
NAVIGATION_COMMANDS = [
    navigate_to_url,
    go_back,
    go_forward,
    reload_page,
    scroll_to_top,
    scroll_to_bottom,
    page_up,
    page_down,
    get_sitemap,
]
