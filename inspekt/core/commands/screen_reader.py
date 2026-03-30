"""
Screen reader simulator command definitions.

Commands for simulating screen reader behavior:
- sr_walk: Walk through a page with simulated SR output
- sr_announce: Announce a specific element
"""

from inspekt.core.commands.base import (
    Category,
    CommandDefinition,
    EmptyParams,
    EmptyResponse,
    SubcommandDefinition,
)
from inspekt.core.schemas.screen_reader import (
    SRAnnounceParams,
    SRAnnounceResponse,
    SRWalkParams,
    SRWalkResponse,
)

# === SR Command Group ===

sr = CommandDefinition(
    id="sr",
    name="Screen Reader Simulator",
    category=Category.ACCESSIBILITY,
    description="""Screen reader simulation commands.

Simulate how JAWS, NVDA, and VoiceOver would announce page content.
Uses announcement patterns sourced from the W3C ARIA-AT project and
a11ysupport.io to approximate real screen reader behavior.

**Subcommands:**
- `walk`: Walk through the page in reading order, showing announcements
- `compare`: Side-by-side comparison of all three screen readers
- `announce`: Announce a specific element
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="sr",
    api_path=None,
    mcp_enabled_default=False,
    is_group=True,
    subcommands=[
        SubcommandDefinition(
            name="walk",
            description="Walk through the page showing screen reader announcements",
            params_schema=SRWalkParams,
            examples=[
                "inspekt sr walk",
                "inspekt sr walk --screen-reader jaws",
                "inspekt sr walk --screen-reader nvda --verbosity low",
            ],
        ),
        SubcommandDefinition(
            name="compare",
            description="Compare announcements across JAWS, NVDA, and VoiceOver",
            params_schema=SRWalkParams,
            examples=[
                "inspekt sr compare",
                "inspekt sr compare --verbosity medium",
            ],
        ),
        SubcommandDefinition(
            name="announce",
            description="Announce a specific element",
            params_schema=SRAnnounceParams,
            examples=[
                "inspekt sr announce",
                "inspekt sr announce --selector 'button.submit'",
                "inspekt sr announce --selector '#main-heading' --screen-reader jaws",
            ],
        ),
    ],
    examples=[
        "inspekt sr walk",
        "inspekt sr compare",
        "inspekt sr announce --selector 'h1'",
    ],
)

# === SR Walk ===

sr_walk = CommandDefinition(
    id="sr_walk",
    name="Screen Reader Walk",
    category=Category.ACCESSIBILITY,
    description="""Walk through a page simulating screen reader announcements.

Linearizes the page into reading order and generates the text that
JAWS, NVDA, and/or VoiceOver would announce for each element.

The walk covers headings, links, buttons, form fields, images, landmarks,
tables, lists, and other ARIA roles. Each element is announced using
the patterns specific to the selected screen reader.

Use `--screen-reader all` (default) for a side-by-side comparison, or
select a specific screen reader for its individual output.

Verbosity levels:
- high: Maximum detail (role, state, description, hints, position)
- medium: Standard (role, state, description)
- low: Minimal (role, name only)""",
    params_schema=SRWalkParams,
    response_schema=SRWalkResponse,
    handler="inspekt.core.handlers.screen_reader.sr_walk",
    cli_name="sr-walk",
    cli_hidden=True,  # Accessed via sr group, not top-level
    api_path="/accessibility/sr/walk",
    api_method="POST",
    mcp_name="screen_reader_walk",
    examples=[
        "inspekt sr walk",
        "inspekt sr walk --screen-reader jaws",
        "inspekt sr walk --screen-reader nvda --verbosity low",
        "inspekt sr walk --format json",
    ],
)

# === SR Announce ===

sr_announce = CommandDefinition(
    id="sr_announce",
    name="Screen Reader Announce",
    category=Category.ACCESSIBILITY,
    description="""Simulate screen reader announcement for a specific element.

If no selector is provided, announces the currently focused element.
Returns what JAWS, NVDA, and VoiceOver would say for the element,
including role, name, state, and description.""",
    params_schema=SRAnnounceParams,
    response_schema=SRAnnounceResponse,
    handler="inspekt.core.handlers.screen_reader.sr_announce",
    cli_name="sr-announce",
    cli_hidden=True,
    api_path="/accessibility/sr/announce",
    api_method="POST",
    mcp_name="screen_reader_announce",
    examples=[
        "inspekt sr announce",
        "inspekt sr announce --selector 'button.submit'",
        "inspekt sr announce --selector 'h1' --screen-reader jaws",
    ],
)

SCREEN_READER_COMMANDS = [sr, sr_walk, sr_announce]
