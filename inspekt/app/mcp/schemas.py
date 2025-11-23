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


class TakeScreenshotResponse(BaseModel):
    """Response from take_screenshot tool."""

    success: bool = Field(..., description="Whether screenshot succeeded")
    data: Optional[str] = Field(default=None, description="Base64-encoded image data")
    format: str = Field(..., description="Image format (png or jpeg)")
    width: int = Field(..., description="Image width in pixels")
    height: int = Field(..., description="Image height in pixels")
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
