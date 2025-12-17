"""
Shared Pydantic schemas for all Inspekt commands.

These schemas are used by CLI, API, and MCP interfaces.
"""

from inspekt.core.schemas.debugging import (
    ClearConsoleLogsResponse,
    ConsoleEntry,
    GetConsoleLogsParams,
    GetConsoleLogsResponse,
)
from inspekt.core.schemas.execution import (
    ExecuteJavaScriptParams,
    ExecuteJavaScriptResponse,
)
from inspekt.core.schemas.extraction import (
    ExtractArticleResponse,
    ExtractLinksParams,
    ExtractLinksResponse,
    ExtractOutlineResponse,
    LinkInfo,
    OutlineItem,
    PageInfoResponse,
)
from inspekt.core.schemas.inspection import (
    GetPageInfoResponse,
    TakeScreenshotParams,
    TakeScreenshotResponse,
)
from inspekt.core.schemas.interaction import (
    ClickElementParams,
    ClickElementResponse,
    TypeTextParams,
    TypeTextResponse,
)
from inspekt.core.schemas.navigation import (
    NavigateParams,
    NavigateResponse,
    ReloadParams,
)
from inspekt.core.schemas.storage import (
    CookieInfo,
    GetCookiesResponse,
    GetSelectedTextParams,
    GetSelectedTextResponse,
    SetCookieParams,
    SetCookieResponse,
)

__all__ = [
    # Navigation
    "NavigateParams",
    "NavigateResponse",
    "ReloadParams",
    # Execution
    "ExecuteJavaScriptParams",
    "ExecuteJavaScriptResponse",
    # Extraction
    "ExtractLinksParams",
    "ExtractLinksResponse",
    "LinkInfo",
    "ExtractOutlineResponse",
    "OutlineItem",
    "PageInfoResponse",
    "ExtractArticleResponse",
    # Interaction
    "ClickElementParams",
    "ClickElementResponse",
    "TypeTextParams",
    "TypeTextResponse",
    # Inspection
    "GetPageInfoResponse",
    "TakeScreenshotParams",
    "TakeScreenshotResponse",
    # Storage
    "GetSelectedTextParams",
    "GetSelectedTextResponse",
    "CookieInfo",
    "GetCookiesResponse",
    "SetCookieParams",
    "SetCookieResponse",
    # Debugging
    "GetConsoleLogsParams",
    "GetConsoleLogsResponse",
    "ConsoleEntry",
    "ClearConsoleLogsResponse",
]
