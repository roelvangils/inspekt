"""
Unified Command Definitions

All Inspekt commands are defined here. Each command specifies:
- Input/output schemas (Pydantic models)
- Handler function for implementation
- Metadata for CLI, API, and MCP generation
"""

from inspekt.core.commands.base import Category, CommandDefinition

# Import all command modules to register them
from inspekt.core.commands.accessibility import ACCESSIBILITY_COMMANDS
from inspekt.core.commands.debugging import DEBUGGING_COMMANDS
from inspekt.core.commands.execution import EXECUTION_COMMANDS
from inspekt.core.commands.extraction import EXTRACTION_COMMANDS
from inspekt.core.commands.inspection import INSPECTION_COMMANDS
from inspekt.core.commands.interaction import INTERACTION_COMMANDS
from inspekt.core.commands.navigation import NAVIGATION_COMMANDS
from inspekt.core.commands.storage import STORAGE_COMMANDS

__all__ = ["CommandDefinition", "Category", "register_all_commands"]


def register_all_commands() -> None:
    """Register all built-in commands with the registry."""
    from inspekt.core.registry import get_registry

    registry = get_registry()

    # Register all command groups
    registry.register_many(NAVIGATION_COMMANDS)
    registry.register_many(EXECUTION_COMMANDS)
    registry.register_many(EXTRACTION_COMMANDS)
    registry.register_many(INTERACTION_COMMANDS)
    registry.register_many(INSPECTION_COMMANDS)
    registry.register_many(STORAGE_COMMANDS)
    registry.register_many(ACCESSIBILITY_COMMANDS)
    registry.register_many(DEBUGGING_COMMANDS)
