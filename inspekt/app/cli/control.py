"""Unified server management commands for Inspekt.

This module provides unified start/stop/restart/status commands that manage
both the bridge server and API server together.
"""

import json
import os
import socket
import subprocess
import sys
import time

import click

from inspekt.app.cli.icons import success, error, info, progress
from inspekt.client import BridgeClient
from inspekt.services.axe_updater import get_axe_updater


def _format_release_date(iso_date: str | None) -> str:
    """Format ISO date string to human-readable format (e.g., 'October 9, 2025')."""
    if not iso_date:
        return ""
    try:
        from datetime import datetime
        # Parse ISO date (e.g., "2025-10-09T16:39:18.813Z")
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        # Use %d and strip leading zero manually for cross-platform compatibility
        day = str(dt.day)  # No leading zero
        return dt.strftime(f"%B {day}, %Y")  # "October 9, 2025"
    except (ValueError, AttributeError):
        return ""


def _check_axe_updates():
    """Check for axe-core updates and prompt user to update."""
    updater = get_axe_updater()

    try:
        # Check for updates (quick, non-blocking)
        click.echo(f"  {progress('Checking for axe-core updates…')}", err=True)
        update_available, current, latest, release_date = updater.is_update_available()

        if not latest:
            # Network error or timeout - silently continue
            return

        # Format release date for display
        date_str = _format_release_date(release_date)
        date_suffix = f" • {date_str}" if date_str else ""

        if not update_available:
            # Already on latest version
            click.echo(f"  {success(f'axe-core is up-to-date ({current}{date_suffix})')}", err=True)
            return

        # Update available - prompt user
        click.echo(f"  {success(f'axe-core {latest} is available{date_suffix} (current: {current})')}", err=True)
        click.echo("", err=True)

        # Ask user if they want to update
        if click.confirm(f"Update to axe-core {latest}?", default=True):
            click.echo("", err=True)

            # Progress callback
            def show_progress(msg):
                click.echo(f"{msg}", err=True)

            # Perform update
            update_success, message = updater.update_to_latest(progress_callback=show_progress)

            if update_success:
                from inspekt.app.cli.icons import success as success_msg
                click.echo(f"\n{success_msg(message)}\n", err=True)
            else:
                click.echo(f"\n{error(f'Update failed: {message}')}", err=True)
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
        click.echo(f"  {info(f'Bridge server is already running on ports {port} (HTTP) and {port + 1} (WebSocket)')}")
        return True

    click.echo(f"  {progress('Starting bridge server…')}")
    subprocess.Popen(
        [sys.executable, "-m", "inspekt.bridge_ws"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # Wait for it to start
    time.sleep(1)
    if bridge_client.is_alive():
        click.echo(f"  {success(f'Bridge server started on ports {port} (HTTP) and {port + 1} (WebSocket)')}")
        return True
    else:
        click.echo(f"  {error('Failed to start bridge server')}", err=True)
        return False


def _start_api_server(host="127.0.0.1", port=8000):
    """Start the API server in daemon mode.

    Returns:
        bool: True if started successfully, False otherwise
    """
    if _is_port_open(host, port):
        click.echo(f"  {info(f'API server is already running on {host}:{port}')}")
        return True

    click.echo(f"  {progress('Starting API server…')}")
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
        click.echo(f"  {success(f'API server started on {host}:{port}')}")
        return True
    else:
        click.echo(f"  {error('Failed to start API server')}", err=True)
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


def _get_project_root():
    """Get the Inspekt project root directory (where mkdocs.yml lives)."""
    import inspekt
    return os.path.dirname(os.path.dirname(inspekt.__file__))


def _start_mkdocs_server(host="127.0.0.1", port=8008):
    """Start the MkDocs documentation server in daemon mode.

    Returns:
        bool: True if started successfully, False otherwise
    """
    if _is_port_open(host, port):
        click.echo(f"  {info(f'MkDocs server is already running on {host}:{port}')}")
        return True

    # MkDocs must run from the directory containing mkdocs.yml
    project_root = _get_project_root()
    mkdocs_config = os.path.join(project_root, "mkdocs.yml")

    if not os.path.exists(mkdocs_config):
        click.echo(f"  {error('mkdocs.yml not found - docs not available in this installation')}", err=True)
        return False

    click.echo(f"  {progress('Starting MkDocs server (building docs)…')}")
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "mkdocs",
            "serve",
            "--dev-addr", f"{host}:{port}",
            "--quiet"
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        cwd=project_root,  # Run from project root where mkdocs.yml lives
    )

    # Wait for it to start - MkDocs needs to build docs first
    # Poll both the port AND the process status to fail fast if process dies
    max_wait = 60  # generous timeout - large docs can take time
    poll_interval = 0.5  # seconds
    waited = 0
    while waited < max_wait:
        time.sleep(poll_interval)
        waited += poll_interval

        # Check if process is still running
        if proc.poll() is not None:
            # Process has exited - something went wrong
            click.echo(f"  {error('MkDocs server exited unexpectedly')}", err=True)
            click.echo(f"    Check that mkdocs is installed: pip install mkdocs mkdocs-material", err=True)
            return False

        # Check if port is now open
        if _is_port_open(host, port):
            click.echo(f"  {success(f'MkDocs server started on {host}:{port}')}")
            return True

    # Timeout - process is still running but port never opened
    click.echo(f"  {error('MkDocs server timeout - docs may still be building')}", err=True)
    click.echo(f"    Try opening http://{host}:{port} manually in a few seconds", err=True)
    return False


def _stop_mkdocs_server():
    """Stop the MkDocs documentation server.

    Returns:
        bool: True if stopped, False if it wasn't running
    """
    result = subprocess.run(
        ["pkill", "-f", "mkdocs serve"],
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
@click.option("--docs", is_flag=True, help="Start local MkDocs documentation server")
@click.option("--docs-port", type=int, default=8008, help="MkDocs server port (default: 8008)")
def start(bridge_only, api_only, foreground, no_update_check, api_port, bridge_port, host, docs, docs_port):
    """Start Inspekt servers (bridge + API) in daemon mode.

    By default, starts both bridge and API servers in background.
    Use --bridge-only or --api-only to start specific servers.
    Use --foreground for debugging (only works with single server).
    Use --docs to also start a local MkDocs documentation server.

    Examples:
        inspekt start                      # Start both servers in background
        inspekt start --docs               # Include local documentation server
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

    start_success = True

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
                start_success = False

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
            click.echo(f"  {info(f'Status:        http://{display_host}:{api_port}/status')}")
            click.echo(f"  {info(f'Swagger UI:    http://{display_host}:{api_port}/docs')}")
            click.echo(f"  {info(f'ReDoc:         http://{display_host}:{api_port}/redoc')}")
            click.echo(f"  {info(f'Health check:  http://{display_host}:{api_port}/health')}")
            click.echo(f"  {info(f'API root:      http://{display_host}:{api_port}/')}")
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
                start_success = False

    # Start MkDocs server if --docs flag is passed
    if docs and start_success:
        if not _start_mkdocs_server(host=host, port=docs_port):
            start_success = False

    # Display summary
    if start_success:
        click.echo(f"\n{success('All servers started successfully')}\n")

        # Show docs first (most relevant when --docs is used)
        if docs:
            display_host = "localhost" if host == "127.0.0.1" else host
            click.echo(f"Docs Server:")
            click.echo(f"  {info(f'MkDocs:        http://{display_host}:{docs_port}')}")
            click.echo(f"  {info(f'Swagger UI:    http://{display_host}:{api_port}/docs')}")
            click.echo(f"  {info(f'ReDoc:         http://{display_host}:{api_port}/redoc')}")

        if start_bridge:
            click.echo(f"Bridge Server:")
            click.echo(f"  {info(f'HTTP API:      http://127.0.0.1:{bridge_port}')}")
            click.echo(f"  {info(f'WebSocket:     ws://127.0.0.1:{bridge_port + 1}')}")

        if start_api:
            display_host = "localhost" if host == "127.0.0.1" else host
            click.echo(f"\nAPI Server:")
            click.echo(f"  {info(f'Status:        http://{display_host}:{api_port}/status')}")
            click.echo(f"  {info(f'Health:        http://{display_host}:{api_port}/health')}")

        click.echo(f"\nWeb-based status: http://localhost:{api_port}/status")
        click.echo(f"View status: inspekt status")
        click.echo(f"Stop servers: inspekt stop")

        # Show tip about --docs if not used
        if not docs:
            click.echo()
            from inspekt.app.cli.table import print_hint
            print_hint(f"Run with `--docs` to start a local documentation server at http://localhost:{docs_port}")
    else:
        click.echo(f"\n{error('Failed to start one or more servers')}", err=True)
        sys.exit(1)


@click.command()
@click.option("--bridge-only", is_flag=True, help="Stop only the bridge server")
@click.option("--api-only", is_flag=True, help="Stop only the API server")
def stop(bridge_only, api_only):
    """Stop Inspekt servers.

    By default, stops all servers (bridge, API, and MkDocs if running).
    Use --bridge-only or --api-only to stop specific servers.

    Examples:
        inspekt stop                # Stop all servers
        inspekt stop --bridge-only  # Stop only bridge server
        inspekt stop --api-only     # Stop only API server
    """
    click.echo("Stopping Inspekt servers…\n")

    # Determine what to stop
    stop_bridge = not api_only
    stop_api = not bridge_only

    bridge_stopped = False
    api_stopped = False
    docs_stopped = False

    # Stop MkDocs server first (if running)
    click.echo(f"  {progress('Stopping MkDocs server…')}")
    if _stop_mkdocs_server():
        click.echo(f"    {success('MkDocs server stopped')}")
        docs_stopped = True
    else:
        click.echo(f"    {info('MkDocs server was not running')}")

    # Stop API server (depends on bridge)
    if stop_api:
        click.echo(f"  {progress('Stopping API server…')}")
        if _stop_api_server():
            click.echo(f"    {success('API server stopped')}")
            api_stopped = True
        else:
            click.echo(f"    {info('API server was not running')}")

    # Stop bridge server
    if stop_bridge:
        click.echo(f"  {progress('Stopping bridge server…')}")
        if _stop_bridge_server():
            click.echo(f"    {success('Bridge server stopped')}")
            bridge_stopped = True
        else:
            click.echo(f"    {info('Bridge server was not running')}")

    # Summary
    if bridge_stopped or api_stopped or docs_stopped:
        click.echo(f"\n{success('Server(s) stopped successfully')}")
    else:
        click.echo(f"\n{info('No servers were running')}")

    # Note about foreground processes
    if stop_bridge or stop_api:
        click.echo("\nNote: If servers are running in foreground, use Ctrl+C to stop them.")


@click.command()
@click.option("--no-update-check", is_flag=True, help="Skip axe-core update check")
@click.option("--api-port", type=int, default=8000, help="API server port (default: 8000)")
@click.option("--bridge-port", type=int, default=8765, help="Bridge server port (default: 8765)")
@click.option("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
@click.option("--docs", is_flag=True, help="Start local MkDocs documentation server")
@click.option("--docs-port", type=int, default=8008, help="MkDocs server port (default: 8008)")
def restart(no_update_check, api_port, bridge_port, host, docs, docs_port):
    """Restart bridge and API servers.

    This command stops any running servers, optionally checks for updates,
    then starts servers fresh in daemon mode.
    Use --docs to also start a local MkDocs documentation server.

    Examples:
        inspekt restart                   # Restart servers
        inspekt restart --docs            # Include documentation server
        inspekt restart --no-update-check # Skip update check
        inspekt restart --api-port 3000   # Use custom API port
    """
    click.echo("Restarting Inspekt servers…\n")

    # Stop all servers
    click.echo(f"  {progress('Stopping MkDocs server…')}")
    docs_stopped = _stop_mkdocs_server()
    if docs_stopped:
        click.echo(f"    {success('MkDocs server stopped')}")
    else:
        click.echo(f"    {info('MkDocs server was not running')}")

    click.echo(f"  {progress('Stopping API server…')}")
    api_stopped = _stop_api_server()
    if api_stopped:
        click.echo(f"    {success('API server stopped')}")
    else:
        click.echo(f"    {info('API server was not running')}")

    click.echo(f"  {progress('Stopping bridge server…')}")
    bridge_stopped = _stop_bridge_server()
    if bridge_stopped:
        click.echo(f"    {success('Bridge server stopped')}")
    else:
        click.echo(f"    {info('Bridge server was not running')}")

    # Wait for processes to fully stop
    time.sleep(0.5)

    click.echo()

    # Check for updates unless disabled
    if not no_update_check:
        _check_axe_updates()

    bridge_success = _start_bridge_server(port=bridge_port)

    if not bridge_success:
        click.echo(f"\n{error('Failed to start bridge server')}", err=True)
        sys.exit(1)

    api_success = _start_api_server(host=host, port=api_port)

    if not api_success:
        click.echo(f"\n{error('Failed to start API server')}", err=True)
        sys.exit(1)

    # Start MkDocs server if --docs flag is passed
    if docs:
        if not _start_mkdocs_server(host=host, port=docs_port):
            click.echo(f"\n{error('Failed to start MkDocs server')}", err=True)
            sys.exit(1)

    # Display summary
    click.echo(f"\n{success('All servers restarted successfully')}\n")

    display_host = "localhost" if host == "127.0.0.1" else host
    click.echo(f"Bridge Server:")
    click.echo(f"  {info(f'HTTP API:      http://127.0.0.1:{bridge_port}')}")
    click.echo(f"  {info(f'WebSocket:     ws://127.0.0.1:{bridge_port + 1}')}")

    click.echo(f"\nAPI Server:")
    click.echo(f"  {info(f'Status:        http://{display_host}:{api_port}/status')}")
    click.echo(f"  {info(f'Health:        http://{display_host}:{api_port}/health')}")

    if docs:
        click.echo(f"\nDocs Server:")
        click.echo(f"  {info(f'MkDocs:        http://{display_host}:{docs_port}')}")
        click.echo(f"  {info(f'Swagger UI:    http://{display_host}:{api_port}/docs')}")
        click.echo(f"  {info(f'ReDoc:         http://{display_host}:{api_port}/redoc')}")

    click.echo(f"\nWeb-based status: http://localhost:{api_port}/status")

    # Show tip about --docs if not used
    if not docs:
        click.echo()
        from inspekt.app.cli.table import print_hint
        print_hint(f"Run with `--docs` to start a local documentation server at http://localhost:{docs_port}")


@click.group(invoke_without_command=True)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def status(ctx, output_json):
    """Check status of all Inspekt servers.

    Shows comprehensive status information for both bridge and API servers,
    including connected browsers, request statistics, and uptime.

    Examples:
        inspekt status        # Human-readable status
        inspekt status --json # JSON output
        inspekt status web    # Open web dashboard
    """
    # If a subcommand is invoked, don't run the default behavior
    if ctx.invoked_subcommand is not None:
        return

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
            click.echo(f"\n{success('Running (status unavailable)')}")
        else:
            click.echo(f"\n{error('Not Running')}")
            click.echo("\nStart with: inspekt start")

        # API Server Section
        click.echo("\n" + "=" * 60)
        click.echo("API SERVER")
        click.echo("=" * 60)

        if api_running:
            click.echo(f"\n{success('Running')}")
            click.echo(f"  Port:              8000")
            click.echo(f"  URL:               http://localhost:8000")
            click.echo(f"  Swagger UI:        http://localhost:8000/docs")
            click.echo(f"  ReDoc:             http://localhost:8000/redoc")
            click.echo(f"  Health Check:      http://localhost:8000/health")
        else:
            click.echo(f"\n{error('Not Running')}")
            click.echo("\nStart with: inspekt start")

        click.echo("\n" + "=" * 60)

        if api_running:
            click.echo(f"\nWeb-based status: http://localhost:8000/status")

    # Exit with error if either server is not running
    if not (bridge_running and api_running):
        sys.exit(1)


@status.command("web")
@click.option("--port", type=int, default=8000, help="API server port (default: 8000)")
def status_web(port):
    """Open the web-based dashboard in your browser.

    Opens the Inspekt status dashboard in your default web browser.
    The API server must be running.

    Examples:
        inspekt status web           # Open dashboard
        inspekt status web --port 3000  # Custom port
    """
    import webbrowser

    url = f"http://localhost:{port}/status"

    # Check if API server is running
    if not _is_port_open("127.0.0.1", port):
        click.echo(f"Error: API server is not running on port {port}", err=True)
        from inspekt.app.cli.table import _style_with_inline_code
        click.echo(_style_with_inline_code("\nStart it with: `inspekt start`", base_fg="red"), err=True)
        sys.exit(1)

    click.echo(f"Opening {url} in your browser...")
    webbrowser.open(url)


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

                click.echo(f"  {info(f'{req_id}... ({age_str}) - {req_type}')}")
        elif pending == 0:
            click.echo(f"\n{success('No pending requests')}")

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
            click.echo(success(f"Cleared {cleared} pending request(s)"))
            if remaining > 0:
                click.echo(f"  {remaining} request(s) remaining")
        else:
            click.echo(f"Error: {result.get('error', 'Unknown error')}", err=True)
            sys.exit(1)

    except http_requests.RequestException as e:
        click.echo(f"Error: Failed to clear queue: {e}", err=True)
        sys.exit(1)
