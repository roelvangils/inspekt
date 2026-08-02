"""Integration tests for the bridge HTTP surface.

Runs the real aiohttp app (via bridge_ws.create_app) on an ephemeral port
with aiohttp's test utilities — no subprocess, no fixed ports, safe to run
alongside a live dev bridge.
"""

import asyncio

import pytest
from aiohttp.test_utils import TestClient, TestServer

from inspekt import bridge_ws
from tests.integration.bridge_helpers import FakeExtension, reset_bridge_state

# Re-export the autouse state-reset fixture for this module
_ = reset_bridge_state


@pytest.fixture
async def client(monkeypatch):
    """TestClient over the bridge app on an ephemeral port.

    The WS connect path touches SQLite (domain sync) — stub it for hermeticity.
    """

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


class TestHealth:
    async def test_health_ok_no_browsers(self, client):
        resp = await client.get("/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["ok"] is True
        assert data["browsers"] == []
        assert data["connected_browsers"] == 0
        assert "uptime_seconds" in data
        assert "server_version" in data

    async def test_health_lists_connected_fake_extension(self, client):
        async with FakeExtension(client) as _fake:
            resp = await client.get("/health")
            data = await resp.json()
            assert data["connected_browsers"] == 1
            assert len(data["browsers"]) == 1
            assert data["browsers"][0]["browser_name"]


class TestRun:
    async def test_run_without_browser_returns_503(self, client):
        resp = await client.post("/run", json={"code": "1 + 1"})
        assert resp.status == 503
        data = await resp.json()
        assert data == {"ok": False, "error": "no_browser_connected"}

    async def test_run_with_empty_code_returns_400(self, client):
        resp = await client.post("/run", json={"code": ""})
        assert resp.status == 400
        data = await resp.json()
        assert data["error"] == "missing code"

    async def test_run_unknown_instance_returns_404(self, client):
        async with FakeExtension(client):
            resp = await client.post(
                "/run", json={"code": "1", "instance": "doesnotexist"}
            )
            assert resp.status == 404
            data = await resp.json()
            assert data["error"] == "instance_not_found"


class TestResult:
    async def test_result_without_request_id_returns_400(self, client):
        resp = await client.get("/result")
        assert resp.status == 400
        data = await resp.json()
        assert data["error"] == "missing request_id"

    async def test_result_unknown_request_id_returns_404(self, client):
        resp = await client.get("/result", params={"request_id": "nope"})
        assert resp.status == 404
        data = await resp.json()
        assert data["error"] == "unknown request_id"


class TestQueue:
    async def test_queue_status_and_clear(self, client):
        async with FakeExtension(client, auto_reply=False):
            run = await client.post("/run", json={"code": "1 + 1"})
            assert run.status == 200

            status = await client.get("/queue/status")
            data = await status.json()
            assert data["pending_count"] == 1

            cleared = await client.post("/queue/clear", json={})
            cleared_data = await cleared.json()
            assert cleared_data["cleared"] == 1

            status2 = await client.get("/queue/status")
            assert (await status2.json())["pending_count"] == 0


class TestCORS:
    async def test_options_preflight_has_cors_headers(self, client):
        resp = await client.options("/run")
        assert resp.status == 200
        assert "Access-Control-Allow-Origin" in resp.headers
        assert "POST" in resp.headers.get("Access-Control-Allow-Methods", "")


class TestRoundTrip:
    async def test_execute_round_trip_via_fake_extension(self, client):
        """The core correlation path: /run -> WS execute -> result -> /result."""
        async with FakeExtension(client, result_value=42) as fake:
            run = await client.post("/run", json={"code": "6 * 7"})
            assert run.status == 200
            request_id = (await run.json())["request_id"]

            result = await client.get(
                "/result", params={"request_id": request_id}
            )
            data = await result.json()
            assert data["ok"] is True
            assert data["result"] == 42

            # The fake actually received the execute message with our code
            assert fake.received_codes == ["6 * 7"]

    async def test_disconnect_wakes_pending_result_waiter(self, client):
        """Closing the browser WS must cancel its pending requests instead of
        letting /result long-poll hang for minutes."""
        fake = FakeExtension(client, auto_reply=False)
        await fake.connect()

        run = await client.post("/run", json={"code": "1 + 1"})
        request_id = (await run.json())["request_id"]

        async def poll():
            resp = await client.get("/result", params={"request_id": request_id})
            return await resp.json()

        poll_task = asyncio.create_task(poll())
        await asyncio.sleep(0.1)  # let the long-poll register its waiter

        await fake.close()

        data = await asyncio.wait_for(poll_task, timeout=5)
        assert data["ok"] is False
