"""
Unified Command Registry.

Central registry for all Inspekt commands with SQLite-backed configuration.
CLI, API, and MCP interfaces all read from this registry.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from inspekt.config import find_config_file
from inspekt.core.commands.base import CATEGORY_ORDER, Category, CommandDefinition

if TYPE_CHECKING:
    from collections.abc import Iterator


class CommandRegistry:
    """
    Central registry of all command definitions.

    This is THE SINGLE SOURCE OF TRUTH for all commands.
    CLI, API, and MCP generators read from this registry.

    Usage:
        # Get the singleton instance
        registry = CommandRegistry.get_instance()

        # Register a command
        registry.register(my_command)

        # Get commands for specific interface
        mcp_commands = registry.get_for_mcp()
    """

    _instance: CommandRegistry | None = None
    _commands: dict[str, CommandDefinition]
    _db_path: Path

    def __new__(cls) -> CommandRegistry:
        """Singleton pattern - only one registry instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._commands = {}
            cls._instance._init_database()
        return cls._instance

    @classmethod
    def get_instance(cls) -> CommandRegistry:
        """Get the singleton registry instance."""
        return cls()

    def _init_database(self) -> None:
        """Initialize SQLite database for command configuration."""
        config_file = find_config_file()
        if config_file:
            config_dir = config_file.parent
        else:
            config_dir = Path.home() / ".inspekt"
            config_dir.mkdir(parents=True, exist_ok=True)

        self._db_path = config_dir / "data.db"
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create command_config table if it doesn't exist, and add new columns."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        try:
            # Create table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS command_config (
                    command_id TEXT PRIMARY KEY,
                    mcp_enabled INTEGER DEFAULT 1,
                    custom_description TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Add new columns if they don't exist (for migration)
            cursor.execute("PRAGMA table_info(command_config)")
            columns = {row[1] for row in cursor.fetchall()}

            if "custom_mcp_name" not in columns:
                cursor.execute("ALTER TABLE command_config ADD COLUMN custom_mcp_name TEXT")

            if "custom_examples" not in columns:
                cursor.execute("ALTER TABLE command_config ADD COLUMN custom_examples TEXT")

            if "schema_annotations" not in columns:
                cursor.execute("ALTER TABLE command_config ADD COLUMN schema_annotations TEXT")

            conn.commit()
        finally:
            conn.close()

    def _get_config(self, command_id: str) -> dict:
        """Get configuration for a command from database."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """SELECT mcp_enabled, custom_description, custom_mcp_name, custom_examples, schema_annotations
                   FROM command_config WHERE command_id = ?""",
                (command_id,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "mcp_enabled": bool(row[0]),
                    "custom_description": row[1],
                    "custom_mcp_name": row[2],
                    "custom_examples": row[3],
                    "schema_annotations": row[4],
                }
            return {
                "mcp_enabled": True,  # Default
                "custom_description": None,
                "custom_mcp_name": None,
                "custom_examples": None,
                "schema_annotations": None,
            }
        finally:
            conn.close()

    def set_mcp_enabled(self, command_id: str, enabled: bool) -> None:
        """Set MCP enabled state for a command."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO command_config (command_id, mcp_enabled, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(command_id) DO UPDATE SET
                    mcp_enabled = excluded.mcp_enabled,
                    updated_at = excluded.updated_at
            """,
                (command_id, int(enabled), datetime.now().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    def set_custom_description(self, command_id: str, description: str | None) -> None:
        """Set custom description for a command (overrides default)."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO command_config (command_id, custom_description, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(command_id) DO UPDATE SET
                    custom_description = excluded.custom_description,
                    updated_at = excluded.updated_at
            """,
                (command_id, description, datetime.now().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    def set_custom_mcp_name(self, command_id: str, mcp_name: str | None) -> None:
        """Set custom MCP tool name for a command (overrides default)."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO command_config (command_id, custom_mcp_name, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(command_id) DO UPDATE SET
                    custom_mcp_name = excluded.custom_mcp_name,
                    updated_at = excluded.updated_at
            """,
                (command_id, mcp_name, datetime.now().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    def set_custom_examples(self, command_id: str, examples: list[str] | None) -> None:
        """Set custom examples for a command (overrides default)."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        try:
            # Store as JSON string
            examples_json = json.dumps(examples) if examples else None
            cursor.execute(
                """
                INSERT INTO command_config (command_id, custom_examples, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(command_id) DO UPDATE SET
                    custom_examples = excluded.custom_examples,
                    updated_at = excluded.updated_at
            """,
                (command_id, examples_json, datetime.now().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    def set_schema_annotations(self, command_id: str, annotations: dict | None) -> None:
        """
        Set schema annotations for a command's input schema.

        Annotations format:
        {
            "field_name": {
                "description": "Custom description for this field",
                "examples": ["example1", "example2"]
            }
        }
        """
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        try:
            annotations_json = json.dumps(annotations) if annotations else None
            cursor.execute(
                """
                INSERT INTO command_config (command_id, schema_annotations, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(command_id) DO UPDATE SET
                    schema_annotations = excluded.schema_annotations,
                    updated_at = excluded.updated_at
            """,
                (command_id, annotations_json, datetime.now().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    def get_schema_annotations(self, command_id: str) -> dict:
        """Get schema annotations for a command."""
        config = self._get_config(command_id)
        if config["schema_annotations"]:
            try:
                return json.loads(config["schema_annotations"])
            except json.JSONDecodeError:
                return {}
        return {}

    def get_effective_input_schema(self, command: CommandDefinition) -> dict:
        """
        Get input schema with annotations merged in.

        Merges custom field descriptions and examples into the base schema.
        """
        base_schema = command.get_input_schema()
        annotations = self.get_schema_annotations(command.id)

        if not annotations:
            return base_schema

        # Deep copy to avoid modifying original
        schema = json.loads(json.dumps(base_schema))

        # Merge annotations into properties
        if "properties" in schema:
            for field_name, field_annotations in annotations.items():
                if field_name in schema["properties"]:
                    prop = schema["properties"][field_name]
                    if "description" in field_annotations:
                        prop["description"] = field_annotations["description"]
                    if "examples" in field_annotations:
                        prop["examples"] = field_annotations["examples"]

        return schema

    def is_mcp_enabled(self, command_id: str) -> bool:
        """Check if MCP is enabled for a command."""
        config = self._get_config(command_id)
        return config["mcp_enabled"]

    def get_description(self, command: CommandDefinition) -> str:
        """Get description for a command (custom or default)."""
        config = self._get_config(command.id)
        if config["custom_description"]:
            return config["custom_description"]
        return command.description

    def get_effective_mcp_name(self, command: CommandDefinition) -> str:
        """Get MCP tool name for a command (custom or default)."""
        config = self._get_config(command.id)
        if config["custom_mcp_name"]:
            return config["custom_mcp_name"]
        return command.get_mcp_name()

    def get_effective_examples(self, command: CommandDefinition) -> list[str]:
        """Get examples for a command (custom or default)."""
        config = self._get_config(command.id)
        if config["custom_examples"]:
            try:
                return json.loads(config["custom_examples"])
            except json.JSONDecodeError:
                return command.examples
        return command.examples

    def is_customized(self, command_id: str) -> dict[str, bool]:
        """Check which fields have custom values for a command."""
        config = self._get_config(command_id)
        return {
            "description": config["custom_description"] is not None,
            "mcp_name": config["custom_mcp_name"] is not None,
            "examples": config["custom_examples"] is not None,
            "schema_annotations": config["schema_annotations"] is not None,
        }

    def reset_custom_field(self, command_id: str, field: str) -> None:
        """Reset a custom field to its default value."""
        if field == "description":
            self.set_custom_description(command_id, None)
        elif field == "mcp_name":
            self.set_custom_mcp_name(command_id, None)
        elif field == "examples":
            self.set_custom_examples(command_id, None)
        elif field == "schema_annotations":
            self.set_schema_annotations(command_id, None)
        elif field == "all":
            self.set_custom_description(command_id, None)
            self.set_custom_mcp_name(command_id, None)
            self.set_custom_examples(command_id, None)
            self.set_schema_annotations(command_id, None)

    # === Registration ===

    def register(self, command: CommandDefinition) -> None:
        """Register a command definition."""
        if command.id in self._commands:
            raise ValueError(f"Command '{command.id}' already registered")
        self._commands[command.id] = command

    def register_many(self, commands: list[CommandDefinition]) -> None:
        """Register multiple commands."""
        for cmd in commands:
            self.register(cmd)

    def unregister(self, command_id: str) -> None:
        """Unregister a command (for plugins)."""
        if command_id in self._commands:
            del self._commands[command_id]

    # === Retrieval ===

    def get(self, command_id: str) -> CommandDefinition | None:
        """Get a command by ID."""
        return self._commands.get(command_id)

    def get_all(self) -> list[CommandDefinition]:
        """Get all registered commands."""
        return list(self._commands.values())

    def __iter__(self) -> Iterator[CommandDefinition]:
        """Iterate over all commands."""
        return iter(self._commands.values())

    def __len__(self) -> int:
        """Number of registered commands."""
        return len(self._commands)

    def __contains__(self, command_id: str) -> bool:
        """Check if a command is registered."""
        return command_id in self._commands

    # === Filtered Retrieval ===

    def get_for_cli(self) -> list[CommandDefinition]:
        """Get commands enabled for CLI (excludes hidden)."""
        return [cmd for cmd in self._commands.values() if not cmd.cli_hidden]

    def get_for_api(self) -> list[CommandDefinition]:
        """Get commands enabled for API."""
        return list(self._commands.values())

    def get_for_mcp(self) -> list[CommandDefinition]:
        """Get commands enabled for MCP (respects database setting)."""
        return [
            cmd
            for cmd in self._commands.values()
            if self.is_mcp_enabled(cmd.id)
        ]

    def get_by_category(self, category: Category) -> list[CommandDefinition]:
        """Get commands in a specific category."""
        return [cmd for cmd in self._commands.values() if cmd.category == category]

    def get_categories(self) -> list[Category]:
        """Get list of categories that have commands (in display order)."""
        used = {cmd.category for cmd in self._commands.values()}
        return [cat for cat in CATEGORY_ORDER if cat in used]

    def get_grouped_by_category(self) -> dict[Category, list[CommandDefinition]]:
        """Get commands grouped by category (in display order)."""
        result: dict[Category, list[CommandDefinition]] = {}
        for cat in CATEGORY_ORDER:
            commands = self.get_by_category(cat)
            if commands:
                result[cat] = commands
        return result

    # === Stats ===

    def get_stats(self) -> dict:
        """Get registry statistics."""
        all_cmds = self.get_all()
        mcp_enabled = [cmd for cmd in all_cmds if self.is_mcp_enabled(cmd.id)]

        return {
            "total": len(all_cmds),
            "cli_count": len(self.get_for_cli()),
            "api_count": len(self.get_for_api()),
            "mcp_count": len(mcp_enabled),
            "categories": len(self.get_categories()),
        }


# === Module-level convenience functions ===


def get_registry() -> CommandRegistry:
    """Get the command registry singleton."""
    return CommandRegistry.get_instance()


def register(command: CommandDefinition) -> CommandDefinition:
    """Register a command and return it (decorator-friendly)."""
    get_registry().register(command)
    return command
