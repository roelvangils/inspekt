"""Domain models for Zen Bridge protocol and configuration.

This module defines Pydantic models for:
- WebSocket message types (execute, result, reinit_control, etc.)
- Configuration schemas (control config, AI config)
- Protocol validation

All models use Pydantic v2 for automatic validation and serialization.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# WebSocket Message Models
# ============================================================================


class ExecuteRequest(BaseModel):
    """Request to execute JavaScript code in the browser.

    Sent from server to browser via WebSocket.
    """

    type: Literal["execute"] = "execute"
    request_id: str = Field(..., description="UUID v4 identifying this request")
    code: str = Field(..., description="JavaScript code to evaluate")

    model_config = {"extra": "forbid"}


class ExecuteResult(BaseModel):
    """Result of JavaScript code execution.

    Sent from browser to server via WebSocket.
    """

    type: Literal["result"] = "result"
    request_id: str = Field(..., description="UUID matching the execute request")
    ok: bool = Field(..., description="True if execution succeeded")
    result: Optional[Any] = Field(None, description="Return value from JavaScript")
    error: Optional[str] = Field(None, description="Error message if ok=False")
    url: Optional[str] = Field(None, description="Current page URL")
    title: Optional[str] = Field(None, description="Current page title")

    model_config = {"extra": "allow"}  # Allow additional fields from browser


class ReinitControlRequest(BaseModel):
    """Request to reinitialize control mode after page reload.

    Sent from browser to server via WebSocket.
    """

    type: Literal["reinit_control"] = "reinit_control"
    config: dict[str, Any] = Field(
        default_factory=dict, description="Control mode configuration"
    )

    model_config = {"extra": "forbid"}


class RefocusNotification(BaseModel):
    """Notification of refocus operation result.

    Sent from browser to server via WebSocket.
    """

    type: Literal["refocus_notification"] = "refocus_notification"
    success: bool = Field(..., description="Whether refocus succeeded")
    message: str = Field(..., description="Human-readable status message")

    model_config = {"extra": "forbid"}


class PingMessage(BaseModel):
    """Keepalive ping message.

    Sent from browser to server via WebSocket.
    """

    type: Literal["ping"] = "ping"

    model_config = {"extra": "forbid"}


class PongMessage(BaseModel):
    """Keepalive pong response.

    Sent from server to browser via WebSocket.
    """

    type: Literal["pong"] = "pong"

    model_config = {"extra": "forbid"}


class BrowserInfoMessage(BaseModel):
    """Browser information message.

    Sent from browser to server when connection is established.
    """

    type: Literal["browser_info"] = "browser_info"
    userAgent: str = Field(..., description="Browser user agent string")
    browserName: str = Field(..., description="Browser name")
    url: str = Field(..., description="Current page URL")
    title: str = Field(..., description="Page title")
    extensionVersion: Optional[str] = Field(None, description="Extension version")

    model_config = {"extra": "forbid"}


class DomainManagementResponse(BaseModel):
    """Domain management response message.

    Sent from browser to server in response to domain management commands.
    """

    type: Literal["response"] = "response"
    requestId: str = Field(..., description="Request ID matching the original command")
    response: dict[str, Any] = Field(..., description="Response data from background script")

    model_config = {"extra": "forbid"}


# Union type for all incoming WebSocket messages (browser → server)
IncomingMessage = (
    ExecuteResult
    | ReinitControlRequest
    | RefocusNotification
    | PingMessage
    | BrowserInfoMessage
    | DomainManagementResponse
)

# Union type for all outgoing WebSocket messages (server → browser)
OutgoingMessage = ExecuteRequest | PongMessage


# ============================================================================
# HTTP API Models
# ============================================================================


class RunRequest(BaseModel):
    """HTTP POST /run request body."""

    code: str = Field(..., min_length=1, description="JavaScript code to execute")

    model_config = {"extra": "forbid"}


class RunResponse(BaseModel):
    """HTTP POST /run response."""

    ok: bool
    request_id: Optional[str] = None
    error: Optional[str] = None

    model_config = {"extra": "forbid"}


class ResultResponse(BaseModel):
    """HTTP GET /result response."""

    ok: bool
    status: Optional[Literal["pending"]] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None

    model_config = {"extra": "allow"}


class BrowserConnection(BaseModel):
    """Information about a connected browser."""

    browser_name: str = Field(..., description="Browser name (Chrome, Firefox, etc.)")
    browser_version: str = Field(default="", description="Browser version number")
    extension_version: Optional[str] = Field(None, description="Extension version")
    url: str = Field(..., description="Current page URL")
    title: str = Field(..., description="Current page title")
    user_agent: str = Field(..., description="Browser user agent string")
    is_most_recent: bool = Field(..., description="Whether this is the most recently active connection")
    connected_duration: float = Field(..., description="How long the connection has been active (seconds)")

    model_config = {"extra": "allow"}


class HealthResponse(BaseModel):
    """HTTP GET /health response."""

    ok: bool
    timestamp: float
    server_version: str = Field(..., description="Inspekt server version")
    uptime_seconds: float = Field(..., description="Server uptime in seconds")
    host: str = Field(..., description="Server host address")
    port: int = Field(..., description="HTTP API port")
    websocket_port: int = Field(..., description="WebSocket port")
    connected_browsers: int
    browsers: list[BrowserConnection] = Field(default_factory=list, description="List of connected browsers")
    pending: int
    completed: int
    total_processed: int = Field(..., description="Total requests processed since startup")
    total_succeeded: int = Field(..., description="Total successful requests since startup")
    total_failed: int = Field(..., description="Total failed requests since startup")
    last_activity: float = Field(..., description="Timestamp of last activity")
    cached_scripts: list[str] = Field(default_factory=list, description="List of cached script names")

    model_config = {"extra": "forbid"}


class Notification(BaseModel):
    """Notification item."""

    type: str
    success: bool
    message: str
    timestamp: float

    model_config = {"extra": "allow"}


class NotificationsResponse(BaseModel):
    """HTTP GET /notifications response."""

    ok: bool
    notifications: list[Notification]

    model_config = {"extra": "forbid"}


class ReinitControlHTTPRequest(BaseModel):
    """HTTP POST /reinit-control request body."""

    config: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


# ============================================================================
# Configuration Models
# ============================================================================


class ControlConfig(BaseModel):
    """Control mode configuration.

    Defines all settings for virtual focus keyboard navigation mode.
    """

    auto_refocus: Literal["always", "only-spa", "never"] = Field(
        default="only-spa",
        alias="auto-refocus",
        description="When to automatically refocus after page changes",
    )

    focus_outline: Literal["custom", "original", "none"] = Field(
        default="custom",
        alias="focus-outline",
        description="Focus outline style",
    )

    speak_name: bool = Field(
        default=False,
        alias="speak-name",
        description="Speak element name via TTS",
    )

    speak_all: bool = Field(
        default=True,
        alias="speak-all",
        description="Speak all terminal output via TTS",
    )

    announce_role: bool = Field(
        default=False,
        alias="announce-role",
        description="Announce element role (button, link, etc.)",
    )

    announce_on_page_load: bool = Field(
        default=False,
        alias="announce-on-page-load",
        description="Announce page title on load",
    )

    navigation_wrap: bool = Field(
        default=True,
        alias="navigation-wrap",
        description="Wrap navigation at end of page",
    )

    scroll_on_focus: bool = Field(
        default=True,
        alias="scroll-on-focus",
        description="Scroll element into view on focus",
    )

    click_delay: int = Field(
        default=0,
        ge=0,
        alias="click-delay",
        description="Delay before click in milliseconds",
    )

    focus_color: str = Field(
        default="#0066ff",
        alias="focus-color",
        description="CSS color for focus outline",
    )

    focus_size: int = Field(
        default=3,
        ge=1,
        alias="focus-size",
        description="Focus outline size in pixels",
    )

    focus_animation: bool = Field(
        default=True,
        alias="focus-animation",
        description="Enable focus animation",
    )

    focus_glow: bool = Field(
        default=True,
        alias="focus-glow",
        description="Enable focus glow effect",
    )

    sound_on_focus: Literal["none", "beep", "click", "subtle"] = Field(
        default="none",
        alias="sound-on-focus",
        description="Sound to play on focus change",
    )

    selector_strategy: Literal["id-first", "aria-first", "css-first"] = Field(
        default="id-first",
        alias="selector-strategy",
        description="Strategy for element selection",
    )

    refocus_timeout: int = Field(
        default=2000,
        ge=100,
        alias="refocus-timeout",
        description="Timeout for refocus operations in milliseconds",
    )

    verbose: bool = Field(
        default=True,
        description="Show verbose terminal announcements",
    )

    verbose_logging: bool = Field(
        default=False,
        alias="verbose-logging",
        description="Enable verbose browser console logging",
    )

    model_config = {"extra": "forbid", "populate_by_name": True}

    @field_validator("focus_color")
    @classmethod
    def validate_focus_color(cls, v: str) -> str:
        """Validate focus color is a valid CSS color string."""
        # Basic validation - just ensure it's a non-empty string
        # Full CSS color validation would be complex, so we keep it simple
        if not v or not isinstance(v, str):
            raise ValueError("focus_color must be a non-empty string")
        return v


class ZenConfig(BaseModel):
    """Complete Zen Bridge configuration.

    This is the top-level config loaded from config.json.
    """

    ai_language: str = Field(
        default="auto",
        alias="ai-language",
        description="Language for AI operations (auto, en, nl, fr, etc.)",
    )

    control: ControlConfig = Field(
        default_factory=ControlConfig,
        description="Control mode configuration",
    )

    model_config = {"extra": "allow", "populate_by_name": True}

    @field_validator("ai_language")
    @classmethod
    def validate_ai_language(cls, v: str) -> str:
        """Validate AI language code."""
        if not v or not isinstance(v, str):
            raise ValueError("ai_language must be a non-empty string")
        return v


# ============================================================================
# Helper Functions
# ============================================================================


def parse_incoming_message(data: dict[str, Any]) -> IncomingMessage:
    """Parse incoming WebSocket message based on type field.

    Args:
        data: Raw message dictionary from WebSocket

    Returns:
        Validated Pydantic model instance

    Raises:
        ValueError: If message type is unknown or validation fails
    """
    msg_type = data.get("type")

    if msg_type == "result":
        return ExecuteResult(**data)
    elif msg_type == "reinit_control":
        return ReinitControlRequest(**data)
    elif msg_type == "refocus_notification":
        return RefocusNotification(**data)
    elif msg_type == "ping":
        return PingMessage(**data)
    elif msg_type == "browser_info":
        return BrowserInfoMessage(**data)
    elif msg_type == "response":
        return DomainManagementResponse(**data)
    else:
        raise ValueError(f"Unknown message type: {msg_type}")


def create_execute_request(request_id: str, code: str) -> ExecuteRequest:
    """Create an execute request message.

    Args:
        request_id: UUID for this request
        code: JavaScript code to execute

    Returns:
        Validated ExecuteRequest model
    """
    return ExecuteRequest(request_id=request_id, code=code)


def create_pong_message() -> PongMessage:
    """Create a pong response message.

    Returns:
        PongMessage instance
    """
    return PongMessage()
