"""
MCP Tool Registry

Centralized registry of all MCP tools that can be used by:
- The MCP server (server.py) for runtime
- The CLI (mcp.py) for documentation

This ensures tool definitions stay in sync between server and CLI.
"""

from dataclasses import dataclass, field
from typing import Any

from inspekt.app.mcp import schemas

# Empty schema for tools with no parameters (MCP requires proper JSON Schema format)
EMPTY_SCHEMA: dict = {"type": "object", "properties": {}}


@dataclass
class ToolDefinition:
    """Definition of an MCP tool."""

    name: str
    description: str
    category: str
    input_schema: dict = field(default_factory=dict)
    response_schema_class: type | None = None  # Pydantic class for response
    is_plugin: bool = False
    plugin_id: str | None = None


@dataclass
class ResourceDefinition:
    """Definition of an MCP resource."""

    uri: str
    name: str
    description: str
    mime_type: str = "text/plain"


# ============================================================================
# Built-in Tool Definitions
# ============================================================================

BUILTIN_TOOLS: list[ToolDefinition] = [
    # Navigation tools
    ToolDefinition(
        name="navigate_to_url",
        description="Navigate to a URL in a real browser with JavaScript execution. Use this instead of simple HTTP fetch when you need to access dynamic content, execute JavaScript, or interact with the page. Supports wait conditions for page load.",
        category="Navigation",
        input_schema=schemas.NavigateToUrlParams.model_json_schema(),
        response_schema_class=schemas.NavigateResponse,
    ),
    ToolDefinition(
        name="go_back",
        description="Navigate back in browser history",
        category="Navigation",
        input_schema=EMPTY_SCHEMA,
        response_schema_class=schemas.NavigateResponse,
    ),
    ToolDefinition(
        name="reload_page",
        description="Reload the current page in the browser",
        category="Navigation",
        input_schema={
            "type": "object",
            "properties": {
                "hard": {
                    "type": "boolean",
                    "description": "Hard reload (bypass cache)",
                    "default": False,
                }
            },
        },
        response_schema_class=schemas.NavigateResponse,
    ),
    # JavaScript execution
    ToolDefinition(
        name="execute_javascript",
        description="Execute arbitrary JavaScript code in the browser context. Use this to interact with the page DOM, extract data dynamically, or manipulate page content.",
        category="Execution",
        input_schema=schemas.ExecuteJavaScriptParams.model_json_schema(),
        response_schema_class=schemas.ExecuteJavaScriptResponse,
    ),
    # Data extraction tools
    ToolDefinition(
        name="extract_links",
        description="Extract all links from a webpage currently open in the browser. Returns structured data including link text, URLs, and link types (internal/external/anchor). Better than parsing HTML as it uses the live DOM.",
        category="Extraction",
        input_schema=schemas.ExtractLinksParams.model_json_schema(),
        response_schema_class=schemas.ExtractLinksResponse,
    ),
    ToolDefinition(
        name="extract_outline",
        description="Extract the heading hierarchy (H1-H6) from a webpage currently open in the browser. Creates a structured outline of the page content. Use this when asked about page structure, headings, or outline.",
        category="Extraction",
        input_schema=EMPTY_SCHEMA,
        response_schema_class=schemas.ExtractOutlineResponse,
    ),
    ToolDefinition(
        name="extract_page_info",
        description="Extract comprehensive metadata from a webpage including title, description, Open Graph tags, meta tags, language, author, and viewport info. Use this for getting detailed page information.",
        category="Extraction",
        input_schema=EMPTY_SCHEMA,
        response_schema_class=schemas.PageInfoResponse,
    ),
    ToolDefinition(
        name="extract_article",
        description="Extract the main article content from a webpage using Mozilla Readability algorithm. Removes navigation, ads, and clutter to return clean article text. Use this for reading news articles, blog posts, or any long-form content.",
        category="Extraction",
        input_schema=EMPTY_SCHEMA,
        response_schema_class=schemas.ExtractArticleResponse,
    ),
    # Element interaction tools
    ToolDefinition(
        name="click_element",
        description="Click an element on the webpage by CSS selector or DevTools reference ($0). Use this to interact with buttons, links, or any clickable elements in the browser.",
        category="Interaction",
        input_schema=schemas.ClickElementParams.model_json_schema(),
        response_schema_class=schemas.ClickElementResponse,
    ),
    ToolDefinition(
        name="type_text",
        description="Type text into the currently focused element in the browser. Use this to fill out forms, search boxes, or any text input fields. Supports typing speed simulation and form submission.",
        category="Interaction",
        input_schema=schemas.TypeTextParams.model_json_schema(),
        response_schema_class=schemas.TypeTextResponse,
    ),
    # Inspection tools
    ToolDefinition(
        name="get_page_info",
        description="Get current page information from the browser including URL, title, viewport dimensions, and scroll position. Use this to check what page is currently open in the browser.",
        category="Inspection",
        input_schema=EMPTY_SCHEMA,
        response_schema_class=schemas.GetPageInfoResponse,
    ),
    ToolDefinition(
        name="take_screenshot",
        description="Capture a screenshot of the browser viewport, full page, or specific element. Returns base64-encoded image data. Use this to visually document or analyze webpage content.",
        category="Inspection",
        input_schema=schemas.TakeScreenshotParams.model_json_schema(),
        response_schema_class=schemas.TakeScreenshotResponse,
    ),
    # Selection and storage tools
    ToolDefinition(
        name="get_selected_text",
        description="Get the currently selected text from the browser in text, HTML, or markdown format. Use this to extract user-highlighted content from the page.",
        category="Selection",
        input_schema=schemas.GetSelectedTextParams.model_json_schema(),
        response_schema_class=schemas.GetSelectedTextResponse,
    ),
    ToolDefinition(
        name="get_cookies",
        description="Get all cookies for the current page from the browser, including httpOnly, secure, and sameSite attributes. Use this to inspect authentication state or session data.",
        category="Storage",
        input_schema=EMPTY_SCHEMA,
        response_schema_class=schemas.GetCookiesResponse,
    ),
    ToolDefinition(
        name="set_cookie",
        description="Set a cookie in the browser with optional attributes (secure, httpOnly, sameSite, expiration). Use this to modify authentication state or session data.",
        category="Storage",
        input_schema=schemas.SetCookieParams.model_json_schema(),
        response_schema_class=schemas.SetCookieResponse,
    ),
    # Accessibility tools
    ToolDefinition(
        name="check_autocomplete",
        description="Check autocomplete attributes on form fields per WCAG 2.1 SC 1.3.5 (Identify Input Purpose). Analyzes all form fields using multi-language heuristics to predict appropriate autocomplete attributes. Returns violations, warnings, and recommendations with confidence scores. Supports English, German, and Dutch field identification.",
        category="Accessibility",
        input_schema=schemas.CheckAutocompleteParams.model_json_schema(),
        response_schema_class=schemas.CheckAutocompleteResponse,
    ),
    ToolDefinition(
        name="run_axe",
        description="Run axe-core accessibility audit (WCAG 2.x). Tests the current page for accessibility violations using the industry-standard axe-core library. Returns violations with impact levels (critical/serious/moderate/minor), affected elements with CSS selectors, and remediation guidance with documentation links. Can test specific WCAG levels (2.0, 2.1, 2.2) or individual rules.",
        category="Accessibility",
        input_schema=schemas.RunAxeParams.model_json_schema(),
        response_schema_class=schemas.RunAxeResponse,
    ),
    # Network tools
    ToolDefinition(
        name="get_network_requests",
        description="Get network requests from the current page using Performance API. Returns detailed information about all resources loaded by the page including scripts, stylesheets, images, fonts, fetch/XHR requests, etc. Includes timing breakdown (DNS, TCP, SSL, TTFB, download), transfer sizes, and cache status. Can filter by resource type and sort by time or size. Note: Limited to ~150-250 entries, no status codes or headers (Performance API limitation).",
        category="Network",
        input_schema=schemas.GetNetworkRequestsParams.model_json_schema(),
        response_schema_class=schemas.GetNetworkRequestsResponse,
    ),
    ToolDefinition(
        name="get_har",
        description="Get full network data from DevTools (HAR format). REQUIRES Chrome DevTools to be open (F12). Provides complete network data including HTTP status codes (200, 404, 500), request/response headers, detailed timing, and initiator info. Use this when you need status codes or headers. Falls back to get_network_requests if DevTools is closed.",
        category="Network",
        input_schema=schemas.GetHARParams.model_json_schema(),
        response_schema_class=schemas.GetHARResponse,
    ),
    # Console tools
    ToolDefinition(
        name="get_console_logs",
        description="Get captured browser console messages (console.log, console.error, console.warn, console.info, console.debug). Messages are automatically captured when pages load. Use this for debugging JavaScript errors, monitoring application logging, checking for deprecation warnings, or verifying no errors occurred after interactions. Can filter by log level.",
        category="Console",
        input_schema=schemas.GetConsoleLogsParams.model_json_schema(),
        response_schema_class=schemas.GetConsoleLogsResponse,
    ),
    ToolDefinition(
        name="clear_console_logs",
        description="Clear the browser console message buffer. Use this to reset before testing specific interactions or to focus on new console output. New messages will continue to be captured after clearing.",
        category="Console",
        input_schema=EMPTY_SCHEMA,
        response_schema_class=schemas.ClearConsoleLogsResponse,
    ),
]

# ============================================================================
# Resource Definitions
# ============================================================================

RESOURCES: list[ResourceDefinition] = [
    ResourceDefinition(
        uri="inspekt-mcp://current-url",
        name="Current Page URL",
        description="The URL of the currently active browser tab",
    ),
    ResourceDefinition(
        uri="inspekt-mcp://page-title",
        name="Page Title",
        description="The title of the currently active browser tab",
    ),
    ResourceDefinition(
        uri="inspekt-mcp://page-metadata",
        name="Page Metadata",
        description="Extended metadata about the current page (JSON)",
        mime_type="application/json",
    ),
    ResourceDefinition(
        uri="inspekt-mcp://browser-info",
        name="Browser Information",
        description="Information about the connected browser (JSON)",
        mime_type="application/json",
    ),
    ResourceDefinition(
        uri="inspekt-mcp://connection-status",
        name="Connection Status",
        description="Bridge server connection status and health (JSON)",
        mime_type="application/json",
    ),
]

# ============================================================================
# Category Order for Display
# ============================================================================

CATEGORY_ORDER = [
    "Navigation",
    "Execution",
    "Extraction",
    "Interaction",
    "Inspection",
    "Selection",
    "Storage",
    "Accessibility",
    "Network",
    "Console",
    "Plugins",
]


# ============================================================================
# Helper Functions
# ============================================================================


def format_params_summary(schema: dict) -> str:
    """Generate 'url (required), wait_for (optional)' from JSON schema."""
    if not schema:
        return "none"

    props = schema.get("properties", {})
    required = set(schema.get("required", []))

    if not props:
        return "none"

    parts = []
    for name in props:
        req = "required" if name in required else "optional"
        parts.append(f"{name} ({req})")

    return ", ".join(parts) if parts else "none"


def format_params_detailed(schema: dict) -> list[dict[str, Any]]:
    """Generate detailed parameter info from JSON schema."""
    if not schema:
        return []

    props = schema.get("properties", {})
    required = set(schema.get("required", []))

    params = []
    for name, prop in props.items():
        param_info = {
            "name": name,
            "type": prop.get("type", "any"),
            "required": name in required,
            "description": prop.get("description", ""),
            "default": prop.get("default"),
        }

        # Handle enum/Literal types
        if "enum" in prop:
            param_info["allowed_values"] = prop["enum"]
        elif "anyOf" in prop:
            # Pydantic uses anyOf for Optional with Literal
            for option in prop["anyOf"]:
                if "enum" in option:
                    param_info["allowed_values"] = option["enum"]
                    break

        params.append(param_info)

    return params


def get_response_schema(tool: ToolDefinition) -> dict | None:
    """Get the response schema for a tool."""
    if tool.response_schema_class:
        return tool.response_schema_class.model_json_schema()
    return None


# ============================================================================
# Registry Functions
# ============================================================================


def get_builtin_tools() -> list[ToolDefinition]:
    """Get all built-in tool definitions."""
    return BUILTIN_TOOLS.copy()


def get_plugin_tools() -> list[ToolDefinition]:
    """Get tool definitions for MCP-enabled plugins."""
    try:
        from inspekt.services.plugin_service import get_plugin_service

        plugin_service = get_plugin_service()
        mcp_plugins = plugin_service.get_mcp_exposed()

        tools = []
        for plugin in mcp_plugins:
            plugin_id = plugin["id"]
            plugin_name = plugin["name"]

            # Run tool
            run_tool = ToolDefinition(
                name=f"plugin_{plugin_id}",
                description=plugin.get("description") or f"Run the '{plugin_name}' plugin",
                category="Plugins",
                input_schema=schemas.PluginExecuteParams.model_json_schema(),
                response_schema_class=schemas.PluginExecuteResponse,
                is_plugin=True,
                plugin_id=plugin_id,
            )
            tools.append(run_tool)

            # Unload tool (if supported)
            unload_mode = plugin.get("unload_mode", "none")
            if unload_mode != "none":
                if unload_mode == "toggle":
                    unload_desc = (
                        f"Unload '{plugin_name}' (toggle - runs the plugin again to reverse)"
                    )
                else:
                    unload_desc = f"Unload '{plugin_name}' (custom unload code)"

                unload_tool = ToolDefinition(
                    name=f"unload_plugin_{plugin_id}",
                    description=unload_desc,
                    category="Plugins",
                    input_schema=schemas.PluginExecuteParams.model_json_schema(),
                    response_schema_class=schemas.PluginExecuteResponse,
                    is_plugin=True,
                    plugin_id=plugin_id,
                )
                tools.append(unload_tool)

        return tools
    except Exception:
        return []


def get_all_tools() -> list[ToolDefinition]:
    """Get all tools (built-in + plugins)."""
    return get_builtin_tools() + get_plugin_tools()


def get_tool(name: str) -> ToolDefinition | None:
    """Get a specific tool by name."""
    for tool in get_all_tools():
        if tool.name == name:
            return tool
    return None


def get_tools_by_category() -> dict[str, list[ToolDefinition]]:
    """Get tools grouped by category, in display order."""
    tools = get_all_tools()
    by_category: dict[str, list[ToolDefinition]] = {}

    for tool in tools:
        cat = tool.category
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(tool)

    # Return in order
    ordered: dict[str, list[ToolDefinition]] = {}
    for cat in CATEGORY_ORDER:
        if cat in by_category:
            ordered[cat] = by_category[cat]

    # Add any remaining categories not in CATEGORY_ORDER
    for cat in by_category:
        if cat not in ordered:
            ordered[cat] = by_category[cat]

    return ordered


def get_resources() -> list[ResourceDefinition]:
    """Get all resource definitions."""
    return RESOURCES.copy()


def get_resource(uri: str) -> ResourceDefinition | None:
    """Get a specific resource by URI."""
    for resource in RESOURCES:
        if resource.uri == uri:
            return resource
    return None
