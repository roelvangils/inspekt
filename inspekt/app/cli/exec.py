"""
Execution commands for the Inspekt Browser Bridge CLI.

This module provides commands for executing JavaScript code in the browser:
- eval: Execute JavaScript code from arguments, files, or stdin
- exec: Execute JavaScript from a file
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

import click
import requests

from inspekt.app.cli.base import format_output
from inspekt.services.bridge_executor import BridgeExecutor

# Bridge server defaults
BRIDGE_HTTP_HOST = "127.0.0.1"
BRIDGE_HTTP_PORT = 8765


def _get_console_logs_since(timestamp: str) -> list[dict]:
    """Fetch console logs that occurred after the given ISO timestamp."""
    try:
        url = f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/console/logs"
        response = requests.get(url, timeout=5)
        data = response.json()

        if not data.get("ok"):
            return []

        entries = data.get("entries", [])
        # Filter to only entries after the timestamp
        new_entries = [e for e in entries if e.get("timestamp", "") > timestamp]
        return new_entries
    except Exception:
        return []


def _format_console_entry(entry: dict) -> str:
    """Format a single console entry for display."""
    level = entry.get("level", "log")
    message = entry.get("message", "")

    # Color map
    level_colors = {
        "error": "red",
        "warn": "yellow",
        "log": "white",
        "info": "cyan",
        "debug": "bright_black",
    }
    color = level_colors.get(level, "white")

    # Handle special prefixes
    prefix_colors = {
        "[table:json]": "blue",
        "[dir]": "blue",
        "[trace]": "magenta",
        "[group]": "cyan",
        "[assert]": "red",
        "[clear]": "bright_black",
    }

    display_msg = message
    for prefix, pcolor in prefix_colors.items():
        if message.startswith(prefix):
            if prefix == "[table:json]":
                display_msg = click.style("[table]", fg="blue") + " …"
            else:
                display_msg = click.style(prefix, fg=pcolor) + message[len(prefix) :]
            break

    # Colorize special values
    if display_msg == "(empty)":
        display_msg = click.style("(empty)", dim=True)
    elif display_msg in ("undefined", "null"):
        display_msg = click.style(display_msg, dim=True)
    elif display_msg in ("NaN", "Infinity", "-Infinity"):
        display_msg = click.style(display_msg, fg="yellow")

    return f"  {click.style(f'[{level}]', fg=color)} {display_msg}"


@click.command()
@click.argument("code", required=False)
@click.option("-f", "--file", type=click.Path(exists=True), help="Execute code from file")
@click.option("-t", "--timeout", type=float, default=10.0, help="Timeout in seconds (default: 10)")
@click.option(
    "--format", type=click.Choice(["auto", "json", "raw"]), default="auto", help="Output format"
)
@click.option("--url", is_flag=True, help="Also print page URL")
@click.option("--title", is_flag=True, help="Also print page title")
@click.option("--no-console", is_flag=True, help="Don't show console output")
def eval(code, file, timeout, format, url, title, no_console):
    """
    Execute JavaScript code in the active browser tab.

    Console output (console.log, console.error, etc.) is shown by default.
    Use --no-console to hide it.

    Examples:

        inspekt eval "document.title"

        inspekt eval "console.log(5+5)"

        inspekt eval --file script.js

        echo "console.log('test')" | inspekt eval
    """
    executor = BridgeExecutor()

    # Read from stdin if no code or file provided
    if not code and not file:
        if not sys.stdin.isatty():
            code = sys.stdin.read()
        else:
            click.echo(
                "Error: No code provided. Use: inspekt eval CODE or inspekt eval --file FILE",
                err=True,
            )
            sys.exit(1)

    try:
        # Get timestamp before execution to filter console logs
        before_ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        if file:
            result = executor.execute_file(file, timeout=timeout)
        else:
            # Inject a context marker so console list shows what code was executed
            # Escape the code for safe embedding in a string
            escaped_code = code.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
            # Use comma operator (not semicolon) since executor wraps in return()
            # Prefix with [inspekt:cmd] for console.py to recognize and format specially
            code_with_marker = f"(console.debug('[inspekt:cmd]' + `{escaped_code}`), {code})"
            result = executor.execute(code_with_marker, timeout=timeout)

        # Show metadata if requested
        if url and result.get("url"):
            click.echo(f"URL: {result['url']}", err=True)
        if title and result.get("title"):
            click.echo(f"Title: {result['title']}", err=True)

        # Show console output (unless disabled)
        if not no_console:
            console_entries = _get_console_logs_since(before_ts)
            if console_entries:
                for entry in console_entries:
                    # Skip the command marker in inline output (it's for console list)
                    if entry.get("message", "").startswith("[inspekt:cmd]"):
                        continue
                    click.echo(_format_console_entry(entry))

        # Show result
        output = format_output(result, format)
        if output and output.strip():
            # Add arrow prefix to distinguish return value from console output
            if not no_console:
                click.echo(click.style("← ", dim=True) + output)
            else:
                click.echo(output)

        # Exit with error code if execution failed
        if not result.get("ok"):
            sys.exit(1)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@click.command()
@click.argument("filepath", type=click.Path(exists=True))
@click.option("-t", "--timeout", type=float, default=10.0, help="Timeout in seconds")
@click.option(
    "--format", type=click.Choice(["auto", "json", "raw"]), default="auto", help="Output format"
)
def exec(filepath, timeout, format):
    """
    Execute JavaScript from a file.

    Example:

        inspekt exec script.js
    """
    executor = BridgeExecutor()

    try:
        result = executor.execute_file(filepath, timeout=timeout)
        output = format_output(result, format)
        click.echo(output)

        if not result.get("ok"):
            sys.exit(1)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
