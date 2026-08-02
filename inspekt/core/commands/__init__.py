"""
Unified Command Definitions

All Inspekt commands are defined here. Each command specifies:
- Input/output schemas (Pydantic models)
- Handler function for implementation
- Metadata for CLI, API, and MCP generation

This is the SINGLE SOURCE OF TRUTH for all command metadata.
The CLI, API, MCP, and dashboard all read from this registry.
"""

# Import all command modules to register them
# === Original modules (with unified handlers) ===
from inspekt.core.commands.accessibility import ACCESSIBILITY_COMMANDS
from inspekt.core.commands.ai import AI_COMMANDS
from inspekt.core.commands.base import Category, CommandDefinition

# === New modules (CLI-only metadata for dashboard visibility) ===
from inspekt.core.commands.console import CONSOLE_COMMANDS
from inspekt.core.commands.control import CONTROL_COMMANDS
from inspekt.core.commands.debugging import DEBUGGING_COMMANDS
from inspekt.core.commands.display import DISPLAY_COMMANDS
from inspekt.core.commands.execution import EXECUTION_COMMANDS
from inspekt.core.commands.extraction import EXTRACTION_COMMANDS
from inspekt.core.commands.inspection import INSPECTION_COMMANDS
from inspekt.core.commands.interaction import INTERACTION_COMMANDS
from inspekt.core.commands.mcp_management import MCP_MANAGEMENT_COMMANDS
from inspekt.core.commands.navigation import NAVIGATION_COMMANDS
from inspekt.core.commands.network import NETWORK_COMMANDS
from inspekt.core.commands.plugin import PLUGIN_COMMANDS
from inspekt.core.commands.recording import RECORDING_COMMANDS
from inspekt.core.commands.screen_reader import SCREEN_READER_COMMANDS
from inspekt.core.commands.selection import SELECTION_COMMANDS
from inspekt.core.commands.storage import STORAGE_COMMANDS
from inspekt.core.commands.utilities import UTILITIES_COMMANDS
from inspekt.core.commands.vm import VM_COMMANDS
from inspekt.core.commands.watch import WATCH_COMMANDS

__all__ = ["Category", "CommandDefinition", "register_all_commands"]

# Track if commands have been registered (prevents duplicate registration)
_commands_registered = False


def register_all_commands() -> None:
    """Register all built-in commands with the registry."""
    global _commands_registered

    # Prevent duplicate registration
    if _commands_registered:
        return

    from inspekt.core.registry import get_registry

    registry = get_registry()

    # Register all command groups
    # === Original modules (with unified handlers) ===
    registry.register_many(NAVIGATION_COMMANDS)
    registry.register_many(EXECUTION_COMMANDS)
    registry.register_many(EXTRACTION_COMMANDS)
    registry.register_many(INTERACTION_COMMANDS)
    registry.register_many(INSPECTION_COMMANDS)
    registry.register_many(STORAGE_COMMANDS)
    registry.register_many(ACCESSIBILITY_COMMANDS)
    registry.register_many(DEBUGGING_COMMANDS)
    registry.register_many(AI_COMMANDS)

    # === New modules (CLI-only, for dashboard visibility) ===
    registry.register_many(CONTROL_COMMANDS)
    registry.register_many(RECORDING_COMMANDS)
    registry.register_many(UTILITIES_COMMANDS)
    registry.register_many(NETWORK_COMMANDS)
    registry.register_many(CONSOLE_COMMANDS)
    registry.register_many(SELECTION_COMMANDS)
    registry.register_many(WATCH_COMMANDS)
    registry.register_many(VM_COMMANDS)
    registry.register_many(MCP_MANAGEMENT_COMMANDS)
    registry.register_many(PLUGIN_COMMANDS)
    registry.register_many(SCREEN_READER_COMMANDS)
    registry.register_many(DISPLAY_COMMANDS)

    # Mark as registered to prevent re-registration
    _commands_registered = True
