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
        inspekt server start --daemon

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
        click.echo(
            "Warning: Bridge server is not running on port {}.".format(bridge_port),
            err=True,
        )
        click.echo("Start it with: inspekt server start --daemon", err=True)
        click.echo("MCP server will start but tools will fail until bridge is running.\n", err=True)

    # Import and run MCP server
    from inspekt.app.mcp.server import InspektMCPServer

    # Enable logging for debugging
    import logging
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
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def info(output_json):
    """
    Show information about available MCP tools and resources.

    Lists all tools (actions) and resources (read-only data) that
    the MCP server exposes to AI assistants.
    """
    # Define tools info (must match server.py descriptions)
    tools = [
        {
            "name": "navigate_to_url",
            "description": "Navigate to a URL in a real browser with JavaScript execution",
            "category": "Navigation",
        },
        {
            "name": "go_back",
            "description": "Navigate back in browser history",
            "category": "Navigation",
        },
        {
            "name": "reload_page",
            "description": "Reload the current page in the browser",
            "category": "Navigation",
        },
        {
            "name": "execute_javascript",
            "description": "Execute arbitrary JavaScript code in the browser context",
            "category": "Execution",
        },
        {
            "name": "extract_links",
            "description": "Extract all links from a webpage currently open in the browser",
            "category": "Extraction",
        },
        {
            "name": "extract_outline",
            "description": "Extract the heading hierarchy (H1-H6) from a webpage",
            "category": "Extraction",
        },
        {
            "name": "extract_page_info",
            "description": "Extract comprehensive metadata from a webpage",
            "category": "Extraction",
        },
        {
            "name": "extract_article",
            "description": "Extract main article content using Mozilla Readability",
            "category": "Extraction",
        },
        {
            "name": "click_element",
            "description": "Click an element on the webpage by CSS selector",
            "category": "Interaction",
        },
        {
            "name": "type_text",
            "description": "Type text into the currently focused element",
            "category": "Interaction",
        },
        {
            "name": "get_page_info",
            "description": "Get current page information from the browser",
            "category": "Inspection",
        },
        {
            "name": "take_screenshot",
            "description": "Capture a screenshot of the browser viewport, full page, or element",
            "category": "Inspection",
        },
        {
            "name": "get_selected_text",
            "description": "Get currently selected text from the browser",
            "category": "Selection",
        },
        {
            "name": "get_cookies",
            "description": "Get all cookies for the current page from the browser",
            "category": "Storage",
        },
        {
            "name": "set_cookie",
            "description": "Set a cookie in the browser with optional attributes",
            "category": "Storage",
        },
    ]

    resources = [
        {
            "uri": "inspekt-mcp://current-url",
            "name": "Current Page URL",
            "description": "The URL of the currently active browser tab",
        },
        {
            "uri": "inspekt-mcp://page-title",
            "name": "Page Title",
            "description": "The title of the currently active browser tab",
        },
        {
            "uri": "inspekt-mcp://page-metadata",
            "name": "Page Metadata",
            "description": "Extended metadata about the current page (JSON)",
        },
        {
            "uri": "inspekt-mcp://browser-info",
            "name": "Browser Information",
            "description": "Information about the connected browser (JSON)",
        },
        {
            "uri": "inspekt-mcp://connection-status",
            "name": "Connection Status",
            "description": "Bridge server connection status and health (JSON)",
        },
    ]

    if output_json:
        # JSON output
        click.echo(json.dumps({"tools": tools, "resources": resources}, indent=2))
    else:
        # Human-readable output
        click.echo("Inspekt MCP Server - Available Tools and Resources\n")

        # Group tools by category
        click.echo("TOOLS (Actions)")
        click.echo("=" * 70)
        categories = {}
        for tool in tools:
            cat = tool["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(tool)

        for category in sorted(categories.keys()):
            click.echo(f"\n{category}:")
            for tool in categories[category]:
                click.echo(f"  • {tool['name']}")
                click.echo(f"    {tool['description']}")

        # Resources
        click.echo("\n\nRESOURCES (Read-only data)")
        click.echo("=" * 70)
        for resource in resources:
            click.echo(f"\n  • {resource['name']}")
            click.echo(f"    URI: {resource['uri']}")
            click.echo(f"    {resource['description']}")

        click.echo(f"\n\nTotal: {len(tools)} tools, {len(resources)} resources")


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

    click.echo("1. Checking bridge server...")
    if not client.is_alive():
        click.echo("   ✗ Bridge server is NOT running", err=True)
        click.echo("   Start it with: inspekt server start --daemon", err=True)
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
    click.echo("\n2. Testing JavaScript execution...")
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
    click.echo("\n3. Testing script loader...")
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
    click.echo("\n4. Testing MCP resources...")
    try:
        from inspekt.app.mcp.resources import ResourceProvider
        from inspekt.services.bridge_executor import BridgeExecutor
        import asyncio

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
    click.echo("\n5. Testing MCP tools...")
    try:
        from inspekt.app.mcp.tools import ToolProvider
        from inspekt.app.mcp import schemas
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
