"""
MCP Tool and Resource Schemas

Pydantic models defining the input parameters and output structures
for all MCP tools and resources.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Navigation Tool Schemas
# ============================================================================


class NavigateToUrlParams(BaseModel):
    """Parameters for navigate_to_url tool."""

    url: str = Field(..., description="The URL to navigate to (must start with http:// or https://)")
    wait_for: Optional[str] = Field(
        default=None,
        description="Wait condition: 'load' (DOMContentLoaded), 'networkidle' (no network activity)",
    )
    timeout: Optional[int] = Field(
        default=30,
        description="Navigation timeout in seconds (default: 30)",
    )


class NavigateResponse(BaseModel):
    """Response from navigation tools."""

    success: bool = Field(..., description="Whether the navigation succeeded")
    url: str = Field(..., description="The final URL after navigation (may differ due to redirects)")
    title: str = Field(..., description="Page title")
    message: Optional[str] = Field(default=None, description="Success or error message")


# ============================================================================
# JavaScript Execution Schemas
# ============================================================================


class ExecuteJavaScriptParams(BaseModel):
    """Parameters for execute_javascript tool."""

    code: str = Field(..., description="JavaScript code to execute in the browser context")
    timeout: Optional[int] = Field(
        default=30, description="Execution timeout in seconds (default: 30)"
    )


class ExecuteJavaScriptResponse(BaseModel):
    """Response from execute_javascript tool."""

    success: bool = Field(..., description="Whether execution succeeded")
    result: Any = Field(..., description="The return value from the JavaScript code")
    console_output: Optional[list[str]] = Field(
        default=None, description="Console messages during execution"
    )
    error: Optional[str] = Field(default=None, description="Error message if execution failed")


# ============================================================================
# Data Extraction Schemas
# ============================================================================


class ExtractLinksParams(BaseModel):
    """Parameters for extract_links tool."""

    filter_type: Optional[Literal["all", "internal", "external"]] = Field(
        default="all", description="Filter links by type: all, internal, or external"
    )
    include_anchors: Optional[bool] = Field(
        default=True, description="Include same-page anchor links (#section)"
    )


class LinkInfo(BaseModel):
    """Information about a single link."""

    url: str = Field(..., description="The link URL (absolute)")
    text: str = Field(..., description="Link text content")
    title: Optional[str] = Field(default=None, description="Link title attribute")
    type: Literal["internal", "external", "anchor"] = Field(
        ..., description="Link type classification"
    )


class ExtractLinksResponse(BaseModel):
    """Response from extract_links tool."""

    success: bool = Field(..., description="Whether extraction succeeded")
    links: list[LinkInfo] = Field(..., description="List of extracted links")
    count: int = Field(..., description="Total number of links found")


class OutlineItem(BaseModel):
    """A heading in the page outline."""

    level: int = Field(..., description="Heading level (1-6)")
    text: str = Field(..., description="Heading text content")
    id: Optional[str] = Field(default=None, description="Element ID if present")


class ExtractOutlineResponse(BaseModel):
    """Response from extract_outline tool."""

    success: bool = Field(..., description="Whether extraction succeeded")
    outline: list[OutlineItem] = Field(..., description="Page heading hierarchy")
    count: int = Field(..., description="Total number of headings")


class PageInfoResponse(BaseModel):
    """Response from extract_page_info tool."""

    success: bool = Field(..., description="Whether extraction succeeded")
    url: str = Field(..., description="Page URL")
    title: str = Field(..., description="Page title")
    description: Optional[str] = Field(default=None, description="Meta description")
    language: Optional[str] = Field(default=None, description="Page language (ISO 639-1 code)")
    author: Optional[str] = Field(default=None, description="Author from meta tags")
    keywords: Optional[list[str]] = Field(default=None, description="Meta keywords")
    og_title: Optional[str] = Field(default=None, description="Open Graph title")
    og_description: Optional[str] = Field(default=None, description="Open Graph description")
    og_image: Optional[str] = Field(default=None, description="Open Graph image URL")
    canonical_url: Optional[str] = Field(default=None, description="Canonical URL")
    viewport_width: int = Field(..., description="Viewport width in pixels")
    viewport_height: int = Field(..., description="Viewport height in pixels")


class ExtractArticleResponse(BaseModel):
    """Response from extract_article tool."""

    success: bool = Field(..., description="Whether extraction succeeded")
    title: Optional[str] = Field(default=None, description="Article title")
    byline: Optional[str] = Field(default=None, description="Article author/byline")
    content: str = Field(..., description="Extracted article content (plain text)")
    excerpt: Optional[str] = Field(default=None, description="Article excerpt/summary")
    length: int = Field(..., description="Content length in characters")


# ============================================================================
# Element Interaction Schemas
# ============================================================================


class ClickElementParams(BaseModel):
    """Parameters for click_element tool."""

    selector: str = Field(
        ..., description="CSS selector or '$0' for DevTools-inspected element"
    )
    click_type: Optional[Literal["single", "double", "right"]] = Field(
        default="single", description="Type of click: single, double, or right-click"
    )


class ClickElementResponse(BaseModel):
    """Response from click_element tool."""

    success: bool = Field(..., description="Whether click succeeded")
    element_found: bool = Field(..., description="Whether the target element was found")
    element_text: Optional[str] = Field(default=None, description="Text content of clicked element")
    message: Optional[str] = Field(default=None, description="Success or error message")


class TypeTextParams(BaseModel):
    """Parameters for type_text tool."""

    text: str = Field(..., description="Text to type into the focused element")
    typing_speed: Optional[Literal["instant", "fast", "normal", "slow"]] = Field(
        default="normal", description="Typing speed simulation"
    )
    submit: Optional[bool] = Field(
        default=False, description="Press Enter after typing (submit form)"
    )


class TypeTextResponse(BaseModel):
    """Response from type_text tool."""

    success: bool = Field(..., description="Whether typing succeeded")
    characters_typed: int = Field(..., description="Number of characters typed")
    message: Optional[str] = Field(default=None, description="Success or error message")


# ============================================================================
# Inspection Schemas
# ============================================================================


class GetPageInfoResponse(BaseModel):
    """Response from get_page_info tool (lightweight version)."""

    success: bool = Field(..., description="Whether operation succeeded")
    url: str = Field(..., description="Current page URL")
    title: str = Field(..., description="Page title")
    viewport_width: int = Field(..., description="Viewport width in pixels")
    viewport_height: int = Field(..., description="Viewport height in pixels")
    scroll_x: int = Field(..., description="Horizontal scroll position")
    scroll_y: int = Field(..., description="Vertical scroll position")


class TakeScreenshotParams(BaseModel):
    """Parameters for take_screenshot tool."""

    target: Optional[Literal["viewport", "page", "element"]] = Field(
        default="viewport", description="Screenshot target: viewport (visible area), page (full page), or element"
    )
    selector: Optional[str] = Field(
        default=None, description="CSS selector for element screenshot (required if target='element')"
    )
    format: Optional[Literal["png", "jpeg"]] = Field(
        default="png", description="Image format"
    )
    quality: Optional[int] = Field(
        default=90, description="JPEG quality (1-100, ignored for PNG)"
    )
    output_path: Optional[str] = Field(
        default=None,
        description="Path to save screenshot file. If not provided, saves to a temp file in /tmp/inspekt/screenshots/.",
    )
    timeout: Optional[int] = Field(
        default=30,
        description="Maximum time in seconds to wait for screenshot (default: 30, max: 30)",
        ge=1,
        le=30,
    )


class TakeScreenshotResponse(BaseModel):
    """Response from take_screenshot tool."""

    success: bool = Field(..., description="Whether screenshot succeeded")
    data: Optional[str] = Field(
        default=None,
        description="Deprecated - always None. Screenshots are saved to files.",
    )
    path: Optional[str] = Field(
        default=None,
        description="Absolute path to the saved screenshot file",
    )
    format: str = Field(..., description="Image format (png or jpeg)")
    width: int = Field(..., description="Image width in pixels")
    height: int = Field(..., description="Image height in pixels")
    size: Optional[int] = Field(
        default=None,
        description="File size in bytes",
    )
    message: Optional[str] = Field(default=None, description="Success or error message")


# ============================================================================
# Selection and Storage Schemas
# ============================================================================


class GetSelectedTextParams(BaseModel):
    """Parameters for get_selected_text tool."""

    format: Optional[Literal["text", "html", "markdown"]] = Field(
        default="text", description="Output format for selected content"
    )


class GetSelectedTextResponse(BaseModel):
    """Response from get_selected_text tool."""

    success: bool = Field(..., description="Whether operation succeeded")
    content: str = Field(..., description="Selected text in requested format")
    format: str = Field(..., description="Format of returned content")
    length: int = Field(..., description="Content length in characters")


class CookieInfo(BaseModel):
    """Information about a cookie."""

    name: str = Field(..., description="Cookie name")
    value: str = Field(..., description="Cookie value")
    domain: str = Field(..., description="Cookie domain")
    path: str = Field(..., description="Cookie path")
    secure: bool = Field(..., description="Secure flag")
    httpOnly: bool = Field(..., description="HttpOnly flag")
    sameSite: Optional[str] = Field(default=None, description="SameSite attribute")
    expires: Optional[str] = Field(default=None, description="Expiration date (ISO 8601)")
    session: bool = Field(..., description="Whether it's a session cookie")
    size: int = Field(..., description="Cookie size in bytes")
    party: Optional[str] = Field(default=None, description="First-party or third-party")


class GetCookiesResponse(BaseModel):
    """Response from get_cookies tool."""

    success: bool = Field(..., description="Whether operation succeeded")
    cookies: list[CookieInfo] = Field(..., description="List of cookies for current page")
    count: int = Field(..., description="Total number of cookies")


class SetCookieParams(BaseModel):
    """Parameters for set_cookie tool."""

    name: str = Field(..., description="Cookie name")
    value: str = Field(..., description="Cookie value")
    domain: Optional[str] = Field(default=None, description="Cookie domain (defaults to current domain)")
    path: Optional[str] = Field(default="/", description="Cookie path")
    secure: Optional[bool] = Field(default=False, description="Secure flag")
    httpOnly: Optional[bool] = Field(default=False, description="HttpOnly flag")
    sameSite: Optional[Literal["Strict", "Lax", "None"]] = Field(
        default="Lax", description="SameSite attribute"
    )
    expires: Optional[str] = Field(
        default=None, description="Expiration date (ISO 8601 format or seconds from now)"
    )


class SetCookieResponse(BaseModel):
    """Response from set_cookie tool."""

    success: bool = Field(..., description="Whether cookie was set successfully")
    message: Optional[str] = Field(default=None, description="Success or error message")


# ============================================================================
# Accessibility Tool Schemas
# ============================================================================


class CheckAutocompleteParams(BaseModel):
    """Parameters for check_autocomplete tool."""

    confidence_threshold: Optional[float] = Field(
        default=0.5,
        description="Minimum confidence (0-1) to consider autocomplete required per WCAG 2.1 SC 1.3.5 (default: 0.5)",
        ge=0.0,
        le=1.0,
    )
    include_hidden: Optional[bool] = Field(
        default=False, description="Include hidden input fields in analysis (default: False)"
    )
    include_disabled: Optional[bool] = Field(
        default=False, description="Include disabled input fields in analysis (default: False)"
    )


class CheckAutocompleteResponse(BaseModel):
    """Response from check_autocomplete tool."""

    success: bool = Field(..., description="Whether the check completed successfully")
    summary: Optional[dict[str, Any]] = Field(
        default=None,
        description="Summary statistics: total fields, violations, warnings, etc.",
    )
    fields: Optional[list[dict[str, Any]]] = Field(
        default=None, description="Detailed analysis for each field with predictions and status"
    )
    message: Optional[str] = Field(default=None, description="Success or error message")


# ============================================================================
# Network Tool Schemas
# ============================================================================


class GetNetworkRequestsParams(BaseModel):
    """Parameters for get_network_requests tool."""

    resource_type: Optional[str] = Field(
        default=None,
        description="Filter by resource type: script, stylesheet, fetch, xhr, image, font, document, svg, video, audio",
    )
    external_only: Optional[bool] = Field(
        default=False, description="Only return requests to external domains"
    )
    sort_by: Optional[Literal["start", "time", "size", "name", "type"]] = Field(
        default="start", description="Sort field: start (chronological), time (slowest first), size (largest first), name, type"
    )
    limit: Optional[int] = Field(
        default=None, description="Maximum number of entries to return"
    )


class NetworkTimingInfo(BaseModel):
    """Timing information for a network request."""

    total: int = Field(..., description="Total request duration in milliseconds")
    dns: int = Field(..., description="DNS lookup time in milliseconds")
    tcp: int = Field(..., description="TCP connection time in milliseconds")
    ssl: int = Field(..., description="SSL handshake time in milliseconds")
    ttfb: int = Field(..., description="Time to first byte in milliseconds")
    download: int = Field(..., description="Download time in milliseconds")


class NetworkEntry(BaseModel):
    """Information about a single network request."""

    index: int = Field(..., description="Request index (order loaded)")
    url: str = Field(..., description="Full request URL")
    name: str = Field(..., description="Resource filename")
    domain: str = Field(..., description="Domain the resource was loaded from")
    path: str = Field(..., description="URL path")
    type: str = Field(..., description="Resource type (script, stylesheet, fetch, image, font, etc.)")
    initiatorType: str = Field(..., description="Original initiator type from Performance API")
    external: bool = Field(..., description="Whether the resource is from an external domain")
    transferSize: int = Field(..., description="Transfer size in bytes")
    encodedSize: int = Field(..., description="Encoded body size in bytes")
    decodedSize: int = Field(..., description="Decoded body size in bytes")
    timing: NetworkTimingInfo = Field(..., description="Timing breakdown")
    startTime: int = Field(..., description="Start time relative to navigation (ms)")
    protocol: str = Field(..., description="Protocol used (h1, h2, h3, etc.)")
    cached: bool = Field(..., description="Whether the resource was served from cache")


class NetworkSummary(BaseModel):
    """Summary statistics for network requests."""

    totalRequests: int = Field(..., description="Total number of requests")
    totalTransferSize: int = Field(..., description="Total transfer size in bytes")
    totalDecodedSize: int = Field(..., description="Total decoded size in bytes")
    byType: dict[str, int] = Field(..., description="Request count by resource type")
    byDomain: dict[str, int] = Field(..., description="Request count by domain")
    averageDuration: int = Field(..., description="Average request duration in milliseconds")
    slowestRequest: Optional[dict[str, Any]] = Field(default=None, description="Slowest request info")
    largestRequest: Optional[dict[str, Any]] = Field(default=None, description="Largest request info")
    cachedRequests: int = Field(..., description="Number of cached requests")
    externalRequests: int = Field(..., description="Number of external requests")


class GetNetworkRequestsResponse(BaseModel):
    """Response from get_network_requests tool."""

    success: bool = Field(..., description="Whether the operation succeeded")
    url: str = Field(..., description="Page URL")
    timestamp: str = Field(..., description="Timestamp of the capture (ISO 8601)")
    entries: list[dict[str, Any]] = Field(..., description="List of network request entries")
    summary: dict[str, Any] = Field(..., description="Summary statistics")
    message: Optional[str] = Field(default=None, description="Success or error message")


class GetHARParams(BaseModel):
    """Parameters for get_har tool."""

    resource_type: Optional[str] = Field(
        default=None,
        description="Filter by resource type: script, stylesheet, fetch, image, font, document",
    )
    errors_only: Optional[bool] = Field(
        default=False, description="Only return failed requests (4xx/5xx status codes)"
    )
    sort_by: Optional[Literal["start", "time", "size", "name", "type", "status"]] = Field(
        default="start", description="Sort field"
    )
    limit: Optional[int] = Field(
        default=None, description="Maximum number of entries to return"
    )


class GetHARResponse(BaseModel):
    """Response from get_har tool."""

    success: bool = Field(..., description="Whether the operation succeeded")
    source: str = Field(default="devtools", description="Data source (devtools)")
    url: str = Field(..., description="Page URL")
    timestamp: str = Field(..., description="Timestamp of the capture (ISO 8601)")
    entries: list[dict[str, Any]] = Field(..., description="List of HAR entries with status codes and headers")
    summary: dict[str, Any] = Field(..., description="Summary statistics including status breakdown")
    message: Optional[str] = Field(default=None, description="Success or error message")


# ============================================================================
# Console Tool Schemas
# ============================================================================


class GetConsoleLogsParams(BaseModel):
    """Parameters for get_console_logs tool."""

    level: Optional[Literal["all", "error", "warn", "log", "info", "debug"]] = Field(
        default="all",
        description="Filter by log level: all (default), error, warn, log, info, or debug",
    )
    limit: Optional[int] = Field(
        default=100, description="Maximum number of messages to return (default: 100)"
    )


class ConsoleEntry(BaseModel):
    """A single console log entry."""

    level: str = Field(..., description="Log level: error, warn, log, info, or debug")
    timestamp: str = Field(..., description="Timestamp when the message was logged (ISO 8601)")
    message: str = Field(..., description="The logged message content")


class GetConsoleLogsResponse(BaseModel):
    """Response from get_console_logs tool."""

    success: bool = Field(..., description="Whether the operation succeeded")
    entries: list[ConsoleEntry] = Field(default=[], description="List of console log entries")
    count: int = Field(default=0, description="Number of entries returned")
    hooked: bool = Field(default=False, description="Whether console hooks are active on the page")
    message: Optional[str] = Field(default=None, description="Success or error message")


class ClearConsoleLogsResponse(BaseModel):
    """Response from clear_console_logs tool."""

    success: bool = Field(..., description="Whether the operation succeeded")
    message: Optional[str] = Field(default=None, description="Success or error message")


# ============================================================================
# Axe-core Accessibility Schemas
# ============================================================================


class RunAxeParams(BaseModel):
    """Parameters for run_axe accessibility tool."""

    level: Optional[Literal["2a", "2aa", "2aaa", "21a", "21aa", "22aa"]] = Field(
        default="21aa",
        description="WCAG conformance level: 2a, 2aa (WCAG 2.0), 21a, 21aa (WCAG 2.1), 22aa (WCAG 2.2)"
    )
    rule: Optional[str] = Field(
        default=None,
        description="Check specific rule by ID (e.g., 'color-contrast', 'link-name'). Mutually exclusive with level."
    )
    selector: Optional[str] = Field(
        default=None,
        description="CSS selector to scope tests to specific element(s)"
    )
    exclude: Optional[list[str]] = Field(
        default=None,
        description="CSS selectors to exclude from testing"
    )
    include_passes: bool = Field(
        default=False,
        description="Include passing checks in results"
    )
    include_incomplete: bool = Field(
        default=False,
        description="Include incomplete checks requiring manual review"
    )


class AxeNode(BaseModel):
    """Information about a single failing element."""

    target: list[str] = Field(..., description="CSS selector path to element")
    html: str = Field(..., description="HTML snippet of the element")
    impact: str = Field(..., description="Impact level: critical, serious, moderate, minor")
    failure_summary: Optional[str] = Field(default=None, description="Description of the failure")


class AxeViolation(BaseModel):
    """A single accessibility violation."""

    id: str = Field(..., description="Rule ID (e.g., 'color-contrast')")
    impact: str = Field(..., description="Impact level: critical, serious, moderate, minor")
    description: str = Field(..., description="What the rule checks")
    help: str = Field(..., description="Short description of how to fix")
    help_url: str = Field(..., description="URL to detailed documentation")
    nodes: list[AxeNode] = Field(..., description="List of failing elements")
    node_count: int = Field(..., description="Number of failing elements")


class AxeSummary(BaseModel):
    """Summary statistics from axe audit."""

    violation_count: int = Field(..., description="Total violations")
    pass_count: int = Field(..., description="Total passes")
    incomplete_count: int = Field(..., description="Checks needing manual review")
    critical_count: int = Field(default=0, description="Critical impact violations")
    serious_count: int = Field(default=0, description="Serious impact violations")
    moderate_count: int = Field(default=0, description="Moderate impact violations")
    minor_count: int = Field(default=0, description="Minor impact violations")


class RunAxeResponse(BaseModel):
    """Response from run_axe accessibility tool."""

    success: bool = Field(..., description="Whether the audit completed successfully")
    url: str = Field(default="", description="Page URL that was tested")
    violations: list[AxeViolation] = Field(default=[], description="List of accessibility violations")
    passes: list[dict[str, Any]] = Field(default=[], description="Passing checks (if include_passes=True)")
    incomplete: list[dict[str, Any]] = Field(default=[], description="Incomplete checks (if include_incomplete=True)")
    summary: Optional[AxeSummary] = Field(default=None, description="Summary statistics")
    axe_version: Optional[str] = Field(default=None, description="Axe-core version used")
    message: Optional[str] = Field(default=None, description="Success or error message")


# ============================================================================
# Plugin Execution Schemas
# ============================================================================


class PluginExecuteParams(BaseModel):
    """Parameters for plugin execution tools."""

    capture_console: bool = Field(
        default=True,
        description="Capture console.log/error/warn output during execution"
    )


class ConsoleEntry(BaseModel):
    """A captured console message."""

    level: str = Field(..., description="Log level: log, error, warn, info, debug")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    message: str = Field(..., description="The logged message")


class PluginExecuteResponse(BaseModel):
    """Response from plugin execution."""

    success: bool = Field(..., description="Whether execution succeeded")
    plugin_name: str = Field(..., description="Name of the executed plugin")
    plugin_id: str = Field(..., description="ID of the executed plugin")
    result: Any = Field(default=None, description="Return value from the plugin (if returns_data=True)")
    console_output: list[ConsoleEntry] = Field(
        default=[],
        description="Captured console messages during execution"
    )
    execution_time_ms: int = Field(..., description="Execution time in milliseconds")
    message: Optional[str] = Field(default=None, description="Success or error message")


# ============================================================================
# Display Schemas (Zoom & Viewport)
# ============================================================================


class SetZoomParams(BaseModel):
    """Parameters for set_zoom tool."""

    level: Optional[int] = Field(
        default=None,
        description="Zoom level as percentage (25–500). E.g., 150 for 150%. Mutually exclusive with action.",
    )
    action: Optional[Literal["in", "out", "reset"]] = Field(
        default=None,
        description="Zoom action: 'in' (next step), 'out' (previous step), 'reset' (100%). Mutually exclusive with level.",
    )


class ZoomResponse(BaseModel):
    """Response from zoom tools."""

    success: bool = Field(..., description="Whether the operation succeeded")
    zoom: float = Field(..., description="Current zoom factor (e.g., 1.5 for 150%)")
    percentage: int = Field(..., description="Current zoom as percentage (e.g., 150)")
    wcag_note: Optional[str] = Field(default=None, description="WCAG guidance for the zoom level")
    previous_zoom: Optional[float] = Field(default=None, description="Previous zoom factor (set operations only)")
    message: Optional[str] = Field(default=None, description="Success or error message")


class SetViewportParams(BaseModel):
    """Parameters for set_viewport tool."""

    width: int = Field(..., description="Viewport width in CSS pixels (320–3840)", ge=320, le=3840)
    height: Optional[int] = Field(
        default=None,
        description="Viewport height in CSS pixels (240–2160). If omitted, only width changes.",
        ge=240,
        le=2160,
    )
    auto_height: bool = Field(
        default=False,
        description="Automatically set height to fill available display (VM only). Overrides height.",
    )


class ViewportResponse(BaseModel):
    """Response from viewport tools."""

    success: bool = Field(..., description="Whether the operation succeeded")
    width: int = Field(..., description="Current viewport width in pixels")
    height: int = Field(..., description="Current viewport height in pixels")
    previous_width: Optional[int] = Field(default=None, description="Previous width (set operations only)")
    previous_height: Optional[int] = Field(default=None, description="Previous height (set operations only)")
    message: Optional[str] = Field(default=None, description="Success or error message")
