"""Shared helpers for bridge integration tests: fake extension + state reset."""

import asyncio
import contextlib

import aiohttp
import pytest

from inspekt import bridge_ws
from inspekt.domain.models import BrowserInfoMessage


@pytest.fixture(autouse=True)
def reset_bridge_state():
    """Clear bridge_ws module-level state around each test (see unit tests)."""

    def _clear():
        bridge_ws.active_connections.clear()
        bridge_ws.browser_info.clear()
        bridge_ws.pending_requests.clear()
        bridge_ws.completed_requests.clear()
        bridge_ws.pending_events.clear()
        bridge_ws.ack_events.clear()
        bridge_ws.instance_ids.clear()
        bridge_ws.instance_aliases.clear()
        bridge_ws.instance_id_to_ws.clear()
        bridge_ws.connection_times.clear()
        bridge_ws.set_active_connection(None)

    _clear()
    yield
    _clear()


class FakeExtension:
    """Minimal stand-in for the browser extension over the /ws endpoint.

    Connects, announces itself with a valid browser_info (satisfying
    is_valid_browser_info: UA > 10 chars + extensionVersion, and built from
    the pydantic model so extra=forbid can't reject it), then echoes:
    - "execute" messages   -> {"type": "result", "request_id": ..., "ok": true}
    - command messages     -> {"type": "response", "requestId": ..., "response": ...}
    """

    def __init__(self, client, auto_reply=True, result_value="fake-result",
                 command_response=None):
        self._client = client
        self.auto_reply = auto_reply
        self.result_value = result_value
        self.command_response = command_response or {"ok": True}
        self.received_codes = []
        self._ws = None
        self._reader_task = None

    async def connect(self):
        self._ws = await self._client.ws_connect("/ws")
        info = BrowserInfoMessage(
            userAgent="Mozilla/5.0 (Macintosh) FakeChrome/120.0 TestExtension",
            browserName="FakeChrome",
            url="https://example.test/page",
            title="Fake Page",
            extensionVersion="1.0.0",
            visible=True,
        )
        await self._ws.send_json(info.model_dump())
        # Give the server a beat to register browser_info before tests assert
        await asyncio.sleep(0.05)
        self._reader_task = asyncio.create_task(self._read_loop())
        return self

    async def _read_loop(self):
        async for msg in self._ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                break
            data = msg.json()
            msg_type = data.get("type")
            if msg_type == "execute":
                self.received_codes.append(data.get("code"))
                if self.auto_reply:
                    await self._ws.send_json({
                        "type": "result",
                        "request_id": data["request_id"],
                        "ok": True,
                        "result": self.result_value,
                        "url": "https://example.test/page",
                        "title": "Fake Page",
                    })
            elif msg_type == "pong":
                pass
            elif "requestId" in data and self.auto_reply:
                await self._ws.send_json({
                    "type": "response",
                    "requestId": data["requestId"],
                    "response": self.command_response,
                })

    async def close(self):
        if self._reader_task:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        # Let the server's finally-block run its disconnect cleanup
        await asyncio.sleep(0.05)

    async def __aenter__(self):
        return await self.connect()

    async def __aexit__(self, *exc):
        await self.close()
