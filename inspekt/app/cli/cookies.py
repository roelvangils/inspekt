"""
Cookies command group - Manage browser cookies.

⚠ DEPRECATED: This command group is deprecated and will be removed in v2.0.0
   Use 'inspekt storage --cookies' instead.

This module provides commands for cookie management:
- list: List all cookies for the current page
- get: Get a specific cookie by name
- set: Set a cookie with various options
- delete: Delete a specific cookie
- clear: Clear all cookies

Migration guide:
  inspekt cookies list             → inspekt storage list --cookies
  inspekt cookies get <name>       → inspekt storage get <name> --cookies
  inspekt cookies set <name> <val> → inspekt storage set <name> <val> --cookies
  inspekt cookies delete <name>    → inspekt storage delete <name> --cookies
  inspekt cookies clear            → inspekt storage clear --cookies
"""

from __future__ import annotations

import json
import sys

import click

from inspekt.app.cli.icons import success
from inspekt.app.cli.icons import warning as warn_icon
from inspekt.services.bridge_executor import get_executor
from inspekt.services.script_loader import ScriptLoader


def _show_deprecation_warning():
    """Show deprecation warning for cookies command group."""
    deprecation_msg = "'inspekt cookies' is deprecated and will be removed in v2.0.0"
    click.echo(
        f"{warn_icon(deprecation_msg)}\n"
        "   Use 'inspekt storage --cookies' instead\n"
        "   Example: inspekt cookies list → inspekt storage list --cookies\n",
        err=True
    )


@click.group()
def cookies():
    """[DEPRECATED] Manage browser cookies (use 'inspekt storage --cookies')."""
    pass


@cookies.command(name="list")
@click.option("--json", "-j", "output_json", is_flag=True, help="Output as JSON")
def cookies_list(output_json):
    """
    List all cookies for the current page.

    Example:
        inspekt cookies list
        inspekt cookies list --json
    """
    _show_deprecation_warning()
    _execute_cookie_action("list", output_json=output_json)


@cookies.command(name="get")
@click.argument("name")
@click.option("--json", "-j", "output_json", is_flag=True, help="Output as JSON")
def cookies_get(name, output_json):
    """
    Get the value of a specific cookie.

    Example:
        inspekt cookies get session_id
        inspekt cookies get session_id --json
    """
    _show_deprecation_warning()
    _execute_cookie_action("get", cookie_name=name, output_json=output_json)


@cookies.command(name="set")
@click.argument("name")
@click.argument("value")
@click.option("--max-age", type=int, help="Max age in seconds")
@click.option("--expires", type=str, help="Expiration date (e.g., 'Wed, 21 Oct 2025 07:28:00 GMT')")
@click.option("--path", type=str, default="/", help="Cookie path (default: /)")
@click.option("--domain", type=str, help="Cookie domain")
@click.option("--secure", is_flag=True, help="Secure flag (HTTPS only)")
@click.option(
    "--same-site",
    type=click.Choice(["Strict", "Lax", "None"], case_sensitive=False),
    help="SameSite attribute",
)
def cookies_set(name, value, max_age, expires, path, domain, secure, same_site):
    """
    Set a cookie.

    Examples:
        inspekt cookies set session_id abc123
        inspekt cookies set token xyz --max-age 3600
        inspekt cookies set user_pref dark --path / --secure
    """
    _show_deprecation_warning()
    options = {"path": path}
    if max_age:
        options["maxAge"] = max_age
    if expires:
        options["expires"] = expires
    if domain:
        options["domain"] = domain
    if secure:
        options["secure"] = True
    if same_site:
        options["sameSite"] = same_site

    _execute_cookie_action("set", cookie_name=name, cookie_value=value, options=options)


@cookies.command(name="delete")
@click.argument("name")
def cookies_delete(name):
    """
    Delete a specific cookie.

    Example:
        inspekt cookies delete session_id
    """
    _show_deprecation_warning()
    _execute_cookie_action("delete", cookie_name=name)


@cookies.command(name="clear")
def cookies_clear():
    """
    Clear all cookies for the current page.

    Example:
        inspekt cookies clear
    """
    _show_deprecation_warning()
    _execute_cookie_action("clear")


def _try_parse_json(value: str):
    """Try to parse a string as JSON. Returns parsed object or original string."""
    if not isinstance(value, str):
        return value

    # Skip if it doesn't look like JSON
    if not (value.startswith('{') or value.startswith('[')):
        return value

    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value


def _format_json_cookie_value(name: str, parsed_value, indent: int = 0) -> list[str]:
    """Format a parsed JSON cookie value for display.

    Args:
        name: Cookie name
        parsed_value: Parsed JSON object (dict or list)
        indent: Current indentation level

    Returns:
        List of formatted lines
    """
    lines = []
    prefix = " " * indent

    if isinstance(parsed_value, dict):
        # Calculate max key length for alignment
        max_key_len = max(len(str(k)) for k in parsed_value) if parsed_value else 0

        for i, (key, val) in enumerate(parsed_value.items()):
            # Format the value
            if isinstance(val, (dict, list)):
                # Nested JSON - show on next line
                val_str = json.dumps(val)
                if len(val_str) > 50:
                    val_str = val_str[:50] + "…"
            elif isinstance(val, str) and len(val) > 50:
                val_str = val[:50] + "…"
            else:
                val_str = str(val)

            # Align arrows
            padding = " " * (max_key_len - len(str(key)))
            lines.append(f"{prefix}{key}{padding} → {val_str}")

    elif isinstance(parsed_value, list):
        for i, item in enumerate(parsed_value):
            if isinstance(item, str) and len(item) > 50:
                item_str = item[:50] + "…"
            else:
                item_str = str(item)
            lines.append(f"{prefix}[{i}] {item_str}")

    return lines


def _display_enhanced_cookies(cookies: list):
    """Display enhanced cookie data with full metadata."""
    for cookie in cookies:
        name = cookie.get("name", "")
        value = cookie.get("value", "")

        # Parse cookie value if it's JSON
        parsed_value = _try_parse_json(value)

        click.echo(f"  {name}")

        # Display value (truncated if long)
        if isinstance(parsed_value, (dict, list)):
            # JSON value
            json_str = json.dumps(parsed_value, indent=4)
            lines = json_str.split('\n')
            if len(lines) > 5:
                # Show first few lines
                for line in lines[:5]:
                    click.echo(f"    {line}")
                click.echo(f"    ... ({len(lines) - 5} more lines)")
            else:
                for line in lines:
                    click.echo(f"    {line}")
        else:
            # Simple value
            display_value = value if len(value) <= 80 else value[:80] + "…"
            click.echo(f"    Value: {display_value}")

        # Display metadata if available
        if cookie.get("domain"):
            click.echo(f"    Domain: {cookie['domain']}")
        if cookie.get("path"):
            click.echo(f"    Path: {cookie['path']}")
        if cookie.get("expires"):
            click.echo(f"    Expires: {cookie['expires']}")
        if cookie.get("type"):
            click.echo(f"    Type: {cookie['type']}")
        if cookie.get("party"):
            click.echo(f"    Party: {cookie['party']}")

        # Security flags
        flags = []
        if cookie.get("secure"):
            flags.append("Secure")
        if cookie.get("httpOnly"):
            flags.append("HttpOnly")
        if cookie.get("sameSite"):
            flags.append(f"SameSite={cookie['sameSite']}")
        if flags:
            click.echo(f"    Flags: {', '.join(flags)}")

        if cookie.get("size"):
            click.echo(f"    Size: {cookie['size']} bytes")

        click.echo()  # Blank line between cookies


def _display_legacy_cookies(cookies_dict: dict):
    """Display legacy cookie data (simple name: value dict)."""
    # Calculate max name length for alignment
    max_name_len = max(len(name) for name in cookies_dict) if cookies_dict else 0

    for name, value in cookies_dict.items():
        # Try to parse as JSON
        parsed_value = _try_parse_json(value)

        if isinstance(parsed_value, (dict, list)):
            # JSON cookie - display formatted
            padding = " " * (max_name_len - len(name))
            click.echo(f"{name}{padding}")

            # Format and display the JSON content with indentation
            json_lines = _format_json_cookie_value(name, parsed_value, indent=max_name_len + 4)
            for line in json_lines:
                click.echo(line)
        else:
            # Regular cookie - display on one line
            padding = " " * (max_name_len - len(name))
            # Truncate long values
            display_value = value if len(value) <= 60 else value[:60] + "…"
            click.echo(f"{name}{padding}    {display_value}")


def _execute_cookie_action(action, cookie_name="", cookie_value="", options=None, output_json=False):
    """Helper function to execute cookie actions."""
    executor = get_executor()
    loader = ScriptLoader()

    # Load the cookies script
    try:
        script = loader.load_script_sync("cookies.js")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Replace placeholders
    options_json = json.dumps(options if options else {})
    code = script.replace("ACTION_PLACEHOLDER", action)
    code = code.replace("NAME_PLACEHOLDER", cookie_name)
    code = code.replace("VALUE_PLACEHOLDER", cookie_value)
    code = code.replace("OPTIONS_PLACEHOLDER", options_json)

    result = executor.execute(code, timeout=60.0)

    if not result.get("ok"):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    response = result.get("result", {})

    if response.get("error"):
        click.echo(f"Error: {response['error']}", err=True)
        sys.exit(1)

    # Display results based on action
    if action == "list":
        cookies_data = response.get("cookies", {})
        count = response.get("count", 0)
        api_used = response.get("apiUsed", "unknown")
        origin = response.get("origin", "")
        hostname = response.get("hostname", "")

        if output_json:
            # Return enhanced data as-is for JSON output
            from inspekt.app.cli.table import print_json
            print_json(response, summary=f"{count} cookie{'s' if count != 1 else ''}")
        elif count == 0:
            click.echo("No cookies found")
        else:
            # Display header with origin and API used
            header = f"Cookies ({count})"
            if hostname:
                header += f" on {hostname}"
            if api_used:
                header += f" - API: {api_used}"
            click.echo(f"{header}\n")

            # Check if we have enhanced cookie data (array) or legacy format (dict)
            if isinstance(cookies_data, list):
                # Enhanced cookie data with full metadata
                _display_enhanced_cookies(cookies_data)
            else:
                # Legacy format - simple dict of name: value
                _display_legacy_cookies(cookies_data)

            # VM terminal: offer a "Data ready to copy" toast
            from inspekt.app.cli.table import emit_copyable_data
            if isinstance(cookies_data, list):
                rows = [
                    [c.get("name", ""), c.get("value", ""), c.get("domain", ""), c.get("path", "/")]
                    for c in cookies_data if isinstance(c, dict)
                ]
                headers = ["Name", "Value", "Domain", "Path"]
            else:
                rows = [[k, str(v)] for k, v in (cookies_data or {}).items()]
                headers = ["Name", "Value"]
            emit_copyable_data(
                headers=headers,
                rows=rows,
                json_data=response,
                summary=f"{count} cookie{'s' if count != 1 else ''}",
            )

    elif action == "get":
        name = response.get("name")
        value = response.get("value")
        exists = response.get("exists")

        if output_json:
            # Parse JSON value if applicable
            parsed_value = _try_parse_json(value) if exists else value

            output_data = {
                "name": name,
                "value": parsed_value,
                "exists": exists
            }
            from inspekt.app.cli.table import print_json
            print_json(output_data, summary=f"cookie {name}" if exists else f"cookie {name} (missing)")
            if not exists:
                sys.exit(1)
        elif exists:
            # Try to parse as JSON for display
            parsed_value = _try_parse_json(value)

            if isinstance(parsed_value, (dict, list)):
                # JSON cookie - display formatted
                click.echo(f"{name}:")
                json_lines = _format_json_cookie_value(name, parsed_value, indent=4)
                for line in json_lines:
                    click.echo(line)
            else:
                # Regular cookie
                click.echo(f"{name} = {value}")
        else:
            click.echo(f"Cookie not found: {name}", err=True)
            sys.exit(1)

    elif action == "set":
        click.echo(success(f"Cookie set: {response.get('name')} = {response.get('value')}"))

    elif action == "delete":
        click.echo(success(f"Cookie deleted: {response.get('name')}"))

    elif action == "clear":
        deleted = response.get("deleted", 0)
        click.echo(success(f"Cleared {deleted} cookie(s)"))
