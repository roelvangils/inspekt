"""
MCP Tool Generator.

Generates MCP tool definitions and handlers from CommandDefinitions.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from inspekt.core.commands.base import CommandDefinition
from inspekt.core.registry import CommandRegistry
from mcp import types

if TYPE_CHECKING:
    from pydantic import BaseModel

logger = logging.getLogger(__name__)


def generate_mcp_tool(cmd: CommandDefinition, registry: CommandRegistry | None = None) -> types.Tool:
    """
    Generate an MCP Tool definition from a CommandDefinition.

    Uses effective values from the registry (custom if set, otherwise defaults).

    Args:
        cmd: The command definition to convert
        registry: Optional registry instance (uses singleton if not provided)

    Returns:
        MCP Tool object ready for use with mcp-py
    """
    if registry is None:
        registry = CommandRegistry.get_instance()

    return types.Tool(
        name=registry.get_effective_mcp_name(cmd),
        description=registry.get_description(cmd),
        inputSchema=registry.get_effective_input_schema(cmd),
    )


def generate_mcp_tools(registry: CommandRegistry | None = None) -> list[types.Tool]:
    """
    Generate all MCP tools from the registry.

    Only includes commands that are MCP-enabled.
    Uses effective values (custom if set, otherwise defaults).

    Args:
        registry: Optional registry instance (uses singleton if not provided)

    Returns:
        List of MCP Tool definitions
    """
    if registry is None:
        registry = CommandRegistry.get_instance()

    tools = []
    for cmd in registry.get_for_mcp():
        tools.append(generate_mcp_tool(cmd, registry))

    return tools


def get_handler(cmd: CommandDefinition) -> Callable[..., Any]:
    """
    Get the handler function for a command.

    Supports both string paths and direct function references.

    Args:
        cmd: The command definition

    Returns:
        The async handler function
    """
    if callable(cmd.handler):
        return cmd.handler

    # Import from string path
    module_path, func_name = cmd.handler.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, func_name)


async def execute_mcp_tool(
    cmd: CommandDefinition,
    arguments: dict[str, Any] | None = None,
) -> list[types.TextContent | types.ImageContent]:
    """
    Execute an MCP tool and return the result.

    Args:
        cmd: The command definition
        arguments: Tool arguments (will be validated against params_schema)

    Returns:
        List of MCP content items (usually TextContent with JSON)
    """
    import json

    arguments = arguments or {}

    try:
        # Validate and parse input
        params = cmd.params_schema(**arguments)

        # Get and call handler
        handler = get_handler(cmd)
        result: BaseModel = await handler(params)

        # Serialize response
        response_json = result.model_dump_json(indent=2)

        return [types.TextContent(type="text", text=response_json)]

    except Exception as e:
        logger.error(f"Error executing MCP tool {cmd.id}: {e}", exc_info=True)
        error_response = {"success": False, "error": str(e)}
        return [types.TextContent(type="text", text=json.dumps(error_response, indent=2))]


class MCPToolRouter:
    """
    Routes MCP tool calls to the appropriate handlers.

    Used by the MCP server to handle tool/call requests.
    """

    def __init__(self, registry: CommandRegistry | None = None):
        """
        Initialize the router.

        Args:
            registry: Optional registry instance (uses singleton if not provided)
        """
        self.registry = registry or CommandRegistry.get_instance()
        self._command_map: dict[str, CommandDefinition] = {}
        self._rebuild_map()

    def _rebuild_map(self) -> None:
        """Rebuild the command lookup map using effective MCP names."""
        self._command_map = {
            self.registry.get_effective_mcp_name(cmd): cmd
            for cmd in self.registry.get_for_mcp()
        }

    def get_tools(self) -> list[types.Tool]:
        """Get all MCP tool definitions."""
        self._rebuild_map()  # Refresh in case config changed
        return generate_mcp_tools(self.registry)

    def has_tool(self, name: str) -> bool:
        """Check if a tool exists."""
        return name in self._command_map

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> list[types.TextContent | types.ImageContent]:
        """
        Call an MCP tool by name.

        Args:
            name: Tool name (MCP name, not command ID)
            arguments: Tool arguments

        Returns:
            List of MCP content items

        Raises:
            ValueError: If tool not found
        """
        self._rebuild_map()  # Refresh in case config changed

        cmd = self._command_map.get(name)
        if not cmd:
            return [
                types.TextContent(
                    type="text",
                    text=f'{{"success": false, "error": "Unknown tool: {name}"}}',
                )
            ]

        return await execute_mcp_tool(cmd, arguments)
