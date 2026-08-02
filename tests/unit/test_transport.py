"""Unit tests for the transport layer.

Tests cover:
- Socket path generation (Unix sockets)
- Deterministic TCP port calculation
- Platform detection and transport auto-selection
- Request/Response dataclasses
- Transport factory functions
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from inspekt.transport import (
    ConnectionError,
    Request,
    Response,
    TimeoutError,
    TransportError,
)
from inspekt.transport.base import SyncTransport, Transport
from inspekt.transport.factory import (
    get_default_transport,
    get_server_address,
    get_transport,
    is_server_available,
)
from inspekt.transport.tcp import SyncTCPTransport, TCPTransport, get_tcp_port
from inspekt.transport.unix_socket import (
    SyncUnixSocketTransport,
    UnixSocketTransport,
    get_socket_path,
)


class TestRequest:
    """Test Request dataclass."""

    def test_request_with_all_fields(self):
        """Test creating a request with all fields."""
        req = Request(
            method="run",
            params={"code": "document.title"},
            request_id="test-123",
        )
        assert req.method == "run"
        assert req.params == {"code": "document.title"}
        assert req.request_id == "test-123"

    def test_request_with_defaults(self):
        """Test request with default values."""
        req = Request(method="ping")
        assert req.method == "ping"
        assert req.params == {}
        # request_id is auto-generated as UUID when not provided
        assert req.request_id is not None
        # Verify it looks like a UUID
        assert len(req.request_id) == 36
        assert req.request_id.count("-") == 4

    def test_request_method_required(self):
        """Test that method is required."""
        with pytest.raises(TypeError):
            Request()  # method is required


class TestResponse:
    """Test Response dataclass."""

    def test_successful_response(self):
        """Test creating a successful response."""
        resp = Response(
            success=True,
            data={"result": "Example Page"},
            request_id="test-123",
        )
        assert resp.success is True
        assert resp.data == {"result": "Example Page"}
        assert resp.error is None
        assert resp.request_id == "test-123"

    def test_error_response(self):
        """Test creating an error response."""
        resp = Response(
            success=False,
            error="ReferenceError: foo is not defined",
            request_id="test-123",
        )
        assert resp.success is False
        assert resp.error == "ReferenceError: foo is not defined"
        assert resp.data is None

    def test_response_defaults(self):
        """Test response with default values."""
        resp = Response(success=True)
        assert resp.success is True
        assert resp.data is None
        assert resp.error is None
        assert resp.request_id is None


class TestTransportExceptions:
    """Test transport exception classes."""

    def test_transport_error_hierarchy(self):
        """Test that exceptions inherit from TransportError."""
        assert issubclass(ConnectionError, TransportError)
        assert issubclass(TimeoutError, TransportError)

    def test_connection_error_message(self):
        """Test ConnectionError with message."""
        with pytest.raises(ConnectionError, match="Connection refused"):
            raise ConnectionError("Connection refused")

    def test_timeout_error_message(self):
        """Test TimeoutError with message."""
        with pytest.raises(TimeoutError, match="timed out after 30s"):
            raise TimeoutError("Request timed out after 30s")


class TestSocketPathGeneration:
    """Test Unix socket path generation."""

    def test_default_socket_path(self):
        """Test default socket path is in ~/.inspekt/."""
        with patch.dict(os.environ, {}, clear=True):
            # Clear XDG_RUNTIME_DIR and INSPEKT_SOCKET_PATH
            os.environ.pop("XDG_RUNTIME_DIR", None)
            os.environ.pop("INSPEKT_SOCKET_PATH", None)
            path = get_socket_path()
            expected = Path.home() / ".inspekt" / "inspekt.sock"
            assert path == expected

    def test_socket_path_with_session_id(self):
        """Test socket path includes session ID."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("XDG_RUNTIME_DIR", None)
            os.environ.pop("INSPEKT_SOCKET_PATH", None)
            path = get_socket_path(session_id="my-session")
            expected = Path.home() / ".inspekt" / "inspekt-my-session.sock"
            assert path == expected

    def test_socket_path_with_xdg_runtime_dir(self, tmp_path):
        """Test socket path uses XDG_RUNTIME_DIR when available."""
        # Use tmp_path as XDG_RUNTIME_DIR to avoid permission issues
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir()

        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime_dir)}, clear=True):
            os.environ.pop("INSPEKT_SOCKET_PATH", None)
            path = get_socket_path()
            expected = runtime_dir / "inspekt" / "inspekt.sock"
            assert path == expected

    def test_socket_path_env_override(self):
        """Test INSPEKT_SOCKET_PATH environment variable override."""
        with patch.dict(
            os.environ,
            {"INSPEKT_SOCKET_PATH": "/tmp/custom.sock"},
            clear=True,
        ):
            path = get_socket_path()
            assert path == Path("/tmp/custom.sock")

    def test_socket_path_env_override_takes_precedence(self):
        """Test that env override takes precedence over XDG_RUNTIME_DIR."""
        with patch.dict(
            os.environ,
            {
                "XDG_RUNTIME_DIR": "/run/user/1000",
                "INSPEKT_SOCKET_PATH": "/tmp/override.sock",
            },
            clear=True,
        ):
            path = get_socket_path()
            assert path == Path("/tmp/override.sock")


class TestTCPPortCalculation:
    """Test deterministic TCP port calculation."""

    def test_default_port(self):
        """Test port for default session."""
        port = get_tcp_port()
        assert 49152 <= port <= 65534

    def test_port_deterministic(self):
        """Test that same session ID produces same port."""
        port1 = get_tcp_port("test-session")
        port2 = get_tcp_port("test-session")
        assert port1 == port2

    def test_different_sessions_different_ports(self):
        """Test that different sessions produce different ports."""
        port1 = get_tcp_port("session-a")
        port2 = get_tcp_port("session-b")
        # While collision is possible, it's extremely unlikely for these inputs
        assert port1 != port2

    def test_port_in_dynamic_range(self):
        """Test that ports are in the IANA dynamic port range."""
        # Test several session IDs
        test_sessions = [None, "default", "test", "prod", "1234567890"]
        for session in test_sessions:
            port = get_tcp_port(session)
            assert (
                49152 <= port <= 65534
            ), f"Port {port} for session '{session}' outside range"

    def test_port_with_none_uses_default(self):
        """Test that None session uses 'default' internally."""
        port_none = get_tcp_port(None)
        port_default = get_tcp_port("default")
        assert port_none == port_default


class TestTransportFactory:
    """Test transport factory functions."""

    def test_get_transport_auto_unix_on_macos(self):
        """Test auto-selection picks Unix on macOS."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("INSPEKT_TRANSPORT", None)
            with patch("platform.system", return_value="Darwin"):
                transport = get_transport(transport_type="auto", async_mode=True)
                assert isinstance(transport, UnixSocketTransport)

    def test_get_transport_auto_unix_on_linux(self):
        """Test auto-selection picks Unix on Linux."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("INSPEKT_TRANSPORT", None)
            with patch("platform.system", return_value="Linux"):
                transport = get_transport(transport_type="auto", async_mode=True)
                assert isinstance(transport, UnixSocketTransport)

    def test_get_transport_auto_tcp_on_windows(self):
        """Test auto-selection picks TCP on Windows."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("INSPEKT_TRANSPORT", None)
            with patch("platform.system", return_value="Windows"):
                transport = get_transport(transport_type="auto", async_mode=True)
                assert isinstance(transport, TCPTransport)

    def test_get_transport_explicit_unix(self):
        """Test explicit Unix transport request."""
        transport = get_transport(transport_type="unix", async_mode=True)
        assert isinstance(transport, UnixSocketTransport)

    def test_get_transport_explicit_tcp(self):
        """Test explicit TCP transport request."""
        transport = get_transport(transport_type="tcp", async_mode=True)
        assert isinstance(transport, TCPTransport)

    def test_get_transport_sync_mode(self):
        """Test getting synchronous transports."""
        unix_sync = get_transport(transport_type="unix", async_mode=False)
        assert isinstance(unix_sync, SyncUnixSocketTransport)

        tcp_sync = get_transport(transport_type="tcp", async_mode=False)
        assert isinstance(tcp_sync, SyncTCPTransport)

    def test_get_transport_invalid_type(self):
        """Test invalid transport type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown transport type"):
            get_transport(transport_type="invalid")

    def test_get_transport_env_override(self):
        """Test INSPEKT_TRANSPORT environment override."""
        with patch.dict(os.environ, {"INSPEKT_TRANSPORT": "tcp"}, clear=True):
            with patch("platform.system", return_value="Darwin"):
                # Even though Darwin would normally use Unix, env forces TCP
                transport = get_transport(transport_type=None, async_mode=True)
                assert isinstance(transport, TCPTransport)


class TestGetServerAddress:
    """Test get_server_address function."""

    def test_unix_address_format(self):
        """Test Unix socket address format."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("XDG_RUNTIME_DIR", None)
            os.environ.pop("INSPEKT_SOCKET_PATH", None)
            os.environ.pop("INSPEKT_TRANSPORT", None)
            address = get_server_address(transport_type="unix")
            assert address.startswith("unix://")
            assert "inspekt.sock" in address

    def test_tcp_address_format(self):
        """Test TCP address format."""
        address = get_server_address(transport_type="tcp")
        assert address.startswith("tcp://127.0.0.1:")
        # Port should be in dynamic range
        port = int(address.split(":")[-1])
        assert 49152 <= port <= 65534

    def test_address_includes_session_id(self):
        """Test that session ID affects the address."""
        addr1 = get_server_address(session_id="session-a", transport_type="tcp")
        addr2 = get_server_address(session_id="session-b", transport_type="tcp")
        assert addr1 != addr2


class TestIsServerAvailable:
    """Test is_server_available function."""

    def test_unix_available_when_socket_exists(self, tmp_path):
        """Test Unix availability check with existing socket."""
        socket_file = tmp_path / "test.sock"
        socket_file.touch()

        with patch.dict(
            os.environ, {"INSPEKT_SOCKET_PATH": str(socket_file)}, clear=True
        ):
            result = is_server_available(transport_type="unix")
            assert result is True

    def test_unix_unavailable_when_socket_missing(self, tmp_path):
        """Test Unix availability check with missing socket."""
        socket_file = tmp_path / "nonexistent.sock"

        with patch.dict(
            os.environ, {"INSPEKT_SOCKET_PATH": str(socket_file)}, clear=True
        ):
            result = is_server_available(transport_type="unix")
            assert result is False


class TestUnixSocketTransport:
    """Test UnixSocketTransport class."""

    def test_address_property(self, tmp_path):
        """Test address property format."""
        socket_path = tmp_path / "test.sock"
        transport = UnixSocketTransport(socket_path=socket_path)
        assert transport.address == f"unix://{socket_path}"

    def test_socket_path_property(self, tmp_path):
        """Test socket_path property."""
        socket_path = tmp_path / "test.sock"
        transport = UnixSocketTransport(socket_path=socket_path)
        assert transport.socket_path == socket_path

    def test_not_connected_by_default(self, tmp_path):
        """Test transport starts disconnected."""
        socket_path = tmp_path / "test.sock"
        transport = UnixSocketTransport(socket_path=socket_path)
        assert transport.is_connected() is False


class TestTCPTransport:
    """Test TCPTransport class."""

    def test_address_property(self):
        """Test address property format."""
        transport = TCPTransport(host="127.0.0.1", port=12345)
        assert transport.address == "tcp://127.0.0.1:12345"

    def test_host_and_port_properties(self):
        """Test host and port properties."""
        transport = TCPTransport(host="localhost", port=8080)
        assert transport.host == "localhost"
        assert transport.port == 8080

    def test_port_from_session_id(self):
        """Test port calculation from session ID."""
        transport = TCPTransport(session_id="test-session")
        expected_port = get_tcp_port("test-session")
        assert transport.port == expected_port

    def test_not_connected_by_default(self):
        """Test transport starts disconnected."""
        transport = TCPTransport()
        assert transport.is_connected() is False


class TestSyncTransports:
    """Test synchronous transport implementations."""

    def test_sync_unix_address_property(self, tmp_path):
        """Test SyncUnixSocketTransport address property."""
        socket_path = tmp_path / "test.sock"
        transport = SyncUnixSocketTransport(socket_path=socket_path)
        assert transport.address == f"unix://{socket_path}"

    def test_sync_tcp_address_property(self):
        """Test SyncTCPTransport address property."""
        transport = SyncTCPTransport(host="127.0.0.1", port=54321)
        assert transport.address == "tcp://127.0.0.1:54321"

    def test_sync_transports_not_connected_by_default(self, tmp_path):
        """Test sync transports start disconnected."""
        socket_path = tmp_path / "test.sock"
        unix_transport = SyncUnixSocketTransport(socket_path=socket_path)
        tcp_transport = SyncTCPTransport()

        assert unix_transport.is_connected() is False
        assert tcp_transport.is_connected() is False


class TestGetDefaultTransport:
    """Test get_default_transport convenience function."""

    def test_returns_async_transport_by_default(self):
        """Test default returns async transport."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("INSPEKT_TRANSPORT", None)
            transport = get_default_transport(async_mode=True)
            assert isinstance(transport, Transport)

    def test_returns_sync_transport_when_requested(self):
        """Test returns sync transport when async_mode=False."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("INSPEKT_TRANSPORT", None)
            transport = get_default_transport(async_mode=False)
            assert isinstance(transport, SyncTransport)
