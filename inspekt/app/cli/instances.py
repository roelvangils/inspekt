"""
Instance management commands for Inspekt.

Commands for listing, aliasing, and identifying browser instances.
"""

from __future__ import annotations

import sys

import click
import requests

from inspekt.config import get_bridge_port


def _get_base_url() -> str:
    """Get the base URL for the bridge server."""
    port = get_bridge_port()
    return f"http://127.0.0.1:{port}"


def _format_time_ago(seconds: float) -> str:
    """Format time ago in human-readable form."""
    if seconds < 60:
        return f"{int(seconds)}s ago"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes}m ago"
    else:
        hours = int(seconds / 3600)
        return f"{hours}h ago"


def _truncate(text: str, max_length: int = 40) -> str:
    """Truncate text to max length with ellipsis."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length - 1] + "…"


@click.group(invoke_without_command=True)
@click.option("--json", "-j", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def instances(ctx, output_json):
    """List and manage connected browser instances.

    Shows all connected browsers with their unique IDs, aliases, and status.
    Use the --instance/-i global flag to target a specific instance.

    \b
    Examples:
        inspekt instances                  # List all instances
        inspekt instances --json           # Output as JSON
        inspekt instances alias b7x2 home  # Set alias 'home' for instance 'b7x2'
        inspekt instances unalias home     # Remove the 'home' alias
        inspekt instances identify b7x2    # Flash/highlight instance
    """
    if ctx.invoked_subcommand is None:
        _list_instances(output_json)


def _list_instances(output_json: bool) -> None:
    """Display all connected browser instances."""
    import json as json_module

    from inspekt.app.cli.icons import get_indicator
    from inspekt.app.cli.table import Table, print_hint

    try:
        response = requests.get(f"{_get_base_url()}/instances", timeout=5.0)
        data = response.json()
    except requests.ConnectionError:
        click.secho("Error: Bridge server is not running. Start it with: inspekt start", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)

    if not data.get("ok"):
        click.secho(f"Error: {data.get('error', 'Unknown error')}", fg="red", err=True)
        sys.exit(1)

    instances_list = data.get("instances", [])

    if output_json:
        click.echo(json_module.dumps({"ok": True, "instances": instances_list}, indent=2))
        return

    if not instances_list:
        click.echo()
        click.secho("No browser instances connected.", fg="yellow")
        click.echo()
        print_hint("Make sure a browser with the Inspekt extension is open and the extension is enabled.")
        return

    click.echo()

    # Build table
    table = Table(
        ["ID", "Alias", "Browser", "Title", "Status", "Last Command"],
        title="Browser Instances",
        icon=get_indicator("browser")
    )

    rows = []
    for inst in instances_list:
        instance_id = inst.get("id", "?")
        alias = inst.get("alias") or "-"
        browser = inst.get("browser", "Unknown")
        title = _truncate(inst.get("title", ""), 35)
        is_active = inst.get("is_active", False)
        last_command_time = inst.get("last_command_time_ago")

        # Status indicator
        if is_active:
            status = click.style("● ACTIVE", fg="green")
        else:
            status = ""

        # Last command time
        if last_command_time is not None:
            last_cmd = _format_time_ago(last_command_time)
        else:
            last_cmd = click.style("never", fg="bright_black")

        rows.append([
            click.style(instance_id, fg="cyan", bold=True),
            click.style(alias, fg="yellow") if alias != "-" else click.style("-", fg="bright_black"),
            browser,
            title,
            status,
            last_cmd
        ])

    table.set_data(rows)
    table.print_header()
    for row in rows:
        table.print_row(row)
    table.print_footer()

    # VM terminal: offer a "Data ready to copy" toast
    from inspekt.app.cli.table import emit_copyable_data
    emit_copyable_data(
        headers=["ID", "Alias", "Browser", "Title", "Status", "Last Command"],
        rows=rows,
        json_data={"instances": instances_list},
        summary=f"{len(instances_list)} instance{'s' if len(instances_list) != 1 else ''}",
    )

    click.echo()
    print_hint("Use `inspekt -i <ID>` or `inspekt -i <alias>` to target a specific instance.")


@instances.command("alias")
@click.argument("instance_id")
@click.argument("alias")
def set_alias(instance_id: str, alias: str):
    """Set a temporary alias for a browser instance.

    Aliases make it easier to target specific browser instances
    without remembering the auto-generated ID.

    \b
    Examples:
        inspekt instances alias b7x2 homepage
        inspekt instances alias k9m4 testing

    After setting an alias, you can use it with any command:
        inspekt -i homepage screenshot
        inspekt -i testing info
    """
    try:
        response = requests.post(
            f"{_get_base_url()}/instances/alias",
            json={"instance_id": instance_id, "alias": alias},
            timeout=5.0
        )
        data = response.json()
    except requests.ConnectionError:
        click.secho("Error: Bridge server is not running. Start it with: inspekt start", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)

    if data.get("ok"):
        actual_id = data.get("instance_id", instance_id)
        actual_alias = data.get("alias", alias)
        click.secho(f"✓ Alias '{actual_alias}' set for instance '{actual_id}'", fg="green")
        click.echo(f"  Use it with: inspekt -i {actual_alias} <command>")
    else:
        error = data.get("error", "Unknown error")
        message = data.get("message", "")
        if message:
            click.secho(f"Error: {message}", fg="red", err=True)
        else:
            click.secho(f"Error: {error}", fg="red", err=True)
        sys.exit(1)


@instances.command("unalias")
@click.argument("alias")
def remove_alias(alias: str):
    """Remove an alias from a browser instance.

    \b
    Example:
        inspekt instances unalias homepage
    """
    try:
        response = requests.delete(
            f"{_get_base_url()}/instances/alias",
            params={"alias": alias},
            timeout=5.0
        )
        data = response.json()
    except requests.ConnectionError:
        click.secho("Error: Bridge server is not running. Start it with: inspekt start", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)

    if data.get("ok"):
        click.secho(f"✓ Alias '{alias}' removed", fg="green")
    else:
        error = data.get("error", "Unknown error")
        message = data.get("message", "")
        if message:
            click.secho(f"Error: {message}", fg="red", err=True)
        else:
            click.secho(f"Error: {error}", fg="red", err=True)
        sys.exit(1)


@instances.command("identify")
@click.argument("instance", required=False)
def identify(instance: str | None):
    """Flash/highlight a browser instance to identify it visually.

    Shows a visual indicator on the browser tab to help you
    identify which tab corresponds to which instance ID.

    If no instance is specified, identifies all connected instances.

    \b
    Examples:
        inspekt instances identify b7x2     # Identify specific instance
        inspekt instances identify homepage # Identify by alias
        inspekt instances identify          # Identify all instances
    """
    from inspekt.services.bridge_executor import get_executor

    executor = get_executor()

    # JavaScript to flash the page with instance ID
    identify_script = """
    (() => {
        const overlay = document.createElement('div');
        overlay.id = '__inspekt_identify_overlay__';
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 123, 255, 0.3);
            z-index: 999999999;
            display: flex;
            align-items: center;
            justify-content: center;
            pointer-events: none;
            animation: inspektFlash 0.3s ease-in-out 3;
        `;

        const style = document.createElement('style');
        style.textContent = `
            @keyframes inspektFlash {
                0%, 100% { opacity: 0; }
                50% { opacity: 1; }
            }
        `;
        document.head.appendChild(style);

        const label = document.createElement('div');
        label.style.cssText = `
            background: #007bff;
            color: white;
            padding: 20px 40px;
            border-radius: 10px;
            font-size: 48px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            font-weight: bold;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
        `;
        label.textContent = 'INSPEKT';
        overlay.appendChild(label);

        document.body.appendChild(overlay);

        setTimeout(() => {
            overlay.remove();
            style.remove();
        }, 1000);

        return { ok: true };
    })();
    """

    try:
        if instance:
            # Identify specific instance - pass instance directly to execute
            result = executor.client.execute(identify_script, timeout=5.0, instance=instance)

            if result.get("ok"):
                click.secho(f"✓ Identified instance '{instance}'", fg="green")
            else:
                click.secho(f"Error: {result.get('error', 'Failed to identify instance')}", fg="red", err=True)
                sys.exit(1)
        else:
            # Identify all instances - get list first
            response = requests.get(f"{_get_base_url()}/instances", timeout=5.0)
            data = response.json()

            if not data.get("ok"):
                click.secho(f"Error: {data.get('error', 'Failed to get instances')}", fg="red", err=True)
                sys.exit(1)

            instances_list = data.get("instances", [])
            if not instances_list:
                click.secho("No browser instances connected.", fg="yellow")
                return

            # Identify each instance
            for inst in instances_list:
                inst_id = inst.get("id")
                if inst_id:
                    try:
                        executor.client.execute(identify_script, timeout=5.0, instance=inst_id)
                        click.echo(f"  Identified: {inst_id}")
                    except Exception:
                        pass  # Continue with other instances

            click.secho(f"✓ Identified {len(instances_list)} instance(s)", fg="green")

    except requests.ConnectionError:
        click.secho("Error: Bridge server is not running. Start it with: inspekt start", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)
