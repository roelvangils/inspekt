"""
CLI command: inspekt tunnel

Exposes a local port to the Inspekt Browser VM via a bore tunnel,
so the VM's browser can access the user's local development server.
"""

from __future__ import annotations

import signal
import socket
import subprocess
import sys

import click
import requests

from inspekt.app.cli.table import print_error, print_hint, print_success, print_warning


# bore server defaults
BORE_SERVER_PORT = 7835
CONTROL_SERVER_PORT = 8888


def _check_local_port(port: int) -> bool:
    """Check if something is listening on the given local port."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except (ConnectionRefusedError, OSError):
        return False


def _get_tunnel_info(host: str) -> dict | None:
    """
    Fetch tunnel info (secret, port) from the VM's control server.

    Returns dict with 'secret' and 'port' keys, or None on failure.
    """
    try:
        resp = requests.get(
            f"http://{host}:{CONTROL_SERVER_PORT}/api/tunnel-info",
            timeout=5,
        )
        if resp.ok:
            return resp.json()
    except (requests.RequestException, ValueError):
        pass
    return None


def _ensure_bore(verbose: bool = False) -> str:
    """
    Ensure bore client is installed, downloading if necessary.

    Returns the path to the bore binary as a string.
    """
    from inspekt.services.bore_manager import BoreManager

    manager = BoreManager()

    if manager.is_installed():
        version = manager.get_installed_version() or "unknown"
        if verbose:
            click.echo(f"  bore client v{version} found")
        return str(manager.binary_path)

    click.echo("  Downloading bore tunnel client…")
    try:
        path = manager.install()
        version = manager.get_installed_version() or "unknown"
        print_success(f"bore v{version} installed")
        return str(path)
    except Exception as e:
        print_error(f"Failed to download bore: {e}")
        print_hint("Install bore manually: https://github.com/ekzhang/bore#installation")
        sys.exit(1)


@click.command()
@click.argument("port", type=int)
@click.option(
    "--host",
    default=None,
    metavar="HOST",
    help="VM host address (default: localhost for local VM).",
)
@click.option(
    "--secret",
    default=None,
    metavar="SECRET",
    help="Tunnel secret (auto-detected from VM if not specified).",
)
@click.option(
    "--remote-port",
    default=None,
    type=int,
    metavar="PORT",
    help="Port on VM side (default: same as local port).",
)
@click.option(
    "--transport",
    type=click.Choice(["bore"]),
    default="bore",
    help="Tunnel transport to use.",
    hidden=True,
)
@click.pass_context
def tunnel(ctx, port: int, host: str | None, secret: str | None, remote_port: int | None, transport: str):
    """Expose a local port to the Inspekt Browser VM.

    Makes your local development server accessible from within the VM's
    browser. Run this on your local machine while the VM is running.

    \b
    Examples:
        inspekt tunnel 3000                         # Expose localhost:3000
        inspekt tunnel 8080 --host vm.example.com   # Cloud VM
        inspekt tunnel 3000 --remote-port 8000      # Different port on VM side
    """
    verbose = ctx.obj.get("verbose", False) if ctx.obj else False

    # Default remote port to same as local
    if remote_port is None:
        remote_port = port

    # Default host to localhost (local VM)
    if host is None:
        host = "localhost"

    # Step 1: Check if local port is listening
    if not _check_local_port(port):
        print_warning(f"Nothing seems to be listening on localhost:{port}")
        print_hint(f"Start your development server first, then run `inspekt tunnel {port}`")
        # Continue anyway — the user might start the server while the tunnel is running

    # Step 2: Ensure bore client is available
    bore_binary = _ensure_bore(verbose=verbose)

    # Step 3: Get tunnel secret from VM
    if secret is None:
        info = _get_tunnel_info(host)
        if info and info.get("secret"):
            secret = info["secret"]
            bore_port = info.get("port", BORE_SERVER_PORT)
        else:
            if host == "localhost":
                print_error("Could not connect to VM control server at localhost:8888")
                print_hint("Make sure the VM is running: `inspekt vm start`")
            else:
                print_error(f"Could not fetch tunnel info from {host}:{CONTROL_SERVER_PORT}")
                print_hint("Use --secret to provide the tunnel secret manually")
            sys.exit(1)
    else:
        bore_port = BORE_SERVER_PORT

    # Step 4: Build bore command
    # bore's --to expects just the hostname; it defaults to port 7835
    cmd = [
        bore_binary,
        "local",
        str(port),
        "--to", host,
        "--port", str(remote_port),
        "--secret", secret,
    ]

    if verbose:
        click.echo(f"  Running: {' '.join(cmd)}")

    # Step 5: Print tunnel info box
    click.echo()
    local_url = f"http://localhost:{port}"
    vm_url = f"http://localhost:{remote_port}"
    box_width = 48

    border_color = "bright_black"
    click.secho(f"  ╭─ Tunnel Active {'─' * (box_width - 19)}╮", fg=border_color)

    inner_width = box_width - 2  # space between │ and │
    for label, color, value in [
        ("Local", "cyan", local_url),
        ("VM", "green", vm_url),
        ("Transport", "bright_black", transport),
    ]:
        content = f" {label:<11} {value}"
        pad = inner_width - len(content)
        click.echo("  │", nl=False)
        click.secho(f" {label:<11}", fg=color, nl=False)
        click.echo(f" {value}{' ' * max(pad, 1)}", nl=False)
        click.secho("│", fg=border_color)

    click.secho(f"  ╰{'─' * (box_width - 2)}╯", fg=border_color)
    click.echo()
    print_hint("Press Ctrl+C to stop the tunnel")
    click.echo()

    # Step 6: Run bore client, forwarding output
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Forward bore output (connection messages, errors)
        for line in process.stdout:
            line = line.rstrip()
            if line:
                click.secho(f"  [bore] {line}", fg="bright_black")

        process.wait()
        if process.returncode not in (0, -2, -signal.SIGINT):
            print_error(f"bore exited with code {process.returncode}")
            sys.exit(1)

    except KeyboardInterrupt:
        # Graceful shutdown
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
        click.echo()
        click.secho("  Tunnel closed.", fg="bright_black")

    except FileNotFoundError:
        print_error(f"bore binary not found at {bore_binary}")
        print_hint("Try removing it and re-running to trigger a fresh download")
        sys.exit(1)
