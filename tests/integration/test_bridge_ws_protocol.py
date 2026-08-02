"""Integration tests for the bridge's WS command protocol and unix socket.

Covers the requestId-correlated command pattern shared by ~15 endpoints
(via /domains/list as the representative) and the length-prefixed JSON
framing of the unix socket transport.
"""

import pytest
from aiohttp.test_utils import TestClient, TestServer

from inspekt import bridge_ws
from inspekt.transport.base import Request
from inspekt.transport.unix_socket import UnixSocketTransport
from tests.integration.bridge_helpers import FakeExtension, reset_bridge_state

_ = reset_bridge_state


@pytest.fixture
async def client(monkeypatch):
    async def _noop(ws):
        return None

    monkeypatch.setattr(bridge_ws, "sync_domains_to_browser", _noop)
    monkeypatch.setattr(bridge_ws, "enable_permanent_bypass_if_isolated", _noop)

    app = bridge_ws.create_app()
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    yield client
    await client.close()


class TestCommandProtocol:
    """The requestId round-trip used by /domains/*, /csp/*, /console/* etc."""

    async def test_domains_list_round_trip(self, client):
        response_payload = {"ok": True, "domains": ["example.test"]}
        async with FakeExtension(client, command_response=response_payload):
            resp = await client.get("/domains/list")
            assert resp.status == 200
            data = await resp.json()
            assert data.get("domains") == ["example.test"]

    async def test_domains_list_without_browser_returns_503(self, client):
        resp = await client.get("/domains/list")
        assert resp.status == 503


class TestUnixSocket:
    """start_socket_server + UnixSocketTransport parity with the HTTP API.

    Uses an explicit tmp_path socket so a live dev bridge's socket at the
    default location is never touched.
    """

    @pytest.fixture
    async def transport(self):
        # Not pytest's tmp_path: its nested directories push the socket path
        # past macOS's 104-char AF_UNIX limit. A plain TemporaryDirectory
        # under the system tempdir stays short enough.
        import tempfile
        from pathlib import Path

        tmpdir = tempfile.TemporaryDirectory(prefix="inspekt-sock-")
        path = Path(tmpdir.name) / "t.sock"
        server = await bridge_ws.start_socket_server(path)
        assert server is not None
        transport = UnixSocketTransport(path)
        await transport.connect()
        yield transport
        await transport.disconnect()
        server.close()
        await server.wait_closed()
        tmpdir.cleanup()

    async def test_health_over_socket(self, transport):
        response = await transport.send(Request(method="health", params={}))
        assert response.success is True
        assert response.data  # health payload present

    async def test_run_without_browser_over_socket(self, transport):
        response = await transport.send(Request(method="run", params={"code": "1 + 1"}))
        payload = response.data or {}
        assert response.success is False or payload.get("ok") is False

    async def test_unknown_method_over_socket(self, transport):
        response = await transport.send(Request(method="definitely_not_a_method", params={}))
        assert response.success is False or response.error
