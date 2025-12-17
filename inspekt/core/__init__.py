"""
Inspekt Core - Unified Command Registry

This module provides the single source of truth for all Inspekt commands.
CLI, API, and MCP interfaces are all generated from the definitions here.
"""

from inspekt.core.commands import register_all_commands
from inspekt.core.commands.base import Category, CommandDefinition
from inspekt.core.registry import CommandRegistry, get_registry

__all__ = [
    "CommandDefinition",
    "Category",
    "CommandRegistry",
    "get_registry",
    "register_all_commands",
]
