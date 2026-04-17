"""Transport layer for Inspekt client-server communication.

This module provides transport abstractions for communication between
the Inspekt CLI/MCP server and the bridge server. It supports:

- Unix domain sockets (default on macOS/Linux) for best performance
- TCP sockets (default on Windows) as fallback
- Auto-selection based on platform

Example usage:

    # Synchronous (for CLI commands)
    from inspekt.transport import get_transport, Request

    transport = get_transport(async_mode=False)
    transport.connect()
    response = transport.send(Request(method="health", params={}))
    transport.disconnect()

    # Asynchronous (for async contexts)
    async with get_transport(async_mode=True) as transport:
        response = await transport.send(Request(method="run", params={"code": "…"}))
"""

from .base import (
    ConnectionError,
    Request,
    Response,
    SyncTransport,
    TimeoutError,
    Transport,
    TransportError,
)
from .factory import (
    get_default_transport,
    get_server_address,
    get_transport,
    is_server_available,
)
from .tcp import SyncTCPTransport, TCPTransport, get_tcp_port
from .unix_socket import (
    SyncUnixSocketTransport,
    UnixSocketTransport,
    get_socket_path,
)

__all__ = [
    # Base classes and types
    "Transport",
    "SyncTransport",
    "Request",
    "Response",
    "TransportError",
    "ConnectionError",
    "TimeoutError",
    # Unix socket transport
    "UnixSocketTransport",
    "SyncUnixSocketTransport",
    "get_socket_path",
    # TCP transport
    "TCPTransport",
    "SyncTCPTransport",
    "get_tcp_port",
    # Factory functions
    "get_transport",
    "get_default_transport",
    "get_server_address",
    "is_server_available",
]
