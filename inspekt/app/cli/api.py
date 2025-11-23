"""API server management commands."""

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


@click.group()
def api():
    """Manage the HTTP API server."""
    pass


@api.command()
@click.option("-p", "--port", type=int, default=8000, help="Port to run on (default: 8000)")
@click.option("-d", "--daemon", is_flag=True, help="Run in background")
@click.option("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
def start(port, daemon, host):
    """Start the HTTP API server (and bridge server if needed).

    This command starts both the bridge server (if not running) and the HTTP API server.
    The API server provides REST endpoints for all Inspekt commands.

    Examples:
        inspekt api start                    # Start on default port 8000
        inspekt api start -p 3000            # Start on custom port
        inspekt api start -d                 # Run in background
        inspekt api start --host 0.0.0.0     # Listen on all interfaces
    """
    # Check if bridge server is running, start it if not
    bridge_client = BridgeClient()

    if not bridge_client.is_alive():
        click.echo("Bridge server not running, starting it first...")
        # Start bridge server in background
        subprocess.Popen(
            [sys.executable, "-m", "inspekt.bridge_ws"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # Wait for it to start
        time.sleep(1)
        if bridge_client.is_alive():
            click.echo("✓ Bridge server started on ports 8765 (HTTP) and 8766 (WebSocket)")
        else:
            click.echo("✗ Failed to start bridge server", err=True)
            sys.exit(1)
    else:
        click.echo("✓ Bridge server is already running")

    # Check if API server is already running
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    api_running = sock.connect_ex((host, port)) == 0
    sock.close()

    if api_running:
        click.echo(f"API server is already running on {host}:{port}")
        click.echo(f"Documentation: http://{host if host != '0.0.0.0' else 'localhost'}:{port}/docs")
        return

    # Start API server
    if daemon:
        # Run in background
        click.echo(f"Starting API server in background on {host}:{port}...")
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
        # Wait a bit to check if it started
        time.sleep(1.5)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if sock.connect_ex((host, port)) == 0:
            sock.close()
            display_host = "localhost" if host == "127.0.0.1" else host
            click.echo(f"✓ API server started successfully")
            click.echo(f"\nAccess Inspekt API at:")
            click.echo(f"  • Status:        http://{display_host}:{port}/status")
            click.echo(f"  • Swagger UI:    http://{display_host}:{port}/docs")
            click.echo(f"  • ReDoc:         http://{display_host}:{port}/redoc")
            click.echo(f"  • Health check:  http://{display_host}:{port}/health")
            click.echo(f"  • API root:      http://{display_host}:{port}/")
        else:
            sock.close()
            click.echo("✗ Failed to start API server", err=True)
            click.echo("\nTroubleshooting:")
            click.echo("  • Make sure uvicorn is installed: pip install uvicorn")
            click.echo("  • Check if port is already in use")
            sys.exit(1)
    else:
        # Run in foreground
        click.echo(f"Starting API server on {host}:{port}...")
        display_host = "localhost" if host == "127.0.0.1" else host
        click.echo(f"\nAPI server running at:")
        click.echo(f"  • Status:        http://{display_host}:{port}/status")
        click.echo(f"  • Swagger UI:    http://{display_host}:{port}/docs")
        click.echo(f"  • ReDoc:         http://{display_host}:{port}/redoc")
        click.echo(f"  • Health check:  http://{display_host}:{port}/health")
        click.echo(f"  • API root:      http://{display_host}:{port}/")
        click.echo("\nPress Ctrl+C to stop the server\n")

        try:
            subprocess.run([
                sys.executable, "-m", "uvicorn",
                "inspekt.app.api.server:app",
                "--host", host,
                "--port", str(port)
            ])
        except KeyboardInterrupt:
            click.echo("\nAPI server stopped")


@api.command()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def status(output_json):
    """Check API and bridge server status."""
    import json
    import socket

    # Check bridge server
    bridge_client = BridgeClient()
    bridge_running = bridge_client.is_alive()

    # Check API server (default port 8000)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    api_running = sock.connect_ex(("127.0.0.1", 8000)) == 0
    sock.close()

    if output_json:
        output_data = {
            "bridge_server": {
                "running": bridge_running,
                "ports": {"http": 8765, "websocket": 8766}
            },
            "api_server": {
                "running": api_running,
                "port": 8000,
                "url": "http://localhost:8000" if api_running else None
            }
        }
        click.echo(json.dumps(output_data, indent=2))
    else:
        click.echo("Inspekt Status:\n")

        # Bridge server status
        if bridge_running:
            click.echo("✓ Bridge server is running")
            click.echo("  Ports: 8765 (HTTP), 8766 (WebSocket)")
        else:
            click.echo("✗ Bridge server is not running")
            click.echo("  Start with: inspekt server start")

        click.echo()

        # API server status
        if api_running:
            click.echo("✓ API server is running")
            click.echo("  URL: http://localhost:8000")
            click.echo("  Docs: http://localhost:8000/docs")
        else:
            click.echo("✗ API server is not running")
            click.echo("  Start with: inspekt api start")

    # Exit with error if either is not running
    if not (bridge_running and api_running):
        sys.exit(1)


@api.command()
@click.option("--bridge", is_flag=True, help="Also stop the bridge server")
def stop(bridge):
    """Stop the API server (and optionally the bridge server).

    By default, only stops the API server. Use --bridge to also stop the bridge server.

    Examples:
        inspekt api stop              # Stop only API server
        inspekt api stop --bridge     # Stop both API and bridge servers
    """
    click.echo("Stopping Inspekt servers...\n")

    api_stopped = False
    bridge_stopped = False

    # Stop API server
    click.echo("• Stopping API server...")
    result = subprocess.run(
        ["pkill", "-f", "uvicorn inspekt.app.api.server"],
        capture_output=True
    )
    if result.returncode == 0:
        click.echo("  ✓ API server stopped")
        api_stopped = True
    else:
        click.echo("  • API server was not running")

    # Stop bridge server if requested
    if bridge:
        click.echo("• Stopping bridge server...")
        result = subprocess.run(
            ["pkill", "-f", "inspekt.bridge_ws"],
            capture_output=True
        )
        if result.returncode == 0:
            click.echo("  ✓ Bridge server stopped")
            bridge_stopped = True
        else:
            click.echo("  • Bridge server was not running")

    # Summary
    if api_stopped or bridge_stopped:
        click.echo("\n✓ Server(s) stopped successfully")
    else:
        click.echo("\n• No servers were running")

    # Show foreground info
    click.echo("\nNote: If servers are running in foreground, use Ctrl+C to stop them.")


@api.command()
@click.option("-p", "--port", type=int, default=8000, help="Port to run on (default: 8000)")
@click.option("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
def restart(port, host):
    """Restart both bridge and API servers.

    This command stops any running bridge and API servers, then starts them fresh.
    Useful for applying configuration changes or clearing server state.

    Examples:
        inspekt api restart                  # Restart on default port 8000
        inspekt api restart -p 3000          # Restart API on custom port
        inspekt api restart --host 0.0.0.0   # Restart listening on all interfaces
    """
    import signal
    import os

    click.echo("Restarting Inspekt servers…\n")

    # Stop API server
    click.echo(" - Stopping API server…")
    result = subprocess.run(
        ["pkill", "-f", "uvicorn inspekt.app.api.server"],
        capture_output=True
    )
    if result.returncode == 0:
        click.echo("  ✓ API server stopped")
    else:
        click.echo("  • API server was not running")

    # Stop bridge server
    click.echo(" - Stopping bridge server…")
    result = subprocess.run(
        ["pkill", "-f", "inspekt.bridge_ws"],
        capture_output=True
    )
    if result.returncode == 0:
        click.echo("  ✓ Bridge server stopped")
    else:
        click.echo("  • Bridge server was not running")

    # Wait a moment for processes to fully stop
    time.sleep(0.5)

    # Check for axe-core updates before restarting servers
    _check_axe_updates()

    click.echo(" - Starting bridge server…")
    # Start bridge server in background
    subprocess.Popen(
        [sys.executable, "-m", "inspekt.bridge_ws"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # Wait for bridge to start
    time.sleep(1)
    bridge_client = BridgeClient()
    if bridge_client.is_alive():
        click.echo("  ✓ Bridge server started on ports 8765 (HTTP) and 8766 (WebSocket)")
    else:
        click.echo("  ✗ Failed to start bridge server", err=True)
        sys.exit(1)

    click.echo(" - Starting API server…")
    # Start API server in background
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

    # Wait for API server to start
    time.sleep(1.5)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sock.connect_ex((host, port)) == 0:
        sock.close()
        display_host = "localhost" if host == "127.0.0.1" else host
        click.echo(f"  ✓ API server started on port {port}")
        click.echo(f"\nAll servers restarted successfully!")
        click.echo(f"\nAccess Inspekt API at:")
        click.echo(f"  • Status:        http://{display_host}:{port}/status")
        click.echo(f"  • Swagger UI:    http://{display_host}:{port}/docs")
        click.echo(f"  • ReDoc:         http://{display_host}:{port}/redoc")
        click.echo(f"  • Health check:  http://{display_host}:{port}/health")
        click.echo(f"  • API root:      http://{display_host}:{port}/")
    else:
        sock.close()
        click.echo("  ✗ Failed to start API server", err=True)
        click.echo("\nTroubleshooting:")
        click.echo("  • Make sure uvicorn is installed: pip install uvicorn")
        click.echo("  • Check if port is already in use")
        sys.exit(1)
