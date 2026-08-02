"""TCP transport implementation for Windows fallback.

This module provides TCP socket transport as a fallback for platforms
that don't support Unix domain sockets (primarily Windows).
"""

import asyncio
import builtins
import hashlib
import json
import socket
import struct
from typing import Optional

from .base import (
    ConnectionError,
    Request,
    Response,
    SyncTransport,
    TimeoutError,
    Transport,
)


def get_tcp_port(session_id: str | None = None) -> int:
    """Calculate deterministic port from session ID.

    Uses SHA256 hash to generate a consistent port for the same session,
    enabling reconnection without coordination.

    Port range: 49152-65535 (dynamic/private ports per IANA)

    Args:
        session_id: Session identifier (None uses "default")

    Returns:
        Deterministic port number in range 49152-65535
    """
    if session_id is None:
        session_id = "default"

    # Hash the session ID and use first 4 bytes to compute port
    hash_bytes = hashlib.sha256(session_id.encode()).digest()
    hash_int = int.from_bytes(hash_bytes[:4], "big")

    # Map to dynamic port range: 49152 + (hash % 16383)
    # This gives us ports 49152-65534
    return 49152 + (hash_int % 16383)


class TCPTransport(Transport):
    """Async TCP transport for Windows or as explicit fallback.

    Uses the same length-prefixed JSON protocol as Unix socket transport.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int | None = None,
        session_id: str | None = None,
    ):
        """Initialize the TCP transport.

        Args:
            host: Server hostname or IP
            port: Explicit port (overrides session_id calculation)
            session_id: Session identifier for port calculation
        """
        self._host = host
        self._port = port if port is not None else get_tcp_port(session_id)
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False

    @property
    def address(self) -> str:
        """Return the server address for logging."""
        return f"tcp://{self._host}:{self._port}"

    @property
    def host(self) -> str:
        """Return the server host."""
        return self._host

    @property
    def port(self) -> int:
        """Return the server port."""
        return self._port

    def is_connected(self) -> bool:
        """Check if connected to the server."""
        return self._connected and self._writer is not None

    async def connect(self) -> None:
        """Connect to the TCP server.

        Raises:
            ConnectionError: If connection fails
        """
        try:
            self._reader, self._writer = await asyncio.open_connection(
                host=self._host,
                port=self._port,
            )
            self._connected = True
        except OSError as e:
            raise ConnectionError(
                f"Failed to connect to {self._host}:{self._port}: {e}. "
                "Is the inspekt server running? Try: inspekt start"
            )

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
        except builtins.TimeoutError:
            raise TimeoutError(f"Request timed out after {timeout}s")
        except asyncio.IncompleteReadError:
            self._connected = False
            raise ConnectionError("Connection closed by server")


class SyncTCPTransport(SyncTransport):
    """Synchronous TCP transport for non-async contexts."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int | None = None,
        session_id: str | None = None,
    ):
        """Initialize the synchronous TCP transport.

        Args:
            host: Server hostname or IP
            port: Explicit port (overrides session_id calculation)
            session_id: Session identifier for port calculation
        """
        self._host = host
        self._port = port if port is not None else get_tcp_port(session_id)
        self._socket: socket.socket | None = None

    @property
    def address(self) -> str:
        """Return the server address for logging."""
        return f"tcp://{self._host}:{self._port}"

    @property
    def host(self) -> str:
        """Return the server host."""
        return self._host

    @property
    def port(self) -> int:
        """Return the server port."""
        return self._port

    def is_connected(self) -> bool:
        """Check if connected to the server."""
        return self._socket is not None

    def connect(self) -> None:
        """Connect to the TCP server.

        Raises:
            ConnectionError: If connection fails
        """
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.connect((self._host, self._port))
        except OSError as e:
            self._socket = None
            raise ConnectionError(
                f"Failed to connect to {self._host}:{self._port}: {e}. "
                "Is the inspekt server running? Try: inspekt start"
            )

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
        except builtins.TimeoutError:
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
