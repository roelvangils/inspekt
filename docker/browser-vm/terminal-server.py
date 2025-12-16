#!/usr/bin/env python3
"""
WebSocket Terminal Server for Inspekt Browser VM.
Provides a PTY-based shell accessible via WebSocket for xterm.js clients.
"""

import asyncio
import json
import os
import pty
import signal
import struct
import fcntl
import termios
from websockets.server import serve
from websockets.exceptions import ConnectionClosed

PORT = 8889
SHELL = os.environ.get('SHELL', '/bin/bash')


class TerminalSession:
    """Manages a single terminal session with PTY."""

    def __init__(self):
        self.master_fd = None
        self.slave_fd = None
        self.pid = None

    def spawn(self, cols=80, rows=24):
        """Spawn a new shell process with PTY."""
        # Create PTY
        self.master_fd, self.slave_fd = pty.openpty()

        # Set initial terminal size
        self._set_size(cols, rows)

        # Fork process
        self.pid = os.fork()

        if self.pid == 0:
            # Child process
            os.close(self.master_fd)
            os.setsid()
            os.dup2(self.slave_fd, 0)
            os.dup2(self.slave_fd, 1)
            os.dup2(self.slave_fd, 2)
            os.close(self.slave_fd)

            # Set environment
            env = os.environ.copy()
            env['TERM'] = 'xterm-256color'
            env['COLORTERM'] = 'truecolor'
            # Mark this as the control panel terminal (supports OSC 1337 downloads)
            env['INSPEKT_TERMINAL'] = 'control-panel'

            # Activate inspekt venv and start shell
            os.execve('/bin/bash', ['/bin/bash', '-c',
                'source /opt/inspekt/.venv/bin/activate && exec /bin/bash'], env)
        else:
            # Parent process
            os.close(self.slave_fd)
            # Set non-blocking mode
            flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def _set_size(self, cols, rows):
        """Set terminal size."""
        if self.master_fd:
            winsize = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)

    def resize(self, cols, rows):
        """Resize the terminal and notify the shell."""
        self._set_size(cols, rows)
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGWINCH)
            except ProcessLookupError:
                pass

    def write(self, data):
        """Write data to the terminal."""
        if self.master_fd:
            os.write(self.master_fd, data)

    def read(self):
        """Read available data from the terminal."""
        if self.master_fd:
            try:
                return os.read(self.master_fd, 4096)
            except (OSError, BlockingIOError):
                return b''
        return b''

    def close(self):
        """Clean up the terminal session."""
        if self.master_fd:
            os.close(self.master_fd)
            self.master_fd = None
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGTERM)
                os.waitpid(self.pid, os.WNOHANG)
            except (ProcessLookupError, ChildProcessError):
                pass
            self.pid = None


async def terminal_handler(websocket):
    """Handle a WebSocket connection for terminal access."""
    session = TerminalSession()

    # Get initial size from query params or use defaults
    cols = 80
    rows = 24

    try:
        # Parse query string for initial size
        if websocket.request and hasattr(websocket.request, 'path'):
            path = websocket.request.path
            if '?' in path:
                query = path.split('?')[1]
                params = dict(p.split('=') for p in query.split('&') if '=' in p)
                cols = int(params.get('cols', 80))
                rows = int(params.get('rows', 24))
    except (ValueError, AttributeError):
        pass

    # Spawn the shell
    session.spawn(cols, rows)
    print(f"[terminal] New session: pid={session.pid}, size={cols}x{rows}")

    async def read_from_pty():
        """Read from PTY and send to WebSocket."""
        while True:
            try:
                data = session.read()
                if data:
                    await websocket.send(data.decode('utf-8', errors='replace'))
                else:
                    await asyncio.sleep(0.01)
            except ConnectionClosed:
                break
            except Exception as e:
                print(f"[terminal] Read error: {e}")
                break

    async def write_to_pty():
        """Read from WebSocket and write to PTY."""
        async for message in websocket:
            try:
                if isinstance(message, str):
                    # Check if it's a control message (JSON)
                    if message.startswith('{'):
                        try:
                            ctrl = json.loads(message)
                            if ctrl.get('type') == 'resize':
                                session.resize(ctrl.get('cols', 80), ctrl.get('rows', 24))
                                print(f"[terminal] Resized to {ctrl.get('cols')}x{ctrl.get('rows')}")
                                continue
                        except json.JSONDecodeError:
                            pass
                    # Regular input
                    session.write(message.encode('utf-8'))
                elif isinstance(message, bytes):
                    session.write(message)
            except Exception as e:
                print(f"[terminal] Write error: {e}")
                break

    try:
        # Run both tasks concurrently
        read_task = asyncio.create_task(read_from_pty())
        write_task = asyncio.create_task(write_to_pty())

        # Wait for either task to complete (connection closed or error)
        done, pending = await asyncio.wait(
            [read_task, write_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    finally:
        session.close()
        print(f"[terminal] Session ended")


async def main():
    """Start the WebSocket terminal server."""
    # Security: Bind to localhost only to prevent external network access
    # The terminal provides shell access, so it should never be exposed externally
    # Access is provided via the control panel on port 6080 (noVNC)
    host = "127.0.0.1"
    print(f"Terminal WebSocket Server")
    print(f"Listening on ws://{host}:{PORT}")
    print(f"Shell: {SHELL}")

    async with serve(terminal_handler, host, PORT):
        await asyncio.Future()  # Run forever


if __name__ == '__main__':
    asyncio.run(main())
