"""
MCP server management command definitions.
"""

from inspekt.core.commands.base import (
    Category,
    CommandDefinition,
    EmptyParams,
    EmptyResponse,
    SubcommandDefinition,
)

mcp = CommandDefinition(
    id="mcp",
    name="MCP Server",
    category=Category.PLUGINS,
    description="""Manage the MCP server for AI assistant integration.

The MCP (Model Context Protocol) server enables AI assistants like
Claude to interact with your browser through Inspekt.

**Subcommands:**
- `start`: Start the MCP server
- `config`: Show MCP configuration for Claude
- `tools`: List available MCP tools
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="mcp",
    api_path=None,
    mcp_enabled_default=False,
    is_group=True,
    subcommands=[
        SubcommandDefinition(
            name="start",
            description="Start the MCP server",
            params_schema=EmptyParams,
            examples=["inspekt mcp start", "inspekt mcp start --bridge-port 8765"],
        ),
        SubcommandDefinition(
            name="info",
            description="Show MCP server information and configuration",
            params_schema=EmptyParams,
            examples=["inspekt mcp info", "inspekt mcp info --json"],
        ),
        SubcommandDefinition(
            name="describe",
            description="Describe an MCP tool in detail",
            params_schema=EmptyParams,
            examples=["inspekt mcp describe navigate_to_url"],
        ),
        SubcommandDefinition(
            name="test",
            description="Test MCP server connectivity and tools",
            params_schema=EmptyParams,
            examples=["inspekt mcp test"],
        ),
    ],
    examples=[
        "inspekt mcp start",
        "inspekt mcp info",
        "inspekt mcp describe navigate_to_url",
    ],
)


MCP_MANAGEMENT_COMMANDS = [mcp]
