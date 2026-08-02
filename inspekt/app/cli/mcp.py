"""MCP server management commands."""

import asyncio
import json
import sys

import click

from inspekt.client import BridgeClient


@click.group()
def mcp():
    """Manage the MCP server for AI assistant integration."""
    pass


@mcp.command()
@click.option(
    "--bridge-port",
    type=int,
    default=8765,
    help="Bridge server port (default: 8765)",
)
@click.option(
    "--cache-ttl",
    type=int,
    default=5,
    help="Resource cache TTL in seconds (default: 5)",
)
def start(bridge_port, cache_ttl):
    """
    Start the MCP server in stdio mode.

    The MCP server exposes Inspekt's browser automation capabilities
    as tools and resources for AI assistants like Claude Desktop.

    The server runs in stdio mode, which is compatible with Claude Desktop
    and other MCP clients that use standard input/output for communication.

    Make sure the bridge server is running first:
        inspekt start --bridge-only

    Then configure your Claude Desktop config to use this server:
        {
          "mcpServers": {
            "inspekt": {
              "command": "inspekt",
              "args": ["mcp", "start"]
            }
          }
        }
    """
    # Check if bridge server is running
    client = BridgeClient(port=bridge_port)
    if not client.is_alive():
        from inspekt.app.cli.table import _style_with_inline_code
        click.echo(
            _style_with_inline_code(f"Warning: Bridge server is not running on port {bridge_port}.", base_fg="yellow"),
            err=True,
        )
        click.echo(_style_with_inline_code("Start it with: `inspekt start --bridge-only`", base_fg="yellow"), err=True)
        click.echo("MCP server will start but tools will fail until bridge is running.\n", err=True)

    # Import and run MCP server
    # Enable logging for debugging
    import logging

    from inspekt.app.mcp.server import InspektMCPServer
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    try:
        # Create and run server
        server = InspektMCPServer(
            bridge_host="127.0.0.1",
            bridge_port=bridge_port,
            resource_cache_ttl=cache_ttl,
        )

        # Run in stdio mode
        asyncio.run(server.run_stdio())

    except KeyboardInterrupt:
        click.echo("\nMCP server stopped", err=True)
        sys.exit(0)
    except Exception as e:
        import traceback
        click.echo(f"Error running MCP server: {e}", err=True)
        click.echo("\nFull traceback:", err=True)
        traceback.print_exc()
        sys.exit(1)


@mcp.command()
@click.option("--json", "-j", "output_json", is_flag=True, help="Output as JSON")
def info(output_json):
    """
    Show information about available MCP tools and resources.

    Lists all tools (actions) and resources (read-only data) that
    the MCP server exposes to AI assistants. Dynamically fetches
    tool definitions including any MCP-enabled plugins.
    """
    from inspekt.app.mcp.registry import (
        format_params_summary,
        get_builtin_tools,
        get_plugin_tools,
        get_resources,
        get_tools_by_category,
    )

    builtin_tools = get_builtin_tools()
    plugin_tools = get_plugin_tools()
    resources = get_resources()

    if output_json:
        # JSON output with full details
        tools_json = []
        for tool in builtin_tools + plugin_tools:
            tools_json.append({
                "name": tool.name,
                "description": tool.description,
                "category": tool.category,
                "parameters": format_params_summary(tool.input_schema),
                "input_schema": tool.input_schema,
                "is_plugin": tool.is_plugin,
            })

        resources_json = []
        for resource in resources:
            resources_json.append({
                "uri": resource.uri,
                "name": resource.name,
                "description": resource.description,
                "mime_type": resource.mime_type,
            })

        from inspekt.app.cli.table import print_json
        total_tools = len(builtin_tools) + len(plugin_tools)
        print_json({
            "tools": tools_json,
            "resources": resources_json,
            "summary": {
                "builtin_tools": len(builtin_tools),
                "plugin_tools": len(plugin_tools),
                "resources": len(resources),
            }
        }, summary=f"{total_tools} MCP tools")
    else:
        # Human-readable output
        click.echo("Inspekt MCP Server - Available Tools and Resources\n")

        # Count totals
        builtin_count = len(builtin_tools)
        plugin_count = len(plugin_tools)

        if plugin_count > 0:
            click.echo(f"TOOLS ({builtin_count} built-in + {plugin_count} plugins)")
        else:
            click.echo(f"TOOLS ({builtin_count} built-in)")
        click.echo("=" * 70)

        # Group tools by category
        tools_by_category = get_tools_by_category()

        for category, tools in tools_by_category.items():
            count = len(tools)
            click.echo(f"\n{category} ({count}):")

            for tool in tools:
                params = format_params_summary(tool.input_schema)
                # Truncate description to first sentence for cleaner output
                desc = tool.description.split(". ")[0]
                if len(desc) > 60:
                    desc = desc[:57] + "…"

                click.echo(f"  • {tool.name}")
                click.echo(f"    {desc}")
                click.echo(f"    Parameters: {params}")

        # Resources
        click.echo(f"\n\nRESOURCES ({len(resources)})")
        click.echo("=" * 70)
        for resource in resources:
            click.echo(f"\n  • {resource.name}")
            click.echo(f"    URI: {resource.uri}")
            click.echo(f"    {resource.description}")

        # Summary
        total_tools = builtin_count + plugin_count
        click.echo(f"\n\nTotal: {total_tools} tools, {len(resources)} resources")
        click.echo("\nUse 'inspekt mcp describe <tool>' for detailed documentation.")

        # VM terminal: offer a "Data ready to copy" toast
        from inspekt.app.cli.table import emit_copyable_data
        tool_rows = []
        for tool in builtin_tools + plugin_tools:
            desc = (tool.description or "").split(". ")[0]
            tool_rows.append([tool.name, tool.category, desc, format_params_summary(tool.input_schema)])
        tools_json = [
            {
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "parameters": format_params_summary(t.input_schema),
                "is_plugin": t.is_plugin,
            }
            for t in builtin_tools + plugin_tools
        ]
        resources_json = [
            {"uri": r.uri, "name": r.name, "description": r.description, "mime_type": r.mime_type}
            for r in resources
        ]
        emit_copyable_data(
            headers=["Name", "Category", "Description", "Parameters"],
            rows=tool_rows,
            json_data={"tools": tools_json, "resources": resources_json,
                       "summary": {"builtin_tools": builtin_count, "plugin_tools": plugin_count,
                                   "resources": len(resources)}},
            summary=f"{total_tools} MCP tool{'s' if total_tools != 1 else ''}",
        )


@mcp.command()
@click.argument("tool_name")
@click.option("--json", "-j", "output_json", is_flag=True, help="Output as JSON")
def describe(tool_name, output_json):
    """
    Show detailed documentation for a specific MCP tool.

    Displays full parameter schemas, descriptions, return types,
    and usage examples for the specified tool.
    """
    from inspekt.app.mcp.registry import (
        format_params_detailed,
        get_response_schema,
        get_tool,
    )

    tool = get_tool(tool_name)

    if not tool:
        # Try with plugin_ prefix
        if not tool_name.startswith("plugin_"):
            tool = get_tool(f"plugin_{tool_name}")

        if not tool:
            click.echo(f"Error: Tool '{tool_name}' not found.", err=True)
            click.echo("\nUse 'inspekt mcp info' to see available tools.", err=True)
            sys.exit(1)

    params = format_params_detailed(tool.input_schema)
    response_schema = get_response_schema(tool)

    if output_json:
        # JSON output
        output = {
            "name": tool.name,
            "category": tool.category,
            "description": tool.description,
            "is_plugin": tool.is_plugin,
            "input_schema": tool.input_schema,
            "response_schema": response_schema,
            "parameters": params,
        }
        from inspekt.app.cli.table import print_json
        print_json(output, summary=f"MCP tool: {tool.name}")
    else:
        # Human-readable output
        click.echo(f"Tool: {tool.name}")
        click.echo(f"Category: {tool.category}")
        if tool.is_plugin:
            click.echo(f"Type: Plugin (ID: {tool.plugin_id})")
        click.echo()

        click.echo("Description:")
        # Word wrap the description
        desc_words = tool.description.split()
        lines = []
        current_line = "  "
        for word in desc_words:
            if len(current_line) + len(word) + 1 > 72:
                lines.append(current_line)
                current_line = "  " + word
            else:
                current_line += " " + word if current_line != "  " else word
        if current_line.strip():
            lines.append(current_line)
        click.echo("\n".join(lines))
        click.echo()

        # Parameters
        click.echo("Parameters:")
        if not params:
            click.echo("  none")
        else:
            for param in params:
                req_str = "[REQUIRED]" if param["required"] else "[optional]"
                type_str = param["type"]
                click.echo(f"  {param['name']} ({type_str}) {req_str}")
                if param["description"]:
                    click.echo(f"    {param['description']}")
                if param.get("allowed_values"):
                    click.echo(f"    Allowed: {', '.join(repr(v) for v in param['allowed_values'])}")
                if param.get("default") is not None:
                    click.echo(f"    Default: {param['default']}")
        click.echo()

        # Response schema
        if response_schema:
            click.echo("Returns:")
            response_props = response_schema.get("properties", {})
            response_required = set(response_schema.get("required", []))
            for name, prop in response_props.items():
                opt = "" if name in response_required else ", optional"
                prop_type = prop.get("type", "any")
                desc = prop.get("description", "")
                click.echo(f"  • {name} ({prop_type}{opt})")
                if desc:
                    click.echo(f"    {desc}")
            click.echo()

        # Example invocation
        click.echo("MCP Invocation Example:")
        example_args = {}
        for param in params:
            if param["required"]:
                # Add placeholder for required params
                if param["type"] == "string":
                    if param.get("allowed_values"):
                        example_args[param["name"]] = param["allowed_values"][0]
                    else:
                        example_args[param["name"]] = f"<{param['name']}>"
                elif param["type"] == "integer":
                    example_args[param["name"]] = 30
                elif param["type"] == "boolean":
                    example_args[param["name"]] = True
                else:
                    example_args[param["name"]] = f"<{param['name']}>"

        example = {
            "name": tool.name,
            "arguments": example_args if example_args else {},
        }
        click.echo(json.dumps(example, indent=2))

        # VM terminal: offer a "Data ready to copy" toast
        from inspekt.app.cli.table import emit_copyable_data
        param_rows = [
            [
                p["name"],
                p["type"],
                "yes" if p["required"] else "no",
                p.get("description", "") or "",
                "" if p.get("default") is None else str(p["default"]),
            ]
            for p in params
        ]
        emit_copyable_data(
            headers=["Name", "Type", "Required", "Description", "Default"],
            rows=param_rows,
            json_data={
                "name": tool.name,
                "category": tool.category,
                "description": tool.description,
                "is_plugin": tool.is_plugin,
                "input_schema": tool.input_schema,
                "response_schema": response_schema,
                "parameters": params,
            },
            summary=f"tool {tool.name}",
        )


@mcp.command()
def test():
    """
    Test MCP server connectivity and basic functionality.

    Checks if the bridge server is running and tests basic
    communication with the browser.
    """
    click.echo("Testing Inspekt MCP Server connectivity...\n")

    # Check bridge server
    client = BridgeClient()

    click.echo("1. Checking bridge server…")
    if not client.is_alive():
        from inspekt.app.cli.table import _style_with_inline_code
        click.echo("   ✗ Bridge server is NOT running", err=True)
        click.echo(_style_with_inline_code("   Start it with: `inspekt start --bridge-only`", base_fg="red"), err=True)
        sys.exit(1)
    else:
        click.echo("   ✓ Bridge server is running")

    # Get browser version and check if connected
    try:
        # Get userscript/extension version
        version = client.get_userscript_version()
        if version and version != 'unknown':
            click.echo(f"   Extension/userscript version: {version}")
        else:
            click.echo("   Extension/userscript version: unknown")

        # Check if browser is connected by trying to execute simple code
        test_result = client.execute("typeof window", timeout=2.0)
        browser_connected = test_result.get("ok", False)
        click.echo(f"   Browser connected: {browser_connected}")
    except Exception:
        click.echo("   Browser connected: False")

    # Test basic JavaScript execution
    click.echo("\n2. Testing JavaScript execution…")
    try:
        result = client.execute("1 + 1", timeout=5.0)
        if result.get("ok") and result.get("result") == 2:
            click.echo("   ✓ JavaScript execution works")
        else:
            click.echo(f"   ✗ Unexpected result: {result}", err=True)
            sys.exit(1)
    except Exception as e:
        click.echo(f"   ✗ Execution failed: {e}", err=True)
        sys.exit(1)

    # Test script loading
    click.echo("\n3. Testing script loader…")
    try:
        from inspekt.services.script_loader import ScriptLoader

        loader = ScriptLoader()
        script = loader.load_script_sync("extended_info.js")
        if script and len(script) > 0:
            click.echo("   ✓ Script loader works")
        else:
            click.echo("   ✗ Failed to load script", err=True)
            sys.exit(1)
    except Exception as e:
        click.echo(f"   ✗ Script loader failed: {e}", err=True)
        sys.exit(1)

    # Test MCP resources
    click.echo("\n4. Testing MCP resources…")
    try:
        import asyncio

        from inspekt.app.mcp.resources import ResourceProvider
        from inspekt.services.bridge_executor import BridgeExecutor

        async def test_resource():
            executor = BridgeExecutor()
            provider = ResourceProvider(executor, cache_ttl=5)

            # Test reading current URL resource
            content = await provider.read_resource("inspekt-mcp://current-url")
            return content

        url = asyncio.run(test_resource())
        if url and len(url) > 0:
            click.echo(f"   ✓ Resources work (current URL: {url})")
        else:
            click.echo("   ✗ Resource returned empty content", err=True)
            sys.exit(1)
    except Exception as e:
        click.echo(f"   ✗ Resource test failed: {e}", err=True)
        sys.exit(1)

    # Test MCP tool
    click.echo("\n5. Testing MCP tools…")
    try:
        from inspekt.app.mcp import schemas
        from inspekt.app.mcp.tools import ToolProvider
        from inspekt.services.script_loader import ScriptLoader

        async def test_tool():
            executor = BridgeExecutor()
            script_loader = ScriptLoader()
            provider = ToolProvider(executor, script_loader)

            # Test get_page_info tool
            result = await provider.get_page_info()
            return result

        result = asyncio.run(test_tool())
        if result.success and result.url:
            click.echo(f"   ✓ Tools work (page: {result.title})")
        else:
            click.echo("   ✗ Tool test failed", err=True)
            sys.exit(1)
    except Exception as e:
        click.echo(f"   ✗ Tool test failed: {e}", err=True)
        sys.exit(1)

    # All tests passed
    click.echo("\n✓ All tests passed! MCP server is ready to use.")
    click.echo("\nTo start the MCP server:")
    click.echo("  inspekt mcp start")
    click.echo("\nTo use with Claude Code, add to your config:")
    click.echo('  "mcpServers": {')
    click.echo('    "inspekt": {')
    click.echo('      "command": "inspekt",')
    click.echo('      "args": ["mcp", "start"]')
    click.echo("    }")
    click.echo("  }")
