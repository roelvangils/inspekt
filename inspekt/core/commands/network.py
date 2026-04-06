"""
Network inspection command definitions.

Commands:
- network: CLI group for network inspection (with subcommands)
- get_network_requests: MCP tool for network requests via Performance API
- get_har: MCP tool for HAR data from DevTools
"""

from inspekt.core.commands.base import (
    Category,
    CommandDefinition,
    EmptyParams,
    EmptyResponse,
    SubcommandDefinition,
)
from inspekt.core.schemas.network import (
    GetHARParams,
    GetHARResponse,
    GetNetworkRequestsParams,
    GetNetworkRequestsResponse,
)


network = CommandDefinition(
    id="network",
    name="Network",
    category=Category.NETWORK,
    description="""Show network requests from the current page.

Displays all network requests made by the page using the Performance API.
Includes timing breakdown, transfer sizes, and cache status.

**Options:**
- `--json`: Output as JSON
- `--sort`: Sort by field (start, time, size, name, type)
- `--domain`: Show domain column
- `--external`: Show only external requests
- `--limit`: Limit number of results

**Subcommands:**
- `har`: Get full HAR data (requires DevTools open)
- `errors`: Show only failed requests
- `slow`: Show slowest requests
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="network",
    api_path=None,
    mcp_enabled_default=False,
    is_group=True,
    subcommands=[
        SubcommandDefinition(
            name="har",
            description="Get full HAR data (requires DevTools open)",
            params_schema=EmptyParams,
            examples=["inspekt network har", "inspekt network har --json"],
        ),
        SubcommandDefinition(
            name="errors",
            description="Show only failed requests (4xx/5xx)",
            params_schema=EmptyParams,
            examples=["inspekt network errors"],
        ),
        SubcommandDefinition(
            name="slow",
            description="Show slowest requests",
            params_schema=EmptyParams,
            examples=["inspekt network slow", "inspekt network slow -n 10"],
        ),
        # Resource type filters
        SubcommandDefinition(
            name="script",
            description="Show only JavaScript requests",
            params_schema=EmptyParams,
            examples=["inspekt network script"],
        ),
        SubcommandDefinition(
            name="stylesheet",
            description="Show only CSS stylesheet requests",
            params_schema=EmptyParams,
            examples=["inspekt network stylesheet"],
        ),
        SubcommandDefinition(
            name="css",
            description="Alias for stylesheet",
            params_schema=EmptyParams,
            examples=["inspekt network css"],
        ),
        SubcommandDefinition(
            name="fetch",
            description="Show only fetch/XHR requests",
            params_schema=EmptyParams,
            examples=["inspekt network fetch"],
        ),
        SubcommandDefinition(
            name="xhr",
            description="Alias for fetch (XMLHttpRequest)",
            params_schema=EmptyParams,
            examples=["inspekt network xhr"],
        ),
        SubcommandDefinition(
            name="image",
            description="Show only image requests",
            params_schema=EmptyParams,
            examples=["inspekt network image"],
        ),
        SubcommandDefinition(
            name="font",
            description="Show only font requests",
            params_schema=EmptyParams,
            examples=["inspekt network font"],
        ),
        SubcommandDefinition(
            name="document",
            description="Show only document requests",
            params_schema=EmptyParams,
            examples=["inspekt network document"],
        ),
        SubcommandDefinition(
            name="svg",
            description="Show only SVG requests",
            params_schema=EmptyParams,
            examples=["inspekt network svg"],
        ),
        SubcommandDefinition(
            name="video",
            description="Show only video requests",
            params_schema=EmptyParams,
            examples=["inspekt network video"],
        ),
        SubcommandDefinition(
            name="audio",
            description="Show only audio requests",
            params_schema=EmptyParams,
            examples=["inspekt network audio"],
        ),
    ],
    examples=[
        "inspekt network",
        "inspekt network --json",
        "inspekt network --external",
        "inspekt network --sort size",
        "inspekt network har",
    ],
)


# === Get Network Requests (MCP Tool) ===

get_network_requests = CommandDefinition(
    id="get_network_requests",
    name="Get Network Requests",
    category=Category.NETWORK,
    description="""Get network requests from the current page using Performance API.

Returns detailed information about all resources loaded by the page including
scripts, stylesheets, images, fonts, fetch/XHR requests, etc.

Includes timing breakdown (DNS, TCP, SSL, TTFB, download), transfer sizes,
and cache status. Can filter by resource type and sort by time or size.

Note: Limited to ~150-250 entries, no status codes or headers
(Performance API limitation).""",
    params_schema=GetNetworkRequestsParams,
    response_schema=GetNetworkRequestsResponse,
    handler="inspekt.core.handlers.network.get_network_requests",
    cli_name=None,  # MCP-only tool
    cli_hidden=True,
    api_path="/network/requests",
    api_method="GET",
    mcp_enabled_default=True,
    examples=[],
)

# === Get HAR (MCP Tool) ===

get_har = CommandDefinition(
    id="get_har",
    name="Get HAR",
    category=Category.NETWORK,
    description="""Get full network data from DevTools (HAR format).

REQUIRES Chrome DevTools to be open (F12). Provides complete network data
including HTTP status codes (200, 404, 500), request/response headers,
detailed timing, and initiator info.

Use this when you need status codes or headers. Falls back to
get_network_requests if DevTools is closed.""",
    params_schema=GetHARParams,
    response_schema=GetHARResponse,
    handler="inspekt.core.handlers.network.get_har",
    cli_name=None,  # MCP-only tool
    cli_hidden=True,
    api_path="/network/har",
    api_method="GET",
    mcp_enabled_default=True,
    examples=[],
)

# All network commands (CLI group + MCP tools)
NETWORK_COMMANDS = [network, get_network_requests, get_har]
