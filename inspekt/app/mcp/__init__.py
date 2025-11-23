"""
Inspekt MCP Server

This module provides a Model Context Protocol (MCP) server that exposes
Inspekt's browser automation capabilities as tools and resources for AI assistants.

The MCP server enables AI models like Claude to:
- Navigate and interact with web pages
- Execute JavaScript in the browser
- Extract structured data from pages
- Take screenshots and inspect elements
- Manage cookies and storage

Server Components:
- server.py: Main MCP server implementation
- tools.py: MCP tool definitions and handlers
- resources.py: MCP resource definitions
- schemas.py: Pydantic schemas for tools and resources

Usage:
    # Start MCP server in stdio mode (for Claude Desktop)
    inspekt mcp start

    # Start MCP server in HTTP mode
    inspekt mcp start --http --port 8768

    # Show available tools and resources
    inspekt mcp info
"""

from inspekt.app.mcp.server import InspektMCPServer

__all__ = ["InspektMCPServer"]
