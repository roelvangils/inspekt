"""
Server management command definitions.

These commands manage the Inspekt bridge and API servers.
They are CLI-only (no unified API handlers) since they control
the servers themselves.
"""

from inspekt.core.commands.base import (
    Category,
    CommandDefinition,
    EmptyParams,
    EmptyResponse,
    SubcommandDefinition,
)


# =============================================================================
# START COMMAND
# =============================================================================

start = CommandDefinition(
    id="start",
    name="Start Servers",
    category=Category.CONTROL,
    description="""Start Inspekt servers (bridge + API) in daemon mode.

By default, starts both bridge and API servers in background.
Automatically checks for accessibility engine updates before starting.

**Options:**
- `--bridge-only`: Start only the bridge server
- `--api-only`: Start only the API server
- `--foreground`: Run in foreground for debugging
- `--docs`: Also start local MkDocs documentation server
- `--api-port`: Custom API port (default: 8000)
- `--bridge-port`: Custom bridge port (default: 8765)
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,  # CLI-only command
    cli_name="start",
    api_path=None,  # Not exposed via API
    mcp_enabled_default=False,  # Not an MCP tool
    examples=[
        "inspekt start",
        "inspekt start --docs",
        "inspekt start --bridge-only",
        "inspekt start --foreground",
        "inspekt start --api-port 3000",
    ],
)


# =============================================================================
# STOP COMMAND
# =============================================================================

stop = CommandDefinition(
    id="stop",
    name="Stop Servers",
    category=Category.CONTROL,
    description="""Stop Inspekt servers.

By default, stops all servers (bridge, API, and MkDocs if running).

**Options:**
- `--bridge-only`: Stop only the bridge server
- `--api-only`: Stop only the API server
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="stop",
    api_path=None,
    mcp_enabled_default=False,
    examples=[
        "inspekt stop",
        "inspekt stop --bridge-only",
        "inspekt stop --api-only",
    ],
)


# =============================================================================
# RESTART COMMAND
# =============================================================================

restart = CommandDefinition(
    id="restart",
    name="Restart Servers",
    category=Category.CONTROL,
    description="""Restart bridge and API servers.

Stops any running servers, checks for accessibility engine updates,
then starts servers fresh in daemon mode.

**Options:**
- `--docs`: Also start local MkDocs documentation server
- `--api-port`: Custom API port (default: 8000)
- `--bridge-port`: Custom bridge port (default: 8765)
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="restart",
    api_path=None,
    mcp_enabled_default=False,
    examples=[
        "inspekt restart",
        "inspekt restart --docs",
        "inspekt restart --api-port 3000",
    ],
)


# =============================================================================
# STATUS COMMAND (GROUP)
# =============================================================================

status = CommandDefinition(
    id="status",
    name="Server Status",
    category=Category.CONTROL,
    description="""Check status of all Inspekt servers.

Shows comprehensive status information for both bridge and API servers,
including connected browsers, request statistics, and uptime.

**Options:**
- `--json`: Output as JSON

**Subcommands:**
- `web`: Open the web-based dashboard in your browser
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="status",
    api_path=None,
    mcp_enabled_default=False,
    is_group=True,
    subcommands=[
        SubcommandDefinition(
            name="web",
            description="Open the web-based dashboard in your browser",
            params_schema=EmptyParams,
            examples=["inspekt status web", "inspekt status web --port 3000"],
        ),
    ],
    examples=[
        "inspekt status",
        "inspekt status --json",
        "inspekt status web",
    ],
)


# =============================================================================
# QUEUE COMMAND (GROUP)
# =============================================================================

queue = CommandDefinition(
    id="queue",
    name="Request Queue",
    category=Category.CONTROL,
    description="""Manage the request queue.

View and manage pending requests in the bridge server queue.
Use this to diagnose or fix stuck requests.

**Subcommands:**
- `status`: View queue status and pending requests
- `clear`: Clear pending requests from the queue
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="queue",
    api_path=None,
    mcp_enabled_default=False,
    is_group=True,
    subcommands=[
        SubcommandDefinition(
            name="status",
            description="Show queue status and pending requests",
            params_schema=EmptyParams,
            examples=["inspekt queue status", "inspekt queue status --json"],
        ),
        SubcommandDefinition(
            name="clear",
            description="Clear pending requests from the queue",
            params_schema=EmptyParams,
            examples=[
                "inspekt queue clear",
                "inspekt queue clear --older-than 30",
                "inspekt queue clear -f",
            ],
        ),
    ],
    examples=[
        "inspekt queue status",
        "inspekt queue clear",
        "inspekt queue clear --older-than 30",
    ],
)


# =============================================================================
# EXPORT ALL COMMANDS
# =============================================================================

CONTROL_COMMANDS = [start, stop, restart, status, queue]
