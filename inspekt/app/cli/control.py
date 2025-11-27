"""Unified server management commands for Inspekt.

This module provides unified start/stop/restart/status commands that manage
both the bridge server and API server together.
"""

import json
import socket
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


def _is_port_open(host, port):
    """Check if a port is open on the given host."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        result = sock.connect_ex((host, port)) == 0
        return result
    finally:
        sock.close()


def _start_bridge_server(port=8765):
    """Start the bridge server in daemon mode.

    Returns:
        bool: True if started successfully, False otherwise
    """
    bridge_client = BridgeClient(port=port)

    if bridge_client.is_alive():
        click.echo(f"  • Bridge server is already running on ports {port} (HTTP) and {port + 1} (WebSocket)")
        return True

    click.echo("  • Starting bridge server…")
    subprocess.Popen(
        [sys.executable, "-m", "inspekt.bridge_ws"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # Wait for it to start
    time.sleep(1)
    if bridge_client.is_alive():
        click.echo(f"  ✓ Bridge server started on ports {port} (HTTP) and {port + 1} (WebSocket)")
        return True
    else:
        click.echo("  ✗ Failed to start bridge server", err=True)
        return False


def _start_api_server(host="127.0.0.1", port=8000):
    """Start the API server in daemon mode.

    Returns:
        bool: True if started successfully, False otherwise
    """
    if _is_port_open(host, port):
        click.echo(f"  • API server is already running on {host}:{port}")
        return True

    click.echo("  • Starting API server…")
    subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "inspekt.app.api.server:app",
            "--host", host,
            "--port", str(port)
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # Wait for it to start
    time.sleep(1.5)
    if _is_port_open(host, port):
        click.echo(f"  ✓ API server started on {host}:{port}")
        return True
    else:
        click.echo("  ✗ Failed to start API server", err=True)
        return False


def _stop_bridge_server():
    """Stop the bridge server.

    Returns:
        bool: True if stopped, False if it wasn't running
    """
    result = subprocess.run(
        ["pkill", "-f", "inspekt.bridge_ws"],
        capture_output=True
    )
    return result.returncode == 0


def _stop_api_server():
    """Stop the API server.

    Returns:
        bool: True if stopped, False if it wasn't running
    """
    result = subprocess.run(
        ["pkill", "-f", "uvicorn inspekt.app.api.server"],
        capture_output=True
    )
    return result.returncode == 0


@click.command()
@click.option("--bridge-only", is_flag=True, help="Start only the bridge server")
@click.option("--api-only", is_flag=True, help="Start only the API server")
@click.option("--foreground", is_flag=True, help="Run in foreground (for debugging)")
@click.option("--no-update-check", is_flag=True, help="Skip axe-core update check")
@click.option("--api-port", type=int, default=8000, help="API server port (default: 8000)")
@click.option("--bridge-port", type=int, default=8765, help="Bridge server port (default: 8765)")
@click.option("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
def start(bridge_only, api_only, foreground, no_update_check, api_port, bridge_port, host):
    """Start Inspekt servers (bridge + API) in daemon mode.

    By default, starts both bridge and API servers in background.
    Use --bridge-only or --api-only to start specific servers.
    Use --foreground for debugging (only works with single server).

    Examples:
        inspekt start                      # Start both servers in background
        inspekt start --bridge-only        # Start only bridge server
        inspekt start --foreground         # Start both in foreground (interactive)
        inspekt start --no-update-check    # Skip axe-core update check
        inspekt start --api-port 3000      # Use custom API port
    """
    # Check for updates unless disabled
    if not no_update_check:
        _check_axe_updates()

    click.echo("\nStarting Inspekt servers…\n")

    # Validate foreground mode
    if foreground and not (bridge_only or api_only):
        click.echo("Error: --foreground requires --bridge-only or --api-only", err=True)
        click.echo("(Cannot run multiple servers in foreground simultaneously)", err=True)
        sys.exit(1)

    # Determine what to start
    start_bridge = not api_only
    start_api = not bridge_only

    success = True

    # Start bridge server
    if start_bridge:
        if foreground:
            # Run bridge in foreground
            from inspekt.bridge_ws import main as start_ws_server

            click.echo("Starting bridge server in foreground…")
            click.echo(f"Ports: {bridge_port} (HTTP), {bridge_port + 1} (WebSocket)\n")
            click.echo("Press Ctrl+C to stop\n")

            try:
                import asyncio
                asyncio.run(start_ws_server())
            except KeyboardInterrupt:
                click.echo("\nBridge server stopped")
            return
        else:
            # Start in daemon mode
            if not _start_bridge_server(port=bridge_port):
                success = False

    # Start API server
    if start_api:
        if foreground:
            # Run API in foreground
            bridge_client = BridgeClient(port=bridge_port)
            if not bridge_client.is_alive():
                click.echo("Error: Bridge server must be running to start API server", err=True)
                click.echo("Start it first with: inspekt start --bridge-only", err=True)
                sys.exit(1)

            click.echo("Starting API server in foreground…")
            display_host = "localhost" if host == "127.0.0.1" else host
            click.echo(f"\nAPI server running at:")
            click.echo(f"  • Status:        http://{display_host}:{api_port}/status")
            click.echo(f"  • Swagger UI:    http://{display_host}:{api_port}/docs")
            click.echo(f"  • ReDoc:         http://{display_host}:{api_port}/redoc")
            click.echo(f"  • Health check:  http://{display_host}:{api_port}/health")
            click.echo(f"  • API root:      http://{display_host}:{api_port}/")
            click.echo("\nPress Ctrl+C to stop the server\n")

            try:
                subprocess.run([
                    sys.executable, "-m", "uvicorn",
                    "inspekt.app.api.server:app",
                    "--host", host,
                    "--port", str(api_port)
                ])
            except KeyboardInterrupt:
                click.echo("\nAPI server stopped")
            return
        else:
            # Start in daemon mode
            if not _start_api_server(host=host, port=api_port):
                success = False

    # Display summary
    if success:
        click.echo("\n✓ All servers started successfully\n")

        if start_bridge:
            click.echo(f"Bridge Server:")
            click.echo(f"  • HTTP API:      http://127.0.0.1:{bridge_port}")
            click.echo(f"  • WebSocket:     ws://127.0.0.1:{bridge_port + 1}")

        if start_api:
            display_host = "localhost" if host == "127.0.0.1" else host
            click.echo(f"\nAPI Server:")
            click.echo(f"  • Status:        http://{display_host}:{api_port}/status")
            click.echo(f"  • Swagger UI:    http://{display_host}:{api_port}/docs")
            click.echo(f"  • ReDoc:         http://{display_host}:{api_port}/redoc")
            click.echo(f"  • Health:        http://{display_host}:{api_port}/health")

        click.echo(f"\nView status: inspekt status")
        click.echo(f"Stop servers: inspekt stop")
    else:
        click.echo("\n✗ Failed to start one or more servers", err=True)
        sys.exit(1)


@click.command()
@click.option("--bridge-only", is_flag=True, help="Stop only the bridge server")
@click.option("--api-only", is_flag=True, help="Stop only the API server")
def stop(bridge_only, api_only):
    """Stop Inspekt servers.

    By default, stops both bridge and API servers.
    Use --bridge-only or --api-only to stop specific servers.

    Examples:
        inspekt stop                # Stop both servers
        inspekt stop --bridge-only  # Stop only bridge server
        inspekt stop --api-only     # Stop only API server
    """
    click.echo("Stopping Inspekt servers…\n")

    # Determine what to stop
    stop_bridge = not api_only
    stop_api = not bridge_only

    bridge_stopped = False
    api_stopped = False

    # Stop API server first (depends on bridge)
    if stop_api:
        click.echo("  • Stopping API server…")
        if _stop_api_server():
            click.echo("    ✓ API server stopped")
            api_stopped = True
        else:
            click.echo("    • API server was not running")

    # Stop bridge server
    if stop_bridge:
        click.echo("  • Stopping bridge server…")
        if _stop_bridge_server():
            click.echo("    ✓ Bridge server stopped")
            bridge_stopped = True
        else:
            click.echo("    • Bridge server was not running")

    # Summary
    if bridge_stopped or api_stopped:
        click.echo("\n✓ Server(s) stopped successfully")
    else:
        click.echo("\n• No servers were running")

    # Note about foreground processes
    if stop_bridge or stop_api:
        click.echo("\nNote: If servers are running in foreground, use Ctrl+C to stop them.")


@click.command()
@click.option("--no-update-check", is_flag=True, help="Skip axe-core update check")
@click.option("--api-port", type=int, default=8000, help="API server port (default: 8000)")
@click.option("--bridge-port", type=int, default=8765, help="Bridge server port (default: 8765)")
@click.option("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
def restart(no_update_check, api_port, bridge_port, host):
    """Restart both bridge and API servers.

    This command stops any running servers, optionally checks for updates,
    then starts both servers fresh in daemon mode.

    Examples:
        inspekt restart                   # Restart both servers
        inspekt restart --no-update-check # Skip update check
        inspekt restart --api-port 3000   # Use custom API port
    """
    click.echo("Restarting Inspekt servers…\n")

    # Stop both servers
    click.echo("  • Stopping API server…")
    api_stopped = _stop_api_server()
    if api_stopped:
        click.echo("    ✓ API server stopped")
    else:
        click.echo("    • API server was not running")

    click.echo("  • Stopping bridge server…")
    bridge_stopped = _stop_bridge_server()
    if bridge_stopped:
        click.echo("    ✓ Bridge server stopped")
    else:
        click.echo("    • Bridge server was not running")

    # Wait for processes to fully stop
    time.sleep(0.5)

    click.echo()

    # Check for updates unless disabled
    if not no_update_check:
        _check_axe_updates()

    bridge_success = _start_bridge_server(port=bridge_port)

    if not bridge_success:
        click.echo("\n✗ Failed to start bridge server", err=True)
        sys.exit(1)

    api_success = _start_api_server(host=host, port=api_port)

    if not api_success:
        click.echo("\n✗ Failed to start API server", err=True)
        sys.exit(1)

    # Display summary
    click.echo("\n✓ All servers restarted successfully\n")

    display_host = "localhost" if host == "127.0.0.1" else host
    click.echo(f"Bridge Server:")
    click.echo(f"  • HTTP API:      http://127.0.0.1:{bridge_port}")
    click.echo(f"  • WebSocket:     ws://127.0.0.1:{bridge_port + 1}")

    click.echo(f"\nAPI Server:")
    click.echo(f"  • Status:        http://{display_host}:{api_port}/status")
    click.echo(f"  • Swagger UI:    http://{display_host}:{api_port}/docs")
    click.echo(f"  • ReDoc:         http://{display_host}:{api_port}/redoc")
    click.echo(f"  • Health:        http://{display_host}:{api_port}/health")


@click.command()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def status(output_json):
    """Check status of all Inspekt servers.

    Shows comprehensive status information for both bridge and API servers,
    including connected browsers, request statistics, and uptime.

    Examples:
        inspekt status        # Human-readable status
        inspekt status --json # JSON output
    """
    bridge_client = BridgeClient()

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

    # Check bridge server status
    bridge_running = bridge_client.is_alive()
    bridge_status = bridge_client.get_status() if bridge_running else None

    # Check API server status
    api_running = _is_port_open("127.0.0.1", 8000)

    if output_json:
        # JSON output
        output_data = {
            "bridge_server": {
                "running": bridge_running,
                "status": bridge_status if bridge_status else None
            },
            "api_server": {
                "running": api_running,
                "port": 8000 if api_running else None
            }
        }
        click.echo(json.dumps(output_data, indent=2))
    else:
        # Human-readable output
        click.echo("Inspekt Server Status\n")

        # Bridge Server Section
        click.echo("=" * 60)
        click.echo("BRIDGE SERVER")
        click.echo("=" * 60)

        if bridge_running and bridge_status:
            # Server Information
            click.echo("\nServer Information:")
            click.echo(f"  Version:           {bridge_status.get('server_version', 'Unknown')}")
            uptime = bridge_status.get('uptime_seconds', 0)
            click.echo(f"  Uptime:            {format_duration(uptime)}")
            host = bridge_status.get('host', '127.0.0.1')
            port = bridge_status.get('port', 8765)
            ws_port = bridge_status.get('websocket_port', 8766)
            click.echo(f"  HTTP API:          http://{host}:{port}")
            click.echo(f"  WebSocket:         ws://{host}:{ws_port}")

            # Connected Browser Instances
            click.echo("\nConnected Browser Instances:")
            browser_count = bridge_status.get('connected_browsers', 0)
            browsers = bridge_status.get('browsers', [])

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
            click.echo(f"  Pending:           {bridge_status.get('pending', 0)}")
            total = bridge_status.get('total_processed', 0)
            succeeded = bridge_status.get('total_succeeded', 0)
            failed = bridge_status.get('total_failed', 0)
            click.echo(f"  Total Processed:   {total} (since startup)")
            click.echo(f"  Succeeded:         {succeeded}")
            click.echo(f"  Failed:            {failed}")
            if total > 0:
                success_rate = (succeeded / total) * 100
                click.echo(f"  Success Rate:      {success_rate:.1f}%")
            last_activity = bridge_status.get('last_activity')
            if last_activity:
                click.echo(f"  Last Activity:     {format_time_ago(last_activity)}")

            # Performance
            cached = bridge_status.get('cached_scripts', [])
            if cached:
                click.echo("\nPerformance:")
                click.echo(f"  Cached Scripts:    {len(cached)} ({', '.join(cached)})")
        elif bridge_running:
            click.echo("\n✓ Running (status unavailable)")
        else:
            click.echo("\n✗ Not Running")
            click.echo("\nStart with: inspekt start")

        # API Server Section
        click.echo("\n" + "=" * 60)
        click.echo("API SERVER")
        click.echo("=" * 60)

        if api_running:
            click.echo("\n✓ Running")
            click.echo(f"  Port:              8000")
            click.echo(f"  URL:               http://localhost:8000")
            click.echo(f"  Swagger UI:        http://localhost:8000/docs")
            click.echo(f"  ReDoc:             http://localhost:8000/redoc")
            click.echo(f"  Health Check:      http://localhost:8000/health")
        else:
            click.echo("\n✗ Not Running")
            click.echo("\nStart with: inspekt start")

        click.echo("\n" + "=" * 60)

    # Exit with error if either server is not running
    if not (bridge_running and api_running):
        sys.exit(1)


# Queue management command group
@click.group()
def queue():
    """Manage the request queue.

    View and manage pending requests in the bridge server queue.
    Use this to diagnose or fix stuck requests.

    Examples:
        inspekt queue status    # View queue status
        inspekt queue clear     # Clear all pending requests
    """
    pass


@queue.command("status")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def queue_status(output_json):
    """Show queue status and pending requests.

    Displays the number of pending and completed requests,
    along with details about each pending request.

    Examples:
        inspekt queue status        # Human-readable output
        inspekt queue status --json # JSON output
    """
    import requests as http_requests

    client = BridgeClient()

    if not client.is_alive():
        click.echo("Error: Bridge server is not running", err=True)
        sys.exit(1)

    try:
        response = http_requests.get(f"{client.base_url}/queue/status", timeout=5)
        data = response.json()

        if output_json:
            click.echo(json.dumps(data, indent=2))
            return

        pending = data.get("pending_count", 0)
        completed = data.get("completed_count", 0)
        oldest_age = data.get("oldest_pending_age", 0)

        click.echo("Queue Status\n")
        click.echo(f"  Pending requests:   {pending}")
        click.echo(f"  Completed (cached): {completed}")

        if oldest_age > 0:
            click.echo(f"  Oldest pending:     {oldest_age:.1f}s ago")

        pending_requests = data.get("pending_requests", [])
        if pending_requests:
            click.echo("\nPending Requests:")
            for req in pending_requests:
                req_id = req.get("request_id", "unknown")[:8]
                age = req.get("age_seconds", 0)
                req_type = req.get("type", "execute")

                # Color code based on age
                if age > 60:
                    age_str = click.style(f"{age:.1f}s", fg="red")
                elif age > 30:
                    age_str = click.style(f"{age:.1f}s", fg="yellow")
                else:
                    age_str = f"{age:.1f}s"

                click.echo(f"  • {req_id}... ({age_str}) - {req_type}")
        elif pending == 0:
            click.echo("\n✓ No pending requests")

    except http_requests.RequestException as e:
        click.echo(f"Error: Failed to get queue status: {e}", err=True)
        sys.exit(1)


@queue.command("clear")
@click.option("--older-than", type=float, default=0,
              help="Only clear requests older than N seconds (default: all)")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def queue_clear(older_than, force):
    """Clear pending requests from the queue.

    By default, clears all pending requests. Use --older-than to only
    clear requests that have been pending for a certain time.

    This is useful when requests get stuck and are blocking new ones.

    Examples:
        inspekt queue clear              # Clear all
        inspekt queue clear --older-than 30  # Clear requests older than 30s
        inspekt queue clear -f           # Skip confirmation
    """
    import requests as http_requests

    client = BridgeClient()

    if not client.is_alive():
        click.echo("Error: Bridge server is not running", err=True)
        sys.exit(1)

    # First get status to show what will be cleared
    try:
        status_response = http_requests.get(f"{client.base_url}/queue/status", timeout=5)
        status_data = status_response.json()
        pending_count = status_data.get("pending_count", 0)

        if pending_count == 0:
            click.echo("No pending requests to clear")
            return

        # Count how many will be cleared
        pending_requests = status_data.get("pending_requests", [])
        to_clear = [r for r in pending_requests if r.get("age_seconds", 0) >= older_than]

        if not to_clear:
            if older_than > 0:
                click.echo(f"No requests older than {older_than}s to clear")
            else:
                click.echo("No pending requests to clear")
            return

        # Confirm unless --force
        if not force:
            if older_than > 0:
                msg = f"Clear {len(to_clear)} request(s) older than {older_than}s?"
            else:
                msg = f"Clear all {len(to_clear)} pending request(s)?"

            if not click.confirm(msg):
                click.echo("Cancelled")
                return

        # Clear the queue
        response = http_requests.post(
            f"{client.base_url}/queue/clear",
            json={"older_than": older_than},
            timeout=5
        )
        result = response.json()

        if result.get("ok"):
            cleared = result.get("cleared", 0)
            remaining = result.get("remaining", 0)
            click.echo(f"✓ Cleared {cleared} pending request(s)")
            if remaining > 0:
                click.echo(f"  {remaining} request(s) remaining")
        else:
            click.echo(f"Error: {result.get('error', 'Unknown error')}", err=True)
            sys.exit(1)

    except http_requests.RequestException as e:
        click.echo(f"Error: Failed to clear queue: {e}", err=True)
        sys.exit(1)
