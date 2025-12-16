"""Virtual Machine commands for Inspekt.

This module provides commands to manage the Inspekt Browser VM,
a Docker-based virtual machine with Chromium and the Inspekt extension pre-installed.
"""

import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import click


# Docker image and container names
IMAGE_NAME = "inspekt-browser-vm"
CONTAINER_NAME = "inspekt-browser-vm"

# Ports used by the VM (all must be free before starting)
NOVNC_PORT = 6080
CONTROL_PORT = 8888
VM_PORTS = [6080, 6081, 8767, 8768, 8889, 9222]  # All ports the VM uses

# Path to docker/browser-vm directory
def get_vm_dir() -> Path:
    """Get the path to the browser-vm directory."""
    # Try to find it relative to the package
    package_dir = Path(__file__).parent.parent.parent.parent
    vm_dir = package_dir / "docker" / "browser-vm"
    if vm_dir.exists():
        return vm_dir

    # Fallback: try current working directory
    cwd_vm_dir = Path.cwd() / "docker" / "browser-vm"
    if cwd_vm_dir.exists():
        return cwd_vm_dir

    return None


def _is_dev_environment() -> bool:
    """Check if running from the Inspekt source repository.

    Detects development environment by checking for pyproject.toml
    in the project root. When detected, dev mode will be auto-enabled
    to mount local source files into the VM container.
    """
    vm_dir = get_vm_dir()
    if vm_dir:
        project_root = vm_dir.parent.parent
        # Check for pyproject.toml (indicates source repo)
        return (project_root / "pyproject.toml").exists()
    return False


def _is_docker_running() -> bool:
    """Check if Docker daemon is running."""
    result = subprocess.run(
        ["docker", "info"],
        capture_output=True
    )
    return result.returncode == 0


def _is_container_running() -> bool:
    """Check if the VM container is running."""
    result = subprocess.run(
        ["docker", "ps", "-q", "-f", f"name={CONTAINER_NAME}"],
        capture_output=True,
        text=True
    )
    return bool(result.stdout.strip())


def _container_exists() -> bool:
    """Check if the VM container exists (running or stopped)."""
    result = subprocess.run(
        ["docker", "ps", "-aq", "-f", f"name={CONTAINER_NAME}"],
        capture_output=True,
        text=True
    )
    return bool(result.stdout.strip())


def _image_exists() -> bool:
    """Check if the VM image exists."""
    result = subprocess.run(
        ["docker", "images", "-q", IMAGE_NAME],
        capture_output=True,
        text=True
    )
    return bool(result.stdout.strip())


def _get_all_vm_containers() -> list[str]:
    """Get IDs of ALL containers from any inspekt-browser-vm image version.

    This finds containers even from old/rebuilt image versions that may still
    be running and occupying ports.
    """
    # Find by image name (includes old versions with different hashes)
    result = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"ancestor={IMAGE_NAME}"],
        capture_output=True,
        text=True
    )
    containers = set(result.stdout.strip().split()) if result.stdout.strip() else set()

    # Also find by container name pattern
    result = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"name={CONTAINER_NAME}"],
        capture_output=True,
        text=True
    )
    if result.stdout.strip():
        containers.update(result.stdout.strip().split())

    return list(containers)


def _check_port_in_use(port: int) -> tuple[bool, str | None]:
    """Check if a port is in use and by what.

    Returns:
        (in_use, description) - description is None if not in use
    """
    import socket

    # First check if port is open
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        result = sock.connect_ex(("127.0.0.1", port))
        if result != 0:
            return False, None
    finally:
        sock.close()

    # Port is in use - try to identify the process (platform-specific)
    try:
        result = subprocess.run(
            ["lsof", "-i", f":{port}", "-t"],
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            pids = result.stdout.strip().split()
            return True, f"PIDs: {', '.join(pids)}"
    except FileNotFoundError:
        pass  # lsof not available

    return True, "unknown process"


def _check_ports_available() -> list[tuple[int, str]]:
    """Check if all VM ports are available.

    Returns:
        List of (port, description) tuples for ports that are in use
    """
    conflicts = []
    for port in VM_PORTS:
        in_use, desc = _check_port_in_use(port)
        if in_use:
            conflicts.append((port, desc or "unknown"))
    return conflicts


def _stop_all_vm_containers(verbose: bool = True) -> int:
    """Stop and remove ALL VM containers (including orphaned ones).

    Returns:
        Number of containers stopped
    """
    containers = _get_all_vm_containers()
    if not containers:
        return 0

    count = 0
    for container_id in containers:
        if verbose:
            click.echo(f"  • Stopping container {container_id[:12]}...")
        subprocess.run(["docker", "stop", container_id], capture_output=True)
        subprocess.run(["docker", "rm", container_id], capture_output=True)
        count += 1

    return count


def _verify_vm_serving_correctly(timeout: int = 10) -> tuple[bool, str | None]:
    """Verify the VM is serving the expected content.

    This catches the case where an old container is still serving on the port.

    Returns:
        (success, error_message)
    """
    import urllib.request
    import urllib.error

    url = f"http://localhost:{NOVNC_PORT}/control.html"
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                content = response.read().decode("utf-8", errors="replace")

                # Check for expected content markers
                if "terminalInitialized" not in content:
                    return False, "Stale content detected (missing expected code)"

                # Get content length to verify it's the full file
                content_length = len(content)
                if content_length < 190000:  # control.html should be ~193KB
                    return False, f"Content too small ({content_length} bytes)"

                return True, None
        except urllib.error.URLError:
            time.sleep(0.5)
        except Exception as e:
            time.sleep(0.5)

    return False, "Timeout waiting for VM to respond"


def _build_image(vm_dir: Path) -> bool:
    """Build the Docker image."""
    click.echo("  • Building Docker image (this may take a few minutes)...")

    # Build from project root with Dockerfile in docker/browser-vm
    project_root = vm_dir.parent.parent
    dockerfile_path = vm_dir / "Dockerfile"

    result = subprocess.run(
        ["docker", "build", "-t", IMAGE_NAME, "-f", str(dockerfile_path), "."],
        cwd=project_root,
        capture_output=False  # Show build output
    )

    return result.returncode == 0


def _start_container(dev_mode: bool = False, vm_dir: Path = None) -> bool:
    """Start the VM container.

    Args:
        dev_mode: If True, mount source files for live editing.
        vm_dir: Path to the browser-vm directory (required if dev_mode is True).
    """
    if dev_mode:
        click.echo("  • Starting container in development mode...")
    else:
        click.echo("  • Starting container...")

    cmd = [
        "docker", "run", "-d",
        "--name", CONTAINER_NAME,
        "--network", "host",
        "--shm-size=2g",
    ]

    # Add volume mounts for development mode
    if dev_mode and vm_dir:
        project_root = vm_dir.parent.parent

        # Disable Python bytecode caching so mounted source files are always used
        # Without this, Python uses stale .pyc files from the Docker build
        cmd.extend(["-e", "PYTHONDONTWRITEBYTECODE=1"])

        # Set dev mode flag so control panel can show [DEV] indicator
        cmd.extend(["-e", "INSPEKT_DEV_MODE=1"])

        # Mount control panel, fonts, and servers for UI/server development
        cmd.extend([
            "-v", f"{vm_dir}/control-panel.html:/usr/share/novnc/control.html:ro",
            "-v", f"{vm_dir}/fonts:/usr/share/novnc/fonts:ro",
            "-v", f"{vm_dir}/control-server.py:/opt/control-server.py:ro",
            "-v", f"{vm_dir}/terminal-server.py:/opt/terminal-server.py:ro",
            "-v", f"{vm_dir}/inspekt-config.json:/root/.config/inspekt.json:ro",
        ])

        # Mount inspekt source for Python code changes
        inspekt_src = project_root / "inspekt"
        if inspekt_src.exists():
            cmd.extend(["-v", f"{inspekt_src}:/opt/inspekt/inspekt:ro"])

        # Mount Chrome extension for extension development
        # Note: Chromium needs restart to reload extension, but no rebuild needed
        extensions_src = project_root / "extensions"
        if extensions_src.exists():
            cmd.extend(["-v", f"{extensions_src}:/opt/inspekt/extensions:ro"])

        click.echo("    Volume mounts:")
        click.echo("    • control-panel.html → /usr/share/novnc/control.html")
        click.echo("    • fonts/ → /usr/share/novnc/fonts/")
        click.echo("    • control-server.py → /opt/control-server.py")
        click.echo("    • terminal-server.py → /opt/terminal-server.py")
        click.echo("    • inspekt-config.json → /root/.config/inspekt.json")
        if inspekt_src.exists():
            click.echo("    • inspekt/ → /opt/inspekt/inspekt/")
        if extensions_src.exists():
            click.echo("    • extensions/ → /opt/inspekt/extensions/")

    cmd.append(IMAGE_NAME)

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        click.echo(f"  ✗ Failed to start container: {result.stderr}", err=True)
        return False

    return True


def _stop_container() -> bool:
    """Stop the VM container."""
    result = subprocess.run(
        ["docker", "stop", CONTAINER_NAME],
        capture_output=True
    )
    return result.returncode == 0


def _remove_container() -> bool:
    """Remove the VM container."""
    result = subprocess.run(
        ["docker", "rm", CONTAINER_NAME],
        capture_output=True
    )
    return result.returncode == 0


def _wait_for_vm(timeout: int = 30) -> bool:
    """Wait for the VM to be ready."""
    import socket

    click.echo("  • Waiting for VM to be ready...")

    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(("127.0.0.1", NOVNC_PORT))
            sock.close()

            if result == 0:
                return True
        except:
            pass

        time.sleep(0.5)

    return False


@click.group()
def vm():
    """Manage the Inspekt Browser VM.

    The Browser VM is a Docker-based virtual machine with Chromium
    and the Inspekt extension pre-installed. Access it via noVNC
    in your browser.

    Examples:
        inspekt vm start    # Build and start the VM
        inspekt vm open     # Open the control panel
        inspekt vm stop     # Stop the VM
        inspekt vm status   # Check VM status
        inspekt vm restart  # Restart the VM
    """
    pass


@vm.command()
@click.option("--rebuild", is_flag=True, help="Force rebuild the Docker image")
@click.option("--no-open", is_flag=True, help="Don't open the control panel after starting")
@click.option("--dev", is_flag=True, help="Development mode: mount source files for live editing")
@click.option("--no-dev", is_flag=True, help="Disable dev mode even in source repo")
def start(rebuild, no_open, dev, no_dev):
    """Start the Inspekt Browser VM.

    Builds the Docker image if needed and starts the container.
    The VM will be accessible at http://localhost:6080/control.html

    When running from the Inspekt source repository, dev mode is automatically
    enabled to mount local source files. Use --no-dev to disable this.

    Examples:
        inspekt vm start           # Start the VM (auto-detects dev environment)
        inspekt vm start --rebuild # Force rebuild the image
        inspekt vm start --no-open # Don't open browser
        inspekt vm start --dev     # Explicitly enable development mode
        inspekt vm start --no-dev  # Disable auto-detected dev mode
    """
    # Check Docker is running
    if not _is_docker_running():
        click.echo("Error: Docker is not running", err=True)
        click.echo("\nPlease start Docker (Docker Desktop, OrbStack, etc.) and try again.", err=True)
        sys.exit(1)

    # Check if already running
    if _is_container_running():
        click.echo("VM is already running")
        click.echo(f"\nControl panel: http://localhost:{NOVNC_PORT}/control.html")
        if not no_open:
            webbrowser.open(f"http://localhost:{NOVNC_PORT}/control.html")
        return

    click.echo("Starting Inspekt Browser VM...\n")

    # SAFEGUARD 1: Check for orphaned containers from old image versions
    orphaned = _get_all_vm_containers()
    if orphaned:
        click.echo(f"  ⚠ Found {len(orphaned)} orphaned container(s) from previous sessions")
        stopped = _stop_all_vm_containers()
        click.echo(f"  ✓ Cleaned up {stopped} container(s)")

    # SAFEGUARD 2: Check for port conflicts
    port_conflicts = _check_ports_available()
    if port_conflicts:
        click.echo("  ⚠ Port conflicts detected:", err=True)
        for port, desc in port_conflicts:
            click.echo(f"    • Port {port} in use ({desc})", err=True)
        click.echo("\n  Run 'inspekt vm cleanup' to stop all VM containers,", err=True)
        click.echo("  or manually stop the conflicting process.", err=True)
        sys.exit(1)

    # Get VM directory
    vm_dir = get_vm_dir()
    if not vm_dir:
        click.echo("Error: Could not find docker/browser-vm directory", err=True)
        click.echo("\nMake sure you're in the Inspekt project directory or have it installed properly.", err=True)
        sys.exit(1)

    # Auto-detect dev environment
    auto_dev = False
    if not dev and not no_dev and _is_dev_environment():
        auto_dev = True
        dev = True
        click.echo("  • Dev environment detected (mounting local source)")

    # Build image if needed
    if rebuild or not _image_exists():
        if not _build_image(vm_dir):
            click.echo("\n✗ Failed to build Docker image", err=True)
            sys.exit(1)
        click.echo("  ✓ Docker image built")
    else:
        click.echo("  • Using existing Docker image")

    # Remove old container if exists (by name)
    if _container_exists():
        click.echo("  • Removing old container...")
        _stop_container()
        _remove_container()

    # Start container
    if not _start_container(dev_mode=dev, vm_dir=vm_dir):
        sys.exit(1)

    # Wait for VM to be ready
    if not _wait_for_vm():
        click.echo("  ✗ VM failed to start within timeout", err=True)
        sys.exit(1)

    # SAFEGUARD 3: Verify correct content is being served
    click.echo("  • Verifying VM is serving correctly...")
    success, error = _verify_vm_serving_correctly()
    if not success:
        click.echo(f"  ✗ VM verification failed: {error}", err=True)
        click.echo("\n  This usually means an old container is still occupying ports.", err=True)
        click.echo("  Run 'inspekt vm cleanup' and try again.", err=True)
        sys.exit(1)

    click.echo("  ✓ VM started and verified")

    if dev:
        click.echo(f"\n✓ Inspekt Browser VM is running (development mode)\n")
        click.echo("  ⚠ Note: Container restart required for file changes")
        click.echo("         (noVNC caches files at startup)\n")
    else:
        click.echo(f"\n✓ Inspekt Browser VM is running\n")
    click.echo(f"  Control panel: http://localhost:{NOVNC_PORT}/control.html")
    click.echo(f"  VNC viewer:    http://localhost:{NOVNC_PORT}/vnc.html")

    click.echo("\nThe VM includes:")
    click.echo("  • Chromium browser with Inspekt extension")
    click.echo("  • Terminal with 'inspekt' command ready")
    click.echo("  • Bridge server for CLI commands")

    # Open control panel
    if not no_open:
        click.echo("\nOpening control panel in your browser...")
        webbrowser.open(f"http://localhost:{NOVNC_PORT}/control.html")


@vm.command()
def stop():
    """Stop the Inspekt Browser VM.

    Stops the running container. Use 'inspekt vm start' to start it again.

    Examples:
        inspekt vm stop
    """
    if not _is_docker_running():
        click.echo("Error: Docker is not running", err=True)
        sys.exit(1)

    if not _is_container_running():
        click.echo("VM is not running")
        return

    click.echo("Stopping Inspekt Browser VM...")

    if _stop_container():
        click.echo("✓ VM stopped")

        # Also remove the container so it can be started fresh
        _remove_container()
    else:
        click.echo("✗ Failed to stop VM", err=True)
        sys.exit(1)


@vm.command()
@click.option("--rebuild", is_flag=True, help="Force rebuild the Docker image")
@click.option("--dev", is_flag=True, help="Development mode: mount source files for live editing")
@click.option("--no-dev", is_flag=True, help="Disable dev mode even in source repo")
def restart(rebuild, dev, no_dev):
    """Restart the Inspekt Browser VM.

    Stops the VM if running and starts it fresh.

    When running from the Inspekt source repository, dev mode is automatically
    enabled to mount local source files. Use --no-dev to disable this.

    Examples:
        inspekt vm restart           # Restart the VM (auto-detects dev environment)
        inspekt vm restart --rebuild # Rebuild and restart
        inspekt vm restart --dev     # Explicitly enable development mode
        inspekt vm restart --no-dev  # Disable auto-detected dev mode
    """
    if not _is_docker_running():
        click.echo("Error: Docker is not running", err=True)
        sys.exit(1)

    click.echo("Restarting Inspekt Browser VM...\n")

    # Stop if running
    if _is_container_running():
        click.echo("  • Stopping VM...")
        _stop_container()
        _remove_container()
        click.echo("  ✓ VM stopped")

    # Get VM directory
    vm_dir = get_vm_dir()
    if not vm_dir:
        click.echo("Error: Could not find docker/browser-vm directory", err=True)
        sys.exit(1)

    # Auto-detect dev environment
    auto_dev = False
    if not dev and not no_dev and _is_dev_environment():
        auto_dev = True
        dev = True
        click.echo("  • Dev environment detected (mounting local source)")

    # Rebuild if requested
    if rebuild:
        if not _build_image(vm_dir):
            click.echo("\n✗ Failed to build Docker image", err=True)
            sys.exit(1)
        click.echo("  ✓ Docker image rebuilt")

    # Start container
    if not _start_container(dev_mode=dev, vm_dir=vm_dir):
        sys.exit(1)

    # Wait for VM to be ready
    if not _wait_for_vm():
        click.echo("  ✗ VM failed to start within timeout", err=True)
        sys.exit(1)

    click.echo("  ✓ VM started")

    if dev:
        click.echo(f"\n✓ Inspekt Browser VM restarted (development mode)\n")
        click.echo("  ⚠ Note: Container restart required for file changes\n")
    else:
        click.echo(f"\n✓ Inspekt Browser VM restarted\n")
    click.echo(f"  Control panel: http://localhost:{NOVNC_PORT}/control.html")


@vm.command("open")
def open_panel():
    """Open the VM control panel in your browser.

    Opens the web-based control panel where you can interact with
    the VM, run commands, and access Chrome and Terminal.

    Examples:
        inspekt vm open
    """
    if not _is_docker_running():
        click.echo("Error: Docker is not running", err=True)
        sys.exit(1)

    if not _is_container_running():
        click.echo("Error: VM is not running", err=True)
        from inspekt.app.cli.table import _style_with_inline_code
        click.echo(_style_with_inline_code("\nStart it with: `inspekt vm start`", base_fg="red"), err=True)
        sys.exit(1)

    url = f"http://localhost:{NOVNC_PORT}/control.html"
    click.echo(f"Opening {url}...")
    webbrowser.open(url)


@vm.command()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def status(output_json):
    """Check the status of the Browser VM.

    Shows whether the VM is running and its connection details.

    Examples:
        inspekt vm status        # Human-readable output
        inspekt vm status --json # JSON output
    """
    import json

    docker_running = _is_docker_running()
    container_running = _is_container_running() if docker_running else False
    image_exists = _image_exists() if docker_running else False

    if output_json:
        data = {
            "docker_running": docker_running,
            "image_exists": image_exists,
            "container_running": container_running,
            "control_panel_url": f"http://localhost:{NOVNC_PORT}/control.html" if container_running else None,
            "vnc_url": f"http://localhost:{NOVNC_PORT}/vnc.html" if container_running else None,
        }
        click.echo(json.dumps(data, indent=2))
        return

    click.echo("Inspekt Browser VM Status\n")
    click.echo("=" * 40)

    # Docker status
    if docker_running:
        click.echo("Docker:     ✓ Running")
    else:
        click.echo("Docker:     ✗ Not running")
        click.echo("\nStart Docker to use the VM.")
        sys.exit(1)

    # Image status
    if image_exists:
        click.echo(f"Image:      ✓ Built ({IMAGE_NAME})")
    else:
        click.echo("Image:      ○ Not built")

    # Container status
    if container_running:
        click.echo("VM:         ✓ Running")
        click.echo("=" * 40)
        click.echo(f"\nControl panel: http://localhost:{NOVNC_PORT}/control.html")
        click.echo(f"VNC viewer:    http://localhost:{NOVNC_PORT}/vnc.html")
    else:
        click.echo("VM:         ✗ Not running")
        click.echo("=" * 40)
        click.echo("\nStart with: inspekt vm start")
        sys.exit(1)


@vm.command()
def logs():
    """Show VM container logs.

    Displays the Docker container logs for debugging.

    Examples:
        inspekt vm logs
    """
    if not _is_docker_running():
        click.echo("Error: Docker is not running", err=True)
        sys.exit(1)

    if not _is_container_running() and not _container_exists():
        click.echo("Error: VM container does not exist", err=True)
        click.echo("\nStart with: inspekt vm start", err=True)
        sys.exit(1)

    # Show logs
    subprocess.run(["docker", "logs", "--tail", "100", CONTAINER_NAME])


@vm.command()
def shell():
    """Open a shell inside the VM container.

    Opens an interactive bash shell inside the running container
    for debugging or manual operations.

    Examples:
        inspekt vm shell
    """
    if not _is_docker_running():
        click.echo("Error: Docker is not running", err=True)
        sys.exit(1)

    if not _is_container_running():
        click.echo("Error: VM is not running", err=True)
        from inspekt.app.cli.table import _style_with_inline_code
        click.echo(_style_with_inline_code("\nStart it with: `inspekt vm start`", base_fg="red"), err=True)
        sys.exit(1)

    click.echo("Opening shell in VM container...")
    click.echo("Type 'exit' to return.\n")

    subprocess.run(["docker", "exec", "-it", CONTAINER_NAME, "/bin/bash"])


@vm.command()
@click.option("--force", is_flag=True, help="Don't ask for confirmation")
def cleanup(force):
    """Clean up ALL VM containers and free ports.

    Stops and removes ALL containers from any version of the inspekt-browser-vm
    image. Use this when you have orphaned containers from previous sessions
    that are blocking ports.

    Examples:
        inspekt vm cleanup        # Clean up with confirmation
        inspekt vm cleanup --force # Clean up without confirmation
    """
    if not _is_docker_running():
        click.echo("Error: Docker is not running", err=True)
        sys.exit(1)

    # Find all VM containers
    containers = _get_all_vm_containers()

    if not containers:
        click.echo("No VM containers found.")
        return

    click.echo(f"Found {len(containers)} VM container(s):")
    for container_id in containers:
        # Get container info
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.Name}} ({{.Image}}) - {{.State.Status}}", container_id],
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            click.echo(f"  • {result.stdout.strip()}")
        else:
            click.echo(f"  • {container_id[:12]}")

    # Check for port conflicts to show user what will be freed
    port_conflicts = _check_ports_available()
    if port_conflicts:
        click.echo(f"\nPorts currently in use:")
        for port, desc in port_conflicts:
            click.echo(f"  • Port {port} ({desc})")

    # Confirm unless --force
    if not force:
        click.echo("")
        if not click.confirm("Stop and remove all these containers?"):
            click.echo("Cancelled.")
            return

    click.echo("\nCleaning up...")
    stopped = _stop_all_vm_containers()
    click.echo(f"✓ Removed {stopped} container(s)")

    # Verify ports are now free
    remaining_conflicts = _check_ports_available()
    if remaining_conflicts:
        click.echo("\n⚠ Some ports are still in use (may be non-Docker processes):")
        for port, desc in remaining_conflicts:
            click.echo(f"  • Port {port} ({desc})")
    else:
        click.echo("✓ All VM ports are now available")
