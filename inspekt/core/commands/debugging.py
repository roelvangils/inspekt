"""
Debugging command definitions.

Commands for debugging browser console:
- get_console_logs: Get captured console messages
- clear_console_logs: Clear the console buffer
"""

from inspekt.core.commands.base import Category, CommandDefinition, EmptyParams
from inspekt.core.schemas.debugging import (
    ClearConsoleLogsResponse,
    GetConsoleLogsParams,
    GetConsoleLogsResponse,
)

# === Get Console Logs ===

get_console_logs = CommandDefinition(
    id="get_console_logs",
    name="Get Console Logs",
    category=Category.DEBUGGING,
    description="""Get captured browser console messages.

Returns console.log, console.error, console.warn, console.info, and
console.debug messages captured since the page loaded.

Console messages are automatically captured via hooks injected by
the browser extension. The buffer holds up to 1000 messages.

Filter options:
- level: all (default), error, warn, log, info, debug
- limit: Maximum messages to return (default: 100)

Useful for:
- Debugging JavaScript errors after interactions
- Monitoring application logging
- Checking for deprecation warnings
- Verifying no errors during automated testing""",
    params_schema=GetConsoleLogsParams,
    response_schema=GetConsoleLogsResponse,
    handler="inspekt.core.handlers.debugging.get_console_logs",
    cli_name="console",
    api_path="/debugging/console",
    api_method="GET",
    examples=[
        "inspekt console",
        "inspekt console --level error",
        "inspekt console --limit 50",
    ],
)

# === Clear Console Logs ===

clear_console_logs = CommandDefinition(
    id="clear_console_logs",
    name="Clear Console Logs",
    category=Category.DEBUGGING,
    description="""Clear the browser console message buffer.

Removes all captured console messages. New messages will
continue to be captured after clearing.

Useful for:
- Resetting before a specific test
- Clearing old messages to focus on new activity
- Starting fresh console monitoring""",
    params_schema=EmptyParams,
    response_schema=ClearConsoleLogsResponse,
    handler="inspekt.core.handlers.debugging.clear_console_logs",
    cli_name="console-clear",
    api_path="/debugging/console/clear",
    api_method="POST",
    examples=["inspekt console-clear"],
)

# All debugging commands
DEBUGGING_COMMANDS = [
    get_console_logs,
    clear_console_logs,
]
