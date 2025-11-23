"""Server management commands for the Zen bridge."""

import json
import subprocess
import sys
import time

import click

from inspekt.client import BridgeClient
from inspekt.services.axe_updater import get_axe_updater


def _check_axe_updates():
    """Check for axe-core updates and prompt user to update."""
    updater = get_axe_updater()

    try:
        # Check for updates (quick, non-blocking)
        click.echo("  • Checking for axe-core updates…", err=True)
        update_available, current, latest = updater.is_update_available()

        if not latest:
            # Network error or timeout - silently continue
            return

        if not update_available:
            # Already on latest version
            click.echo(f"  ✓ axe-core is up-to-date ({current})", err=True)
            return

        # Update available - prompt user
        click.echo(f"  ✓ axe-core {latest} is available (current: {current})", err=True)
        click.echo("", err=True)

        # Ask user if they want to update
        if click.confirm(f"Update to axe-core {latest}?", default=True):
            click.echo("", err=True)

            # Progress callback
            def show_progress(msg):
                click.echo(f"{msg}", err=True)

            # Perform update
            success, message = updater.update_to_latest(progress_callback=show_progress)

            if success:
                click.echo(f"\n✓ {message}\n", err=True)
            else:
                click.echo(f"\n✗ Update failed: {message}", err=True)
                click.echo("Continuing with current version.\n", err=True)
        else:
            click.echo("Skipping update.\n", err=True)

    except Exception:
        # Silently continue on any error - don't block server start
        pass


@click.group()
def server():
    """Manage the bridge server."""
    pass


@server.command()
@click.option("-p", "--port", type=int, default=8765, help="Port to run on (default: 8765)")
@click.option("-d", "--daemon", is_flag=True, help="Run in background")
def start(port, daemon):
    """Start the bridge server."""
    # Check for axe-core updates before starting server
    _check_axe_updates()

    client = BridgeClient(port=port)

    if client.is_alive():
        click.echo(f"Bridge server is already running on port {port}")
        return

    if daemon:
        # Run in background
        click.echo(f"Starting WebSocket bridge server in background on port {port}...")
        subprocess.Popen(
            [sys.executable, "-m", "inspekt.bridge_ws"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # Wait a bit and check if it started
        import time

        time.sleep(0.5)
        if client.is_alive():
            click.echo(
                "WebSocket server started successfully on ports 8765 (HTTP) and 8766 (WebSocket)"
            )
        else:
            click.echo("Failed to start server", err=True)
            sys.exit(1)
    else:
        # Run in foreground
        from inspekt.bridge_ws import main as start_ws_server

        try:
            import asyncio

            asyncio.run(start_ws_server())
        except KeyboardInterrupt:
            click.echo("\nServer stopped")


@server.command()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def status(output_json):
    """Check bridge server status."""
    client = BridgeClient()

    def format_duration(seconds):
        """Format duration in human-readable format."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            mins = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s"
        else:
            hours = int(seconds / 3600)
            mins = int((seconds % 3600) / 60)
            secs = int(seconds % 60)
            return f"{hours}h {mins}m {secs}s"

    def format_time_ago(timestamp):
        """Format timestamp as 'X time ago'."""
        ago = time.time() - timestamp
        if ago < 60:
            return f"{int(ago)} seconds ago"
        elif ago < 3600:
            return f"{int(ago/60)} minutes ago"
        else:
            return f"{int(ago/3600)} hours ago"

    if client.is_alive():
        status = client.get_status()
        if output_json:
            # Full JSON output with all fields
            click.echo(json.dumps(status, indent=2))
        elif status:
            # Enhanced human-readable output
            click.echo("Inspekt Server Status\n")

            # Server Information
            click.echo("Server Information:")
            click.echo(f"  Version:           {status.get('server_version', 'Unknown')}")
            uptime = status.get('uptime_seconds', 0)
            click.echo(f"  Uptime:            {format_duration(uptime)}")
            host = status.get('host', '127.0.0.1')
            port = status.get('port', 8765)
            ws_port = status.get('websocket_port', 8766)
            click.echo(f"  HTTP API:          http://{host}:{port}")
            click.echo(f"  WebSocket:         ws://{host}:{ws_port}")

            # Connected Browser Instances
            click.echo("\nConnected Browser Instances:")
            browser_count = status.get('connected_browsers', 0)
            browsers = status.get('browsers', [])

            if browser_count == 0:
                click.echo("  No browsers connected")
            else:
                click.echo(f"  Total:             {browser_count} active connection{'s' if browser_count != 1 else ''}")

                for i, browser in enumerate(browsers, 1):
                    # Display browser name with version
                    browser_name = browser['browser_name']
                    browser_version = browser.get('browser_version', '')
                    if browser_version:
                        browser_display = f"{browser_name} {browser_version}"
                    else:
                        browser_display = browser_name

                    click.echo(f"\n  [{i}] {browser_display}{' (last active)' if browser['is_most_recent'] else ''}")
                    if browser.get('extension_version'):
                        click.echo(f"      Extension:     v{browser['extension_version']}")
                    url = browser.get('url', '')
                    if url:
                        # Truncate long URLs
                        display_url = url if len(url) <= 60 else url[:57] + '...'
                        click.echo(f"      Page:          {display_url}")
                    title = browser.get('title', '')
                    if title:
                        # Truncate long titles
                        display_title = title if len(title) <= 60 else title[:57] + '...'
                        click.echo(f"      Title:         {display_title}")
                    duration = browser.get('connected_duration', 0)
                    click.echo(f"      Connected:     {format_duration(duration)}")

            # Request Statistics
            click.echo("\nRequest Statistics:")
            click.echo(f"  Pending:           {status.get('pending', 0)}")
            total = status.get('total_processed', 0)
            succeeded = status.get('total_succeeded', 0)
            failed = status.get('total_failed', 0)
            click.echo(f"  Total Processed:   {total} (since startup)")
            click.echo(f"  Succeeded:         {succeeded}")
            click.echo(f"  Failed:            {failed}")
            if total > 0:
                success_rate = (succeeded / total) * 100
                click.echo(f"  Success Rate:      {success_rate:.1f}%")
            last_activity = status.get('last_activity')
            if last_activity:
                click.echo(f"  Last Activity:     {format_time_ago(last_activity)}")

            # Performance
            cached = status.get('cached_scripts', [])
            if cached:
                click.echo("\nPerformance:")
                click.echo(f"  Cached Scripts:    {len(cached)} ({', '.join(cached)})")

            # API Server
            api_server = status.get('api_server', {})
            click.echo("\nAPI Server:")
            if api_server and api_server.get('running'):
                click.echo(f"  Status:            Running")
                click.echo(f"  Port:              {api_server.get('port', 8000)}")
                api_uptime = api_server.get('uptime_seconds', 0)
                click.echo(f"  Uptime:            {format_duration(api_uptime)}")
                click.echo(f"  URL:               http://localhost:{api_server.get('port', 8000)}")
                click.echo(f"  Swagger UI:        http://localhost:{api_server.get('port', 8000)}/docs")
                click.echo(f"  ReDoc:             http://localhost:{api_server.get('port', 8000)}/redoc")

                # API Request Statistics
                api_total = api_server.get('total_requests', 0)
                api_succeeded = api_server.get('succeeded', 0)
                api_failed = api_server.get('failed', 0)
                if api_total > 0:
                    click.echo(f"  Total Requests:    {api_total}")
                    click.echo(f"  Succeeded:         {api_succeeded}")
                    click.echo(f"  Failed:            {api_failed}")
                    api_success_rate = (api_succeeded / api_total) * 100
                    click.echo(f"  Success Rate:      {api_success_rate:.1f}%")
            else:
                click.echo(f"  Status:            Not Running")
                click.echo(f"  Start with:        inspekt api start")

        else:
            click.echo("Inspekt Server Status (Running, status unavailable)")
    else:
        if output_json:
            click.echo(json.dumps({"running": False}, indent=2))
        else:
            click.echo("Inspekt Server Status (Not Running)")
            click.echo("Start it with: inspekt server start")
        sys.exit(1)


@server.command()
def stop():
    """Stop the bridge server."""
    click.echo("Note: Use Ctrl+C to stop the server if running in foreground")
    click.echo("For daemon mode, use: pkill -f 'inspekt.bridge_ws'")
