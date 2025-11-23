"""
Domain command group - Manage allowed domains for browser automation.

This module provides commands for domain permission management:
- add: Add a domain to the allow list
- remove: Remove a domain from the allow list
- list: List all allowed domains with timestamps

Domains are stored in chrome.storage.sync and managed via the bridge server.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime

import click
import requests

from inspekt.services.domain_service import get_domain_service

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

    The domain will be added to chrome.storage.sync with a timestamp.
    Parent domains grant access to subdomains (e.g., github.com allows www.github.com).

    Examples:
        inspekt domain add github.com
        inspekt domain add localhost
        inspekt domain add example.com
    """
    try:
        response = requests.post(
            f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/domains/add",
            json={"domain": domain_name},
            timeout=10.0
        )

        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                click.echo(f"✓ Domain added: {domain_name}")
                if result.get("already_exists"):
                    click.echo("  (Domain was already in the allow list)")
            else:
                click.echo(f"Error: {result.get('error', 'Unknown error')}", err=True)
                sys.exit(1)
        else:
            click.echo(f"Error: HTTP {response.status_code}", err=True)
            sys.exit(1)

    except requests.exceptions.ConnectionError:
        click.echo("Error: Could not connect to bridge server", err=True)
        click.echo("Make sure the server is running: inspekt server start", err=True)
        sys.exit(1)
    except requests.exceptions.Timeout:
        click.echo("Error: Request timed out", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@domain.command(name="remove")
@click.argument("domain_name")
def domain_remove(domain_name):
    """
    Remove a domain from the allowed list.

    The domain will be removed from chrome.storage.sync.

    Examples:
        inspekt domain remove github.com
        inspekt domain remove localhost
    """
    try:
        response = requests.delete(
            f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/domains/remove",
            json={"domain": domain_name},
            timeout=10.0
        )

        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                click.echo(f"✓ Domain removed: {domain_name}")
                if result.get("not_found"):
                    click.echo("  (Domain was not in the allow list)")
            else:
                click.echo(f"Error: {result.get('error', 'Unknown error')}", err=True)
                sys.exit(1)
        else:
            click.echo(f"Error: HTTP {response.status_code}", err=True)
            sys.exit(1)

    except requests.exceptions.ConnectionError:
        click.echo("Error: Could not connect to bridge server", err=True)
        click.echo("Make sure the server is running: inspekt server start", err=True)
        sys.exit(1)
    except requests.exceptions.Timeout:
        click.echo("Error: Request timed out", err=True)
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

    Examples:
        inspekt domain list              # Human-readable format
        inspekt domain list --json       # JSON format
    """
    try:
        response = requests.get(
            f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/domains/list",
            timeout=10.0
        )

        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                domains = result.get("domains", {})

                # Also get bypass status
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
            else:
                click.echo(f"Error: {result.get('error', 'Unknown error')}", err=True)
                sys.exit(1)
        else:
            click.echo(f"Error: HTTP {response.status_code}", err=True)
            sys.exit(1)

    except requests.exceptions.ConnectionError:
        click.echo("Error: Could not connect to bridge server", err=True)
        click.echo("Make sure the server is running: inspekt server start", err=True)
        sys.exit(1)
    except requests.exceptions.Timeout:
        click.echo("Error: Request timed out", err=True)
        sys.exit(1)
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
                        click.echo(f"  Expires at: {expires_at}")
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
        click.echo("Make sure the server is running: inspekt server start", err=True)
        sys.exit(1)
    except requests.exceptions.Timeout:
        click.echo("Error: Request timed out", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@domain.command(name="migrate")
def domain_migrate():
    """
    Migrate domains from browser extension storage to SQLite database.

    This command fetches all domains from the browser extension's chrome.storage.sync
    and imports them into the local SQLite database. This is a one-time migration
    that should be run when upgrading to the SQLite-based domain storage.

    Examples:
        inspekt domain migrate
    """
    try:
        click.echo("Fetching domains from browser extension...")

        # Get domains from browser extension via bridge server
        response = requests.get(
            f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/domains/list",
            timeout=10.0
        )

        if response.status_code != 200:
            click.echo(f"Error: HTTP {response.status_code}", err=True)
            sys.exit(1)

        result = response.json()
        if not result.get("ok"):
            click.echo(f"Error: {result.get('error', 'Unknown error')}", err=True)
            sys.exit(1)

        browser_domains = result.get("domains", {})

        if not browser_domains:
            click.echo("No domains found in browser extension storage")
            return

        click.echo(f"Found {len(browser_domains)} domain(s) in browser extension")

        # Convert to DomainService format
        domains_to_import = []
        for domain_name, metadata in browser_domains.items():
            domains_to_import.append({
                "domain": domain_name,
                "addedAt": metadata.get("addedAt"),
                "permanent": metadata.get("permanent", True)
            })

        # Import into SQLite
        domain_service = get_domain_service()
        import_result = domain_service.import_domains(domains_to_import)

        if import_result.get("ok"):
            imported = import_result.get("imported", 0)
            total = import_result.get("total", 0)

            click.echo(f"✓ Migration complete!")
            click.echo(f"  Imported: {imported} new domain(s)")

            if imported < total:
                skipped = total - imported
                click.echo(f"  Skipped: {skipped} domain(s) (already in database)")
        else:
            click.echo("Error: Failed to import domains", err=True)
            sys.exit(1)

    except requests.exceptions.ConnectionError:
        click.echo("Error: Could not connect to bridge server", err=True)
        click.echo("Make sure the server is running: inspekt server start", err=True)
        sys.exit(1)
    except requests.exceptions.Timeout:
        click.echo("Error: Request timed out", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@domain.command(name="sync")
def domain_sync():
    """
    Sync domains from SQLite database to browser extension storage.

    This command sends all domains from the local SQLite database to the browser
    extension's chrome.storage.sync. Use this to ensure the browser extension has
    the latest domain list from the database.

    Examples:
        inspekt domain sync
    """
    try:
        response = requests.post(
            f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/domains/sync",
            timeout=10.0
        )

        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                synced = result.get("synced", 0)
                click.echo(f"✓ Synced {synced} domain(s) to browser extension")
            else:
                error = result.get("error", "Unknown error")
                click.echo(f"Warning: Sync completed with error: {error}", err=True)
        else:
            click.echo(f"Error: HTTP {response.status_code}", err=True)
            sys.exit(1)

    except requests.exceptions.ConnectionError:
        click.echo("Error: Could not connect to bridge server", err=True)
        click.echo("Make sure the server is running: inspekt server start", err=True)
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

def _display_domains(domains, bypass_status=None):
    """Display domains in human-readable format."""
    if not domains:
        click.echo("No allowed domains")
        return

    count = len(domains)
    click.echo(f"Allowed domains ({count}):\n")

    # Sort domains alphabetically
    sorted_domains = sorted(domains.items())

    for domain, metadata in sorted_domains:
        added_at = metadata.get("addedAt", "Unknown")

        # Format timestamp
        try:
            dt = datetime.fromisoformat(added_at.replace("Z", "+00:00"))
            formatted_date = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, AttributeError):
            formatted_date = added_at

        # Display domain info in compact format
        click.echo(f"  {domain} ({formatted_date})")

    # Show bypass status if active and not expired
    if bypass_status and bypass_status.get("enabled"):
        remaining_minutes = bypass_status.get("remainingMinutes", 0)
        if remaining_minutes > 0:
            click.echo(f"\n⚡ Bypass currently active ({remaining_minutes} minutes remaining)")

    click.echo()
