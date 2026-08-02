"""
Storage command definitions.

Commands for browser storage and selection:
- get_selected_text: Get user-selected text
- get_cookies: Get page cookies
- set_cookie: Set a cookie
"""

from inspekt.core.commands.base import Category, CommandDefinition, EmptyParams
from inspekt.core.schemas.storage import (
    GetCookiesResponse,
    GetSelectedTextParams,
    GetSelectedTextResponse,
    SetCookieParams,
    SetCookieResponse,
)

# === Get Selected Text ===

get_selected_text = CommandDefinition(
    id="get_selected_text",
    name="Get Selected Text",
    category=Category.STORAGE,
    description="""Get the currently selected text from the page.

Returns the user's text selection in multiple formats:
- text: Plain text (default)
- html: Raw HTML of selection
- markdown: Converted to markdown format

Perfect for AI workflows:
1. User selects text in browser
2. AI assistant extracts it
3. AI can translate, summarize, explain, etc.

Works with any text selection, including:
- Paragraphs and articles
- Tables and lists
- Code blocks""",
    params_schema=GetSelectedTextParams,
    response_schema=GetSelectedTextResponse,
    handler="inspekt.core.handlers.storage.get_selected_text",
    cli_name="selection text",
    api_path="/storage/selection",
    api_method="GET",
    examples=[
        "inspekt selection",
        "inspekt selection --format html",
        "inspekt selection --format markdown",
    ],
)

# === Get Cookies ===

get_cookies = CommandDefinition(
    id="get_cookies",
    name="Get Cookies",
    category=Category.STORAGE,
    description="""Get all cookies for the current page.

Returns comprehensive cookie information:
- Name and value
- Domain and path
- Security flags (Secure, HttpOnly, SameSite)
- Expiration and session status
- Size and first/third-party classification

Useful for:
- Debugging authentication issues
- Privacy auditing
- Session management
- Security analysis""",
    params_schema=EmptyParams,
    response_schema=GetCookiesResponse,
    handler="inspekt.core.handlers.storage.get_cookies",
    cli_name="cookies",
    api_path="/storage/cookies",
    api_method="GET",
    examples=["inspekt cookies"],
)

# === Set Cookie ===

set_cookie = CommandDefinition(
    id="set_cookie",
    name="Set Cookie",
    category=Category.STORAGE,
    description="""Set a cookie with full attribute control.

Supports all standard cookie attributes:
- name/value (required)
- domain (defaults to current)
- path (defaults to "/")
- secure flag
- httpOnly flag
- sameSite (Strict, Lax, None)
- expires (ISO 8601 or relative)

Note: httpOnly cookies can only be set if the page's
Content Security Policy allows it.""",
    params_schema=SetCookieParams,
    response_schema=SetCookieResponse,
    handler="inspekt.core.handlers.storage.set_cookie",
    cli_name="set-cookie",
    api_path="/storage/cookies",
    api_method="POST",
    examples=[
        "inspekt set-cookie --name session --value abc123",
        "inspekt set-cookie --name pref --value dark --expires '2025-12-31'",
    ],
)

# All storage commands
STORAGE_COMMANDS = [
    get_selected_text,
    get_cookies,
    set_cookie,
]
