"""
CLI introspection utilities for command registry validation.

This module provides tools to discover all CLI commands from Click
and compare them against the CommandDefinition registry.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from click import Command, Group


def get_all_cli_commands(cli_group: Group, prefix: str = "") -> dict[str, dict]:
    """
    Recursively discover all CLI commands from a Click group.

    Returns a dict mapping command paths to metadata:
    {
        "record": {"name": "record", "help": "...", "hidden": False},
        "cookies.list": {"name": "list", "help": "...", "hidden": False},
    }

    Args:
        cli_group: The Click Group to introspect
        prefix: Prefix for nested commands (e.g., "cookies" for "cookies.list")

    Returns:
        Dict mapping command paths to metadata dicts
    """
    from click import Context, Group

    commands: dict[str, dict] = {}

    # Create a dummy context for command resolution
    ctx = Context(cli_group)

    for name in cli_group.list_commands(ctx):
        try:
            cmd = cli_group.get_command(ctx, name)
            if cmd is None:
                continue

            # Build the full command path
            path = f"{prefix}.{name}" if prefix else name

            # Extract metadata
            metadata = {
                "name": name,
                "help": cmd.help or "",
                "hidden": getattr(cmd, "hidden", False),
                "deprecated": getattr(cmd, "deprecated", False),
                "params": [p.name for p in getattr(cmd, "params", [])],
            }

            if isinstance(cmd, Group):
                # It's a command group - add the group itself
                metadata["is_group"] = True
                commands[path] = metadata

                # Recurse into subcommands
                subcommands = get_all_cli_commands(cmd, prefix=path)
                commands.update(subcommands)
            else:
                metadata["is_group"] = False
                commands[path] = metadata

        except Exception:
            # Skip commands that can't be loaded (e.g., import errors)
            continue

    return commands


def infer_category_from_module(module_name: str) -> str:
    """
    Map CLI module names to Category display values.

    Args:
        module_name: The module name (e.g., "navigation", "control")

    Returns:
        The category display string (e.g., "Navigation", "Control")
    """
    mapping = {
        # Navigation
        "navigation": "Navigation",
        # Execution
        "exec": "Execution",
        "execution": "Execution",
        # Extraction
        "extraction": "Extraction",
        # Interaction
        "interaction": "Interaction",
        # Inspection
        "inspection": "Inspection",
        # Selection
        "selection": "Selection",
        # Storage
        "storage": "Storage",
        "cookies": "Storage",
        # Accessibility
        "accessibility": "Accessibility",
        # Network
        "network": "Network",
        # Debugging
        "debugging": "Debugging",
        "console": "Debugging",
        # Control
        "control": "Control",
        "watch": "Control",
        # Recording
        "record": "Recording",
        "replay": "Recording",
        # Utilities
        "util": "Utilities",
        "validation": "Utilities",
        "save": "Utilities",
        "robots": "Utilities",
        "domain": "Utilities",
        "info": "Utilities",
        "vm": "Utilities",
        # Plugins
        "plugin": "Plugins",
        "mcp": "Plugins",
    }
    return mapping.get(module_name, "Utilities")


def get_registered_cli_names() -> set[str]:
    """
    Get all CLI names (including aliases) from the registry.

    Returns:
        Set of CLI command names and aliases
    """
    from inspekt.core.commands import register_all_commands
    from inspekt.core.registry import get_registry

    register_all_commands()
    registry = get_registry()

    names = set()
    for cmd in registry.get_all():
        names.add(cmd.get_cli_name())
        names.update(cmd.cli_aliases)

        # Also add subcommand paths for groups
        if cmd.is_group:
            for sub in cmd.subcommands:
                names.add(f"{cmd.get_cli_name()}.{sub.name}")

    return names


def find_missing_definitions(
    excluded: set[str] | None = None,
) -> list[str]:
    """
    Find CLI commands that lack CommandDefinitions.

    Args:
        excluded: Set of command names to exclude from the check

    Returns:
        List of command names missing from the registry
    """
    from inspekt.app.cli import cli

    if excluded is None:
        excluded = set()

    cli_commands = get_all_cli_commands(cli)
    registered = get_registered_cli_names()

    missing = []
    for name, metadata in cli_commands.items():
        if name in excluded:
            continue
        if metadata.get("hidden"):
            continue
        if name not in registered:
            missing.append(name)

    return sorted(missing)


def get_cli_command_details(command_path: str) -> dict[str, Any] | None:
    """
    Get full CLI details for a command including options.

    This extracts the same information shown by `--help`, ensuring
    the modal dialog shows exactly what users see in the terminal.

    Args:
        command_path: The command path (e.g., "extract.images", "axe", "screenshot.viewport")

    Returns:
        Dictionary with:
        - full_help: Complete help text
        - short_help: First line of help
        - options: List of option dicts with name, short, type, default, required, is_flag, help
        - examples: List of examples extracted from docstring

        Returns None if command not found.
    """
    from click import Context, Group, Option, Argument

    from inspekt.app.cli import cli

    # Navigate to the command
    parts = command_path.split(".")
    current: Group | Command = cli
    ctx = Context(cli)

    try:
        for part in parts:
            if not isinstance(current, Group):
                return None
            ctx = Context(current, parent=ctx)
            current = current.get_command(ctx, part)
            if current is None:
                return None
    except Exception:
        return None

    # Extract help text
    full_help = current.help or ""
    # Get first non-empty line as short help
    short_help = ""
    for line in full_help.split("\n"):
        line = line.strip()
        if line:
            short_help = line
            break

    # Extract options
    options = []
    for param in getattr(current, "params", []):
        if isinstance(param, Option):
            # Get option names
            opts = param.opts  # e.g., ['-d', '--output-dir']
            long_name = None
            short_name = None

            for opt in opts:
                if opt.startswith("--"):
                    long_name = opt[2:]  # Remove --
                elif opt.startswith("-") and len(opt) == 2:
                    short_name = opt  # Keep as -d

            if not long_name:
                # Fallback to param name
                long_name = param.name

            # Get type name
            type_name = "TEXT"
            if param.type:
                type_name = param.type.name.upper() if hasattr(param.type, "name") else str(param.type)

            # Handle special types
            if param.is_flag:
                type_name = "FLAG"
            elif hasattr(param.type, "__class__"):
                cls_name = param.type.__class__.__name__
                if cls_name == "Path":
                    if getattr(param.type, "file_okay", True) and not getattr(param.type, "dir_okay", True):
                        type_name = "FILE"
                    elif getattr(param.type, "dir_okay", True) and not getattr(param.type, "file_okay", True):
                        type_name = "DIRECTORY"
                    else:
                        type_name = "PATH"
                elif cls_name == "Choice":
                    choices = getattr(param.type, "choices", [])
                    type_name = f"[{'|'.join(choices)}]" if choices else "CHOICE"
                elif cls_name == "IntRange":
                    type_name = "INTEGER"
                elif cls_name == "FloatRange":
                    type_name = "FLOAT"

            # Get default value (avoid showing None or empty for flags)
            # Ensure only JSON-serializable types are returned
            default = param.default
            if param.is_flag:
                default = None  # Don't show default for flags
            elif default is None or (isinstance(default, (list, tuple)) and len(default) == 0):
                default = None
            elif not isinstance(default, (str, int, float, bool)):
                # Convert non-serializable defaults to string representation
                default = str(default)

            options.append({
                "name": long_name,
                "short": short_name,
                "type": type_name,
                "required": param.required,
                "default": default,
                "is_flag": param.is_flag,
                "help": param.help or "",
            })

    # Extract examples from docstring
    examples = _extract_examples_from_help(full_help)

    return {
        "full_help": full_help,
        "short_help": short_help,
        "options": options,
        "examples": examples,
    }


def _extract_examples_from_help(help_text: str) -> list[str]:
    """
    Extract examples from Click docstring help text.

    Click docstrings often have examples in this format:
        Examples:
            inspekt command --flag
            inspekt command --other-flag

    Or with \\b marker for literal blocks:
        \\b
        Examples:
            inspekt command

    Args:
        help_text: The full help text from the command

    Returns:
        List of example command strings
    """
    if not help_text:
        return []

    examples = []

    # Look for Examples: section
    # Match lines after "Examples:" until we hit another section or end
    patterns = [
        # Standard "Examples:" section
        r"Examples?:\s*\n((?:[ \t]+.*\n?)+)",
        # Lines starting with "inspekt " that look like examples
        r"^\s*(inspekt\s+\S.*?)(?:\s+#.*)?$",
    ]

    # Try to find Examples: section first
    match = re.search(patterns[0], help_text, re.IGNORECASE | re.MULTILINE)
    if match:
        example_block = match.group(1)
        # Extract individual example lines
        for line in example_block.split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                # Remove inline comments
                if "#" in line:
                    line = line.split("#")[0].strip()
                if line:
                    examples.append(line)
    else:
        # Fall back to finding individual inspekt commands
        for match in re.finditer(patterns[1], help_text, re.MULTILINE):
            example = match.group(1).strip()
            if example and example not in examples:
                examples.append(example)

    return examples
