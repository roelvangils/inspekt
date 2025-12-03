"""
Plugin command group - Manage custom JavaScript plugins (bookmarklets).

This module provides commands for plugin management:
- list: List all plugins
- add: Add a new plugin
- remove: Delete a plugin
- run: Execute a plugin in the browser
- unload: Unload/reverse a plugin's effects
- show: Display plugin details
- export: Export plugins to JSON file
- import: Import plugins from JSON file
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
import requests

from inspekt.services.plugin_service import get_plugin_service, parse_bookmarklet

# Bridge server defaults
BRIDGE_HTTP_HOST = "127.0.0.1"
BRIDGE_HTTP_PORT = 8765


@click.group()
def plugin():
    """Manage custom JavaScript plugins (bookmarklets)."""
    pass


@plugin.command(name="list")
@click.option("--category", "-c", help="Filter by category")
@click.option("--mcp", is_flag=True, help="Only show MCP-exposed plugins")
@click.option("--json", "-j", "output_json", is_flag=True, help="Output as JSON")
def plugin_list(category, mcp, output_json):
    """
    List all plugins.

    Shows all plugins with their metadata. Use --category to filter
    or --mcp to show only MCP-exposed plugins.

    Examples:
        inspekt plugin list
        inspekt plugin list --category a11y
        inspekt plugin list --mcp
        inspekt plugin list --json
    """
    try:
        plugin_service = get_plugin_service()
        plugins = plugin_service.list_plugins(category=category, mcp_only=mcp)

        if output_json:
            click.echo(json.dumps(plugins, indent=2))
        else:
            _display_plugins(plugins)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@plugin.command(name="add")
@click.argument("name")
@click.option("--code", "-c", help="JavaScript code")
@click.option("--file", "-f", "file_path", type=click.Path(exists=True), help="Read code from file")
@click.option("--url", "-u", help="Bookmarklet URL (javascript:...)")
@click.option("--description", "-d", help="Plugin description")
@click.option("--category", help="Category for organization")
@click.option("--tags", "-t", help="Comma-separated tags")
@click.option("--mcp", is_flag=True, help="Expose as MCP tool")
@click.option("--returns-data", is_flag=True, help="Plugin returns JSON data")
def plugin_add(name, code, file_path, url, description, category, tags, mcp, returns_data):
    """
    Add a new plugin.

    Provide code via --code, --file, or --url (bookmarklet).
    Bookmarklet URLs are automatically parsed and cleaned.

    Examples:
        inspekt plugin add "Dark Mode" --code "(function(){...})();"
        inspekt plugin add "Text Spacing" --url "javascript:(function(){...})();"
        inspekt plugin add "Custom" --file ./my-plugin.js --category utility
        inspekt plugin add "Extractor" --code "..." --returns-data --mcp
    """
    try:
        # Validate input sources
        sources = sum([bool(code), bool(file_path), bool(url)])
        if sources == 0:
            click.echo("Error: Provide code via --code, --file, or --url", err=True)
            sys.exit(1)
        if sources > 1:
            click.echo("Error: Provide only one of --code, --file, or --url", err=True)
            sys.exit(1)

        plugin_service = get_plugin_service()

        # Get code from source
        warnings = []
        if file_path:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
        elif url:
            code, warnings = parse_bookmarklet(url)
            if not code:
                click.echo("Error: Could not extract code from bookmarklet", err=True)
                sys.exit(1)

        # Parse tags
        tag_list = [t.strip() for t in tags.split(",")] if tags else None

        result = plugin_service.add_plugin(
            name=name,
            code=code,
            description=description,
            source_url=url if url else None,
            category=category,
            tags=tag_list,
            returns_data=returns_data,
            mcp_exposed=mcp,
        )

        if result.get("ok"):
            plugin_data = result["plugin"]
            click.echo(f"Plugin added: {plugin_data['name']} (id: {plugin_data['id']})")

            if warnings:
                for w in warnings:
                    click.echo(f"  Note: {w}")

            if mcp:
                click.echo(f"  MCP tool: plugin_{plugin_data['id']}")
        else:
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@plugin.command(name="remove")
@click.argument("name_or_id")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def plugin_remove(name_or_id, force):
    """
    Remove a plugin.

    Accepts plugin name or ID. Use --force to skip confirmation.

    Examples:
        inspekt plugin remove text-spacing
        inspekt plugin remove "Text Spacing Bookmarklet"
        inspekt plugin remove dark-mode --force
    """
    try:
        plugin_service = get_plugin_service()

        # Try to find plugin by ID first, then by name
        plugin_data = plugin_service.get_plugin(name_or_id)
        if not plugin_data:
            plugin_data = plugin_service.get_plugin_by_name(name_or_id)

        if not plugin_data:
            click.echo(f"Error: Plugin '{name_or_id}' not found", err=True)
            sys.exit(1)

        if not force:
            if not click.confirm(f"Delete plugin '{plugin_data['name']}'?"):
                click.echo("Cancelled")
                return

        result = plugin_service.delete_plugin(plugin_data["id"])

        if result.get("ok"):
            click.echo(f"Plugin removed: {plugin_data['name']}")
        else:
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@plugin.command(name="run")
@click.argument("name_or_id")
@click.option("--timeout", "-t", type=int, default=30, help="Execution timeout (seconds)")
@click.option("--json", "-j", "output_json", is_flag=True, help="Output result as JSON")
@click.option("--quiet", "-q", is_flag=True, help="Suppress console output")
def plugin_run(name_or_id, timeout, output_json, quiet):
    """
    Execute a plugin in the browser.

    Runs the plugin code in the current browser tab and captures
    console output. If the plugin returns data, it's displayed.

    Examples:
        inspekt plugin run text-spacing
        inspekt plugin run "Dark Mode" --timeout 10
        inspekt plugin run extractor --json
    """
    try:
        plugin_service = get_plugin_service()

        # Find plugin
        plugin_data = plugin_service.get_plugin(name_or_id)
        if not plugin_data:
            plugin_data = plugin_service.get_plugin_by_name(name_or_id)

        if not plugin_data:
            click.echo(f"Error: Plugin '{name_or_id}' not found", err=True)
            sys.exit(1)

        # Execute via API
        result = _execute_plugin(
            plugin_data["code"],
            timeout=timeout or plugin_data.get("timeout", 30),
            capture_console=not quiet,
            returns_data=plugin_data.get("returns_data", False),
        )

        # Update run count
        plugin_service.increment_run_count(plugin_data["id"])

        if output_json:
            click.echo(json.dumps(result, indent=2))
        else:
            if result.get("ok"):
                click.echo(f"Plugin executed: {plugin_data['name']}")

                # Show execution time
                if result.get("execution_time_ms"):
                    click.echo(f"  Time: {result['execution_time_ms']}ms")

                # Show return value if present
                if result.get("result") is not None:
                    click.echo(f"  Result: {json.dumps(result['result'], indent=2)}")

                # Show console output
                console = result.get("console_output", [])
                if console and not quiet:
                    click.echo(f"  Console ({len(console)} entries):")
                    for entry in console[-10:]:  # Show last 10
                        level = entry.get("level", "log")
                        msg = entry.get("message", "")
                        color = {"error": "red", "warn": "yellow"}.get(level)
                        prefix = f"    [{level}] "
                        click.echo(click.style(prefix, fg=color) + msg)
            else:
                click.echo(f"Error: {result.get('error')}", err=True)
                sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@plugin.command(name="unload")
@click.argument("name_or_id")
@click.option("--timeout", "-t", type=int, default=30, help="Execution timeout (seconds)")
@click.option("--json", "-j", "output_json", is_flag=True, help="Output result as JSON")
@click.option("--quiet", "-q", is_flag=True, help="Suppress console output")
def plugin_unload(name_or_id, timeout, output_json, quiet):
    """
    Unload/reverse a plugin's effects.

    Behavior depends on the plugin's unload mode:
    - toggle: Re-runs the plugin code (for toggle-style plugins)
    - custom: Runs the custom unload code
    - none: Returns error (plugin doesn't support unloading)

    Examples:
        inspekt plugin unload text-spacing
        inspekt plugin unload "Dark Mode"
    """
    try:
        plugin_service = get_plugin_service()

        # Find plugin
        plugin_data = plugin_service.get_plugin(name_or_id)
        if not plugin_data:
            plugin_data = plugin_service.get_plugin_by_name(name_or_id)

        if not plugin_data:
            click.echo(f"Error: Plugin '{name_or_id}' not found", err=True)
            sys.exit(1)

        unload_mode = plugin_data.get("unload_mode", "none")

        if unload_mode == "none":
            click.echo(f"Error: Plugin '{plugin_data['name']}' does not support unloading", err=True)
            sys.exit(1)

        # Determine which code to run
        if unload_mode == "toggle":
            code_to_run = plugin_data["code"]
            action = "toggled"
        elif unload_mode == "custom":
            code_to_run = plugin_data.get("unload_code")
            if not code_to_run:
                click.echo(f"Error: Plugin has custom unload mode but no unload code", err=True)
                sys.exit(1)
            action = "unloaded"
        else:
            click.echo(f"Error: Unknown unload mode: {unload_mode}", err=True)
            sys.exit(1)

        # Execute unload code
        result = _execute_plugin(
            code_to_run,
            timeout=timeout or plugin_data.get("timeout", 30),
            capture_console=not quiet,
            returns_data=plugin_data.get("returns_data", False),
        )

        if output_json:
            click.echo(json.dumps(result, indent=2))
        else:
            if result.get("ok"):
                click.echo(f"Plugin {action}: {plugin_data['name']}")

                if result.get("execution_time_ms"):
                    click.echo(f"  Time: {result['execution_time_ms']}ms")

                console = result.get("console_output", [])
                if console and not quiet:
                    click.echo(f"  Console ({len(console)} entries):")
                    for entry in console[-10:]:
                        level = entry.get("level", "log")
                        msg = entry.get("message", "")
                        color = {"error": "red", "warn": "yellow"}.get(level)
                        prefix = f"    [{level}] "
                        click.echo(click.style(prefix, fg=color) + msg)
            else:
                click.echo(f"Error: {result.get('error')}", err=True)
                sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@plugin.command(name="show")
@click.argument("name_or_id")
@click.option("--json", "-j", "output_json", is_flag=True, help="Output as JSON")
def plugin_show(name_or_id, output_json):
    """
    Display plugin details.

    Shows full plugin information including code.

    Examples:
        inspekt plugin show text-spacing
        inspekt plugin show "Dark Mode" --json
    """
    try:
        plugin_service = get_plugin_service()

        # Find plugin
        plugin_data = plugin_service.get_plugin(name_or_id)
        if not plugin_data:
            plugin_data = plugin_service.get_plugin_by_name(name_or_id)

        if not plugin_data:
            click.echo(f"Error: Plugin '{name_or_id}' not found", err=True)
            sys.exit(1)

        if output_json:
            click.echo(json.dumps(plugin_data, indent=2))
        else:
            _display_plugin_details(plugin_data)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@plugin.command(name="export")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--ids", help="Comma-separated plugin IDs to export")
def plugin_export(output, ids):
    """
    Export plugins to JSON file.

    Exports all plugins or specific ones to a JSON file
    that can be shared and imported.

    Examples:
        inspekt plugin export
        inspekt plugin export --output my-plugins.json
        inspekt plugin export --ids text-spacing,dark-mode
    """
    try:
        plugin_service = get_plugin_service()
        plugin_ids = [id.strip() for id in ids.split(",")] if ids else None

        result = plugin_service.export_plugins(plugin_ids)

        if not result.get("ok"):
            click.echo(f"Error: Export failed", err=True)
            sys.exit(1)

        export_data = result["data"]
        json_str = json.dumps(export_data, indent=2)

        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(json_str)
            click.echo(f"Exported {result['count']} plugin(s) to {output}")
        else:
            click.echo(json_str)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@plugin.command(name="import")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--replace", is_flag=True, help="Replace existing plugins with same name")
@click.option("--skip", is_flag=True, default=True, help="Skip existing plugins (default)")
def plugin_import(file_path, replace, skip):
    """
    Import plugins from JSON file.

    Imports plugins from an export file. By default, existing
    plugins with the same name are skipped.

    Examples:
        inspekt plugin import plugins.json
        inspekt plugin import plugins.json --replace
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        plugin_service = get_plugin_service()
        conflict_mode = "replace" if replace else "skip"

        result = plugin_service.import_plugins(data, conflict_mode=conflict_mode)

        if result.get("ok"):
            click.echo(f"Imported {result['imported']} plugin(s)")
            if result.get("skipped"):
                click.echo(f"  Skipped {result['skipped']} (already exist)")
            if result.get("errors"):
                click.echo("  Errors:")
                for err in result["errors"]:
                    click.echo(f"    - {err}")
        else:
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

    except json.JSONDecodeError:
        click.echo("Error: Invalid JSON file", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# Helper Functions
# ============================================================================


def _execute_plugin(
    code: str,
    timeout: float = 30.0,
    capture_console: bool = True,
    returns_data: bool = False,
) -> dict:
    """Execute plugin code via the bridge server."""
    import time

    start_time = time.time()

    try:
        # Clear console before execution
        if capture_console:
            try:
                requests.post(
                    f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/console/clear",
                    timeout=5.0,
                )
            except requests.exceptions.RequestException:
                pass

        # Execute code
        response = requests.post(
            f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/run",
            json={"code": code, "timeout": timeout},
            timeout=timeout + 5,
        )

        execution_time_ms = int((time.time() - start_time) * 1000)

        if response.status_code != 200:
            return {
                "ok": False,
                "error": f"Bridge returned HTTP {response.status_code}",
                "execution_time_ms": execution_time_ms,
            }

        result_data = response.json()

        # Capture console output
        console_output = []
        if capture_console:
            try:
                console_response = requests.get(
                    f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/console/logs",
                    timeout=5.0,
                )
                if console_response.status_code == 200:
                    console_data = console_response.json()
                    console_output = console_data.get("entries", [])
            except requests.exceptions.RequestException:
                pass

        if not result_data.get("ok"):
            return {
                "ok": False,
                "error": result_data.get("error", "Execution failed"),
                "console_output": console_output,
                "execution_time_ms": execution_time_ms,
            }

        return {
            "ok": True,
            "result": result_data.get("result") if returns_data else None,
            "console_output": console_output,
            "execution_time_ms": execution_time_ms,
        }

    except requests.exceptions.ConnectionError:
        return {
            "ok": False,
            "error": "Could not connect to bridge server. Run: inspekt start",
        }
    except requests.exceptions.Timeout:
        return {
            "ok": False,
            "error": f"Execution timed out after {timeout} seconds",
        }


def _display_plugins(plugins: list[dict]) -> None:
    """Display plugins in table format."""
    from inspekt.app.cli.table import Table

    if not plugins:
        table = Table(["Name", "Category", "MCP", "Runs"], [30, 15, 5, 8])
        table.print_empty_message("No plugins found")
        return

    click.echo(f"Plugins ({len(plugins)}):")
    click.echo()

    table = Table(
        headers=["Name", "Category", "MCP", "Runs"],
        widths=[30, 15, 5, 8],
        alignments=["left", "left", "center", "right"],
    )

    table.print_header()

    for p in plugins:
        mcp_indicator = "*" if p.get("mcp_exposed") else ""
        table.print_row([
            p["name"][:30],
            (p.get("category") or "-")[:15],
            mcp_indicator,
            str(p.get("run_count", 0)),
        ])

    table.print_footer()

    # Legend
    mcp_count = sum(1 for p in plugins if p.get("mcp_exposed"))
    if mcp_count:
        click.echo(f"\n  * = MCP tool ({mcp_count} exposed)")


def _display_plugin_details(plugin: dict) -> None:
    """Display detailed plugin information."""
    click.echo(f"Plugin: {plugin['name']}")
    click.echo(f"  ID: {plugin['id']}")

    if plugin.get("description"):
        click.echo(f"  Description: {plugin['description']}")

    if plugin.get("category"):
        click.echo(f"  Category: {plugin['category']}")

    if plugin.get("tags"):
        click.echo(f"  Tags: {', '.join(plugin['tags'])}")

    click.echo(f"  Returns data: {'Yes' if plugin.get('returns_data') else 'No'}")
    click.echo(f"  Timeout: {plugin.get('timeout', 30)}s")
    click.echo(f"  MCP exposed: {'Yes' if plugin.get('mcp_exposed') else 'No'}")

    if plugin.get("mcp_exposed"):
        click.echo(f"  MCP tool name: plugin_{plugin['id']}")

    # Unload behavior
    unload_mode = plugin.get("unload_mode", "none")
    unload_labels = {
        "toggle": "Toggle (run again to unload)",
        "custom": "Custom unload code",
        "none": "Not reversible",
    }
    click.echo(f"  Unload: {unload_labels.get(unload_mode, unload_mode)}")

    click.echo(f"  Run count: {plugin.get('run_count', 0)}")

    if plugin.get("last_run_at"):
        dt = datetime.fromtimestamp(plugin["last_run_at"], tz=timezone.utc)
        click.echo(f"  Last run: {dt.astimezone().strftime('%Y-%m-%d %H:%M')}")

    if plugin.get("source_url"):
        click.echo(f"  Source URL: {plugin['source_url'][:60]}...")

    # Show code preview
    code = plugin.get("code", "")
    click.echo(f"\n  Code ({len(code)} chars):")
    lines = code.split("\n")[:10]  # First 10 lines
    for line in lines:
        click.echo(f"    {line[:80]}")
    if len(code.split("\n")) > 10:
        click.echo("    ...")

    # Show unload code if custom mode
    if unload_mode == "custom" and plugin.get("unload_code"):
        unload_code = plugin["unload_code"]
        click.echo(f"\n  Unload code ({len(unload_code)} chars):")
        lines = unload_code.split("\n")[:5]
        for line in lines:
            click.echo(f"    {line[:80]}")
        if len(unload_code.split("\n")) > 5:
            click.echo("    ...")
