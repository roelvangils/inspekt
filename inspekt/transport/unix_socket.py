"""Unix socket transport implementation.

This module provides Unix domain socket transport for fast, secure
local IPC between the Inspekt CLI/MCP server and the bridge server.
"""

import asyncio
import json
import os
import socket
import struct
from pathlib import Path
from typing import Optional

from .base import (
    ConnectionError,
    Request,
    Response,
    SyncTransport,
    TimeoutError,
    Transport,
)


def get_socket_path(session_id: Optional[str] = None) -> Path:
    """Get the Unix socket path for a session.

    Uses XDG_RUNTIME_DIR if available (Linux standard), otherwise
    falls back to ~/.inspekt/ directory.

    Args:
        session_id: Optional session identifier for multi-instance support

    Returns:
        Path to the Unix socket file
    """
    # Check for environment variable override
    env_path = os.environ.get("INSPEKT_SOCKET_PATH")
    if env_path:
        return Path(env_path)

    # Use XDG_RUNTIME_DIR if available (Linux), otherwise ~/.inspekt/
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        base_dir = Path(runtime_dir) / "inspekt"
    else:
        base_dir = Path.home() / ".inspekt"

    base_dir.mkdir(parents=True, exist_ok=True)

    if session_id:
        return base_dir / f"inspekt-{session_id}.sock"
    return base_dir / "inspekt.sock"


class UnixSocketTransport(Transport):
    """Async Unix socket transport for client-server communication.

    Uses length-prefixed JSON protocol for message framing:
    - 4-byte big-endian length prefix
    - UTF-8 encoded JSON payload
    """

    def __init__(
        self,
        socket_path: Optional[Path] = None,
        session_id: Optional[str] = None,
    ):
        """Initialize the Unix socket transport.

        Args:
            socket_path: Explicit socket path (overrides session_id)
            session_id: Session identifier for socket path generation
        """
        self._socket_path = socket_path or get_socket_path(session_id)
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected = False

    @property
    def address(self) -> str:
        """Return the socket address for logging."""
        return f"unix://{self._socket_path}"

    @property
    def socket_path(self) -> Path:
        """Return the socket path."""
        return self._socket_path

    def is_connected(self) -> bool:
        """Check if connected to the server."""
        return self._connected and self._writer is not None

    async def connect(self) -> None:
        """Connect to the Unix socket server.

        Raises:
            ConnectionError: If socket doesn't exist or connection fails
        """
        if not self._socket_path.exists():
            raise ConnectionError(
                f"Socket not found: {self._socket_path}. "
                "Is the inspekt server running? Try: inspekt start"
            )

        try:
            self._reader, self._writer = await asyncio.open_unix_connection(
                path=str(self._socket_path)
            )
            self._connected = True
        except OSError as e:
            raise ConnectionError(f"Failed to connect to {self._socket_path}: {e}")

    async def disconnect(self) -> None:
        """Close the connection."""
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None
        self._connected = False

    async def send(self, request: Request, timeout: float = 30.0) -> Response:
        """Send a request and wait for response.

        Protocol:
        - Send: 4-byte length prefix (big-endian) + JSON payload
        - Receive: 4-byte length prefix (big-endian) + JSON payload

        Args:
            request: The request to send
            timeout: Maximum wait time in seconds

        Returns:
            Response from server

        Raises:
            ConnectionError: If not connected or connection lost
            TimeoutError: If request times out
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to server")

        # Serialize request
        payload = json.dumps(
            {
                "method": request.method,
                "params": request.params,
                "id": request.request_id,
            }
        ).encode("utf-8")

        # Send with length prefix
        length_prefix = struct.pack(">I", len(payload))
        self._writer.write(length_prefix + payload)
        await self._writer.drain()

        # Receive response with timeout
        try:
            async with asyncio.timeout(timeout):
                # Read length prefix (4 bytes)
                length_data = await self._reader.readexactly(4)
                response_length = struct.unpack(">I", length_data)[0]

                # Read response payload
                response_data = await self._reader.readexactly(response_length)
                response_json = json.loads(response_data.decode("utf-8"))

                return Response(
                    success=response_json.get("success", False),
                    data=response_json.get("data"),
                    error=response_json.get("error"),
                    request_id=response_json.get("id"),
                )
        except asyncio.TimeoutError:
            raise TimeoutError(f"Request timed out after {timeout}s")
        except asyncio.IncompleteReadError:
            self._connected = False
            raise ConnectionError("Connection closed by server")


class SyncUnixSocketTransport(SyncTransport):
    """Synchronous Unix socket transport for non-async contexts.

    Used by CLI commands that need synchronous execution.
    """

    def __init__(
        self,
        socket_path: Optional[Path] = None,
        session_id: Optional[str] = None,
    ):
        """Initialize the synchronous Unix socket transport.

        Args:
            socket_path: Explicit socket path (overrides session_id)
            session_id: Session identifier for socket path generation
        """
        self._socket_path = socket_path or get_socket_path(session_id)
        self._socket: Optional[socket.socket] = None

    @property
    def address(self) -> str:
        """Return the socket address for logging."""
        return f"unix://{self._socket_path}"

    @property
    def socket_path(self) -> Path:
        """Return the socket path."""
        return self._socket_path

    def is_connected(self) -> bool:
        """Check if connected to the server."""
        return self._socket is not None

    def connect(self) -> None:
        """Connect to the Unix socket server.

        Raises:
            ConnectionError: If socket doesn't exist or connection fails
        """
        if not self._socket_path.exists():
            raise ConnectionError(
                f"Socket not found: {self._socket_path}. "
                "Is the inspekt server running? Try: inspekt start"
            )

        try:
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.connect(str(self._socket_path))
        except OSError as e:
            self._socket = None
            raise ConnectionError(f"Failed to connect to {self._socket_path}: {e}")

    def disconnect(self) -> None:
        """Close the connection."""
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
        self._socket = None

    def send(self, request: Request, timeout: float = 30.0) -> Response:
        """Send a request and wait for response.

        Args:
            request: The request to send
            timeout: Maximum wait time in seconds

        Returns:
            Response from server

        Raises:
            ConnectionError: If not connected or connection lost
            TimeoutError: If request times out
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to server")

        self._socket.settimeout(timeout)

        # Serialize request
        payload = json.dumps(
            {
                "method": request.method,
                "params": request.params,
                "id": request.request_id,
            }
        ).encode("utf-8")

        # Send with length prefix
        length_prefix = struct.pack(">I", len(payload))
        try:
            self._socket.sendall(length_prefix + payload)

            # Receive length prefix (4 bytes)
            length_data = self._recv_exactly(4)
            response_length = struct.unpack(">I", length_data)[0]

            # Receive response payload
            response_data = self._recv_exactly(response_length)
            response_json = json.loads(response_data.decode("utf-8"))

            return Response(
                success=response_json.get("success", False),
                data=response_json.get("data"),
                error=response_json.get("error"),
                request_id=response_json.get("id"),
            )
        except socket.timeout:
            raise TimeoutError(f"Request timed out after {timeout}s")
        except (BrokenPipeError, ConnectionResetError) as e:
            self._socket = None
            raise ConnectionError(f"Connection lost: {e}")

    def _recv_exactly(self, n: int) -> bytes:
        """Receive exactly n bytes from socket.

        Args:
            n: Number of bytes to receive

        Returns:
            Exactly n bytes of data

        Raises:
            ConnectionError: If connection closed before receiving all data
        """
        data = b""
        while len(data) < n:
            chunk = self._socket.recv(n - len(data))
            if not chunk:
                raise ConnectionError("Connection closed by server")
            data += chunk
        return data
