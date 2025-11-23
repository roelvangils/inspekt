"""
Inspekt MCP Server

Main MCP server implementation that exposes Inspekt's browser automation
capabilities as tools and resources for AI assistants.
"""

import asyncio
import logging
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import Server, NotificationOptions
from mcp.server.models import InitializationOptions

from inspekt.app.mcp import schemas
from inspekt.app.mcp.resources import ResourceProvider
from inspekt.app.mcp.tools import ToolProvider
from inspekt.services.bridge_executor import BridgeExecutor
from inspekt.services.script_loader import ScriptLoader

logger = logging.getLogger(__name__)


class InspektMCPServer:
    """MCP server for Inspekt browser automation."""

    def __init__(
        self,
        bridge_host: str = "127.0.0.1",
        bridge_port: int = 8765,
        resource_cache_ttl: int = 5,
    ):
        """
        Initialize MCP server.

        Args:
            bridge_host: Bridge server host (default: localhost)
            bridge_port: Bridge server port (default: 8765)
            resource_cache_ttl: Resource cache TTL in seconds (default: 5)
        """
        # Initialize services
        self.executor = BridgeExecutor(host=bridge_host, port=bridge_port)
        self.script_loader = ScriptLoader()

        # Initialize providers
        self.tool_provider = ToolProvider(self.executor, self.script_loader)
        self.resource_provider = ResourceProvider(self.executor, resource_cache_ttl)

        # Create MCP server
        self.server = Server("inspekt")

        # Register handlers
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register all MCP protocol handlers."""

        # ====================================================================
        # List available tools
        # ====================================================================
        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            """List all available tools."""
            return [
                # Navigation tools
                types.Tool(
                    name="navigate_to_url",
                    description="Navigate to a URL in a real browser with JavaScript execution. Use this instead of simple HTTP fetch when you need to access dynamic content, execute JavaScript, or interact with the page. Supports wait conditions for page load.",
                    inputSchema=schemas.NavigateToUrlParams.model_json_schema(),
                ),
                types.Tool(
                    name="go_back",
                    description="Navigate back in browser history",
                    inputSchema={},
                ),
                types.Tool(
                    name="reload_page",
                    description="Reload the current page in the browser",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "hard": {
                                "type": "boolean",
                                "description": "Hard reload (bypass cache)",
                                "default": False,
                            }
                        },
                    },
                ),
                # JavaScript execution
                types.Tool(
                    name="execute_javascript",
                    description="Execute arbitrary JavaScript code in the browser context. Use this to interact with the page DOM, extract data dynamically, or manipulate page content.",
                    inputSchema=schemas.ExecuteJavaScriptParams.model_json_schema(),
                ),
                # Data extraction tools
                types.Tool(
                    name="extract_links",
                    description="Extract all links from a webpage currently open in the browser. Returns structured data including link text, URLs, and link types (internal/external/anchor). Better than parsing HTML as it uses the live DOM.",
                    inputSchema=schemas.ExtractLinksParams.model_json_schema(),
                ),
                types.Tool(
                    name="extract_outline",
                    description="Extract the heading hierarchy (H1-H6) from a webpage currently open in the browser. Creates a structured outline of the page content. Use this when asked about page structure, headings, or outline.",
                    inputSchema={},
                ),
                types.Tool(
                    name="extract_page_info",
                    description="Extract comprehensive metadata from a webpage including title, description, Open Graph tags, meta tags, language, author, and viewport info. Use this for getting detailed page information.",
                    inputSchema={},
                ),
                types.Tool(
                    name="extract_article",
                    description="Extract the main article content from a webpage using Mozilla Readability algorithm. Removes navigation, ads, and clutter to return clean article text. Use this for reading news articles, blog posts, or any long-form content.",
                    inputSchema={},
                ),
                # Element interaction tools
                types.Tool(
                    name="click_element",
                    description="Click an element on the webpage by CSS selector or DevTools reference ($0). Use this to interact with buttons, links, or any clickable elements in the browser.",
                    inputSchema=schemas.ClickElementParams.model_json_schema(),
                ),
                types.Tool(
                    name="type_text",
                    description="Type text into the currently focused element in the browser. Use this to fill out forms, search boxes, or any text input fields. Supports typing speed simulation and form submission.",
                    inputSchema=schemas.TypeTextParams.model_json_schema(),
                ),
                # Inspection tools
                types.Tool(
                    name="get_page_info",
                    description="Get current page information from the browser including URL, title, viewport dimensions, and scroll position. Use this to check what page is currently open in the browser.",
                    inputSchema={},
                ),
                types.Tool(
                    name="take_screenshot",
                    description="Capture a screenshot of the browser viewport, full page, or specific element. Returns base64-encoded image data. Use this to visually document or analyze webpage content.",
                    inputSchema=schemas.TakeScreenshotParams.model_json_schema(),
                ),
                # Selection and storage tools
                types.Tool(
                    name="get_selected_text",
                    description="Get the currently selected text from the browser in text, HTML, or markdown format. Use this to extract user-highlighted content from the page.",
                    inputSchema=schemas.GetSelectedTextParams.model_json_schema(),
                ),
                types.Tool(
                    name="get_cookies",
                    description="Get all cookies for the current page from the browser, including httpOnly, secure, and sameSite attributes. Use this to inspect authentication state or session data.",
                    inputSchema={},
                ),
                types.Tool(
                    name="set_cookie",
                    description="Set a cookie in the browser with optional attributes (secure, httpOnly, sameSite, expiration). Use this to modify authentication state or session data.",
                    inputSchema=schemas.SetCookieParams.model_json_schema(),
                ),
                # Accessibility tools
                types.Tool(
                    name="check_autocomplete",
                    description="Check autocomplete attributes on form fields per WCAG 2.1 SC 1.3.5 (Identify Input Purpose). Analyzes all form fields using multi-language heuristics to predict appropriate autocomplete attributes. Returns violations, warnings, and recommendations with confidence scores. Supports English, German, and Dutch field identification.",
                    inputSchema=schemas.CheckAutocompleteParams.model_json_schema(),
                ),
            ]

        # ====================================================================
        # Call a tool
        # ====================================================================
        @self.server.call_tool()
        async def handle_call_tool(
            name: str, arguments: dict[str, Any] | None
        ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
            """Handle tool execution."""
            logger.info(f"Tool called: {name}")

            # Ensure bridge server is running
            if not self.executor.is_server_running():
                return [
                    types.TextContent(
                        type="text",
                        text="Error: Bridge server is not running. Start it with: inspekt server start",
                    )
                ]

            arguments = arguments or {}

            try:
                # Route to appropriate tool handler
                if name == "navigate_to_url":
                    params = schemas.NavigateToUrlParams(**arguments)
                    result = await self.tool_provider.navigate_to_url(params)
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "go_back":
                    result = await self.tool_provider.go_back()
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "reload_page":
                    hard = arguments.get("hard", False)
                    result = await self.tool_provider.reload_page(hard)
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "execute_javascript":
                    params = schemas.ExecuteJavaScriptParams(**arguments)
                    result = await self.tool_provider.execute_javascript(params)
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "extract_links":
                    params = schemas.ExtractLinksParams(**arguments)
                    result = await self.tool_provider.extract_links(params)
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "extract_outline":
                    result = await self.tool_provider.extract_outline()
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "extract_page_info":
                    result = await self.tool_provider.extract_page_info()
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "extract_article":
                    result = await self.tool_provider.extract_article()
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "click_element":
                    params = schemas.ClickElementParams(**arguments)
                    result = await self.tool_provider.click_element(params)
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "type_text":
                    params = schemas.TypeTextParams(**arguments)
                    result = await self.tool_provider.type_text(params)
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "get_page_info":
                    result = await self.tool_provider.get_page_info()
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "take_screenshot":
                    params = schemas.TakeScreenshotParams(**arguments)
                    result = await self.tool_provider.take_screenshot(params)
                    # For screenshots, return both JSON and image if available
                    contents = [types.TextContent(type="text", text=result.model_dump_json(indent=2))]
                    if result.success and result.data:
                        # TODO: Return ImageContent if needed
                        pass
                    return contents

                elif name == "get_selected_text":
                    params = schemas.GetSelectedTextParams(**arguments)
                    result = await self.tool_provider.get_selected_text(params)
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "get_cookies":
                    result = await self.tool_provider.get_cookies()
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "set_cookie":
                    params = schemas.SetCookieParams(**arguments)
                    result = await self.tool_provider.set_cookie(params)
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "check_autocomplete":
                    params = schemas.CheckAutocompleteParams(**arguments)
                    result = await self.tool_provider.check_autocomplete(params)
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                else:
                    return [
                        types.TextContent(
                            type="text", text=f"Error: Unknown tool '{name}'"
                        )
                    ]

            except Exception as e:
                logger.error(f"Error executing tool {name}: {e}", exc_info=True)
                return [
                    types.TextContent(
                        type="text", text=f"Error executing tool: {str(e)}"
                    )
                ]

        # ====================================================================
        # List available resources
        # ====================================================================
        @self.server.list_resources()
        async def handle_list_resources() -> list[types.Resource]:
            """List all available resources."""
            return await self.resource_provider.list_resources()

        # ====================================================================
        # Read a resource
        # ====================================================================
        @self.server.read_resource()
        async def handle_read_resource(uri: str) -> str:
            """Handle resource read."""
            logger.info(f"Resource read: {uri}")

            # Ensure bridge server is running
            if not self.executor.is_server_running():
                return "Error: Bridge server is not running. Start it with: inspekt server start"

            try:
                content = await self.resource_provider.read_resource(uri)
                return content
            except ValueError as e:
                logger.error(f"Invalid resource URI: {e}")
                return f"Error: {str(e)}"
            except Exception as e:
                logger.error(f"Error reading resource {uri}: {e}", exc_info=True)
                return f"Error reading resource: {str(e)}"

    async def run_stdio(self) -> None:
        """Run server using stdio transport (for Claude Desktop)."""
        logger.info("Starting Inspekt MCP server (stdio mode)")

        # Check bridge server before starting
        if not self.executor.is_server_running():
            logger.warning(
                "Bridge server is not running. Tools will fail until server is started."
            )
            logger.warning("Start bridge server with: inspekt server start")

        # Run server
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            init_options = InitializationOptions(
                server_name="inspekt",
                server_version="1.0.0",
                capabilities=self.server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            )
            await self.server.run(read_stream, write_stream, init_options)

    async def run_http(self, host: str = "127.0.0.1", port: int = 8768) -> None:
        """
        Run server using HTTP transport (for web clients).

        Note: HTTP transport implementation requires additional SSE setup.
        This is a placeholder for future HTTP support.
        """
        raise NotImplementedError(
            "HTTP transport not yet implemented. Use stdio mode for now."
        )


async def main() -> None:
    """Main entry point for running the server directly."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create and run server
    server = InspektMCPServer()
    await server.run_stdio()


if __name__ == "__main__":
    asyncio.run(main())
