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
    "ClearConsoleLogsResponse",
    # Interaction
    "ClickElementParams",
    "ClickElementResponse",
    "ConsoleEntry",
    "CookieInfo",
    # Execution
    "ExecuteJavaScriptParams",
    "ExecuteJavaScriptResponse",
    "ExtractArticleResponse",
    # Extraction
    "ExtractLinksParams",
    "ExtractLinksResponse",
    "ExtractOutlineResponse",
    # Debugging
    "GetConsoleLogsParams",
    "GetConsoleLogsResponse",
    "GetCookiesResponse",
    # Inspection
    "GetPageInfoResponse",
    # Storage
    "GetSelectedTextParams",
    "GetSelectedTextResponse",
    "LinkInfo",
    # Navigation
    "NavigateParams",
    "NavigateResponse",
    "OutlineItem",
    "PageInfoResponse",
    "ReloadParams",
    "SetCookieParams",
    "SetCookieResponse",
    "TakeScreenshotParams",
    "TakeScreenshotResponse",
    "TypeTextParams",
    "TypeTextResponse",
]
