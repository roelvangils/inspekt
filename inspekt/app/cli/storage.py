"""
Storage command group - Manage browser storage (cookies, localStorage, sessionStorage).

This module provides unified commands for storage management across all storage types:
- list: List storage items
- get: Get a specific item by key
- set: Set an item with key-value
- delete: Delete a specific item
- clear: Clear all items

Supports cookies, localStorage, and sessionStorage with flexible filtering.
"""

from __future__ import annotations

import json
import sys

import click

from inspekt.app.cli.icons import success
from inspekt.app.cli.icons import warning as warn_icon
from inspekt.services.bridge_executor import get_executor
from inspekt.services.script_loader import ScriptLoader


@click.group()
def storage():
    """Manage browser storage (cookies, localStorage, sessionStorage)."""
    pass


@storage.command(name="list")
# New flag-based filtering
@click.option("--cookies", "-c", is_flag=True, help="Include cookies")
@click.option("--local", "-l", is_flag=True, help="Include localStorage")
@click.option("--session", "-s", is_flag=True, help="Include sessionStorage")
@click.option("--all", "-a", is_flag=True, help="Include all storage types (default)")
# Backward compatibility
@click.option(
    "--type",
    "storage_type",
    type=click.Choice(["local", "session", "all", "cookies"], case_sensitive=False),
    help="[DEPRECATED] Use --cookies, --local, --session, or --all instead",
)
# Output format
@click.option("--json", "-j", "output_json", is_flag=True, help="Output as JSON")
def storage_list(cookies, local, session, all, storage_type, output_json):
    """
    List all storage items.

    By default, lists all storage types. Use flags to filter specific types.

    Examples:
        inspekt storage list                    # All types
        inspekt storage list --cookies          # Just cookies
        inspekt storage list --local --session  # localStorage + sessionStorage
        inspekt storage list --all --json       # All types as JSON

    Legacy examples (deprecated --type flag):
        inspekt storage list --type=local
        inspekt storage list --type=all --json
    """
    # Determine which storage types to include
    types = _determine_storage_types(cookies, local, session, all, storage_type)

    # Show deprecation warning if old --type flag is used
    if storage_type:
        _show_deprecation_warning(
            "--type", f"--{storage_type}" if storage_type != "all" else "--all"
        )

    # Execute unified storage action
    result = _execute_unified_storage_action("list", types)

    # Display results
    if output_json:
        from inspekt.app.cli.table import print_json

        print_json(result, summary="storage items")
    else:
        _display_unified_list_result(result)
        _emit_storage_list_signal(result)


def _emit_storage_list_signal(result: dict) -> None:
    """Emit a copyable-data toast for `storage list` output."""
    from inspekt.app.cli.table import emit_copyable_data

    storage_data = result.get("storage", {}) or {}
    rows: list[list[str]] = []
    for storage_key in ("cookies", "localStorage", "sessionStorage"):
        info = storage_data.get(storage_key) or {}
        if not info.get("ok", True):
            continue
        items = info.get("items")
        if isinstance(items, dict):
            for k, v in items.items():
                rows.append([storage_key, str(k), str(v)])
        elif isinstance(items, list):
            for item in items:
                name = item.get("name", "") if isinstance(item, dict) else ""
                value = item.get("value", "") if isinstance(item, dict) else ""
                rows.append([storage_key, str(name), str(value)])

    if not rows and not result.get("storage"):
        return

    count = len(rows)
    emit_copyable_data(
        headers=["Type", "Key", "Value"],
        rows=rows,
        json_data=result,
        summary=f"{count} storage item{'s' if count != 1 else ''}",
    )


@storage.command(name="get")
@click.argument("key")
# Storage type selection
@click.option("--cookies", "-c", is_flag=True, help="Get from cookies")
@click.option("--local", "-l", is_flag=True, help="Get from localStorage")
@click.option("--session", "-s", is_flag=True, help="Get from sessionStorage")
# Backward compatibility
@click.option(
    "--type",
    "storage_type",
    type=click.Choice(["local", "session", "cookies"], case_sensitive=False),
    help="[DEPRECATED] Use --cookies, --local, or --session instead",
)
# Output format
@click.option("--json", "-j", "output_json", is_flag=True, help="Output as JSON")
def storage_get(key, cookies, local, session, storage_type, output_json):
    """
    Get the value of a specific storage item.

    Searches in the specified storage type. Defaults to localStorage if no type specified.

    Examples:
        inspekt storage get user_token                # localStorage (default)
        inspekt storage get session_id --cookies      # Cookie
        inspekt storage get temp_data --session       # sessionStorage
        inspekt storage get preferences --local --json
    """
    # Determine storage type (for get, only one type is allowed)
    types = _determine_storage_types(
        cookies, local, session, False, storage_type, default_local=True
    )

    # Show deprecation warning if old --type flag is used
    if storage_type:
        _show_deprecation_warning("--type", f"--{storage_type}")

    # Get only allows one type
    if len(types) > 1:
        click.echo("Error: Please specify only one storage type for 'get' command", err=True)
        sys.exit(1)

    storage_type_name = types[0]

    # Execute action
    result = _execute_unified_storage_action("get", types, key=key)

    # Extract result for the specific storage type
    storage_key = _get_storage_key(storage_type_name)
    storage_result = result.get("storage", {}).get(storage_key, {})

    if output_json:
        from inspekt.app.cli.table import print_json

        print_json(storage_result, summary=f"{key}")
        if not storage_result.get("exists"):
            sys.exit(1)
    elif storage_result.get("exists"):
        value = storage_result.get("value")
        _display_value(value)
    else:
        click.echo(f"Key not found: {key}", err=True)
        sys.exit(1)


@storage.command(name="set")
@click.argument("key")
@click.argument("value")
# Storage type selection
@click.option("--cookies", "-c", is_flag=True, help="Set as cookie")
@click.option("--local", "-l", is_flag=True, help="Set in localStorage")
@click.option("--session", "-s", is_flag=True, help="Set in sessionStorage")
# Backward compatibility
@click.option(
    "--type",
    "storage_type",
    type=click.Choice(["local", "session", "cookies"], case_sensitive=False),
    help="[DEPRECATED] Use --cookies, --local, or --session instead",
)
# Cookie-specific options
@click.option("--max-age", type=int, help="Cookie max age in seconds")
@click.option("--expires", type=str, help="Cookie expiration date")
@click.option("--path", type=str, default="/", help="Cookie path (default: /)")
@click.option("--domain", type=str, help="Cookie domain")
@click.option("--secure", is_flag=True, help="Secure flag (HTTPS only)")
@click.option(
    "--same-site",
    type=click.Choice(["Strict", "Lax", "None"], case_sensitive=False),
    help="SameSite attribute",
)
def storage_set(
    key,
    value,
    cookies,
    local,
    session,
    storage_type,
    max_age,
    expires,
    path,
    domain,
    secure,
    same_site,
):
    """
    Set a storage item.

    Stores in the specified storage type. Defaults to localStorage if no type specified.

    Examples:
        inspekt storage set user_token abc123                    # localStorage
        inspekt storage set session_id xyz --cookies             # Cookie
        inspekt storage set temp '{"data":"value"}' --session    # sessionStorage

    Cookie-specific examples:
        inspekt storage set session_id abc --cookies --max-age 3600 --secure
        inspekt storage set auth_token xyz --cookies --path / --same-site Strict
    """
    # Determine storage type
    types = _determine_storage_types(
        cookies, local, session, False, storage_type, default_local=True
    )

    # Show deprecation warning if old --type flag is used
    if storage_type:
        _show_deprecation_warning("--type", f"--{storage_type}")

    # Set only allows one type
    if len(types) > 1:
        click.echo("Error: Please specify only one storage type for 'set' command", err=True)
        sys.exit(1)

    storage_type_name = types[0]

    # Build options for cookies
    options = {}
    if storage_type_name == "cookies":
        if max_age is not None:
            options["maxAge"] = max_age
        if expires:
            options["expires"] = expires
        if path:
            options["path"] = path
        if domain:
            options["domain"] = domain
        if secure:
            options["secure"] = True
        if same_site:
            options["sameSite"] = same_site

    # Execute action
    _execute_unified_storage_action("set", types, key=key, value=value, options=options)

    # Display success message
    storage_display = {"cookies": "cookie", "local": "localStorage", "session": "sessionStorage"}[
        storage_type_name
    ]

    click.echo(success(f"Item set in {storage_display}: {key}"))


@storage.command(name="delete")
@click.argument("key")
# Storage type selection
@click.option("--cookies", "-c", is_flag=True, help="Delete from cookies")
@click.option("--local", "-l", is_flag=True, help="Delete from localStorage")
@click.option("--session", "-s", is_flag=True, help="Delete from sessionStorage")
# Backward compatibility
@click.option(
    "--type",
    "storage_type",
    type=click.Choice(["local", "session", "cookies"], case_sensitive=False),
    help="[DEPRECATED] Use --cookies, --local, or --session instead",
)
def storage_delete(key, cookies, local, session, storage_type):
    """
    Delete a specific storage item.

    Deletes from the specified storage type. Defaults to localStorage if no type specified.

    Examples:
        inspekt storage delete user_token                  # localStorage
        inspekt storage delete session_id --cookies        # Cookie
        inspekt storage delete temp_data --session         # sessionStorage
    """
    # Determine storage type
    types = _determine_storage_types(
        cookies, local, session, False, storage_type, default_local=True
    )

    # Show deprecation warning if old --type flag is used
    if storage_type:
        _show_deprecation_warning("--type", f"--{storage_type}")

    # Delete only allows one type
    if len(types) > 1:
        click.echo("Error: Please specify only one storage type for 'delete' command", err=True)
        sys.exit(1)

    storage_type_name = types[0]

    # Execute action
    _execute_unified_storage_action("delete", types, key=key)

    # Display success message
    storage_display = {"cookies": "cookies", "local": "localStorage", "session": "sessionStorage"}[
        storage_type_name
    ]

    click.echo(success(f"Item deleted from {storage_display}: {key}"))


@storage.command(name="clear")
# Storage type selection
@click.option("--cookies", "-c", is_flag=True, help="Clear cookies")
@click.option("--local", "-l", is_flag=True, help="Clear localStorage")
@click.option("--session", "-s", is_flag=True, help="Clear sessionStorage")
@click.option("--all", "-a", is_flag=True, help="Clear all storage types (default)")
# Backward compatibility
@click.option(
    "--type",
    "storage_type",
    type=click.Choice(["local", "session", "all", "cookies"], case_sensitive=False),
    help="[DEPRECATED] Use --cookies, --local, --session, or --all instead",
)
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def storage_clear(cookies, local, session, all, storage_type, force):
    """
    Clear all storage items.

    By default, clears all storage types. Use flags to filter specific types.

    Examples:
        inspekt storage clear --force              # Clear all types
        inspekt storage clear --cookies            # Just cookies
        inspekt storage clear --local --session    # localStorage + sessionStorage
    """
    # Determine which storage types to clear
    types = _determine_storage_types(cookies, local, session, all, storage_type)

    # Show deprecation warning if old --type flag is used
    if storage_type:
        _show_deprecation_warning(
            "--type", f"--{storage_type}" if storage_type != "all" else "--all"
        )

    # Build confirmation message
    if not force:
        type_names = [_get_storage_display_name(t) for t in types]
        storage_description = (
            " and ".join(type_names)
            if len(type_names) <= 2
            else ", ".join(type_names[:-1]) + f", and {type_names[-1]}"
        )

        if not click.confirm(
            f"Are you sure you want to clear all items from {storage_description}?"
        ):
            click.echo("Cancelled")
            return

    # Execute clear action
    result = _execute_unified_storage_action("clear", types)

    # Display results for each type
    for storage_type in types:
        storage_key = _get_storage_key(storage_type)
        storage_result = result.get("storage", {}).get(storage_key, {})
        deleted = storage_result.get("deleted", 0)
        display_name = _get_storage_display_name(storage_type)
        click.echo(success(f"Cleared {deleted} item(s) from {display_name}"))


# ============================================================================
# Helper Functions
# ============================================================================


def _determine_storage_types(cookies, local, session, all_flag, legacy_type, default_local=False):
    """
    Determine which storage types to include based on flags.

    Args:
        cookies: --cookies flag
        local: --local flag
        session: --session flag
        all_flag: --all flag
        legacy_type: --type flag value (deprecated)
        default_local: If True and no flags set, default to ['local']

    Returns:
        List of storage type strings: ['cookies', 'local', 'session']
    """
    types = []

    # Priority 1: New flags
    if cookies:
        types.append("cookies")
    if local:
        types.append("local")
    if session:
        types.append("session")
    if all_flag:
        types = ["cookies", "local", "session"]

    # Priority 2: Legacy --type flag (for backward compatibility)
    if not types and legacy_type:
        if legacy_type == "all":
            types = ["cookies", "local", "session"]
        elif legacy_type == "cookies":
            types = ["cookies"]
        elif legacy_type == "local":
            types = ["local"]
        elif legacy_type == "session":
            types = ["session"]

    # Priority 3: Default behavior
    if not types:
        if default_local:
            types = ["local"]
        else:
            # Default for list/clear is all types
            types = ["cookies", "local", "session"]

    return types


def _get_storage_key(storage_type):
    """Map storage type to output key name."""
    return {"cookies": "cookies", "local": "localStorage", "session": "sessionStorage"}[
        storage_type
    ]


def _get_storage_display_name(storage_type):
    """Map storage type to human-readable display name."""
    return {"cookies": "cookies", "local": "localStorage", "session": "sessionStorage"}[
        storage_type
    ]


def _show_deprecation_warning(old_flag, new_flag):
    """Show deprecation warning for legacy flags."""
    deprecation_msg = f"'{old_flag}' flag is deprecated and will be removed in v2.0.0"
    click.echo(f"{warn_icon(deprecation_msg)}\n   Use '{new_flag}' instead\n", err=True)


def _execute_unified_storage_action(action, types, key="", value="", options=None):
    """
    Execute unified storage action using storage_unified.js script.

    Args:
        action: Action to perform ('list', 'get', 'set', 'delete', 'clear')
        types: List of storage types to include (['cookies', 'local', 'session'])
        key: Key name for get/set/delete operations
        value: Value for set operation
        options: Additional options (e.g., cookie options)

    Returns:
        Unified response object
    """
    executor = get_executor()
    loader = ScriptLoader()

    # Load the unified storage script
    try:
        script = loader.load_script_sync("storage_unified.js")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Replace placeholders
    code = script.replace("ACTION_PLACEHOLDER", action)
    code = code.replace("TYPES_PLACEHOLDER", json.dumps(types))
    code = code.replace("KEY_PLACEHOLDER", key)
    code = code.replace("VALUE_PLACEHOLDER", value)
    code = code.replace("OPTIONS_PLACEHOLDER", json.dumps(options if options else {}))

    # Execute
    result = executor.execute(code, timeout=60.0)

    if not result.get("ok"):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    response = result.get("result", {})

    if not response.get("ok"):
        click.echo(f"Error: {response.get('error')}", err=True)
        sys.exit(1)

    return response


def _display_unified_list_result(result):
    """Display unified list results in human-readable format."""
    storage_data = result.get("storage", {})
    hostname = result.get("hostname", "")
    totals = result.get("totals", {})

    # Display header
    origin_display = f" on {hostname}" if hostname else ""
    total_items = totals.get("totalItems", 0)

    if total_items == 0:
        click.echo(f"No storage items found{origin_display}")
        return

    click.echo(f"Storage{origin_display} ({total_items} items total):\n")

    # Display each storage type
    for storage_key in ["cookies", "localStorage", "sessionStorage"]:
        if storage_key not in storage_data:
            continue

        storage_info = storage_data[storage_key]

        # Check if there was an error for this storage type
        if not storage_info.get("ok", True):
            click.echo(f"  {storage_key}: {storage_info.get('error', 'Unknown error')}")
            continue

        count = storage_info.get("count", 0)
        if count == 0:
            continue

        click.echo(f"  {storage_key} ({count} items):")

        # Display items based on format
        items = storage_info.get("items")

        if storage_key == "cookies" and isinstance(items, list):
            # Enhanced cookies format (array)
            _display_cookie_list(items)
        elif isinstance(items, dict):
            # Standard key-value format (localStorage, sessionStorage, or legacy cookies)
            _display_key_value_items(items, indent="    ")

        click.echo()  # Blank line between storage types


def _display_cookie_list(cookies):
    """Display enhanced cookie list."""
    for cookie in cookies:
        name = cookie.get("name", "")
        value = cookie.get("value", "")

        # Try to parse JSON value
        value_parsed = cookie.get("valueParsed")
        if value_parsed and value_parsed != value:
            # Value was successfully parsed
            click.echo(f"    {name}:")
            click.echo(
                f"      Value: {value[:50]}…" if len(value) > 50 else f"      Value: {value}"
            )
            if isinstance(value_parsed, (dict, list)):
                parsed_str = json.dumps(value_parsed, indent=2)
                for line in parsed_str.split("\n"):
                    click.echo(f"      {line}")
        else:
            # Plain value
            display_value = value if len(value) <= 50 else value[:50] + "…"
            click.echo(f"    {name} = {display_value}")

        # Show key metadata
        if cookie.get("domain"):
            click.echo(f"      Domain: {cookie['domain']}")
        if cookie.get("expires"):
            click.echo(f"      Expires: {cookie['expires']}")
        if cookie.get("expiresInDays") is not None:
            days = cookie["expiresInDays"]
            if days > 0:
                click.echo(f"      Expires in: {days} days")

        # Security info
        security_flags = cookie.get("securityFlags", [])
        if security_flags:
            click.echo(f"      Security: {', '.join(security_flags)}")


def _display_key_value_items(items, indent="  "):
    """Display key-value storage items."""
    for key, value in items.items():
        if isinstance(value, dict):
            # JSON object
            json_str = json.dumps(value, indent=2)
            indented = ("\n" + indent + "  ").join(json_str.split("\n"))
            click.echo(f"{indent}{key} = {indented}")
        elif isinstance(value, list):
            # Array
            click.echo(f"{indent}{key} =")
            for item in value:
                click.echo(f"{indent}  - {item}")
        else:
            # Plain value
            display_value = str(value) if len(str(value)) <= 60 else str(value)[:60] + "…"
            click.echo(f"{indent}{key} = {display_value}")


def _display_value(value):
    """Display a single value."""
    if isinstance(value, dict):
        click.echo(json.dumps(value, indent=2))
    elif isinstance(value, list):
        for item in value:
            click.echo(f"  - {item}")
    else:
        click.echo(value)
