"""
Process manager for running multiple Inspekt servers in foreground mode.

Provides:
- Async subprocess management with output streaming
- Unified, prefixed log output with colors
- Graceful shutdown with confirmation prompt
- Health monitoring and failure handling
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import signal
import socket
import sys
from dataclasses import dataclass, field
from enum import Enum

import click


class ServerType(Enum):
    """Server types with display configuration."""

    BRIDGE = ("BRIDGE", "cyan")
    API = ("API", "green")
    DOCS = ("DOCS", "yellow")

    @property
    def prefix(self) -> str:
        """Return formatted prefix string."""
        return f"[{self.value[0]}]"

    @property
    def color(self) -> str:
        """Return the color for this server type."""
        return self.value[1]


@dataclass
class ManagedProcess:
    """Represents a managed server process."""

    server_type: ServerType
    process: asyncio.subprocess.Process | None = None
    started: bool = False
    healthy: bool = False
    error_message: str | None = None
    host: str = "127.0.0.1"
    port: int = 0
    _stream_tasks: list = field(default_factory=list)


class ProcessManager:
    """
    Manages multiple server processes running in foreground mode.

    Features:
    - Runs servers as async subprocesses
    - Streams and prefixes stdout/stderr output
    - Handles Ctrl+C with confirmation prompt
    - Monitors health during startup
    - Continues running if one server fails
    """

    def __init__(self):
        self.processes: dict[ServerType, ManagedProcess] = {}
        self.shutdown_requested = False
        self.shutdown_event = asyncio.Event()
        self._prompt_active = False
        self._prompt_task: asyncio.Future | None = None

    def _is_port_in_use(self, host: str, port: int) -> bool:
        """Check if a port is already in use."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0  # 0 means connection succeeded = port in use
        except Exception:
            return False

    async def start_bridge(self, port: int = 8765) -> ManagedProcess:
        """Start the bridge server as an async subprocess."""
        managed = ManagedProcess(
            server_type=ServerType.BRIDGE,
            host="127.0.0.1",
            port=port,
        )
        self.processes[ServerType.BRIDGE] = managed

        # Pre-flight check: is port already in use?
        if self._is_port_in_use("127.0.0.1", port):
            managed.error_message = f"Port {port} already in use. Run: inspekt stop"
            return managed

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "inspekt.bridge_ws",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            managed.process = proc
            managed.started = True

            # Start output streaming tasks
            if proc.stdout:
                task = asyncio.create_task(self._stream_pipe(managed, proc.stdout, is_stderr=False))
                managed._stream_tasks.append(task)
            if proc.stderr:
                task = asyncio.create_task(self._stream_pipe(managed, proc.stderr, is_stderr=True))
                managed._stream_tasks.append(task)

        except Exception as e:
            managed.error_message = str(e)

        return managed

    async def start_api(self, host: str, port: int) -> ManagedProcess:
        """Start the API server (uvicorn) as an async subprocess."""
        managed = ManagedProcess(
            server_type=ServerType.API,
            host=host,
            port=port,
        )
        self.processes[ServerType.API] = managed

        # Pre-flight check: is port already in use?
        if self._is_port_in_use(host, port):
            managed.error_message = f"Port {port} already in use. Run: inspekt stop"
            return managed

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "uvicorn",
                "inspekt.app.api.server:app",
                "--host",
                host,
                "--port",
                str(port),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            managed.process = proc
            managed.started = True

            # Start output streaming tasks
            if proc.stdout:
                task = asyncio.create_task(self._stream_pipe(managed, proc.stdout, is_stderr=False))
                managed._stream_tasks.append(task)
            if proc.stderr:
                task = asyncio.create_task(self._stream_pipe(managed, proc.stderr, is_stderr=True))
                managed._stream_tasks.append(task)

        except Exception as e:
            managed.error_message = str(e)

        return managed

    async def start_docs(self, host: str, port: int, project_root: str) -> ManagedProcess:
        """Start MkDocs server as an async subprocess."""
        import importlib.util
        import os

        managed = ManagedProcess(
            server_type=ServerType.DOCS,
            host=host,
            port=port,
        )
        self.processes[ServerType.DOCS] = managed

        # Pre-flight check: is mkdocs installed?
        if importlib.util.find_spec("mkdocs") is None:
            managed.error_message = "mkdocs not installed. Run: pip install mkdocs mkdocs-material"
            return managed

        # Pre-flight check: does mkdocs.yml exist?
        mkdocs_config = os.path.join(project_root, "mkdocs.yml")
        if not os.path.exists(mkdocs_config):
            managed.error_message = "mkdocs.yml not found - docs not available in this installation"
            return managed

        # Pre-flight check: is port already in use?
        if self._is_port_in_use(host, port):
            managed.error_message = f"Port {port} already in use"
            return managed

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "mkdocs",
                "serve",
                "--dev-addr",
                f"{host}:{port}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_root,
            )

            managed.process = proc
            managed.started = True

            # Start output streaming tasks
            if proc.stdout:
                task = asyncio.create_task(self._stream_pipe(managed, proc.stdout, is_stderr=False))
                managed._stream_tasks.append(task)
            if proc.stderr:
                task = asyncio.create_task(self._stream_pipe(managed, proc.stderr, is_stderr=True))
                managed._stream_tasks.append(task)

        except Exception as e:
            managed.error_message = str(e)

        return managed

    async def _stream_pipe(
        self,
        managed: ManagedProcess,
        pipe: asyncio.StreamReader,
        is_stderr: bool = False,
    ) -> None:
        """Stream output from a pipe with colored prefix."""
        prefix = managed.server_type.prefix
        color = managed.server_type.color

        try:
            while True:
                line = await pipe.readline()
                if not line:
                    break

                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    # Skip empty lines and avoid output during shutdown prompt
                    if not self._prompt_active:
                        styled_prefix = click.style(prefix, fg=color, bold=True)
                        click.echo(f"{styled_prefix} {text}")
        except asyncio.CancelledError:
            pass
        except Exception:
            pass  # Process ended or pipe closed

    async def wait_for_health(
        self,
        managed: ManagedProcess,
        timeout: float = 30.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """Wait for a server to become healthy by checking port availability."""
        # Handle pre-flight failures (process never started)
        if not managed.started and managed.error_message:
            managed.healthy = False
            return False

        start_time = asyncio.get_event_loop().time()
        host = managed.host
        port = managed.port

        while asyncio.get_event_loop().time() - start_time < timeout:
            # Check if process died
            if managed.process and managed.process.returncode is not None:
                managed.healthy = False
                managed.error_message = f"Process exited with code {managed.process.returncode}"
                return False

            # Check if port is open
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((host, port))
                sock.close()
                if result == 0:
                    managed.healthy = True
                    return True
            except Exception:
                pass

            await asyncio.sleep(poll_interval)

        managed.error_message = f"Timeout waiting for port {port}"
        return False

    def setup_signal_handlers(self) -> None:
        """Install signal handlers for graceful shutdown with prompt."""
        loop = asyncio.get_event_loop()

        def handle_signal(sig: int) -> None:
            if self.shutdown_requested:
                # Second signal - force shutdown
                click.echo("\nForce shutting down…")
                self.shutdown_event.set()
                return

            self.shutdown_requested = True
            # Schedule the prompt in the event loop (keep a reference so the
            # task isn't garbage collected before it runs)
            self._prompt_task = asyncio.ensure_future(self._prompt_shutdown())

        # Handle SIGINT (Ctrl+C) and SIGTERM
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))

    async def _prompt_shutdown(self) -> None:
        """Prompt user for shutdown confirmation."""
        self._prompt_active = True
        click.echo()  # New line after ^C

        # Use click.confirm in a thread to not block the event loop
        def confirm_sync() -> bool:
            try:
                return click.confirm(
                    click.style("Stop all servers?", fg="yellow"),
                    default=False,
                )
            except (EOFError, KeyboardInterrupt):
                return True  # Force stop on second Ctrl+C or EOF

        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            confirmed = await loop.run_in_executor(pool, confirm_sync)

        self._prompt_active = False

        if confirmed:
            self.shutdown_event.set()
        else:
            self.shutdown_requested = False
            click.echo("Continuing…")

    async def shutdown_all(self, force: bool = False) -> None:
        """Stop all managed processes gracefully."""
        from inspekt.app.cli.icons import progress, success

        click.echo()
        click.echo(f"  {progress('Stopping servers…')}")

        for server_type, managed in self.processes.items():
            if managed.process and managed.process.returncode is None:
                prefix = click.style(server_type.prefix, fg=server_type.color)

                try:
                    # Cancel stream tasks first
                    for task in managed._stream_tasks:
                        task.cancel()

                    # Send SIGTERM for graceful shutdown
                    managed.process.terminate()

                    # Wait for graceful shutdown (max 5 seconds)
                    try:
                        await asyncio.wait_for(managed.process.wait(), timeout=5.0)
                        click.echo(f"  {prefix} {success('stopped')}")
                    except TimeoutError:
                        # Force kill if still running
                        managed.process.kill()
                        await managed.process.wait()
                        click.echo(f"  {prefix} killed")

                except ProcessLookupError:
                    pass  # Already dead

        click.echo()

    async def monitor_processes(self) -> None:
        """Monitor processes and handle failures."""
        from inspekt.app.cli.icons import error

        while not self.shutdown_event.is_set():
            for server_type, managed in self.processes.items():
                if managed.started and managed.process:
                    # Check if process died unexpectedly
                    if managed.process.returncode is not None and managed.healthy:
                        managed.healthy = False
                        prefix = click.style(server_type.prefix, fg="red", bold=True)
                        code = managed.process.returncode
                        click.echo(f"{prefix} {error(f'Server crashed (exit code {code})')}")
                        managed.error_message = f"Crashed with exit code {code}"

            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=1.0)
            except TimeoutError:
                pass  # Continue monitoring
