"""
Plugin management command definitions.
"""

from inspekt.core.commands.base import (
    Category,
    CommandDefinition,
    EmptyParams,
    EmptyResponse,
    SubcommandDefinition,
)

plugin = CommandDefinition(
    id="plugin",
    name="Plugins",
    category=Category.PLUGINS,
    description="""Manage custom JavaScript plugins (bookmarklets).

Plugins are JavaScript snippets that can be executed in the browser.
They can be organized by category and optionally exposed to MCP.

**Subcommands:**
- `list`: List all plugins
- `add`: Add a new plugin
- `run`: Run a plugin by name
- `remove`: Remove a plugin
- `edit`: Edit a plugin
- `export`: Export plugins to JSON
- `import`: Import plugins from JSON
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="plugin",
    api_path=None,
    mcp_enabled_default=False,
    is_group=True,
    subcommands=[
        SubcommandDefinition(
            name="list",
            description="List all plugins",
            params_schema=EmptyParams,
            examples=[
                "inspekt plugin list",
                "inspekt plugin list --category accessibility",
                "inspekt plugin list --mcp",
            ],
        ),
        SubcommandDefinition(
            name="add",
            description="Add a new plugin",
            params_schema=EmptyParams,
            examples=["inspekt plugin add", "inspekt plugin add --from-file script.js"],
        ),
        SubcommandDefinition(
            name="run",
            description="Run a plugin by name",
            params_schema=EmptyParams,
            examples=["inspekt plugin run my-plugin"],
        ),
        SubcommandDefinition(
            name="remove",
            description="Remove a plugin",
            params_schema=EmptyParams,
            examples=["inspekt plugin remove my-plugin"],
        ),
        SubcommandDefinition(
            name="edit",
            description="Edit a plugin",
            params_schema=EmptyParams,
            examples=["inspekt plugin edit my-plugin"],
        ),
        SubcommandDefinition(
            name="export",
            description="Export plugins to JSON",
            params_schema=EmptyParams,
            examples=["inspekt plugin export", "inspekt plugin export -o plugins.json"],
        ),
        SubcommandDefinition(
            name="import",
            description="Import plugins from JSON",
            params_schema=EmptyParams,
            examples=["inspekt plugin import plugins.json"],
        ),
        SubcommandDefinition(
            name="show",
            description="Show plugin details and code",
            params_schema=EmptyParams,
            examples=["inspekt plugin show my-plugin"],
        ),
        SubcommandDefinition(
            name="unload",
            description="Unload a currently loaded plugin",
            params_schema=EmptyParams,
            examples=["inspekt plugin unload my-plugin"],
        ),
    ],
    examples=[
        "inspekt plugin list",
        "inspekt plugin add",
        "inspekt plugin run accessibility-check",
        "inspekt plugin export",
    ],
)


PLUGIN_COMMANDS = [plugin]
