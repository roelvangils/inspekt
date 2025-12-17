"""
Interface generators for the Unified Command Registry.

These generators create CLI, API, and MCP interfaces from CommandDefinitions.
"""

from inspekt.core.generators.mcp import generate_mcp_tool, generate_mcp_tools

__all__ = [
    "generate_mcp_tool",
    "generate_mcp_tools",
]
