"""
Inspekt MCP Server

Main MCP server implementation that exposes Inspekt's browser automation
capabilities as tools and resources for AI assistants.

Uses the Unified Command Registry for migrated commands, with fallback
to legacy handlers for unmigrated commands.
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
from inspekt.core import get_registry, register_all_commands
from inspekt.core.generators.mcp import MCPToolRouter
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

        # Initialize legacy providers (for unmigrated tools)
        self.tool_provider = ToolProvider(self.executor, self.script_loader)
        self.resource_provider = ResourceProvider(self.executor, resource_cache_ttl)

        # Initialize unified command registry
        register_all_commands()
        self.registry = get_registry()
        self.unified_router = MCPToolRouter(self.registry)

        # Create MCP server
        self.server = Server("inspekt")

        # Register handlers
        self._register_handlers()

    async def _execute_plugin(
        self, plugin_id: str, params: schemas.PluginExecuteParams
    ) -> schemas.PluginExecuteResponse:
        """
        Execute a plugin by ID.

        Args:
            plugin_id: Plugin slug ID
            params: Execution parameters

        Returns:
            PluginExecuteResponse with execution results
        """
        import time
        import requests as http_requests

        from inspekt.services.plugin_service import get_plugin_service

        start_time = time.time()
        plugin_service = get_plugin_service()

        # Get plugin
        plugin = plugin_service.get_plugin(plugin_id)
        if not plugin:
            return schemas.PluginExecuteResponse(
                success=False,
                plugin_name="",
                plugin_id=plugin_id,
                execution_time_ms=0,
                message=f"Plugin '{plugin_id}' not found",
            )

        # Clear console before execution if capturing
        if params.capture_console:
            try:
                http_requests.post(
                    f"http://{self.executor.host}:{self.executor.port}/console/clear",
                    timeout=5.0,
                )
            except Exception:
                pass

        # Execute the plugin code
        try:
            result = await asyncio.to_thread(
                self.executor.execute,
                plugin["code"],
                plugin.get("timeout", 30.0),
            )
        except Exception as e:
            return schemas.PluginExecuteResponse(
                success=False,
                plugin_name=plugin["name"],
                plugin_id=plugin_id,
                execution_time_ms=int((time.time() - start_time) * 1000),
                message=f"Execution error: {str(e)}",
            )

        execution_time_ms = int((time.time() - start_time) * 1000)

        # Capture console output
        console_output = []
        if params.capture_console:
            try:
                console_response = http_requests.get(
                    f"http://{self.executor.host}:{self.executor.port}/console/logs",
                    timeout=5.0,
                )
                if console_response.status_code == 200:
                    console_data = console_response.json()
                    for entry in console_data.get("entries", []):
                        console_output.append(schemas.ConsoleEntry(
                            level=entry.get("level", "log"),
                            timestamp=entry.get("timestamp", ""),
                            message=entry.get("message", ""),
                        ))
            except Exception:
                pass

        # Update run count
        plugin_service.increment_run_count(plugin_id)

        if not result.get("ok"):
            return schemas.PluginExecuteResponse(
                success=False,
                plugin_name=plugin["name"],
                plugin_id=plugin_id,
                console_output=console_output,
                execution_time_ms=execution_time_ms,
                message=result.get("error", "Execution failed"),
            )

        return schemas.PluginExecuteResponse(
            success=True,
            plugin_name=plugin["name"],
            plugin_id=plugin_id,
            result=result.get("result") if plugin.get("returns_data") else None,
            console_output=console_output,
            execution_time_ms=execution_time_ms,
            message=f"Plugin '{plugin['name']}' executed successfully",
        )

    async def _unload_plugin(
        self, plugin_id: str, params: schemas.PluginExecuteParams
    ) -> schemas.PluginExecuteResponse:
        """
        Unload/reverse a plugin by ID.

        Args:
            plugin_id: Plugin slug ID
            params: Execution parameters

        Returns:
            PluginExecuteResponse with execution results
        """
        import time
        import requests as http_requests

        from inspekt.services.plugin_service import get_plugin_service

        start_time = time.time()
        plugin_service = get_plugin_service()

        # Get plugin
        plugin = plugin_service.get_plugin(plugin_id)
        if not plugin:
            return schemas.PluginExecuteResponse(
                success=False,
                plugin_name="",
                plugin_id=plugin_id,
                execution_time_ms=0,
                message=f"Plugin '{plugin_id}' not found",
            )

        unload_mode = plugin.get("unload_mode", "none")

        if unload_mode == "none":
            return schemas.PluginExecuteResponse(
                success=False,
                plugin_name=plugin["name"],
                plugin_id=plugin_id,
                execution_time_ms=0,
                message=f"Plugin '{plugin['name']}' does not support unloading",
            )

        # Determine which code to run
        if unload_mode == "toggle":
            code_to_run = plugin["code"]
            action = "toggled"
        elif unload_mode == "custom":
            code_to_run = plugin.get("unload_code")
            if not code_to_run:
                return schemas.PluginExecuteResponse(
                    success=False,
                    plugin_name=plugin["name"],
                    plugin_id=plugin_id,
                    execution_time_ms=0,
                    message=f"Plugin has custom unload mode but no unload code",
                )
            action = "unloaded"
        else:
            return schemas.PluginExecuteResponse(
                success=False,
                plugin_name=plugin["name"],
                plugin_id=plugin_id,
                execution_time_ms=0,
                message=f"Unknown unload mode: {unload_mode}",
            )

        # Clear console before execution if capturing
        if params.capture_console:
            try:
                http_requests.post(
                    f"http://{self.executor.host}:{self.executor.port}/console/clear",
                    timeout=5.0,
                )
            except Exception:
                pass

        # Execute the unload code
        try:
            result = await asyncio.to_thread(
                self.executor.execute,
                code_to_run,
                plugin.get("timeout", 30.0),
            )
        except Exception as e:
            return schemas.PluginExecuteResponse(
                success=False,
                plugin_name=plugin["name"],
                plugin_id=plugin_id,
                execution_time_ms=int((time.time() - start_time) * 1000),
                message=f"Execution error: {str(e)}",
            )

        execution_time_ms = int((time.time() - start_time) * 1000)

        # Capture console output
        console_output = []
        if params.capture_console:
            try:
                console_response = http_requests.get(
                    f"http://{self.executor.host}:{self.executor.port}/console/logs",
                    timeout=5.0,
                )
                if console_response.status_code == 200:
                    console_data = console_response.json()
                    for entry in console_data.get("entries", []):
                        console_output.append(schemas.ConsoleEntry(
                            level=entry.get("level", "log"),
                            timestamp=entry.get("timestamp", ""),
                            message=entry.get("message", ""),
                        ))
            except Exception:
                pass

        if not result.get("ok"):
            return schemas.PluginExecuteResponse(
                success=False,
                plugin_name=plugin["name"],
                plugin_id=plugin_id,
                console_output=console_output,
                execution_time_ms=execution_time_ms,
                message=result.get("error", "Execution failed"),
            )

        return schemas.PluginExecuteResponse(
            success=True,
            plugin_name=plugin["name"],
            plugin_id=plugin_id,
            result=result.get("result") if plugin.get("returns_data") else None,
            console_output=console_output,
            execution_time_ms=execution_time_ms,
            message=f"Plugin '{plugin['name']}' {action} successfully",
        )

    def _register_handlers(self) -> None:
        """Register all MCP protocol handlers."""

        # ====================================================================
        # List available tools
        # ====================================================================
        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            """List all available tools from both unified and legacy registries."""
            from inspekt.app.mcp.registry import get_all_tools

            # Get tools from unified registry (migrated commands)
            unified_tools = self.unified_router.get_tools()
            unified_names = {t.name for t in unified_tools}

            # Get tools from legacy registry (excluding migrated ones)
            legacy_tools = []
            for tool_def in get_all_tools():
                if tool_def.name not in unified_names:
                    legacy_tools.append(
                        types.Tool(
                            name=tool_def.name,
                            description=tool_def.description,
                            inputSchema=tool_def.input_schema,
                        )
                    )

            # Combine: unified tools first, then legacy
            return unified_tools + legacy_tools

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
                        text="Error: Bridge server is not running. Start it with: inspekt start",
                    )
                ]

            arguments = arguments or {}

            try:
                # First, try unified registry (for migrated commands)
                if self.unified_router.has_tool(name):
                    logger.debug(f"Routing {name} to unified registry")
                    return await self.unified_router.call_tool(name, arguments)

                # Legacy handlers below (for unmigrated commands)
                # TODO: Remove these as commands are migrated

                if name == "execute_javascript":
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

                elif name == "run_axe":
                    params = schemas.RunAxeParams(**arguments)
                    result = await self.tool_provider.run_axe(params)
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "get_network_requests":
                    params = schemas.GetNetworkRequestsParams(**arguments)
                    result = await self.tool_provider.get_network_requests(params)
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "get_har":
                    params = schemas.GetHARParams(**arguments)
                    result = await self.tool_provider.get_har(params)
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "get_console_logs":
                    params = schemas.GetConsoleLogsParams(**arguments)
                    result = await self.tool_provider.get_console_logs(params)
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "clear_console_logs":
                    result = await self.tool_provider.clear_console_logs()
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                # Navigation tools
                elif name == "navigate_to_url":
                    params = schemas.NavigateToUrlParams(**arguments)
                    result = await self.tool_provider.navigate_to_url(params)
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "go_back":
                    result = await self.tool_provider.go_back()
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name == "reload_page":
                    hard = arguments.get("hard", False)
                    result = await self.tool_provider.reload_page(hard=hard)
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                # Handle dynamic plugin tools
                elif name.startswith("unload_plugin_"):
                    plugin_id = name[14:]  # Remove "unload_plugin_" prefix
                    params = schemas.PluginExecuteParams(**arguments)
                    result = await self._unload_plugin(plugin_id, params)
                    return [types.TextContent(type="text", text=result.model_dump_json(indent=2))]

                elif name.startswith("plugin_"):
                    plugin_id = name[7:]  # Remove "plugin_" prefix
                    params = schemas.PluginExecuteParams(**arguments)
                    result = await self._execute_plugin(plugin_id, params)
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
                return "Error: Bridge server is not running. Start it with: inspekt start"

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
            logger.warning("Start bridge server with: inspekt start")

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
