"""
Plugin management service.

Manages custom JavaScript plugins (bookmarklets) in SQLite database:
- CRUD operations for plugins
- Bookmarklet URL parsing and code extraction
- Plugin execution with console capture
- MCP tool generation
- Import/export functionality
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import UTC
from typing import Any
from urllib.parse import unquote

from inspekt.config import get_data_dir


def generate_slug(name: str) -> str:
    """
    Generate a URL-safe slug from a plugin name.

    Examples:
        "Text Spacing Bookmarklet" -> "text-spacing-bookmarklet"
        "JSON Viewer" -> "json-viewer"
        "My Plugin!!!" -> "my-plugin"
    """
    # Lowercase
    slug = name.lower()
    # Replace spaces and underscores with hyphens
    slug = re.sub(r"[\s_]+", "-", slug)
    # Remove non-alphanumeric characters (except hyphens)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    # Remove consecutive hyphens
    slug = re.sub(r"-+", "-", slug)
    # Strip leading/trailing hyphens
    slug = slug.strip("-")
    return slug or "plugin"


def parse_bookmarklet(input_text: str) -> tuple[str, list[str]]:
    """
    Parse any bookmarklet format and return (clean_code, warnings).

    Handles:
    - javascript: URLs (encoded and plain)
    - void() wrappers
    - IIFE formats
    - Trailing undefined;
    - Raw JavaScript code

    Args:
        input_text: Raw input (URL or code)

    Returns:
        (code, warnings) tuple where warnings list parsing info
    """
    input_text = input_text.strip()
    warnings: list[str] = []
    code = input_text

    # Case 1: URL-encoded bookmarklet (most common paste from browser)
    if input_text.startswith("javascript:") and "%" in input_text:
        code = unquote(input_text[11:])  # Remove 'javascript:' prefix and decode
        warnings.append("Code was URL-decoded")

    # Case 2: Plain bookmarklet URL
    elif input_text.startswith("javascript:"):
        code = input_text[11:]
        warnings.append("Stripped javascript: prefix")

    # Post-processing: Handle void wrapper
    # Matches: void(...), void 0||(...), void(0)||(...)
    void_match = re.match(r"^void\s*(?:\(0\)|0)?\s*(?:\|\|)?\s*\((.*)\)\s*;?$", code, re.DOTALL)
    if void_match:
        code = void_match.group(1)
        warnings.append("Removed void() wrapper")

    # Post-processing: Handle simpler void pattern
    simple_void_match = re.match(r"^void\s*\((.*)\)\s*;?$", code, re.DOTALL)
    if simple_void_match and not void_match:
        code = simple_void_match.group(1)
        warnings.append("Removed void() wrapper")

    # Post-processing: Handle trailing semicolons and undefined
    code = re.sub(r";\s*undefined\s*;?\s*$", "", code)
    code = re.sub(r";\s*$", ";", code)  # Keep single trailing semicolon if present

    return code.strip(), warnings


class PluginService:
    """Manages plugin storage and execution."""

    def __init__(self):
        """Initialize plugin service."""
        self.db_path = get_data_dir() / "data.db"
        self._ensure_plugins_table()

    def _ensure_plugins_table(self) -> None:
        """Ensure plugins table exists with all columns."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS plugins (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    credits TEXT,
                    code TEXT NOT NULL,
                    source_url TEXT,
                    category TEXT,
                    tags TEXT,
                    returns_data INTEGER DEFAULT 0,
                    timeout INTEGER DEFAULT 30,
                    mcp_exposed INTEGER DEFAULT 0,
                    unload_mode TEXT DEFAULT 'none',
                    unload_code TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    run_count INTEGER DEFAULT 0,
                    last_run_at INTEGER,
                    autorun INTEGER DEFAULT 0,
                    autorun_domains TEXT,
                    engine TEXT DEFAULT 'js',
                    proxy_config TEXT DEFAULT '{}',
                    builtin INTEGER DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_plugins_category
                ON plugins(category)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_plugins_mcp
                ON plugins(mcp_exposed)
            """)

            # Migration: Add unload columns if they don't exist
            cursor.execute("PRAGMA table_info(plugins)")
            columns = {row[1] for row in cursor.fetchall()}

            if "unload_mode" not in columns:
                cursor.execute("ALTER TABLE plugins ADD COLUMN unload_mode TEXT DEFAULT 'none'")
            if "unload_code" not in columns:
                cursor.execute("ALTER TABLE plugins ADD COLUMN unload_code TEXT")
            if "credits" not in columns:
                cursor.execute("ALTER TABLE plugins ADD COLUMN credits TEXT")
            if "autorun" not in columns:
                cursor.execute("ALTER TABLE plugins ADD COLUMN autorun INTEGER DEFAULT 0")
            if "autorun_domains" not in columns:
                cursor.execute("ALTER TABLE plugins ADD COLUMN autorun_domains TEXT")
            if "engine" not in columns:
                cursor.execute("ALTER TABLE plugins ADD COLUMN engine TEXT DEFAULT 'js'")
            if "proxy_config" not in columns:
                cursor.execute("ALTER TABLE plugins ADD COLUMN proxy_config TEXT DEFAULT '{}'")
            if "builtin" not in columns:
                cursor.execute("ALTER TABLE plugins ADD COLUMN builtin INTEGER DEFAULT 0")

            conn.commit()
        finally:
            conn.close()

    def add_plugin(
        self,
        name: str,
        code: str,
        description: str | None = None,
        credits: str | None = None,
        source_url: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        returns_data: bool = False,
        timeout: int = 30,
        mcp_exposed: bool = False,
        unload_mode: str = "none",
        unload_code: str | None = None,
    ) -> dict[str, Any]:
        """
        Add a new plugin.

        Args:
            name: Human-readable plugin name
            code: JavaScript code
            description: Optional description
            credits: Original author/source attribution
            source_url: Original bookmarklet URL if imported
            category: Optional category for filtering
            tags: Optional list of tags
            returns_data: Whether plugin returns JSON data
            timeout: Execution timeout in seconds
            mcp_exposed: Whether to expose as MCP tool
            unload_mode: How to unload - 'toggle', 'custom', or 'none'
            unload_code: Custom JavaScript code for unloading (when unload_mode='custom')

        Returns:
            {"ok": True, "plugin": {...}} or {"ok": False, "error": "…"}
        """
        plugin_id = generate_slug(name)
        timestamp = int(time.time())
        tags_json = json.dumps(tags or [])

        # Validate unload_mode
        if unload_mode not in ("toggle", "custom", "none"):
            unload_mode = "none"

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Check for existing plugin with same name or ID
            cursor.execute(
                "SELECT id, name FROM plugins WHERE id = ? OR LOWER(name) = LOWER(?)",
                (plugin_id, name),
            )
            existing = cursor.fetchone()
            if existing:
                return {
                    "ok": False,
                    "error": f"Plugin with name '{existing[1]}' already exists",
                }

            cursor.execute(
                """
                INSERT INTO plugins (
                    id, name, description, credits, code, source_url, category, tags,
                    returns_data, timeout, mcp_exposed, unload_mode, unload_code,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    plugin_id,
                    name,
                    description,
                    credits,
                    code,
                    source_url,
                    category,
                    tags_json,
                    1 if returns_data else 0,
                    timeout,
                    1 if mcp_exposed else 0,
                    unload_mode,
                    unload_code,
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()

            return {
                "ok": True,
                "plugin": {
                    "id": plugin_id,
                    "name": name,
                    "description": description,
                    "credits": credits,
                    "code": code,
                    "source_url": source_url,
                    "category": category,
                    "tags": tags or [],
                    "returns_data": returns_data,
                    "timeout": timeout,
                    "mcp_exposed": mcp_exposed,
                    "unload_mode": unload_mode,
                    "unload_code": unload_code,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "run_count": 0,
                    "last_run_at": None,
                },
            }

        except sqlite3.IntegrityError as e:
            return {"ok": False, "error": f"Database error: {e}"}
        finally:
            conn.close()

    def add_from_bookmarklet(
        self,
        bookmarklet: str,
        name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Add a plugin from a bookmarklet URL or code.

        Args:
            bookmarklet: Bookmarklet URL (javascript:...) or raw code
            name: Optional name (required if code doesn't suggest one)
            **kwargs: Additional plugin attributes

        Returns:
            {"ok": True, "plugin": {...}, "warnings": [...]} or {"ok": False, "error": "…"}
        """
        code, warnings = parse_bookmarklet(bookmarklet)

        if not code:
            return {"ok": False, "error": "Could not extract code from bookmarklet"}

        if not name:
            return {"ok": False, "error": "Plugin name is required"}

        # Store original URL if it was a javascript: URL
        source_url = bookmarklet if bookmarklet.startswith("javascript:") else None

        result = self.add_plugin(name=name, code=code, source_url=source_url, **kwargs)

        if result.get("ok"):
            result["warnings"] = warnings

        return result

    def get_plugin(self, plugin_id: str) -> dict[str, Any] | None:
        """
        Get a plugin by ID.

        Args:
            plugin_id: Plugin slug ID

        Returns:
            Plugin dict or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM plugins WHERE id = ?", (plugin_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_dict(row)

        finally:
            conn.close()

    def get_plugin_by_name(self, name: str) -> dict[str, Any] | None:
        """
        Get a plugin by name (case-insensitive).

        Args:
            name: Plugin name

        Returns:
            Plugin dict or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT * FROM plugins WHERE LOWER(name) = LOWER(?)", (name,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_dict(row)

        finally:
            conn.close()

    def update_plugin(self, plugin_id: str, **updates: Any) -> dict[str, Any]:
        """
        Update a plugin.

        Args:
            plugin_id: Plugin slug ID
            **updates: Fields to update (name, code, description, etc.)

        Returns:
            {"ok": True, "plugin": {...}} or {"ok": False, "error": "…"}
        """
        # Get existing plugin
        existing = self.get_plugin(plugin_id)
        if not existing:
            return {"ok": False, "error": f"Plugin '{plugin_id}' not found"}

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Build update query dynamically
            allowed_fields = {
                "name",
                "description",
                "credits",
                "code",
                "source_url",
                "category",
                "tags",
                "returns_data",
                "timeout",
                "mcp_exposed",
                "unload_mode",
                "unload_code",
                "autorun",
                "autorun_domains",
                "engine",
                "proxy_config",
                "builtin",
            }

            set_clauses = []
            values = []

            for field, value in updates.items():
                if field not in allowed_fields:
                    continue

                if field == "tags":
                    value = json.dumps(value if isinstance(value, list) else [])
                elif field == "proxy_config":
                    value = json.dumps(value) if isinstance(value, dict) else value
                elif field in ("returns_data", "mcp_exposed", "autorun", "builtin"):
                    value = 1 if value else 0
                elif field == "unload_mode" and value not in ("toggle", "custom", "none"):
                    value = "none"

                set_clauses.append(f"{field} = ?")
                values.append(value)

            if not set_clauses:
                return {"ok": False, "error": "No valid fields to update"}

            # Always update updated_at
            set_clauses.append("updated_at = ?")
            values.append(int(time.time()))

            # If name changed, update ID too
            new_id = plugin_id
            if "name" in updates:
                new_id = generate_slug(updates["name"])
                if new_id != plugin_id:
                    # Check if new ID conflicts
                    cursor.execute(
                        "SELECT id FROM plugins WHERE id = ? AND id != ?",
                        (new_id, plugin_id),
                    )
                    if cursor.fetchone():
                        return {
                            "ok": False,
                            "error": f"Plugin with ID '{new_id}' already exists",
                        }
                    set_clauses.append("id = ?")
                    values.append(new_id)

            values.append(plugin_id)

            query = f"UPDATE plugins SET {', '.join(set_clauses)} WHERE id = ?"
            cursor.execute(query, values)
            conn.commit()

            # Return updated plugin
            updated = self.get_plugin(new_id)
            return {"ok": True, "plugin": updated}

        finally:
            conn.close()

    def delete_plugin(self, plugin_id: str) -> dict[str, Any]:
        """
        Delete a plugin.

        Args:
            plugin_id: Plugin slug ID

        Returns:
            {"ok": True, "deleted": True} or {"ok": False, "error": "…"}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM plugins WHERE id = ?", (plugin_id,))
            deleted = cursor.rowcount > 0
            conn.commit()

            if not deleted:
                return {"ok": False, "error": f"Plugin '{plugin_id}' not found"}

            return {"ok": True, "deleted": True, "id": plugin_id}

        finally:
            conn.close()

    def list_plugins(
        self,
        category: str | None = None,
        mcp_only: bool = False,
    ) -> list[dict[str, Any]]:
        """
        List all plugins with optional filtering.

        Args:
            category: Filter by category
            mcp_only: Only return MCP-exposed plugins

        Returns:
            List of plugin dicts
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            conditions = []
            values = []

            if category:
                conditions.append("category = ?")
                values.append(category)

            if mcp_only:
                conditions.append("mcp_exposed = 1")

            query = "SELECT * FROM plugins"
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY name ASC"

            cursor.execute(query, values)
            rows = cursor.fetchall()

            return [self._row_to_dict(row) for row in rows]

        finally:
            conn.close()

    def get_mcp_exposed(self) -> list[dict[str, Any]]:
        """
        Get all plugins exposed as MCP tools.

        Returns:
            List of MCP-exposed plugin dicts
        """
        return self.list_plugins(mcp_only=True)

    def get_categories(self) -> list[str]:
        """
        Get all unique categories.

        Returns:
            List of category strings
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT DISTINCT category FROM plugins WHERE category IS NOT NULL ORDER BY category"
            )
            return [row[0] for row in cursor.fetchall()]

        finally:
            conn.close()

    def get_all_tags(self) -> list[str]:
        """
        Get all unique tags across all plugins.

        Returns:
            List of tag strings
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT tags FROM plugins WHERE tags IS NOT NULL")
            all_tags: set[str] = set()

            for (tags_json,) in cursor.fetchall():
                try:
                    tags = json.loads(tags_json)
                    if isinstance(tags, list):
                        all_tags.update(tags)
                except json.JSONDecodeError:
                    continue

            return sorted(all_tags)

        finally:
            conn.close()

    def set_autorun(self, plugin_id: str, enabled: bool, domains: str | None = None) -> dict[str, Any]:
        """Toggle autorun for a plugin."""
        plugin = self.get_plugin(plugin_id)
        if not plugin:
            return {"ok": False, "error": f"Plugin '{plugin_id}' not found"}

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE plugins SET autorun = ?, autorun_domains = ?, updated_at = ? WHERE id = ?",
                (1 if enabled else 0, domains if enabled else plugin.get("autorun_domains"), int(time.time()), plugin_id),
            )
            conn.commit()
            return {"ok": True, "autorun": enabled}
        finally:
            conn.close()

    def get_autorun_plugins(self) -> list[dict[str, Any]]:
        """Get all plugins with autorun enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM plugins WHERE autorun = 1 ORDER BY name ASC")
            return [self._row_to_dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def increment_run_count(self, plugin_id: str) -> None:
        """Increment run count and update last_run_at for a plugin."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                UPDATE plugins
                SET run_count = run_count + 1, last_run_at = ?
                WHERE id = ?
            """,
                (int(time.time()), plugin_id),
            )
            conn.commit()
        finally:
            conn.close()

    def export_plugins(
        self, plugin_ids: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Export plugins to JSON format.

        Args:
            plugin_ids: Optional list of plugin IDs to export (all if None)

        Returns:
            {"ok": True, "data": {...}} with exportable JSON data
        """
        if plugin_ids:
            plugins = [
                p for p in self.list_plugins() if p["id"] in plugin_ids
            ]
        else:
            plugins = self.list_plugins()

        # Convert to export format (exclude internal fields)
        export_plugins = []
        for p in plugins:
            export_plugins.append({
                "id": p["id"],
                "name": p["name"],
                "description": p["description"],
                "credits": p["credits"],
                "code": p["code"],
                "source_url": p["source_url"],
                "category": p["category"],
                "tags": p["tags"],
                "returns_data": p["returns_data"],
                "mcp_exposed": p["mcp_exposed"],
                "unload_mode": p["unload_mode"],
                "unload_code": p["unload_code"],
            })

        from datetime import datetime

        export_data = {
            "version": "1.0",
            "exported_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "plugins": export_plugins,
        }

        return {"ok": True, "data": export_data, "count": len(export_plugins)}

    def import_plugins(
        self,
        data: dict[str, Any],
        conflict_mode: str = "skip",
    ) -> dict[str, Any]:
        """
        Import plugins from JSON data.

        Args:
            data: Export data with "plugins" array
            conflict_mode: "skip" (ignore conflicts) or "replace" (overwrite)

        Returns:
            {"ok": True, "imported": N, "skipped": N, "errors": [...]}
        """
        plugins = data.get("plugins", [])
        if not isinstance(plugins, list):
            return {"ok": False, "error": "Invalid import format: 'plugins' must be an array"}

        imported = 0
        skipped = 0
        errors: list[str] = []

        for plugin_data in plugins:
            name = plugin_data.get("name")
            code = plugin_data.get("code")

            if not name or not code:
                errors.append("Skipped plugin with missing name or code")
                skipped += 1
                continue

            # Check if exists
            existing = self.get_plugin_by_name(name)

            if existing:
                if conflict_mode == "skip":
                    skipped += 1
                    continue
                elif conflict_mode == "replace":
                    # Delete existing and re-add
                    self.delete_plugin(existing["id"])

            result = self.add_plugin(
                name=name,
                code=code,
                description=plugin_data.get("description"),
                credits=plugin_data.get("credits"),
                source_url=plugin_data.get("source_url"),
                category=plugin_data.get("category"),
                tags=plugin_data.get("tags", []),
                returns_data=plugin_data.get("returns_data", False),
                mcp_exposed=plugin_data.get("mcp_exposed", False),
                unload_mode=plugin_data.get("unload_mode", "none"),
                unload_code=plugin_data.get("unload_code"),
            )

            if result.get("ok"):
                imported += 1
            else:
                errors.append(f"Failed to import '{name}': {result.get('error')}")
                skipped += 1

        return {
            "ok": True,
            "imported": imported,
            "skipped": skipped,
            "total": len(plugins),
            "errors": errors if errors else None,
        }

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert a database row to a plugin dict."""
        tags_json = row["tags"]
        try:
            tags = json.loads(tags_json) if tags_json else []
        except json.JSONDecodeError:
            tags = []

        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "credits": row["credits"],
            "code": row["code"],
            "source_url": row["source_url"],
            "category": row["category"],
            "tags": tags,
            "returns_data": bool(row["returns_data"]),
            "timeout": row["timeout"],
            "mcp_exposed": bool(row["mcp_exposed"]),
            "unload_mode": row["unload_mode"] or "none",
            "unload_code": row["unload_code"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "run_count": row["run_count"],
            "last_run_at": row["last_run_at"],
            "autorun": bool(row["autorun"]),
            "autorun_domains": row["autorun_domains"],
            "engine": row["engine"] or "js",
            "proxy_config": json.loads(row["proxy_config"]) if row["proxy_config"] else {},
            "builtin": bool(row["builtin"]),
        }


# Global singleton instance
_plugin_service: PluginService | None = None


def get_plugin_service() -> PluginService:
    """Get the plugin service singleton."""
    global _plugin_service
    if _plugin_service is None:
        _plugin_service = PluginService()
    return _plugin_service
