# Unix Socket Transport Implementation Plan

**Goal**: Migrate Inspekt's CLI-to-server communication from HTTP to Unix sockets for improved performance, reliability, and security—while preserving the HTTP API for external integrations and the WebSocket bridge to browser extensions.

**Author**: Claude Code Analysis
**Date**: January 2026
**Estimated Scope**: Medium (affects CLI client, bridge server, MCP server)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture](#2-current-architecture)
3. [Target Architecture](#3-target-architecture)
4. [Implementation Phases](#4-implementation-phases)
5. [Detailed Implementation](#5-detailed-implementation)
6. [File Changes Summary](#6-file-changes-summary)
7. [Testing Strategy](#7-testing-strategy)
8. [Migration & Backwards Compatibility](#8-migration--backwards-compatibility)
9. [Rollback Plan](#9-rollback-plan)
10. [Success Criteria](#10-success-criteria)

---

## 1. Executive Summary

### What Changes
- CLI commands communicate with bridge server via Unix socket instead of HTTP
- MCP server communicates with bridge server via Unix socket instead of HTTP
- URL scheme handlers inherit the new transport (they invoke CLI)
- Bridge server listens on both Unix socket AND HTTP (for external API)

### What Stays the Same
- HTTP API on port 8767 (FastAPI) - unchanged for external integrations
- WebSocket on port 8766 - unchanged for browser extension
- Browser extension connection model - completely unchanged
- All CLI command interfaces - unchanged (internal transport only)

### Benefits
- **Performance**: Unix sockets are 2-3x faster than TCP localhost
- **Reliability**: Deterministic socket paths, no port conflicts
- **Security**: No TCP port exposure for local IPC
- **Auto-start**: CLI can spawn server if not running
- **Multi-instance**: Multiple sessions with isolated sockets

---

## 2. Current Architecture

### Communication Flow
```
┌─────────────┐     HTTP POST      ┌─────────────────┐     WebSocket     ┌─────────────┐
│   CLI       │ ──────────────────►│  Bridge Server  │◄─────────────────►│  Browser    │
│  (client.py)│   localhost:8765   │  (bridge_ws.py) │   localhost:8766  │  Extension  │
└─────────────┘                    └─────────────────┘                   └─────────────┘
                                          ▲
                                          │ HTTP
                                          │
                                   ┌──────┴──────┐
                                   │  HTTP API   │
                                   │  (FastAPI)  │
                                   │  port 8767  │
                                   └─────────────┘
```

### Current Files Involved

| File | Purpose | Lines |
|------|---------|-------|
| `inspekt/client.py` | HTTP client for CLI→Server | ~25,000 |
| `inspekt/bridge_ws.py` | HTTP+WebSocket server | ~2,900 |
| `inspekt/app/mcp/server.py` | MCP server (uses client.py) | ~17,000 |
| `inspekt/config.py` | Configuration management | ~250 |

### Current Client Implementation (`client.py`)

The client uses `requests` library for HTTP:
```python
# Current pattern (simplified)
def run_code(code: str) -> dict:
    response = requests.post(
        f"http://{host}:{port}/run",
        json={"code": code},
        timeout=timeout
    )
    return response.json()
```

### Current Server Implementation (`bridge_ws.py`)

The server uses aiohttp for both HTTP and WebSocket:
```python
# Current pattern (simplified)
app = web.Application()
app.router.add_post('/run', handle_run)
app.router.add_get('/ws', handle_websocket)
web.run_app(app, host='127.0.0.1', port=8765)
```

---

## 3. Target Architecture

### New Communication Flow
```
┌─────────────┐   Unix Socket    ┌─────────────────┐     WebSocket     ┌─────────────┐
│   CLI       │ ────────────────►│  Bridge Server  │◄─────────────────►│  Browser    │
│  (client.py)│  ~/.inspekt/sock │  (bridge_ws.py) │   localhost:8766  │  Extension  │
└─────────────┘                  └─────────────────┘                   └─────────────┘
                                         ▲
      ┌─────────────┐                    │ HTTP (unchanged)
      │  MCP Server │ ───────────────────┤
      └─────────────┘   Unix Socket      │
                                  ┌──────┴──────┐
                                  │  HTTP API   │
                                  │  (FastAPI)  │
                                  │  port 8767  │
                                  └─────────────┘
```

### Socket Path Convention
```
Default:     ~/.inspekt/inspekt.sock
With session: ~/.inspekt/inspekt-{session_id}.sock
Isolated:    /tmp/inspekt-isolated.sock
```

### New Module Structure
```
inspekt/
├── transport/                    # NEW: Transport abstraction layer
│   ├── __init__.py
│   ├── base.py                  # Abstract Transport class
│   ├── unix_socket.py           # Unix socket implementation
│   ├── tcp.py                   # TCP fallback (Windows)
│   └── http.py                  # HTTP transport (legacy/external)
├── client.py                    # MODIFIED: Use transport layer
├── bridge_ws.py                 # MODIFIED: Add socket listener
└── config.py                    # MODIFIED: Add transport config
```

---

## 4. Implementation Phases

### Phase 1: Transport Abstraction Layer (Foundation)
**Files**: New `inspekt/transport/` module
**Risk**: Low (additive, no breaking changes)
**Estimated effort**: Create abstract base and implementations

### Phase 2: Server-Side Socket Listener
**Files**: `inspekt/bridge_ws.py`
**Risk**: Medium (modifies core server)
**Estimated effort**: Add Unix socket listener alongside HTTP

### Phase 3: Client Migration
**Files**: `inspekt/client.py`
**Risk**: Medium (affects all CLI commands)
**Estimated effort**: Replace HTTP calls with socket transport

### Phase 4: MCP Server Migration
**Files**: `inspekt/app/mcp/server.py`
**Risk**: Low (isolated component)
**Estimated effort**: Update to use socket transport

### Phase 5: Auto-Start & Reliability
**Files**: `inspekt/client.py`, CLI commands
**Risk**: Low (enhancement)
**Estimated effort**: Add daemon auto-start and retry logic

### Phase 6: Configuration & CLI Options
**Files**: `inspekt/config.py`, CLI
**Risk**: Low (configuration)
**Estimated effort**: Add transport configuration options

---

## 5. Detailed Implementation

### Phase 1: Transport Abstraction Layer

#### 5.1.1 Create `inspekt/transport/__init__.py`
```python
"""Transport layer for Inspekt client-server communication."""

from .base import Transport, TransportError, ConnectionError, TimeoutError
from .unix_socket import UnixSocketTransport
from .tcp import TCPTransport
from .http import HTTPTransport
from .factory import get_transport, get_default_transport

__all__ = [
    "Transport",
    "TransportError",
    "ConnectionError",
    "TimeoutError",
    "UnixSocketTransport",
    "TCPTransport",
    "HTTPTransport",
    "get_transport",
    "get_default_transport",
]
```

#### 5.1.2 Create `inspekt/transport/base.py`
```python
"""Abstract base class for transport implementations."""

from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import dataclass
import json


class TransportError(Exception):
    """Base exception for transport errors."""
    pass


class ConnectionError(TransportError):
    """Failed to connect to server."""
    pass


class TimeoutError(TransportError):
    """Operation timed out."""
    pass


@dataclass
class Request:
    """A request to send to the server."""
    method: str
    params: dict[str, Any]
    request_id: Optional[str] = None


@dataclass
class Response:
    """A response from the server."""
    success: bool
    data: Any
    error: Optional[str] = None
    request_id: Optional[str] = None


class Transport(ABC):
    """Abstract base class for client-server transport."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the server."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection."""
        pass

    @abstractmethod
    async def send(self, request: Request, timeout: float = 30.0) -> Response:
        """Send a request and wait for response."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if currently connected."""
        pass

    @property
    @abstractmethod
    def address(self) -> str:
        """Return the server address (for logging/debugging)."""
        pass

    async def __aenter__(self) -> "Transport":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.disconnect()


class SyncTransport(ABC):
    """Synchronous transport interface for non-async contexts."""

    @abstractmethod
    def connect(self) -> None:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def send(self, request: Request, timeout: float = 30.0) -> Response:
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        pass

    @property
    @abstractmethod
    def address(self) -> str:
        pass

    def __enter__(self) -> "SyncTransport":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()
```

#### 5.1.3 Create `inspekt/transport/unix_socket.py`
```python
"""Unix socket transport implementation."""

import asyncio
import json
import os
import socket
import struct
from pathlib import Path
from typing import Optional
import uuid

from .base import (
    Transport,
    SyncTransport,
    Request,
    Response,
    ConnectionError,
    TimeoutError,
    TransportError,
)


def get_socket_path(session_id: Optional[str] = None) -> Path:
    """Get the Unix socket path for a session.

    Args:
        session_id: Optional session identifier for multi-instance support

    Returns:
        Path to the Unix socket file
    """
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
    """Async Unix socket transport for client-server communication."""

    def __init__(
        self,
        socket_path: Optional[Path] = None,
        session_id: Optional[str] = None,
    ):
        self._socket_path = socket_path or get_socket_path(session_id)
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected = False

    @property
    def address(self) -> str:
        return f"unix://{self._socket_path}"

    def is_connected(self) -> bool:
        return self._connected and self._writer is not None

    async def connect(self) -> None:
        """Connect to the Unix socket server."""
        if not self._socket_path.exists():
            raise ConnectionError(
                f"Socket not found: {self._socket_path}. "
                "Is the inspekt server running? Try: inspekt server start"
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
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to server")

        # Generate request ID if not provided
        if not request.request_id:
            request.request_id = str(uuid.uuid4())

        # Serialize request
        payload = json.dumps({
            "method": request.method,
            "params": request.params,
            "id": request.request_id,
        }).encode("utf-8")

        # Send with length prefix
        length_prefix = struct.pack(">I", len(payload))
        self._writer.write(length_prefix + payload)
        await self._writer.drain()

        # Receive response with timeout
        try:
            async with asyncio.timeout(timeout):
                # Read length prefix
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
    """Synchronous Unix socket transport for non-async contexts."""

    def __init__(
        self,
        socket_path: Optional[Path] = None,
        session_id: Optional[str] = None,
    ):
        self._socket_path = socket_path or get_socket_path(session_id)
        self._socket: Optional[socket.socket] = None

    @property
    def address(self) -> str:
        return f"unix://{self._socket_path}"

    def is_connected(self) -> bool:
        return self._socket is not None

    def connect(self) -> None:
        """Connect to the Unix socket server."""
        if not self._socket_path.exists():
            raise ConnectionError(
                f"Socket not found: {self._socket_path}. "
                "Is the inspekt server running? Try: inspekt server start"
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
        """Send a request and wait for response."""
        if not self.is_connected():
            raise ConnectionError("Not connected to server")

        self._socket.settimeout(timeout)

        # Generate request ID if not provided
        if not request.request_id:
            request.request_id = str(uuid.uuid4())

        # Serialize request
        payload = json.dumps({
            "method": request.method,
            "params": request.params,
            "id": request.request_id,
        }).encode("utf-8")

        # Send with length prefix
        length_prefix = struct.pack(">I", len(payload))
        try:
            self._socket.sendall(length_prefix + payload)

            # Receive length prefix
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
        """Receive exactly n bytes from socket."""
        data = b""
        while len(data) < n:
            chunk = self._socket.recv(n - len(data))
            if not chunk:
                raise ConnectionError("Connection closed by server")
            data += chunk
        return data
```

#### 5.1.4 Create `inspekt/transport/tcp.py`
```python
"""TCP transport implementation (Windows fallback)."""

import asyncio
import hashlib
import json
import socket
import struct
from typing import Optional
import uuid

from .base import (
    Transport,
    SyncTransport,
    Request,
    Response,
    ConnectionError,
    TimeoutError,
)


def get_tcp_port(session_id: Optional[str] = None) -> int:
    """Calculate deterministic port from session ID.

    Uses the same algorithm as webctl for consistency:
    port = 49152 + (SHA256(session_id)[:8] % 16383)

    This ensures the same session always uses the same port,
    enabling reconnection without coordination.
    """
    if session_id is None:
        session_id = "default"

    hash_bytes = hashlib.sha256(session_id.encode()).digest()
    hash_int = int.from_bytes(hash_bytes[:4], "big")
    return 49152 + (hash_int % 16383)


class TCPTransport(Transport):
    """Async TCP transport for Windows or as fallback."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: Optional[int] = None,
        session_id: Optional[str] = None,
    ):
        self._host = host
        self._port = port or get_tcp_port(session_id)
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected = False

    @property
    def address(self) -> str:
        return f"tcp://{self._host}:{self._port}"

    def is_connected(self) -> bool:
        return self._connected and self._writer is not None

    async def connect(self) -> None:
        """Connect to the TCP server."""
        try:
            self._reader, self._writer = await asyncio.open_connection(
                host=self._host,
                port=self._port,
            )
            self._connected = True
        except OSError as e:
            raise ConnectionError(
                f"Failed to connect to {self._host}:{self._port}: {e}. "
                "Is the inspekt server running? Try: inspekt server start"
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
        """Send a request and wait for response."""
        if not self.is_connected():
            raise ConnectionError("Not connected to server")

        if not request.request_id:
            request.request_id = str(uuid.uuid4())

        payload = json.dumps({
            "method": request.method,
            "params": request.params,
            "id": request.request_id,
        }).encode("utf-8")

        length_prefix = struct.pack(">I", len(payload))
        self._writer.write(length_prefix + payload)
        await self._writer.drain()

        try:
            async with asyncio.timeout(timeout):
                length_data = await self._reader.readexactly(4)
                response_length = struct.unpack(">I", length_data)[0]
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


class SyncTCPTransport(SyncTransport):
    """Synchronous TCP transport for non-async contexts."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: Optional[int] = None,
        session_id: Optional[str] = None,
    ):
        self._host = host
        self._port = port or get_tcp_port(session_id)
        self._socket: Optional[socket.socket] = None

    @property
    def address(self) -> str:
        return f"tcp://{self._host}:{self._port}"

    def is_connected(self) -> bool:
        return self._socket is not None

    def connect(self) -> None:
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.connect((self._host, self._port))
        except OSError as e:
            self._socket = None
            raise ConnectionError(
                f"Failed to connect to {self._host}:{self._port}: {e}"
            )

    def disconnect(self) -> None:
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
        self._socket = None

    def send(self, request: Request, timeout: float = 30.0) -> Response:
        if not self.is_connected():
            raise ConnectionError("Not connected to server")

        self._socket.settimeout(timeout)

        if not request.request_id:
            request.request_id = str(uuid.uuid4())

        payload = json.dumps({
            "method": request.method,
            "params": request.params,
            "id": request.request_id,
        }).encode("utf-8")

        length_prefix = struct.pack(">I", len(payload))
        try:
            self._socket.sendall(length_prefix + payload)

            length_data = self._recv_exactly(4)
            response_length = struct.unpack(">I", length_data)[0]
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
        data = b""
        while len(data) < n:
            chunk = self._socket.recv(n - len(data))
            if not chunk:
                raise ConnectionError("Connection closed by server")
            data += chunk
        return data
```

#### 5.1.5 Create `inspekt/transport/factory.py`
```python
"""Transport factory for automatic transport selection."""

import platform
import os
from pathlib import Path
from typing import Optional, Union

from .base import Transport, SyncTransport
from .unix_socket import UnixSocketTransport, SyncUnixSocketTransport, get_socket_path
from .tcp import TCPTransport, SyncTCPTransport, get_tcp_port


def get_transport(
    session_id: Optional[str] = None,
    transport_type: Optional[str] = None,
    async_mode: bool = True,
) -> Union[Transport, SyncTransport]:
    """Get the appropriate transport for the current platform.

    Args:
        session_id: Optional session identifier for multi-instance support
        transport_type: Force a specific transport ("unix", "tcp", "auto")
        async_mode: Return async or sync transport

    Returns:
        Appropriate Transport or SyncTransport instance
    """
    if transport_type is None:
        transport_type = os.environ.get("INSPEKT_TRANSPORT", "auto")

    # Determine transport based on platform
    if transport_type == "auto":
        if platform.system() == "Windows":
            transport_type = "tcp"
        else:
            transport_type = "unix"

    if transport_type == "unix":
        if async_mode:
            return UnixSocketTransport(session_id=session_id)
        else:
            return SyncUnixSocketTransport(session_id=session_id)
    elif transport_type == "tcp":
        if async_mode:
            return TCPTransport(session_id=session_id)
        else:
            return SyncTCPTransport(session_id=session_id)
    else:
        raise ValueError(f"Unknown transport type: {transport_type}")


def get_default_transport(async_mode: bool = True) -> Union[Transport, SyncTransport]:
    """Get the default transport for the current platform."""
    return get_transport(session_id=None, transport_type="auto", async_mode=async_mode)


def get_server_address(
    session_id: Optional[str] = None,
    transport_type: Optional[str] = None,
) -> str:
    """Get the server address string for a given configuration.

    Useful for logging and debugging.
    """
    if transport_type is None:
        transport_type = os.environ.get("INSPEKT_TRANSPORT", "auto")

    if transport_type == "auto":
        if platform.system() == "Windows":
            transport_type = "tcp"
        else:
            transport_type = "unix"

    if transport_type == "unix":
        return f"unix://{get_socket_path(session_id)}"
    elif transport_type == "tcp":
        port = get_tcp_port(session_id)
        return f"tcp://127.0.0.1:{port}"
    else:
        return f"unknown://{transport_type}"
```

### Phase 2: Server-Side Socket Listener

#### 5.2.1 Modify `inspekt/bridge_ws.py`

Add Unix socket listener alongside existing HTTP server. Key changes:

```python
# Add imports at top of file
import asyncio
import struct
from pathlib import Path
from inspekt.transport.unix_socket import get_socket_path
from inspekt.transport.tcp import get_tcp_port

# Add new class for socket protocol handler
class SocketProtocolHandler:
    """Handles the length-prefixed JSON protocol for socket clients."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer

    async def read_request(self) -> Optional[dict]:
        """Read a length-prefixed JSON request."""
        try:
            length_data = await self.reader.readexactly(4)
            length = struct.unpack(">I", length_data)[0]
            data = await self.reader.readexactly(length)
            return json.loads(data.decode("utf-8"))
        except (asyncio.IncompleteReadError, ConnectionResetError):
            return None

    async def write_response(self, response: dict) -> None:
        """Write a length-prefixed JSON response."""
        data = json.dumps(response).encode("utf-8")
        length_prefix = struct.pack(">I", len(data))
        self.writer.write(length_prefix + data)
        await self.writer.drain()


# Add socket client handler
async def handle_socket_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    """Handle a Unix socket client connection."""
    handler = SocketProtocolHandler(reader, writer)

    try:
        while True:
            request = await handler.read_request()
            if request is None:
                break

            method = request.get("method", "")
            params = request.get("params", {})
            request_id = request.get("id")

            # Route to existing handlers based on method
            try:
                result = await dispatch_socket_method(method, params)
                await handler.write_response({
                    "success": True,
                    "data": result,
                    "id": request_id,
                })
            except Exception as e:
                await handler.write_response({
                    "success": False,
                    "error": str(e),
                    "id": request_id,
                })
    finally:
        writer.close()
        await writer.wait_closed()


async def dispatch_socket_method(method: str, params: dict) -> Any:
    """Dispatch socket method to existing handlers.

    Maps socket methods to existing HTTP endpoint handlers.
    """
    # Map methods to existing handler functions
    method_handlers = {
        "run": lambda p: handle_run_internal(p.get("code", "")),
        "eval": lambda p: handle_run_internal(p.get("code", "")),
        "health": lambda p: {"status": "ok", "connections": len(active_connections)},
        "status": lambda p: get_status(),
        # Add more method mappings as needed
    }

    handler = method_handlers.get(method)
    if handler is None:
        raise ValueError(f"Unknown method: {method}")

    return await handler(params)


# Add socket server startup
async def start_socket_server(session_id: Optional[str] = None) -> asyncio.Server:
    """Start the Unix socket server."""
    socket_path = get_socket_path(session_id)

    # Remove stale socket file
    if socket_path.exists():
        socket_path.unlink()

    server = await asyncio.start_unix_server(
        handle_socket_client,
        path=str(socket_path),
    )

    # Set socket permissions (owner read/write only)
    socket_path.chmod(0o600)

    print(f"Socket server listening on {socket_path}")
    return server


# Modify main() to start both servers
async def main():
    """Start all servers (HTTP, WebSocket, Unix socket)."""
    # Start Unix socket server
    socket_server = await start_socket_server()

    # Start HTTP/WebSocket server (existing code)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, HTTP_PORT)
    await site.start()

    print(f"HTTP server listening on http://{HOST}:{HTTP_PORT}")
    print(f"WebSocket server listening on ws://{HOST}:{WS_PORT}/ws")

    # Keep running
    try:
        await asyncio.Event().wait()
    finally:
        socket_server.close()
        await socket_server.wait_closed()
        await runner.cleanup()
```

### Phase 3: Client Migration

#### 5.3.1 Modify `inspekt/client.py`

Create a new `BridgeClient` class that uses the transport layer:

```python
# Add at top of client.py
from inspekt.transport import get_transport, Request, Response, ConnectionError
from inspekt.transport.factory import get_server_address

class BridgeClient:
    """Client for communicating with the Inspekt bridge server.

    Uses Unix socket transport by default, with TCP fallback on Windows.
    Falls back to HTTP for backwards compatibility if socket fails.
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        transport_type: Optional[str] = None,
        auto_start: bool = True,
        max_retries: int = 50,
        retry_delay: float = 0.1,
    ):
        self.session_id = session_id
        self.transport_type = transport_type
        self.auto_start = auto_start
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._transport = None

    def _get_transport(self):
        """Get or create transport instance."""
        if self._transport is None:
            self._transport = get_transport(
                session_id=self.session_id,
                transport_type=self.transport_type,
                async_mode=False,  # Use sync transport for CLI
            )
        return self._transport

    def _ensure_connected(self) -> None:
        """Ensure connection to server, starting it if needed."""
        transport = self._get_transport()

        if transport.is_connected():
            return

        # Try to connect
        try:
            transport.connect()
            return
        except ConnectionError:
            if not self.auto_start:
                raise

        # Auto-start server
        self._start_server()

        # Retry connection with backoff
        for attempt in range(self.max_retries):
            try:
                transport.connect()
                return
            except ConnectionError:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)

        raise ConnectionError(
            f"Failed to connect to server after {self.max_retries} attempts. "
            f"Server address: {transport.address}"
        )

    def _start_server(self) -> None:
        """Start the inspekt server in background."""
        import subprocess
        import sys

        # Start server as background process
        if sys.platform == "win32":
            # Windows: use CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(
                [sys.executable, "-m", "inspekt", "server", "start", "--daemon"],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            # Unix: use start_new_session
            subprocess.Popen(
                [sys.executable, "-m", "inspekt", "server", "start", "--daemon"],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def run(self, code: str, timeout: float = 30.0) -> dict:
        """Execute JavaScript code in the browser.

        Args:
            code: JavaScript code to execute
            timeout: Maximum time to wait for response

        Returns:
            Execution result dictionary
        """
        self._ensure_connected()

        request = Request(
            method="run",
            params={"code": code},
        )

        response = self._get_transport().send(request, timeout=timeout)

        if not response.success:
            raise RuntimeError(response.error or "Unknown error")

        return response.data

    def health(self) -> dict:
        """Check server health."""
        self._ensure_connected()
        request = Request(method="health", params={})
        response = self._get_transport().send(request, timeout=5.0)
        return response.data

    def close(self) -> None:
        """Close the connection."""
        if self._transport:
            self._transport.disconnect()
            self._transport = None


# Keep existing functions for backwards compatibility
def run_code(code: str, **kwargs) -> dict:
    """Execute JavaScript code (backwards-compatible function)."""
    client = BridgeClient()
    try:
        return client.run(code, **kwargs)
    finally:
        client.close()
```

### Phase 4: MCP Server Migration

#### 5.4.1 Modify `inspekt/app/mcp/server.py`

Update MCP server to use socket transport:

```python
# Replace HTTP client usage with socket transport
from inspekt.client import BridgeClient

# Create shared client instance
_bridge_client: Optional[BridgeClient] = None

def get_bridge_client() -> BridgeClient:
    """Get or create the bridge client."""
    global _bridge_client
    if _bridge_client is None:
        _bridge_client = BridgeClient(auto_start=True)
    return _bridge_client

# Update tool implementations to use client
@server.tool()
async def execute_javascript(code: str) -> str:
    """Execute JavaScript in the browser."""
    client = get_bridge_client()
    result = client.run(code)
    return json.dumps(result)
```

### Phase 5: Configuration Updates

#### 5.5.1 Modify `inspekt/config.py`

Add transport configuration:

```python
@dataclass
class TransportConfig:
    """Transport layer configuration."""

    # Transport type: "auto", "unix", "tcp"
    type: str = "auto"

    # TCP settings (for Windows or explicit TCP mode)
    tcp_host: str = "127.0.0.1"
    tcp_port: Optional[int] = None  # Auto-calculated if None

    # Unix socket settings
    socket_path: Optional[str] = None  # Auto-calculated if None

    # Connection settings
    auto_start: bool = True
    connect_timeout: float = 5.0
    max_retries: int = 50
    retry_delay: float = 0.1


# Add to main Config class
@dataclass
class Config:
    # ... existing fields ...

    # New transport configuration
    transport: TransportConfig = field(default_factory=TransportConfig)
```

---

## 6. File Changes Summary

### New Files
| File | Purpose | Lines (est.) |
|------|---------|--------------|
| `inspekt/transport/__init__.py` | Module exports | 20 |
| `inspekt/transport/base.py` | Abstract base classes | 120 |
| `inspekt/transport/unix_socket.py` | Unix socket implementation | 200 |
| `inspekt/transport/tcp.py` | TCP implementation | 180 |
| `inspekt/transport/factory.py` | Transport factory | 80 |

### Modified Files
| File | Changes | Impact |
|------|---------|--------|
| `inspekt/bridge_ws.py` | Add socket server listener | Medium |
| `inspekt/client.py` | Add `BridgeClient` class, keep backwards compat | Medium |
| `inspekt/config.py` | Add `TransportConfig` | Low |
| `inspekt/app/mcp/server.py` | Use `BridgeClient` | Low |
| `inspekt/app/cli/server.py` | Add socket address output | Low |

### Unchanged Files
| File | Reason |
|------|--------|
| `inspekt/app/api/server.py` | HTTP API stays HTTP |
| `extensions/*` | Browser extension unchanged |
| All CLI command files | Use client.py abstraction |

---

## 7. Testing Strategy

### Unit Tests

Create `tests/unit/test_transport.py`:
```python
import pytest
from inspekt.transport import (
    UnixSocketTransport,
    TCPTransport,
    Request,
    Response,
    get_transport,
)

class TestUnixSocketTransport:
    def test_socket_path_default(self):
        transport = UnixSocketTransport()
        assert "inspekt.sock" in transport.address

    def test_socket_path_with_session(self):
        transport = UnixSocketTransport(session_id="test")
        assert "inspekt-test.sock" in transport.address

    def test_connect_no_server(self):
        transport = UnixSocketTransport(session_id="nonexistent")
        with pytest.raises(ConnectionError):
            transport.connect()

class TestTCPTransport:
    def test_deterministic_port(self):
        t1 = TCPTransport(session_id="test")
        t2 = TCPTransport(session_id="test")
        assert t1._port == t2._port

    def test_different_sessions_different_ports(self):
        t1 = TCPTransport(session_id="session1")
        t2 = TCPTransport(session_id="session2")
        assert t1._port != t2._port

class TestTransportFactory:
    def test_unix_on_macos(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        transport = get_transport(async_mode=False)
        assert "unix://" in transport.address

    def test_tcp_on_windows(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "Windows")
        transport = get_transport(async_mode=False)
        assert "tcp://" in transport.address
```

### Integration Tests

Create `tests/integration/test_socket_server.py`:
```python
import pytest
import asyncio
from inspekt.transport import UnixSocketTransport, Request

@pytest.fixture
async def socket_server():
    """Start test socket server."""
    # Start server, yield, cleanup
    ...

@pytest.mark.integration
async def test_socket_roundtrip(socket_server):
    """Test request/response over Unix socket."""
    transport = UnixSocketTransport()
    await transport.connect()

    response = await transport.send(Request(
        method="health",
        params={},
    ))

    assert response.success
    assert "status" in response.data

    await transport.disconnect()
```

### End-to-End Tests

Create `tests/e2e/test_cli_socket.py`:
```python
import subprocess
import pytest

@pytest.mark.e2e
def test_cli_uses_socket():
    """Test CLI commands work over socket transport."""
    # Start server
    subprocess.run(["inspekt", "server", "start", "--daemon"])

    # Run command
    result = subprocess.run(
        ["inspekt", "health"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "ok" in result.stdout
```

---

## 8. Migration & Backwards Compatibility

### Backwards Compatibility Strategy

1. **Keep HTTP endpoints active**: The HTTP API on port 8767 remains unchanged
2. **Keep `client.py` functions**: Existing `run_code()` etc. functions continue to work
3. **Environment variable override**: `INSPEKT_TRANSPORT=http` forces HTTP transport
4. **Graceful fallback**: If socket fails, fall back to HTTP automatically

### Migration Path

```
Phase 1: Add transport layer (no behavior change)
Phase 2: Add socket server (HTTP still works)
Phase 3: Client defaults to socket (HTTP fallback available)
Phase 4: Document new transport (HTTP still supported)
Phase 5: (Future) Consider deprecating HTTP for CLI
```

### Environment Variables

| Variable | Values | Default | Description |
|----------|--------|---------|-------------|
| `INSPEKT_TRANSPORT` | `auto`, `unix`, `tcp`, `http` | `auto` | Force transport type |
| `INSPEKT_SOCKET_PATH` | path | auto | Override socket path |
| `INSPEKT_TCP_PORT` | number | auto | Override TCP port |
| `INSPEKT_AUTO_START` | `0`, `1` | `1` | Auto-start server |

---

## 9. Rollback Plan

If issues arise, rollback is straightforward:

### Immediate Rollback (No Code Changes)
```bash
# Force HTTP transport via environment variable
export INSPEKT_TRANSPORT=http

# All commands now use HTTP
inspekt eval "document.title"
```

### Code Rollback
1. Revert `client.py` changes (restore HTTP-only client)
2. Remove socket listener from `bridge_ws.py`
3. Transport module can remain (unused)

### Rollback Indicators
- Socket connection failures > 10% of requests
- Performance degradation vs HTTP baseline
- Platform-specific issues (permissions, paths)

---

## 10. Success Criteria

### Functional Requirements
- [ ] CLI commands work over Unix socket on macOS/Linux
- [ ] CLI commands work over TCP on Windows
- [ ] HTTP API unchanged and functional
- [ ] MCP server works with socket transport
- [ ] URL scheme triggers work (via CLI)
- [ ] Auto-start server when CLI runs
- [ ] Graceful fallback to HTTP if socket fails

### Performance Requirements
- [ ] Socket transport ≥ 2x faster than HTTP for local calls
- [ ] Connection establishment < 100ms
- [ ] No regression in HTTP API performance

### Reliability Requirements
- [ ] Reconnection works after server restart
- [ ] Stale socket files cleaned up automatically
- [ ] Multiple sessions can run simultaneously
- [ ] Proper error messages on connection failure

### Testing Requirements
- [ ] Unit test coverage > 90% for transport module
- [ ] Integration tests pass on macOS, Linux, Windows
- [ ] E2E tests verify CLI→socket→browser flow
- [ ] Performance benchmarks documented

---

## Appendix A: Quick Start Commands

After implementation, these commands demonstrate the new functionality:

```bash
# Start server (creates socket automatically)
inspekt server start

# Check socket path
inspekt config get transport.socket_path

# Force TCP transport
INSPEKT_TRANSPORT=tcp inspekt eval "document.title"

# Force HTTP transport (backwards compat)
INSPEKT_TRANSPORT=http inspekt eval "document.title"

# Check server status (shows socket info)
inspekt server status
```

---

## Appendix B: Protocol Specification

### Socket Message Format

```
┌─────────────────┬─────────────────────────────────────┐
│  Length (4B)    │  JSON Payload (variable)            │
│  Big-endian     │  UTF-8 encoded                      │
└─────────────────┴─────────────────────────────────────┘
```

### Request Format
```json
{
  "method": "run",
  "params": {"code": "document.title"},
  "id": "uuid-v4"
}
```

### Response Format
```json
{
  "success": true,
  "data": {"result": "Page Title"},
  "id": "uuid-v4"
}
```

### Error Response
```json
{
  "success": false,
  "error": "Error message",
  "id": "uuid-v4"
}
```

---

## Appendix C: Reference Implementation

This plan draws from webctl's transport implementation:
- `webctl/protocol/transport.py` - Transport abstraction pattern
- `webctl/protocol/client.py` - Client connection handling
- `webctl/daemon/server.py` - Server socket listener pattern
- `webctl/cli/app.py` - Auto-start and retry logic

---

**End of Plan**
