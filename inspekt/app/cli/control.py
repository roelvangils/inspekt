"""Unified server management commands for Inspekt.

This module provides unified start/stop/restart/status commands that manage
both the bridge server and API server together.
"""

import asyncio
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
from inspekt.services.ibm_updater import get_ibm_updater
from inspekt.services.engines import get_all_engines


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


def _check_engine_updates():
    """Check for updates for all accessibility engines using the unified engine system."""
    engines = get_all_engines()

    click.echo(" Checking for engine updates…", err=True)

    for engine in engines:
        # Format engine display: "Axe-core (Deque Systems)"
        provider_suffix = f" ({engine.provider})" if engine.provider else ""
        engine_display = f"{engine.engine_name}{provider_suffix}"

        try:
            update_available, current, latest, release_date = engine.is_update_available()

            if not latest:
                # Network error - show concise error status
                click.echo(f"  {engine_display}: {click.style('check failed', fg='yellow')}", err=True)
                continue

            if not current:
                # Not installed - install it
                click.echo(f"  {engine_display}: {click.style('not installed', fg='yellow')} → installing {latest}", err=True)

                def show_progress(msg):
                    click.echo(f"    {msg}", err=True)

                install_success, message = engine.update_to_latest(progress_callback=show_progress)

                if install_success:
                    click.echo(f"    {click.style('installed', fg='green')}", err=True)
                else:
                    click.echo(f"    {click.style(f'failed: {message}', fg='red')}", err=True)
                continue

            if not update_available:
                click.echo(f"  {engine_display}: {click.style('up to date', fg='green')} ({current})", err=True)
                continue

            # Update available - show status and prompt user
            click.echo(f"  {engine_display}: {click.style('update available', fg='cyan')} ({current} → {latest})", err=True)

            if click.confirm(f"    Update to {engine.engine_name} {latest}?", default=True):
                def show_progress(msg):
                    click.echo(f"    {msg}", err=True)

                update_success, message = engine.update_to_latest(progress_callback=show_progress)

                if update_success:
                    click.echo(f"    {click.style('updated', fg='green')}", err=True)
                else:
                    click.echo(f"    {click.style(f'failed: {message}', fg='red')}", err=True)
            else:
                click.echo(f"    {click.style('skipped', fg='yellow')}", err=True)

        except Exception:
            # Show concise error status
            click.echo(f"  {engine_display}: {click.style('check failed', fg='yellow')}", err=True)

    click.echo("", err=True)  # Blank line after engine checks


def _check_readability_updates():
    """Check for Mozilla Readability updates and show status.

    Unlike accessibility engines, Readability is not auto-updated.
    This just shows the current version and whether an update is available.
    """
    from inspekt.services.readability_updater import get_readability_updater

    updater = get_readability_updater()

    try:
        update_available, current, latest, release_date = updater.is_update_available()

        if not latest:
            # Network error - silently skip
            return

        # Format release date for display
        date_str = _format_release_date(release_date)
        date_suffix = f" • {date_str}" if date_str else ""

        if not current:
            # Not installed - this shouldn't happen normally but handle it
            click.echo(f"  @mozilla/readability: {click.style('not installed', fg='yellow')}", err=True)
            click.echo(f"    Run `inspekt update readability` to install", err=True)
            return

        if not update_available:
            # Up to date - show briefly
            click.echo(f"  @mozilla/readability: {click.style('up to date', fg='green')} ({current})", err=True)
            return

        # Update available - show without auto-updating
        click.echo(f"  @mozilla/readability: {click.style('update available', fg='cyan')} ({current} → {latest}{date_suffix})", err=True)
        click.echo(f"    Run `inspekt update readability` to update", err=True)

    except Exception:
        # Silently skip on errors
        pass


def _check_axe_updates():
    """Check for axe-core updates and prompt user to update.

    DEPRECATED: Use _check_engine_updates() instead for unified engine management.
    This function is kept for backwards compatibility.
    """
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


def _check_ibm_updates():
    """Check for IBM Equal Access updates and prompt user to update.

    DEPRECATED: Use _check_engine_updates() instead for unified engine management.
    This function is kept for backwards compatibility.
    """
    updater = get_ibm_updater()

    try:
        # Check for updates (quick, non-blocking)
        click.echo(f"  {progress('Checking for IBM Equal Access updates…')}", err=True)
        update_available, current, latest, release_date = updater.is_update_available()

        if not latest:
            # Network error or timeout - silently continue
            return

        # Format release date for display
        date_str = _format_release_date(release_date)
        date_suffix = f" • {date_str}" if date_str else ""

        if not current:
            # Not installed yet - install it
            click.echo(f"  {info(f'IBM Equal Access {latest} will be installed{date_suffix}')}", err=True)
            click.echo("", err=True)

            def show_progress(msg):
                click.echo(f"{msg}", err=True)

            install_success, message = updater.update_to_latest(progress_callback=show_progress)

            if install_success:
                from inspekt.app.cli.icons import success as success_msg
                click.echo(f"\n{success_msg(message)}\n", err=True)
            else:
                click.echo(f"\n{error(f'Installation failed: {message}')}", err=True)
            return

        if not update_available:
            # Already on latest version
            click.echo(f"  {success(f'IBM Equal Access is up-to-date ({current}{date_suffix})')}", err=True)
            return

        # Update available - prompt user
        click.echo(f"  {success(f'IBM Equal Access {latest} is available{date_suffix} (current: {current})')}", err=True)
        click.echo("", err=True)

        # Ask user if they want to update
        if click.confirm(f"Update to IBM Equal Access {latest}?", default=True):
            click.echo("", err=True)

            def show_progress(msg):
                click.echo(f"{msg}", err=True)

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


async def _start_foreground(
    bridge: bool,
    api: bool,
    docs: bool,
    bridge_port: int,
    api_port: int,
    docs_port: int,
    host: str,
) -> None:
    """Run servers in foreground with unified, color-coded output.

    Uses ProcessManager to run all requested servers as async subprocesses,
    multiplexing their output with colored prefixes.
    """
    from inspekt.services.process_manager import ProcessManager

    manager = ProcessManager()
    manager.setup_signal_handlers()

    click.echo("Running in foreground mode (Ctrl+C to stop)\n")

    # Start requested servers
    startup_tasks = []

    if bridge:
        click.echo(f"  {progress(f'Starting bridge on ports {bridge_port}/{bridge_port + 1}…')}")
        managed = await manager.start_bridge(port=bridge_port)
        startup_tasks.append(managed)

    if api:
        click.echo(f"  {progress(f'Starting API on {host}:{api_port}…')}")
        managed = await manager.start_api(host=host, port=api_port)
        startup_tasks.append(managed)

    if docs:
        project_root = _get_project_root()
        click.echo(f"  {progress(f'Starting docs on {host}:{docs_port}…')}")
        managed = await manager.start_docs(
            host=host, port=docs_port, project_root=project_root
        )
        startup_tasks.append(managed)

    click.echo()

    # Wait for all servers to become healthy
    all_healthy = True
    for managed in startup_tasks:
        healthy = await manager.wait_for_health(managed)
        prefix = click.style(managed.server_type.prefix, fg=managed.server_type.color, bold=True)
        if healthy:
            click.echo(f"  {prefix} {success('ready')}")
        else:
            click.echo(f"  {prefix} {error(managed.error_message or 'failed to start')}")
            all_healthy = False

    if not all_healthy:
        click.echo(f"\n{error('Some servers failed to start')}")
        # Still run if at least one server is healthy (per user requirement)
        healthy_count = sum(1 for m in startup_tasks if m.healthy)
        if healthy_count == 0:
            await manager.shutdown_all()
            sys.exit(1)
        click.echo(f"Continuing with {healthy_count} healthy server(s)...\n")
    else:
        click.echo(f"\n{success('All servers ready')}")

    click.echo("─" * 60)
    click.echo()

    # Start process monitor and wait for shutdown
    monitor_task = asyncio.create_task(manager.monitor_processes())

    # Wait for shutdown event
    await manager.shutdown_event.wait()

    # Clean up
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass

    await manager.shutdown_all()


@click.command()
@click.option("--bridge-only", is_flag=True, help="Start only the bridge server")
@click.option("--api-only", is_flag=True, help="Start only the API server")
@click.option("--foreground", is_flag=True, help="Run in foreground (for debugging)")
@click.option("--api-port", type=int, default=8000, help="API server port (default: 8000)")
@click.option("--bridge-port", type=int, default=8765, help="Bridge server port (default: 8765)")
@click.option("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
@click.option("--docs", is_flag=True, help="Start local MkDocs documentation server")
@click.option("--docs-port", type=int, default=8008, help="MkDocs server port (default: 8008)")
def start(bridge_only, api_only, foreground, api_port, bridge_port, host, docs, docs_port):
    """Start Inspekt servers (bridge + API).

    By default, starts both bridge and API servers in background (daemon mode).
    Automatically checks for accessibility engine updates before starting.
    Use --bridge-only or --api-only to start specific servers.
    Use --foreground to run all servers with unified, color-coded output.
    Use --docs to also start a local MkDocs documentation server.

    Examples:
        inspekt start                      # Start both servers in background
        inspekt start --docs               # Include local documentation server
        inspekt start --bridge-only        # Start only bridge server
        inspekt start --foreground         # Run all servers with unified output
        inspekt start --foreground --docs  # Include docs in foreground mode
        inspekt start --api-port 3000      # Use custom API port
    """
    # Check for engine and library updates automatically
    _check_engine_updates()
    _check_readability_updates()

    click.echo("Starting Inspekt servers...\n")

    # Determine what to start
    start_bridge = not api_only
    start_api = not bridge_only

    # Foreground mode: run all requested servers with unified output
    if foreground:
        import asyncio

        asyncio.run(
            _start_foreground(
                bridge=start_bridge,
                api=start_api,
                docs=docs,
                bridge_port=bridge_port,
                api_port=api_port,
                docs_port=docs_port,
                host=host,
            )
        )
        return

    # Daemon mode: start servers in background
    start_success = True

    # Start bridge server
    if start_bridge:
        if not _start_bridge_server(port=bridge_port):
            start_success = False

    # Start API server
    if start_api:
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

        # Show dev mode reminder about syncing extensions
        from inspekt.config import is_dev_mode
        if is_dev_mode():
            from inspekt.app.cli.table import print_hint
            print_hint("Dev mode: If you changed shared extension code, run `make sync-extensions`")
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
@click.option("--foreground", is_flag=True, help="Run in foreground with unified output")
@click.option("--api-port", type=int, default=8000, help="API server port (default: 8000)")
@click.option("--bridge-port", type=int, default=8765, help="Bridge server port (default: 8765)")
@click.option("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
@click.option("--docs", is_flag=True, help="Start local MkDocs documentation server")
@click.option("--docs-port", type=int, default=8008, help="MkDocs server port (default: 8008)")
def restart(foreground, api_port, bridge_port, host, docs, docs_port):
    """Restart bridge and API servers.

    This command stops any running servers, checks for accessibility engine
    updates, then starts servers fresh.
    Use --foreground to run with unified, color-coded output.
    Use --docs to also start a local MkDocs documentation server.

    Examples:
        inspekt restart                   # Restart servers in background
        inspekt restart --foreground      # Restart with unified output
        inspekt restart --docs            # Include documentation server
        inspekt restart --foreground --docs  # All servers with unified output
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

    # Check for engine and library updates automatically
    _check_engine_updates()
    _check_readability_updates()

    # Foreground mode: run all servers with unified output
    if foreground:
        click.echo("Starting Inspekt servers...\n")
        asyncio.run(
            _start_foreground(
                bridge=True,
                api=True,
                docs=docs,
                bridge_port=bridge_port,
                api_port=api_port,
                docs_port=docs_port,
                host=host,
            )
        )
        return

    # Daemon mode: start servers in background
    click.echo("Starting Inspekt servers...\n")

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
        # Human-readable output using Table formatting
        from inspekt.app.cli.table import Table, format_status_icon
        from inspekt.app.cli.icons import get_icon

        click.echo()  # Initial spacing

        # ═══════════════════════════════════════════════════════════════════
        # BRIDGE SERVER TABLE
        # ═══════════════════════════════════════════════════════════════════
        bridge_icon = get_icon("Bridge Server") or ""
        bridge_data = []

        if bridge_running and bridge_status:
            status_text = click.style("Running", fg="green")
            bridge_data.append(["Status", f"{format_status_icon('pass')} {status_text}"])
            bridge_data.append(["Version", bridge_status.get('server_version', 'Unknown')])
            uptime = bridge_status.get('uptime_seconds', 0)
            bridge_data.append(["Uptime", format_duration(uptime)])
            host = bridge_status.get('host', '127.0.0.1')
            port = bridge_status.get('port', 8765)
            ws_port = bridge_status.get('websocket_port', 8766)
            bridge_data.append(["HTTP API", f"http://{host}:{port}"])
            bridge_data.append(["WebSocket", f"ws://{host}:{ws_port}"])
        elif bridge_running:
            status_text = click.style("Running (status unavailable)", fg="yellow")
            bridge_data.append(["Status", f"{format_status_icon('warning')} {status_text}"])
        else:
            status_text = click.style("Not Running", fg="red")
            bridge_data.append(["Status", f"{format_status_icon('fail')} {status_text}"])
            bridge_data.append(["", click.style("Start with: inspekt start", fg="bright_black")])

        bridge_table = Table(["Property", "Value"], title="Bridge Server", icon=bridge_icon)
        bridge_table.set_data(bridge_data)
        bridge_table.print_header(skip_column_headers=True)
        for row in bridge_data:
            bridge_table.print_row(row)
        bridge_table.print_footer()

        # ═══════════════════════════════════════════════════════════════════
        # CONNECTED INSTANCES TABLE (only if bridge is running)
        # ═══════════════════════════════════════════════════════════════════
        if bridge_running and bridge_status:
            browser_count = bridge_status.get('connected_browsers', 0)
            browsers = bridge_status.get('browsers', [])

            click.echo()  # Spacing between tables
            browser_icon = get_icon("Connected Browsers") or ""

            if browser_count == 0:
                browser_data = [["", click.style("No browsers connected", fg="bright_black")]]
            else:
                browser_data = []
                for browser in browsers:
                    # Instance ID and alias
                    instance_id = browser.get('instance_id', '?')
                    alias = browser.get('alias')

                    # Browser name with version
                    browser_name = browser['browser_name']
                    browser_version = browser.get('browser_version', '')
                    if browser_version:
                        browser_display = f"{browser_name} {browser_version}"
                    else:
                        browser_display = browser_name

                    # Format instance identifier: [ID] or [ID:alias]
                    if alias:
                        instance_label = click.style(f"[{instance_id}:{alias}]", fg="cyan", bold=True)
                    else:
                        instance_label = click.style(f"[{instance_id}]", fg="cyan", bold=True)

                    # Mark active instance
                    if browser['is_most_recent']:
                        browser_display = click.style(browser_display, bold=True)
                        active_marker = click.style(" ● ACTIVE", fg="green")
                    else:
                        active_marker = ""

                    # Build info parts
                    info_parts = []
                    url = browser.get('url', '')
                    if url:
                        display_url = url if len(url) <= 45 else url[:42] + '...'
                        info_parts.append(display_url)
                    title = browser.get('title', '')
                    if title:
                        display_title = title if len(title) <= 45 else title[:42] + '...'
                        info_parts.append(click.style(display_title, fg="bright_black"))

                    # Extension version and connection duration
                    meta_parts = []
                    if browser.get('extension_version'):
                        meta_parts.append(f"v{browser['extension_version']}")
                    duration = browser.get('connected_duration', 0)
                    meta_parts.append(format_duration(duration))
                    meta_line = click.style(" • ".join(meta_parts), fg="bright_black")

                    # First row: instance ID + browser name + URL
                    browser_data.append([f"{instance_label} {browser_display}{active_marker}", info_parts[0] if info_parts else ""])
                    # Second row: title (if exists)
                    if len(info_parts) > 1:
                        browser_data.append(["", info_parts[1]])
                    # Third row: meta info
                    browser_data.append(["", meta_line])

            browser_table = Table(["Instance", "Details"], title="Connected Instances", icon=browser_icon)
            browser_table.set_data(browser_data)
            browser_table.print_header(skip_column_headers=True)
            for row in browser_data:
                browser_table.print_row(row)
            browser_table.print_footer()

            # ═══════════════════════════════════════════════════════════════════
            # REQUEST STATISTICS TABLE
            # ═══════════════════════════════════════════════════════════════════
            click.echo()  # Spacing
            stats_icon = get_icon("Request Statistics") or ""

            total = bridge_status.get('total_processed', 0)
            succeeded = bridge_status.get('total_succeeded', 0)
            failed = bridge_status.get('total_failed', 0)
            pending = bridge_status.get('pending', 0)
            success_rate = f"{(succeeded / total) * 100:.1f}%" if total > 0 else "-"
            last_activity = bridge_status.get('last_activity')
            last_activity_str = format_time_ago(last_activity) if last_activity else "-"

            stats_data = [
                ["Pending", str(pending)],
                ["Processed", f"{total} (since startup)"],
                ["Succeeded", click.style(str(succeeded), fg="green") if succeeded > 0 else str(succeeded)],
                ["Failed", click.style(str(failed), fg="red") if failed > 0 else str(failed)],
                ["Success Rate", success_rate],
                ["Last Activity", last_activity_str],
            ]

            stats_table = Table(["Metric", "Value"], title="Request Statistics", icon=stats_icon)
            stats_table.set_data(stats_data)
            stats_table.print_header(skip_column_headers=True)
            for row in stats_data:
                stats_table.print_row(row)
            stats_table.print_footer()

        # ═══════════════════════════════════════════════════════════════════
        # API SERVER TABLE
        # ═══════════════════════════════════════════════════════════════════
        click.echo()  # Spacing
        api_icon = get_icon("API Server") or ""
        api_data = []

        if api_running:
            status_text = click.style("Running", fg="green")
            api_data.append(["Status", f"{format_status_icon('pass')} {status_text}"])
            api_data.append(["Port", "8000"])
            api_data.append(["URL", "http://localhost:8000"])
            api_data.append(["Swagger UI", "http://localhost:8000/docs"])
            api_data.append(["ReDoc", "http://localhost:8000/redoc"])
            api_data.append(["Health Check", "http://localhost:8000/health"])
        else:
            status_text = click.style("Not Running", fg="red")
            api_data.append(["Status", f"{format_status_icon('fail')} {status_text}"])
            api_data.append(["", click.style("Start with: inspekt start", fg="bright_black")])

        api_table = Table(["Property", "Value"], title="API Server", icon=api_icon)
        api_table.set_data(api_data)
        api_table.print_header(skip_column_headers=True)
        for row in api_data:
            api_table.print_row(row)
        api_table.print_footer()

        # Footer hint
        if api_running:
            click.echo()
            from inspekt.app.cli.table import print_hint
            print_hint("Web-based status: http://localhost:8000/status")

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
