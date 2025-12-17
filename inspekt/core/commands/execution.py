"""
Execution command definitions.

Commands for executing code in the browser:
- execute_javascript: Run arbitrary JavaScript
"""

from inspekt.core.commands.base import Category, CommandDefinition
from inspekt.core.schemas.execution import (
    ExecuteJavaScriptParams,
    ExecuteJavaScriptResponse,
)

# === Execute JavaScript ===

execute_javascript = CommandDefinition(
    id="execute_javascript",
    name="Execute JavaScript",
    category=Category.EXECUTION,
    description="""Execute arbitrary JavaScript code in the browser context.

Runs JavaScript in the page's execution context with full DOM access.
The code can:
- Access and modify the DOM
- Call page's JavaScript functions
- Use browser APIs (localStorage, fetch, etc.)
- Return values (primitives, objects, arrays)

The result is serialized and returned. Async code is supported -
return a Promise and it will be awaited.

Security note: This is a powerful capability. The executed code
runs with the page's privileges, not the extension's.

Timeout defaults to 30 seconds for long-running operations.""",
    params_schema=ExecuteJavaScriptParams,
    response_schema=ExecuteJavaScriptResponse,
    handler="inspekt.core.handlers.execution.execute_javascript",
    cli_name="eval",
    api_path="/execution/eval",
    api_method="POST",
    examples=[
        "inspekt eval 'document.title'",
        "inspekt eval 'document.querySelectorAll(\"a\").length'",
        "inspekt eval 'await fetch(\"/api/data\").then(r => r.json())'",
    ],
)

# All execution commands
EXECUTION_COMMANDS = [
    execute_javascript,
]
