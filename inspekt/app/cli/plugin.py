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
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
import requests

from inspekt.app.cli.output import OutputHandler
from inspekt.services.plugin_service import get_plugin_service, parse_bookmarklet

# Bridge server defaults
BRIDGE_HTTP_HOST = "127.0.0.1"
BRIDGE_HTTP_PORT = 8765


def complete_plugin_names(ctx, param, incomplete):
    """Shell completion for plugin names/IDs."""
    try:
        plugin_service = get_plugin_service()
        plugins = plugin_service.list_plugins()

        matches = []
        for p in plugins:
            # Include both name and ID for completion
            name = p.get("name", "")
            plugin_id = p.get("id", "")

            # Match on name (case-insensitive)
            if incomplete.lower() in name.lower():
                matches.append(name)
            # Match on ID
            elif incomplete.lower() in plugin_id.lower():
                matches.append(plugin_id)

        return sorted(set(matches))
    except Exception:
        return []


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
@click.option("--autorun", is_flag=True, help="Enable autorun on page load")
@click.option("--domains", help="Comma-separated domain patterns for autorun")
@click.option("--update", is_flag=True, help="Update if plugin already exists")
def plugin_add(name, code, file_path, url, description, category, tags, mcp, returns_data, autorun, domains, update):
    """
    Add a new plugin.

    Provide code via --code, --file, or --url (bookmarklet).
    Bookmarklet URLs are automatically parsed and cleaned.
    Use --update to overwrite an existing plugin with the same name.

    Examples:
        inspekt plugin add "Dark Mode" --code "(function(){...})();"
        inspekt plugin add "Text Spacing" --url "javascript:(function(){...})();"
        inspekt plugin add "Custom" --file ./my-plugin.js --category utility
        inspekt plugin add "Extractor" --code "…" --returns-data --mcp
        inspekt plugin add "Dark Mode" --code "…" --update
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
            autorun=autorun,
            autorun_domains=domains,
        )

        if result.get("ok"):
            plugin_data = result["plugin"]
            click.echo(f"Plugin added: {plugin_data['name']} (id: {plugin_data['id']})")

            if warnings:
                for w in warnings:
                    click.echo(f"  Note: {w}")

            if mcp:
                click.echo(f"  MCP tool: plugin_{plugin_data['id']}")
        elif update and "already exists" in result.get("error", ""):
            # Update existing plugin
            from inspekt.services.plugin_service import generate_slug

            plugin_id = generate_slug(name)
            updates = {"code": code}
            if description is not None:
                updates["description"] = description
            if category is not None:
                updates["category"] = category
            if tag_list is not None:
                updates["tags"] = tag_list
            if url:
                updates["source_url"] = url
            if returns_data:
                updates["returns_data"] = returns_data
            if mcp:
                updates["mcp_exposed"] = mcp

            update_result = plugin_service.update_plugin(plugin_id, **updates)
            if update_result.get("ok"):
                plugin_data = update_result["plugin"]
                click.echo(f"Plugin updated: {plugin_data['name']} (id: {plugin_data['id']})")
            else:
                click.echo(f"Error: {update_result.get('error')}", err=True)
                sys.exit(1)
        else:
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@plugin.command(name="remove")
@click.argument("name_or_id", shell_complete=complete_plugin_names)
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
@click.argument("name_or_id", required=False, default=None, shell_complete=complete_plugin_names)
@click.option("--interactive", "-i", is_flag=True, help="Browse and select plugin interactively")
@click.option("--category", "-c", help="Filter by category (with --interactive)")
@click.option("--timeout", "-t", type=int, default=30, help="Execution timeout (seconds)")
@click.option("--json", "-j", "output_json", is_flag=True, help="Output result as JSON")
@click.option("--quiet", "-q", is_flag=True, help="Suppress console output")
def plugin_run(name_or_id, interactive, category, timeout, output_json, quiet):
    """
    Execute a plugin in the browser.

    Runs the plugin code in the current browser tab and captures
    console output. If the plugin returns data, it's displayed.

    Examples:
        inspekt plugin run text-spacing
        inspekt plugin run "Dark Mode" --timeout 10
        inspekt plugin run extractor --json
        inspekt plugin run --interactive
        inspekt plugin run -i --category a11y
    """
    try:
        if interactive:
            name_or_id = _interactive_plugin_select(category=category)
            if name_or_id is None:
                return  # User cancelled
        elif name_or_id is None:
            raise click.UsageError(
                "Missing argument 'NAME_OR_ID'. Use --interactive to browse plugins."
            )

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
                from inspekt.app.cli.icons import get_icon
                from inspekt.app.cli.table import print_hint, print_success

                # Get page context for richer feedback
                page_title = None
                page_url = None
                try:
                    from inspekt.client import BridgeClient

                    client = BridgeClient()
                    page_result = client.execute("({url: location.href, title: document.title})")
                    if page_result.get("ok"):
                        page_data = page_result.get("result", {})
                        page_title = page_data.get("title")
                        page_url = page_data.get("url")
                except Exception:
                    pass

                # Success message with plugin icon
                icon = get_icon("Plugin")
                time_ms = result.get("execution_time_ms", 0)
                run_count = plugin_data.get("run_count", 0) + 1
                print_success(f"{icon} `{plugin_data['name']}` executed in {time_ms}ms (run #{run_count})")

                # Show page context
                if page_title or page_url:
                    display = page_title or page_url
                    if len(display) > 60:
                        display = display[:57] + "…"
                    click.secho(f"  on {display}", fg="bright_black")

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

                # Show unload hint if plugin supports it
                unload_mode = plugin_data.get("unload_mode", "none")
                if unload_mode != "none":
                    print_hint(f"Run `inspekt plugin unload {plugin_data['id']}` to reverse")
            else:
                click.echo(f"Error: {result.get('error')}", err=True)
                sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@plugin.command(name="unload")
@click.argument("name_or_id", shell_complete=complete_plugin_names)
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
@click.argument("name_or_id", shell_complete=complete_plugin_names)
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


@plugin.command(name="autorun")
@click.argument("name_or_id", shell_complete=complete_plugin_names)
@click.option("--domains", "-d", help="Comma-separated domain/path patterns (e.g. 'github.com, *.gitlab.com')")
@click.option("--off", is_flag=True, help="Disable autorun for this plugin")
def plugin_autorun(name_or_id, domains, off):
    """
    Enable or disable autorun for a plugin.

    When autorun is enabled, the plugin executes automatically on every
    page load. Use --domains to restrict to specific domains.

    Domain patterns:
        github.com          Match github.com and www.github.com
        *.github.com        Match any subdomain of github.com
        github.com/org/*    Match path prefix on github.com

    Examples:
        inspekt plugin autorun dark-mode
        inspekt plugin autorun dark-mode --domains "github.com, *.gitlab.com"
        inspekt plugin autorun dark-mode --off
    """
    from inspekt.app.cli.table import print_hint, print_success

    try:
        plugin_service = get_plugin_service()

        # Find plugin
        plugin_data = plugin_service.get_plugin(name_or_id)
        if not plugin_data:
            plugin_data = plugin_service.get_plugin_by_name(name_or_id)

        if not plugin_data:
            click.echo(f"Error: Plugin '{name_or_id}' not found", err=True)
            sys.exit(1)

        if off:
            result = plugin_service.update_plugin(
                plugin_data["id"], autorun=False, autorun_domains=None
            )
            if result.get("ok"):
                print_success(f"Autorun disabled for `{plugin_data['name']}`")
            else:
                click.echo(f"Error: {result.get('error')}", err=True)
                sys.exit(1)
        else:
            updates = {"autorun": True}
            if domains is not None:
                updates["autorun_domains"] = domains
            elif not plugin_data.get("autorun"):
                # First time enabling — no domains means all pages
                updates["autorun_domains"] = None

            result = plugin_service.update_plugin(plugin_data["id"], **updates)
            if result.get("ok"):
                plugin_updated = result["plugin"]
                domain_str = plugin_updated.get("autorun_domains")
                if domain_str:
                    print_success(f"Autorun enabled for `{plugin_data['name']}` on: {domain_str}")
                else:
                    print_success(f"Autorun enabled for `{plugin_data['name']}` on all pages")
                print_hint("Plugin will auto-execute on every page load")
            else:
                click.echo(f"Error: {result.get('error')}", err=True)
                sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@plugin.command(name="export")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--ids", help="Comma-separated plugin IDs to export")
@click.option("--open", "open_after", is_flag=True, help="Open exported file in default application")
@click.option("--reveal", "reveal_after", is_flag=True, help="Reveal exported file in file explorer")
def plugin_export(output, ids, open_after, reveal_after):
    """
    Export plugins to JSON file.

    Exports all plugins or specific ones to a JSON file
    that can be shared and imported.

    Examples:
        inspekt plugin export
        inspekt plugin export --output my-plugins.json
        inspekt plugin export --ids text-spacing,dark-mode
        inspekt plugin export -o plugins.json --open
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

            # Open file if --open flag was set
            if open_after:
                OutputHandler.open_file(output)

            # Reveal file if --reveal flag was set
            if reveal_after:
                OutputHandler.reveal_file(output)
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


def _interactive_plugin_select(category: str | None = None) -> str | None:
    """Launch gum filter for interactive plugin selection. Returns plugin ID or None if cancelled."""
    from inspekt.app.cli.table import print_error, print_hint

    if not shutil.which("gum"):
        print_error("gum is not installed (needed for interactive mode)")
        print_hint("Install with `brew install gum` or see https://github.com/charmbracelet/gum")
        sys.exit(1)

    plugin_service = get_plugin_service()
    plugins = plugin_service.list_plugins(category=category)

    if not plugins:
        label = f" in category '{category}'" if category else ""
        print_error(f"No plugins found{label}")
        print_hint("Add plugins with `inspekt plugin add`")
        return None

    # Build display lines and a mapping back to plugin IDs
    display_map: dict[str, str] = {}
    lines = []
    for p in plugins:
        desc = p.get("description") or ""
        if len(desc) > 50:
            desc = desc[:47] + "…"
        cat = p.get("category")
        if desc and cat:
            line = f"{p['name']} ({cat}) — {desc}"
        elif desc:
            line = f"{p['name']} — {desc}"
        elif cat:
            line = f"{p['name']} ({cat})"
        else:
            line = p["name"]
        display_map[line] = p["id"]
        lines.append(line)

    header = f"Select a plugin ({len(lines)} available)"
    if category:
        header = f"Select a plugin in '{category}' ({len(lines)} available)"

    try:
        result = subprocess.run(
            [
                "gum", "filter",
                "--header", header,
                "--placeholder", "Type to search…",
                "--height", str(max(10, min(len(lines) + 2, 20))),
                "--header.foreground", "39",
                "--indicator.foreground", "39",
                "--match.foreground", "39",
            ],
            input="\n".join(lines),
            stdout=subprocess.PIPE,
            text=True,
        )
    except OSError as e:
        print_error(f"Failed to launch gum: {e}")
        sys.exit(1)

    if result.returncode != 0 or not result.stdout.strip():
        click.echo("Cancelled")
        return None

    selected_line = result.stdout.strip()
    return display_map.get(selected_line)


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
    """Display plugins in table format with auto-width columns and title bar."""
    from inspekt.app.cli.icons import get_icon
    from inspekt.app.cli.table import Table

    headers = ["Name", "Category", "MCP", "Auto", "Runs"]
    alignments = ["left", "left", "center", "center", "right"]
    title = f"Plugins ({len(plugins)})"
    icon = get_icon("Plugins")

    if not plugins:
        # For empty tables, use minimum widths based on headers
        table = Table(headers, alignments=alignments, title=title, icon=icon)
        table.set_data([])  # Empty data, widths based on headers
        table.print_empty_message("No plugins found")
        return

    click.echo()

    # Build all rows first for auto-width calculation
    rows = []
    for p in plugins:
        mcp_indicator = "*" if p.get("mcp_exposed") else ""
        auto_indicator = "*" if p.get("autorun") else ""
        rows.append([
            p["name"],
            p.get("category") or "-",
            mcp_indicator,
            auto_indicator,
            str(p.get("run_count", 0)),
        ])

    table = Table(headers, alignments=alignments, title=title, icon=icon)
    table.set_data(rows)
    table.print_header()

    for row in rows:
        table.print_row(row)

    table.print_footer()

    # Legend
    mcp_count = sum(1 for p in plugins if p.get("mcp_exposed"))
    auto_count = sum(1 for p in plugins if p.get("autorun"))
    legends = []
    if mcp_count:
        legends.append(f"MCP * = MCP tool ({mcp_count} exposed)")
    if auto_count:
        legends.append(f"Auto * = autorun ({auto_count} enabled)")
    if legends:
        click.echo(f"\n  {' | '.join(legends)}")


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

    # Autorun
    if plugin.get("autorun"):
        domains = plugin.get("autorun_domains")
        if domains:
            click.echo(f"  Autorun: Yes (domains: {domains})")
        else:
            click.echo(f"  Autorun: Yes (all pages)")
    else:
        click.echo(f"  Autorun: No")

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
        click.echo(f"  Source URL: {plugin['source_url'][:60]}…")

    # Show code preview
    code = plugin.get("code", "")
    click.echo(f"\n  Code ({len(code)} chars):")
    lines = code.split("\n")[:10]  # First 10 lines
    for line in lines:
        click.echo(f"    {line[:80]}")
    if len(code.split("\n")) > 10:
        click.echo("    …")

    # Show unload code if custom mode
    if unload_mode == "custom" and plugin.get("unload_code"):
        unload_code = plugin["unload_code"]
        click.echo(f"\n  Unload code ({len(unload_code)} chars):")
        lines = unload_code.split("\n")[:5]
        for line in lines:
            click.echo(f"    {line[:80]}")
        if len(unload_code.split("\n")) > 5:
            click.echo("    …")
