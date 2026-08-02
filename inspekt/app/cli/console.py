"""
Console command group - Capture and manage browser console messages.

This module provides commands for browser console message management:
- list: Show captured console messages (log, error, warn, info, debug)
- clear: Clear the console message buffer

Console messages are captured by hooks injected into the page when it loads.
Messages are stored in a buffer in the browser (max 1000 messages) and can be
retrieved via the CLI.

Note: Only messages logged AFTER the page load are captured. Messages logged
during initial page load may not be captured.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime

import click

from inspekt.app.cli.icons import get_indicator, get_log_level_icon, success
from inspekt.app.cli.table import Table
from inspekt.client import BridgeClient


def render_console_table(table_json: str) -> None:
    """Render a console.table() as a formatted table with auto-width columns."""
    try:
        data = json.loads(table_json)
        rows = data.get("data", [])
        columns = data.get("columns")

        if not rows:
            click.echo("           (empty table)")
            return

        # Convert to list if object
        if isinstance(rows, dict):
            rows = [{"key": k, "value": v} for k, v in rows.items()]

        # Handle primitive arrays
        if rows and not isinstance(rows[0], dict):
            rows = [{"#": i, "value": v} for i, v in enumerate(rows)]
            columns = ["#", "value"]
        else:
            # Get column headers for object arrays
            if not columns:
                columns = list(dict.fromkeys(k for row in rows for k in (row.keys() if isinstance(row, dict) else [])))
            # Add index column and index value to each row
            columns = ["#"] + columns
            rows = [{"#": i, **row} for i, row in enumerate(rows)]

        # Build row data for auto-width calculation
        table_rows = []
        for row in rows:
            values = [str(row.get(col, "")) for col in columns]
            table_rows.append(values)

        # Create table with auto-width (terminal-aware)
        table = Table(columns)
        table.set_data(table_rows)
        table.print_header()

        for row_values in table_rows:
            table.print_row(row_values)
        table.print_footer()

    except Exception as e:
        click.echo(f"           [table] (parse error: {e})")

# Bridge server defaults
BRIDGE_HTTP_HOST = "127.0.0.1"
BRIDGE_HTTP_PORT = 8765


@click.group()
def console():
    """Browser console message commands."""
    pass


@console.command(name="list")
@click.option(
    '--level', '-l',
    type=click.Choice(['all', 'error', 'warn', 'log', 'info', 'debug']),
    default='all',
    help='Filter by log level (default: all)'
)
@click.option(
    '--limit', '-n',
    type=int,
    default=100,
    help='Maximum number of messages to show (default: 100)'
)
@click.option(
    '--json', '-j', 'output_json',
    is_flag=True,
    help='Output as JSON'
)
@click.option(
    '--tail', '-t',
    is_flag=True,
    help='Show most recent messages first'
)
def list_logs(level, limit, output_json, tail):
    """
    Show captured console messages from the browser.

    Displays console.log, console.error, console.warn, console.info, and
    console.debug messages that were captured since the page loaded.

    Messages are captured automatically when pages load. Use --level to
    filter by severity and --limit to control how many messages to show.

    Examples:
        inspekt console list
        inspekt console list --level error
        inspekt console list --limit 50 --tail
        inspekt console list --json | jq '.entries[].message'
    """
    try:
        client = BridgeClient()

        if not client.is_alive():
            if output_json:
                click.echo(json.dumps({
                    "ok": False,
                    "error": "Bridge server is not running"
                }))
            else:
                from inspekt.app.cli.table import _style_with_inline_code
                click.echo(
                    _style_with_inline_code("Error: Bridge server is not running. Start it with `inspekt start`.", base_fg="red"),
                    err=True
                )
            sys.exit(1)

        # Use session for HTTP requests
        import requests
        url = f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/console/logs"

        response = requests.get(url, timeout=15)
        data = response.json()

        if not data.get("ok"):
            error_msg = data.get("error", "Failed to get console logs")
            if output_json:
                click.echo(json.dumps({"ok": False, "error": error_msg}))
            else:
                click.echo(f"Error: {error_msg}", err=True)
            sys.exit(1)

        entries = data.get("entries", [])
        hooked = data.get("hooked", False)

        # Filter by level if specified
        if level != 'all':
            entries = [e for e in entries if e.get("level") == level]

        # Sort by timestamp (newest first if tail, oldest first otherwise)
        entries.sort(key=lambda e: e.get("timestamp", ""), reverse=tail)

        # Apply limit
        if limit and limit > 0:
            entries = entries[:limit]

        if output_json:
            # Filter out command markers from JSON output
            json_entries = [e for e in entries if not e.get("message", "").startswith("[inspekt:cmd]")]
            from inspekt.app.cli.table import print_json
            print_json(
                {"ok": True, "count": len(json_entries), "entries": json_entries, "hooked": hooked},
                summary=f"{len(json_entries)} console log entries",
            )
        else:
            if not hooked:
                click.echo("Note: Console hooks not active. Reload the page to start capturing.", err=True)
                click.echo("", err=True)

            if not entries:
                click.echo("No console messages captured.")
                return

            # Format and display messages
            level_colors = {
                'error': 'red',
                'warn': 'yellow',
                'log': 'white',
                'info': 'cyan',
                'debug': 'bright_black'
            }

            for entry in entries:
                entry_level = entry.get("level", "log")
                timestamp = entry.get("timestamp", "")
                message = entry.get("message", "")

                # Parse timestamp for display (convert UTC to local time)
                time_str = ""
                if timestamp:
                    try:
                        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                        # Convert to local timezone
                        local_dt = dt.astimezone()
                        time_str = local_dt.strftime("%H:%M:%S")
                    except (ValueError, TypeError):
                        time_str = timestamp[:8] if len(timestamp) > 8 else timestamp

                color = level_colors.get(entry_level, 'white')

                # Get log level icon (if nerdfont enabled)
                level_icon = get_log_level_icon(entry_level)
                level_display = f"{level_icon} [{entry_level}]" if level_icon else f"[{entry_level}]"

                # Check for special table format
                if message.startswith('[table:json]'):
                    click.echo(
                        f"{click.style(time_str, dim=True)} "
                        f"{click.style(level_display, fg=color)} "
                        f"{click.style('[table]', fg='blue')}"
                    )
                    render_console_table(message[12:])  # Skip '[table:json]' prefix
                    continue

                # Check for command marker (from inspekt eval)
                if message.startswith('[inspekt:cmd]'):
                    cmd_text = message[13:]  # Skip '[inspekt:cmd]' prefix
                    cmd_icon = get_indicator("command") or "▸"
                    click.echo(
                        f"{click.style(time_str, dim=True)} "
                        f"{click.style(cmd_icon, fg='green')} "
                        f"{click.style(cmd_text, fg='green')}"
                    )
                    continue

                # Colorize special prefixes
                prefix_colors = {
                    '[dir]': 'blue',
                    '[trace]': 'magenta',
                    '[group]': 'cyan',
                    '[assert]': 'red',
                    '[clear]': 'bright_black',
                }
                display_message = message
                for prefix, prefix_color in prefix_colors.items():
                    if message.startswith(prefix):
                        display_message = click.style(prefix, fg=prefix_color) + message[len(prefix):]
                        break

                # Colorize special values
                if display_message == '(empty)':
                    display_message = click.style('(empty)', dim=True)
                elif display_message == 'undefined':
                    display_message = click.style('undefined', dim=True)
                elif display_message == 'null':
                    display_message = click.style('null', dim=True)
                elif display_message in ('NaN', 'Infinity', '-Infinity'):
                    display_message = click.style(display_message, fg='yellow')

                # Truncate very long single-line messages, but keep multiline intact
                if '\n' not in message and len(message) > 200 and not output_json:
                    display_message = message[:200] + "…"

                click.echo(
                    f"{click.style(time_str, dim=True)} "
                    f"{click.style(level_display, fg=color)} "
                    f"{display_message}"
                )

            # VM terminal: offer a "Data ready to copy" toast
            from inspekt.app.cli.table import emit_copyable_data
            rows = [
                [e.get("timestamp", ""), e.get("level", ""), e.get("message", "")]
                for e in entries if not e.get("message", "").startswith("[inspekt:cmd]")
            ]
            emit_copyable_data(
                headers=["Timestamp", "Level", "Message"],
                rows=rows,
                json_data={"entries": entries, "count": len(entries), "hooked": hooked},
                summary=f"{len(rows)} console message{'s' if len(rows) != 1 else ''}",
            )

    except requests.exceptions.ConnectionError:
        if output_json:
            click.echo(json.dumps({"ok": False, "error": "Could not connect to bridge server"}))
        else:
            click.echo("Error: Could not connect to bridge server", err=True)
        sys.exit(1)
    except Exception as e:
        if output_json:
            click.echo(json.dumps({"ok": False, "error": str(e)}))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@console.command(name="clear")
@click.option(
    '--json', '-j', 'output_json',
    is_flag=True,
    help='Output as JSON'
)
def clear_logs(output_json):
    """
    Clear the console message buffer.

    Removes all captured console messages from the browser's buffer.
    New messages will continue to be captured until the page is navigated away.

    Examples:
        inspekt console clear
        inspekt console clear --json
    """
    try:
        client = BridgeClient()

        if not client.is_alive():
            if output_json:
                click.echo(json.dumps({
                    "ok": False,
                    "error": "Bridge server is not running"
                }))
            else:
                from inspekt.app.cli.table import _style_with_inline_code
                click.echo(
                    _style_with_inline_code("Error: Bridge server is not running. Start it with `inspekt start`.", base_fg="red"),
                    err=True
                )
            sys.exit(1)

        import requests
        url = f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/console/clear"

        response = requests.post(url, timeout=15)
        data = response.json()

        if not data.get("ok"):
            error_msg = data.get("error", "Failed to clear console logs")
            if output_json:
                click.echo(json.dumps({"ok": False, "error": error_msg}))
            else:
                click.echo(f"Error: {error_msg}", err=True)
            sys.exit(1)

        if output_json:
            click.echo(json.dumps({"ok": True, "message": "Console buffer cleared"}))
        else:
            click.echo(success("Console buffer cleared"))

    except requests.exceptions.ConnectionError:
        if output_json:
            click.echo(json.dumps({"ok": False, "error": "Could not connect to bridge server"}))
        else:
            click.echo("Error: Could not connect to bridge server", err=True)
        sys.exit(1)
    except Exception as e:
        if output_json:
            click.echo(json.dumps({"ok": False, "error": str(e)}))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@console.command(name="log")
@click.argument("expression")
@click.option("-t", "--timeout", type=float, default=10.0, help="Timeout in seconds (default: 10)")
def log_expression(expression, timeout):
    """
    Evaluate an expression and log the result.

    Shorthand for: inspekt eval "console.log(expression)"

    Examples:
        inspekt log "5+5"
        inspekt log "document.title"
        inspekt log "[1,2,3].map(x => x*2)"
    """
    import requests

    from inspekt.services.bridge_executor import BridgeExecutor

    executor = BridgeExecutor()

    # Get timestamp before execution to filter console logs
    before_ts = datetime.now().astimezone().isoformat()

    # Wrap expression in console.log()
    code = f"console.log({expression})"

    try:
        result = executor.execute(code, timeout=timeout)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error', 'Unknown error')}", err=True)
            sys.exit(1)

        # Fetch and display the console output
        try:
            url = f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/console/logs"
            response = requests.get(url, timeout=5)
            data = response.json()

            if data.get("ok"):
                entries = data.get("entries", [])
                # Get only entries after our timestamp (last one should be ours)
                if entries:
                    last_entry = entries[-1]
                    message = last_entry.get("message", "")
                    # Don't show command markers
                    if not message.startswith("[inspekt:cmd]"):
                        click.echo(message)
        except Exception:
            pass  # Console output is best-effort

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
