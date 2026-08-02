"""
Selection command definitions.
"""

from inspekt.core.commands.base import (
    Category,
    CommandDefinition,
    EmptyParams,
    EmptyResponse,
    SubcommandDefinition,
)

selection = CommandDefinition(
    id="selection",
    name="Selection",
    category=Category.SELECTION,
    description="""Get the current text selection in the browser.

Returns the selected text in various formats (plain text, HTML, Markdown).

**Options:**
- `--json`: Output as JSON with all formats

**Subcommands:**
- `text`: Get selection as plain text
- `html`: Get selection as HTML
- `markdown`: Get selection as Markdown
- `screenshot`: Take screenshot of selection
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="selection",
    api_path=None,
    mcp_enabled_default=False,
    is_group=True,
    subcommands=[
        SubcommandDefinition(
            name="text",
            description="Get selection as plain text",
            params_schema=EmptyParams,
            examples=["inspekt selection text"],
        ),
        SubcommandDefinition(
            name="html",
            description="Get selection as HTML",
            params_schema=EmptyParams,
            examples=["inspekt selection html"],
        ),
        SubcommandDefinition(
            name="markdown",
            description="Get selection as Markdown",
            params_schema=EmptyParams,
            examples=["inspekt selection markdown"],
        ),
        SubcommandDefinition(
            name="screenshot",
            description="Take screenshot of selection",
            params_schema=EmptyParams,
            examples=["inspekt selection screenshot"],
        ),
    ],
    examples=[
        "inspekt selection",
        "inspekt selection --json",
        "inspekt selection text",
        "inspekt selection markdown",
    ],
)


selected = CommandDefinition(
    id="selected",
    name="Selected (Deprecated)",
    category=Category.SELECTION,
    description="""[DEPRECATED] Get the current text selection in the browser.

Please use 'inspekt selection text' instead.
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="selected",
    api_path=None,
    mcp_enabled_default=False,
    deprecated=True,
    deprecated_message="Use 'inspekt selection text' instead.",
    examples=[
        "inspekt selected",
    ],
)


SELECTION_COMMANDS = [selection, selected]
