"""
Recording command definitions.

These commands handle browser interaction recording and playback.
They are CLI-only as they involve interactive terminal sessions.
"""

from inspekt.core.commands.base import (
    Category,
    CommandDefinition,
    EmptyParams,
    EmptyResponse,
    SubcommandDefinition,
)

# =============================================================================
# RECORD COMMAND (GROUP)
# =============================================================================

record = CommandDefinition(
    id="record",
    name="Record",
    category=Category.RECORDING,
    description="""Record browser interactions to a YAML file.

Starts recording all user actions on the currently open browser page.
Press Ctrl+C to stop recording and save the file.

The recording captures:
- Clicks, typing, and keyboard navigation
- Form submissions and downloads
- Page navigations and scrolling
- Optional: hover events, state snapshots

**Key Options:**
- `--include-hover`: Capture hover events (longer recordings)
- `--mask-passwords`: Replace password input with asterisks
- `--replay`: Immediately replay after recording
- `--interactive`: Show dialog popover with controls
- `--capture-state`: Snapshot localStorage/cookies
- `--faithful`: Capture focus styles for pixel-perfect replay

**Subcommands:**
- `tutorial`: Interactive tutorial for the record command
- `list`: List all recordings in the default directory
- `open`: Open a recording file in your default YAML editor
- `rename`: Rename a recording file
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,  # CLI-only command (interactive terminal)
    cli_name="record",
    api_path=None,
    mcp_enabled_default=False,
    is_group=True,
    subcommands=[
        SubcommandDefinition(
            name="tutorial",
            description="Interactive tutorial for the record command",
            params_schema=EmptyParams,
            examples=["inspekt record tutorial", "inspekt record tutorial --speak"],
        ),
        SubcommandDefinition(
            name="list",
            description="List all recordings in the default directory",
            params_schema=EmptyParams,
            examples=["inspekt record list", "inspekt record list --json"],
        ),
        SubcommandDefinition(
            name="show",
            description="Show contents of a recording file",
            params_schema=EmptyParams,
            examples=["inspekt record show my_session.yaml"],
        ),
        SubcommandDefinition(
            name="delete",
            description="Delete a recording file",
            params_schema=EmptyParams,
            examples=["inspekt record delete my_session.yaml"],
        ),
        SubcommandDefinition(
            name="edit",
            description="Edit a recording file in your default editor",
            params_schema=EmptyParams,
            examples=["inspekt record edit my_session.yaml"],
        ),
        SubcommandDefinition(
            name="tidy",
            description="Clean up and optimize a recording file",
            params_schema=EmptyParams,
            examples=["inspekt record tidy my_session.yaml"],
        ),
    ],
    examples=[
        "inspekt record",
        "inspekt record --include-hover",
        "inspekt record --interactive",
        "inspekt record --replay",
        "inspekt record -o my_session.yaml",
        "inspekt record tutorial",
    ],
)


# =============================================================================
# REPLAY COMMAND
# =============================================================================

replay = CommandDefinition(
    id="replay",
    name="Replay",
    category=Category.RECORDING,
    description="""Replay recorded browser interactions from a YAML file.

Plays back a previously recorded session, reproducing all user actions
with precise timing and visual feedback.

**Key Options:**
- `--speed N`: Playback speed multiplier (e.g., 2.0 for 2x)
- `--slow`: Half speed (0.5x)
- `--instant`: Skip delays, execute actions immediately
- `--step`: Pause after each step (press Enter to continue)
- `--video`: Generate MP4 video of the replay
- `--smooth`: Smooth video recording (experimental)
- `--assertions`: Verify expected state after each step
- `--loop N`: Loop playback N times

**Video Options:**
- `--video`: Record replay as MP4 video
- `--fps N`: Video frame rate (default: 30)
- `--crf N`: Video quality (0-51, lower is better)
- `--smooth`: Use browser tab capture for smooth video

If no file is specified, replays the most recent recording.
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="replay",
    api_path=None,
    mcp_enabled_default=False,
    examples=[
        "inspekt replay",
        "inspekt replay session.yaml",
        "inspekt replay --speed 2.0",
        "inspekt replay --slow",
        "inspekt replay --step",
        "inspekt replay --video",
        "inspekt replay --video --smooth",
        "inspekt replay --loop 3",
    ],
)


# =============================================================================
# EXPORT ALL COMMANDS
# =============================================================================

RECORDING_COMMANDS = [record, replay]
