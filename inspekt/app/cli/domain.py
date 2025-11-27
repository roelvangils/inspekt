"""
Domain command group - Manage allowed domains for browser automation.

This module provides commands for domain permission management:
- add: Add a domain to the allow list
- remove: Remove a domain from the allow list
- list: List all allowed domains with timestamps
- bypass: Temporarily allow all domains

Domains are stored in SQLite (primary) and auto-synced to browser extension.
The www. prefix is automatically stripped (github.com allows www.github.com).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime

import click
import requests

from inspekt.services.domain_service import get_domain_service, normalize_domain

# Bridge server defaults (same as in bridge_ws.py and client.py)
BRIDGE_HTTP_HOST = "127.0.0.1"
BRIDGE_HTTP_PORT = 8765


@click.group()
def domain():
    """Manage allowed domains for browser automation."""
    pass


@domain.command(name="add")
@click.argument("domain_name")
def domain_add(domain_name):
    """
    Add a domain to the allowed list.

    The domain is normalized (www. prefix stripped) and stored in SQLite,
    then auto-synced to the browser extension if connected.

    Parent domains grant access to subdomains (e.g., github.com allows www.github.com).

    Examples:
        inspekt domain add github.com
        inspekt domain add www.example.com  # Stored as example.com
        inspekt domain add localhost
    """
    try:
        domain_service = get_domain_service()

        # Add to SQLite (domain is normalized automatically)
        result = domain_service.add_domain(domain_name)

        if result.get("ok"):
            stored_domain = result.get("domain")

            # Show what was stored
            if result.get("original"):
                click.echo(f"✓ Domain added: {stored_domain} (normalized from {domain_name})")
            else:
                click.echo(f"✓ Domain added: {stored_domain}")

            if result.get("already_exists"):
                click.echo("  (Domain was already in the allow list)")

            # Auto-sync to browser extension
            _sync_to_browser_silent()

        else:
            click.echo(f"Error: Failed to add domain", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@domain.command(name="remove")
@click.argument("domain_name")
def domain_remove(domain_name):
    """
    Remove a domain from the allowed list.

    The domain is normalized (www. prefix stripped) before removal,
    then auto-synced to the browser extension if connected.

    Examples:
        inspekt domain remove github.com
        inspekt domain remove www.example.com  # Removes example.com
        inspekt domain remove localhost
    """
    try:
        domain_service = get_domain_service()

        # Remove from SQLite (domain is normalized automatically)
        result = domain_service.remove_domain(domain_name)

        if result.get("ok"):
            stored_domain = result.get("domain")

            if result.get("deleted"):
                # Show what was removed
                if result.get("original"):
                    click.echo(f"✓ Domain removed: {stored_domain} (normalized from {domain_name})")
                else:
                    click.echo(f"✓ Domain removed: {stored_domain}")

                # Auto-sync to browser extension
                _sync_to_browser_silent()
            else:
                click.echo(f"Domain not found: {stored_domain}")

        else:
            click.echo(f"Error: Failed to remove domain", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@domain.command(name="list")
@click.option("--json", "-j", "output_json", is_flag=True, help="Output as JSON")
def domain_list(output_json):
    """
    List all allowed domains.

    Shows all domains with their timestamps and metadata.
    This command reads directly from the local SQLite database
    and does not require a browser connection.

    Examples:
        inspekt domain list              # Human-readable format
        inspekt domain list --json       # JSON format
    """
    try:
        from datetime import timezone

        domain_service = get_domain_service()

        # Get all domains from SQLite
        domains_list = domain_service.get_all_domains()

        # Convert to the expected format
        domains = {}
        for item in domains_list:
            # Convert Unix timestamp to ISO format
            dt = datetime.fromtimestamp(item["added_at"], tz=timezone.utc)
            iso_timestamp = dt.isoformat().replace("+00:00", "Z")

            domains[item["domain"]] = {
                "addedAt": iso_timestamp,
                "permanent": item["permanent"]
            }

        # Try to get bypass status (optional - don't fail if bridge not connected)
        bypass_status = None
        try:
            bypass_response = requests.post(
                f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/domains/bypass",
                json={"duration": -1},  # Special value to just get status
                timeout=5.0
            )
            if bypass_response.status_code == 200:
                bypass_result = bypass_response.json()
                if bypass_result.get("ok"):
                    bypass_status = bypass_result
        except Exception:
            # Bypass status fetch failed, continue without it
            pass

        if output_json:
            click.echo(json.dumps(domains, indent=2))
        else:
            _display_domains(domains, bypass_status)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@domain.command(name="bypass")
@click.argument("duration", type=int)
def domain_bypass(duration):
    """
    Set temporary bypass for all domains.

    Allows all domains for the specified duration in minutes.
    Use 0 to disable bypass.

    Examples:
        inspekt domain bypass 15     # Allow all for 15 minutes
        inspekt domain bypass 60     # Allow all for 1 hour
        inspekt domain bypass 0      # Disable bypass
    """
    try:
        response = requests.post(
            f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/domains/bypass",
            json={"duration": duration},
            timeout=10.0
        )

        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                if result.get("enabled"):
                    click.echo(f"✓ Temporary bypass enabled for {duration} minutes")
                    expires_at = result.get("expiresAt")
                    if expires_at:
                        formatted_expires = _format_human_datetime(expires_at)
                        click.echo(f"  Expires at: {formatted_expires}")
                else:
                    click.echo("✓ Temporary bypass disabled")
            else:
                click.echo(f"Error: {result.get('error', 'Unknown error')}", err=True)
                sys.exit(1)
        else:
            click.echo(f"Error: HTTP {response.status_code}", err=True)
            sys.exit(1)

    except requests.exceptions.ConnectionError:
        click.echo("Error: Could not connect to bridge server", err=True)
        click.echo("Make sure the server is running: inspekt start", err=True)
        sys.exit(1)
    except requests.exceptions.Timeout:
        click.echo("Error: Request timed out", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# Helper Functions
# ============================================================================

def _sync_to_browser_confirmed(timeout: float = 10.0) -> tuple[bool, str]:
    """
    Sync domains to browser extension with confirmation.

    Waits for browser to confirm the sync was applied.

    Args:
        timeout: Maximum time to wait for browser confirmation

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        domain_service = get_domain_service()
        domains = domain_service.get_domains_for_browser_sync()

        response = requests.post(
            f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/domains/sync",
            json={"domains": domains},
            timeout=timeout
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("ok") and data.get("browsers_synced", 0) > 0:
                return True, f"Synced to {data['browsers_synced']} browser(s)"
            elif data.get("ok"):
                return False, "No browser confirmed sync"
            else:
                return False, data.get("error", "Sync failed")
        return False, f"HTTP {response.status_code}"

    except requests.exceptions.Timeout:
        return False, "Timeout waiting for browser confirmation"
    except requests.exceptions.ConnectionError:
        return False, "Bridge server not connected"
    except Exception as e:
        return False, str(e)


def _sync_to_browser_silent():
    """
    Fire-and-forget sync to browser extension (legacy wrapper).

    This is called automatically after add/remove operations.
    """
    success, _ = _sync_to_browser_confirmed(timeout=10.0)
    return success


def _enable_browser_bypass(duration_minutes: int) -> bool:
    """Enable browser-side bypass via /domains/bypass endpoint."""
    try:
        response = requests.post(
            f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/domains/bypass",
            json={"duration": duration_minutes},
            timeout=10.0
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("ok", False) and data.get("enabled", False)
        return False
    except Exception:
        return False


def _disable_browser_bypass() -> bool:
    """Disable browser-side bypass."""
    try:
        response = requests.post(
            f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/domains/bypass",
            json={"duration": 0},
            timeout=10.0
        )
        return response.status_code == 200
    except Exception:
        return False


def _reload_browser_page() -> bool:
    """Reload the current browser page to apply changes."""
    try:
        response = requests.post(
            f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/execute",
            json={"code": "location.reload()"},
            timeout=5.0
        )
        if response.status_code == 200:
            click.echo("  Page reloaded")
            return True
        return False
    except Exception:
        return False


def _format_human_datetime(iso_string):
    """Convert ISO datetime string to human-readable local format."""
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        # Convert to local timezone for display
        local_dt = dt.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return iso_string


def _display_domains(domains, bypass_status=None):
    """Display domains in table format."""
    from inspekt.app.cli.table import Table

    # Show bypass status if active
    if bypass_status and bypass_status.get("enabled"):
        remaining_minutes = bypass_status.get("remainingMinutes", 0)
        if remaining_minutes > 0:
            click.echo(click.style(f"⚡ Bypass active ({remaining_minutes} min remaining)", fg="yellow"))
            click.echo()

    if not domains:
        table = Table(["Domain", "Added"], [40, 20])
        table.print_empty_message("No allowed domains")
        return

    count = len(domains)
    click.echo(f"Allowed domains ({count}):")
    click.echo()

    # Create table with domain and date columns
    table = Table(
        headers=["Domain", "Added"],
        widths=[40, 20],
        alignments=["left", "left"]
    )

    table.print_header()

    # Sort domains alphabetically
    sorted_domains = sorted(domains.items())

    for domain, metadata in sorted_domains:
        added_at = metadata.get("addedAt", "Unknown")
        formatted_date = _format_human_datetime(added_at)

        table.print_row([domain, formatted_date])

    table.print_footer()


# ============================================================================
# Top-level yolo command (registered separately in __init__.py)
# ============================================================================

@click.command()
@click.option("--disable", "-d", is_flag=True, help="Disable yolo mode")
@click.option("--status", "-s", is_flag=True, help="Check yolo mode status")
def yolo(disable, status):
    """
    YOLO mode - bypass ALL domain checks for 1 hour.

    When yolo mode is active:
    - CLI skips domain permission prompts
    - Browser extension skips domain checks
    - All domains are allowed without confirmation

    This is useful for development or when working across many domains.
    Yolo mode automatically expires after 1 hour.

    Examples:
        inspekt yolo              # Enable for 1 hour
        inspekt yolo --status     # Check if active and time remaining
        inspekt yolo --disable    # Disable early
    """
    try:
        domain_service = get_domain_service()

        if status:
            yolo_status = domain_service.get_yolo_status()
            if yolo_status.get("enabled"):
                remaining = yolo_status.get("remaining_minutes", 0)
                click.echo(f"YOLO mode is ACTIVE ({remaining} minutes remaining)")
            else:
                click.echo("YOLO mode is not active")
            return

        if disable:
            domain_service.disable_yolo_mode()
            browser_ok = _disable_browser_bypass()
            click.echo("✓ YOLO mode disabled")
            if not browser_ok:
                click.echo("  (Browser bypass may need page refresh)", err=True)
            return

        # Enable yolo mode for 60 minutes
        result = domain_service.enable_yolo_mode(duration_minutes=60)

        if result.get("ok"):
            click.echo("✓ YOLO mode enabled for 1 hour")
            click.echo("  All domain checks bypassed (CLI + browser)")

            # Also enable browser bypass and reload page
            browser_ok = _enable_browser_bypass(duration_minutes=60)
            if browser_ok:
                click.echo("  Browser bypass synced")
                # Auto-reload to apply bypass immediately
                _reload_browser_page()
        else:
            click.echo(f"Error: Failed to enable yolo mode", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
