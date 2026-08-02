"""
Watch and control command definitions.
"""

from inspekt.core.commands.base import (
    Category,
    CommandDefinition,
    EmptyParams,
    EmptyResponse,
    SubcommandDefinition,
)

watch = CommandDefinition(
    id="watch",
    name="Watch",
    category=Category.CONTROL,
    description="""Watch browser events in real-time.

Stream events from the browser to your terminal.
Press Ctrl+C to stop watching.

**Subcommands:**
- `input`: Watch keyboard input in real-time
- `all`: Watch all events (keyboard, mouse, etc.)
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="watch",
    api_path=None,
    mcp_enabled_default=False,
    is_group=True,
    subcommands=[
        SubcommandDefinition(
            name="input",
            description="Watch keyboard input in real-time",
            params_schema=EmptyParams,
            examples=["inspekt watch input"],
        ),
        SubcommandDefinition(
            name="all",
            description="Watch all events (keyboard, mouse, etc.)",
            params_schema=EmptyParams,
            examples=["inspekt watch all"],
        ),
    ],
    examples=[
        "inspekt watch input",
        "inspekt watch all",
    ],
)


control_mode = CommandDefinition(
    id="control_mode",
    name="Control Mode",
    category=Category.CONTROL,
    description="""Control the browser remotely from your terminal.

All keyboard input from your terminal will be sent directly to the browser,
allowing you to navigate, type, and interact with the page remotely.

Supports:
- Regular text input
- Special keys (arrows, Enter, Tab, Escape, etc.)
- Modifier keys (Ctrl, Alt, Shift, Cmd)

Press Ctrl+D to exit control mode.
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="control",
    api_path=None,
    mcp_enabled_default=False,
    examples=[
        "inspekt control",
    ],
)


WATCH_COMMANDS = [watch, control_mode]
