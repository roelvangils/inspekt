"""Transport factory for automatic transport selection.

This module provides factory functions for creating the appropriate
transport based on platform and configuration.
"""

import os
import platform

from .base import SyncTransport, Transport
from .tcp import SyncTCPTransport, TCPTransport, get_tcp_port
from .unix_socket import (
    SyncUnixSocketTransport,
    UnixSocketTransport,
    get_socket_path,
)


def get_transport(
    session_id: str | None = None,
    transport_type: str | None = None,
    async_mode: bool = True,
) -> Transport | SyncTransport:
    """Get the appropriate transport for the current platform.

    Auto-selects Unix socket on macOS/Linux and TCP on Windows,
    unless explicitly overridden.

    Args:
        session_id: Optional session identifier for multi-instance support
        transport_type: Force a specific transport ("unix", "tcp", "auto")
        async_mode: Return async or sync transport

    Returns:
        Appropriate Transport or SyncTransport instance

    Raises:
        ValueError: If transport_type is not recognized
    """
    # Check environment variable override
    if transport_type is None:
        transport_type = os.environ.get("INSPEKT_TRANSPORT", "auto")

    # Auto-select based on platform
    if transport_type == "auto":
        if platform.system() == "Windows":
            transport_type = "tcp"
        else:
            transport_type = "unix"

    # Create the appropriate transport
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


def get_default_transport(async_mode: bool = True) -> Transport | SyncTransport:
    """Get the default transport for the current platform.

    Convenience function that calls get_transport with default settings.

    Args:
        async_mode: Return async or sync transport

    Returns:
        Default Transport or SyncTransport for this platform
    """
    return get_transport(session_id=None, transport_type="auto", async_mode=async_mode)


def get_server_address(
    session_id: str | None = None,
    transport_type: str | None = None,
) -> str:
    """Get the server address string for a given configuration.

    Useful for logging and debugging without creating a transport.

    Args:
        session_id: Optional session identifier
        transport_type: Transport type ("unix", "tcp", "auto")

    Returns:
        Address string like "unix:///path/to/socket" or "tcp://127.0.0.1:49152"
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


def is_server_available(
    session_id: str | None = None,
    transport_type: str | None = None,
) -> bool:
    """Check if the server is potentially available.

    For Unix sockets, checks if the socket file exists.
    For TCP, attempts a quick connection test.

    This is a lightweight check - the server might still be
    unresponsive even if this returns True.

    Args:
        session_id: Optional session identifier
        transport_type: Transport type ("unix", "tcp", "auto")

    Returns:
        True if server appears to be available
    """
    if transport_type is None:
        transport_type = os.environ.get("INSPEKT_TRANSPORT", "auto")

    if transport_type == "auto":
        if platform.system() == "Windows":
            transport_type = "tcp"
        else:
            transport_type = "unix"

    if transport_type == "unix":
        socket_path = get_socket_path(session_id)
        return socket_path.exists()
    elif transport_type == "tcp":
        import socket

        port = get_tcp_port(session_id)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            return result == 0
        except Exception:
            return False

    return False
