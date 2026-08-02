"""Abstract base class for transport implementations.

This module defines the transport layer abstraction for Inspekt's
client-server communication, supporting both async and sync interfaces.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


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
    """A request to send to the server.

    Attributes:
        method: The method/endpoint to call (e.g., "run", "health")
        params: Dictionary of parameters for the method
        request_id: Optional unique identifier for request tracking
    """

    method: str
    params: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None

    def __post_init__(self) -> None:
        """Generate request_id if not provided."""
        if self.request_id is None:
            self.request_id = str(uuid.uuid4())


@dataclass
class Response:
    """A response from the server.

    Attributes:
        success: Whether the request succeeded
        data: The response data (if successful)
        error: Error message (if failed)
        request_id: The request ID this response is for
    """

    success: bool
    data: Any = None
    error: str | None = None
    request_id: str | None = None


class Transport(ABC):
    """Abstract base class for async client-server transport.

    Implementations handle the actual communication mechanism
    (Unix socket, TCP, HTTP) while providing a unified interface.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the server.

        Raises:
            ConnectionError: If connection fails
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection."""
        pass

    @abstractmethod
    async def send(self, request: Request, timeout: float = 30.0) -> Response:
        """Send a request and wait for response.

        Args:
            request: The request to send
            timeout: Maximum time to wait for response in seconds

        Returns:
            Response from the server

        Raises:
            ConnectionError: If not connected or connection lost
            TimeoutError: If request times out
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if currently connected to the server."""
        pass

    @property
    @abstractmethod
    def address(self) -> str:
        """Return the server address (for logging/debugging)."""
        pass

    async def __aenter__(self) -> "Transport":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.disconnect()


class SyncTransport(ABC):
    """Synchronous transport interface for non-async contexts.

    Used by CLI commands that run synchronously.
    """

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the server.

        Raises:
            ConnectionError: If connection fails
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection."""
        pass

    @abstractmethod
    def send(self, request: Request, timeout: float = 30.0) -> Response:
        """Send a request and wait for response.

        Args:
            request: The request to send
            timeout: Maximum time to wait for response in seconds

        Returns:
            Response from the server

        Raises:
            ConnectionError: If not connected or connection lost
            TimeoutError: If request times out
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if currently connected to the server."""
        pass

    @property
    @abstractmethod
    def address(self) -> str:
        """Return the server address (for logging/debugging)."""
        pass

    def __enter__(self) -> "SyncTransport":
        """Sync context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Sync context manager exit."""
        self.disconnect()
