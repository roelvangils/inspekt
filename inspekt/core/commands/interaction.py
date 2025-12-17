"""
Interaction command definitions.

Commands for interacting with web pages:
- click_element: Click elements by selector
- type_text: Type text into focused elements
"""

from inspekt.core.commands.base import Category, CommandDefinition
from inspekt.core.schemas.interaction import (
    ClickElementParams,
    ClickElementResponse,
    TypeTextParams,
    TypeTextResponse,
)

# === Click Element ===

click_element = CommandDefinition(
    id="click_element",
    name="Click Element",
    category=Category.INTERACTION,
    description="""Click an element on the page by CSS selector.

Supports different click types:
- single: Normal left click (default)
- double: Double-click
- right: Right-click (context menu)

The special selector '$0' targets the element currently selected
in Chrome DevTools, enabling seamless DevTools integration.

The command waits for the element to be clickable and returns
the element's text content for verification.""",
    params_schema=ClickElementParams,
    response_schema=ClickElementResponse,
    handler="inspekt.core.handlers.interaction.click_element",
    cli_name="click",
    api_path="/interaction/click",
    api_method="POST",
    examples=[
        "inspekt click 'button.submit'",
        "inspekt click '#login-btn' --type double",
        "inspekt click '$0'  # Click DevTools-selected element",
    ],
)

# === Type Text ===

type_text = CommandDefinition(
    id="type_text",
    name="Type Text",
    category=Category.INTERACTION,
    description="""Type text into the currently focused element.

Simulates realistic keyboard input with configurable typing speed:
- instant: All text at once (default for long text)
- fast: 50ms between characters
- normal: 100ms between characters (default)
- slow: 200ms between characters

Each character triggers proper input events, making it work
with reactive frameworks (React, Vue, etc.) that listen for
input events rather than value changes.

The --submit flag presses Enter after typing, useful for:
- Search boxes
- Login forms
- Chat inputs""",
    params_schema=TypeTextParams,
    response_schema=TypeTextResponse,
    handler="inspekt.core.handlers.interaction.type_text",
    cli_name="type",
    api_path="/interaction/type",
    api_method="POST",
    examples=[
        "inspekt type 'Hello, world!'",
        "inspekt type 'search query' --submit",
        "inspekt type 'password123' --speed instant",
    ],
)

# All interaction commands
INTERACTION_COMMANDS = [
    click_element,
    type_text,
]
