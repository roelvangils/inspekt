"""
Console message command definitions.
"""

from inspekt.core.commands.base import (
    Category,
    CommandDefinition,
    EmptyParams,
    EmptyResponse,
    SubcommandDefinition,
)


console = CommandDefinition(
    id="console",
    name="Console",
    category=Category.DEBUGGING,
    description="""Browser console message commands.

Access and manage console messages from the browser.

**Subcommands:**
- `list`: List console messages with filtering
- `clear`: Clear the console buffer
- `log`: Execute JavaScript and log the result
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="console",
    api_path=None,
    mcp_enabled_default=False,
    is_group=True,
    subcommands=[
        SubcommandDefinition(
            name="list",
            description="List console messages with optional filtering",
            params_schema=EmptyParams,
            examples=[
                "inspekt console list",
                "inspekt console list --level error",
                "inspekt console list -n 20",
            ],
        ),
        SubcommandDefinition(
            name="clear",
            description="Clear the console message buffer",
            params_schema=EmptyParams,
            examples=["inspekt console clear"],
        ),
        SubcommandDefinition(
            name="log",
            description="Execute JavaScript and log the result",
            params_schema=EmptyParams,
            examples=["inspekt console log 'document.title'"],
        ),
    ],
    examples=[
        "inspekt console list",
        "inspekt console list --level error",
        "inspekt console clear",
    ],
)


log_expression = CommandDefinition(
    id="log_expression",
    name="Log Expression",
    category=Category.DEBUGGING,
    description="""Execute JavaScript and log the result (shorthand for `console log`).

Evaluates a JavaScript expression in the browser and prints the result.
Useful for quick debugging and inspection.
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="log",
    api_path=None,
    mcp_enabled_default=False,
    examples=[
        "inspekt log 'document.title'",
        "inspekt log 'window.innerWidth'",
    ],
)


CONSOLE_COMMANDS = [console, log_expression]
