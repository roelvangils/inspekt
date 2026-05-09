#!/usr/bin/env python3
"""
Overlay Bus WebSocket server for Inspekt Browser VM.

Mediates between in-Chromium content-script producers and host-browser
control-panel consumers. Per-session pubsub fanout with a small in-memory
snapshot cache so late-joining consumers can rehydrate.

Endpoint:
    ws://VNC_HOST:8890/overlay/ws?role=producer&session=<tabTargetId>:<frameId>
    ws://VNC_HOST:8890/overlay/ws?role=consumer

Protocol: see plan at docs/development/overlay-bus.md (TBD) — JSON frames
with top-level v: 1, types overlay.{set,update,clear,batch,event,session.*,
snapshot}.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

from websockets.exceptions import ConnectionClosed
from websockets.server import serve

PORT = 8890
PROTOCOL_VERSION = 1
IDLE_SESSION_TIMEOUT = 5 * 60  # seconds; producer with no traffic gets GC'd
ALLOWED_CONSUMER_ORIGINS = {
    # noVNC web UI is the only legitimate consumer host. The control panel runs
    # at /control.html on this same origin. Browsers send Origin on WS upgrade.
    "http://localhost:6080",
    "http://127.0.0.1:6080",
    "http://inspekt:6080",
}
# Explicit override (e.g. for desktop app file:// origins or LAN dev).
_extra = os.environ.get("INSPEKT_OVERLAY_EXTRA_ORIGINS", "").strip()
if _extra:
    ALLOWED_CONSUMER_ORIGINS.update(o.strip() for o in _extra.split(",") if o.strip())

logger = logging.getLogger("overlay-bus")
logging.basicConfig(level=logging.INFO, format="[overlay-bus] %(message)s")


class Session:
    """Per-(tab,frame) registry of live overlays + connected producer."""

    __slots__ = ("session_id", "producer", "entries", "last_seen", "started_at")

    def __init__(self, session_id: str, producer: Any) -> None:
        self.session_id = session_id
        self.producer = producer
        self.entries: dict[str, dict] = {}  # id -> {kind, rect, payload, opts}
        self.last_seen = time.monotonic()
        self.started_at = time.time()

    def apply_op(self, op: dict) -> None:
        """Apply one set/update/clear op against the in-memory snapshot."""
        op_type = op.get("type")
        oid = op.get("id")
        if not isinstance(oid, str):
            return
        if op_type == "overlay.set":
            self.entries[oid] = {
                "id": oid,
                "kind": op.get("kind", "unknown"),
                "rect": op.get("rect") or {},
                "payload": op.get("payload") or {},
                "opts": op.get("opts") or {},
            }
        elif op_type == "overlay.update":
            existing = self.entries.get(oid)
            if existing is None:
                return
            if "rect" in op:
                existing["rect"] = op["rect"]
            if "payload" in op:
                existing["payload"] = {**existing.get("payload", {}), **(op["payload"] or {})}
            if "opts" in op:
                existing["opts"] = {**existing.get("opts", {}), **(op["opts"] or {})}
        elif op_type == "overlay.clear":
            self.entries.pop(oid, None)

    def snapshot_message(self) -> dict:
        return {
            "v": PROTOCOL_VERSION,
            "type": "overlay.snapshot",
            "sessionId": self.session_id,
            "entries": list(self.entries.values()),
        }


class Hub:
    """Central registry of sessions, producers, and consumers."""

    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.consumers: set[Any] = set()
        self._lock = asyncio.Lock()

    async def register_producer(self, session_id: str, ws: Any) -> Session:
        async with self._lock:
            existing = self.sessions.get(session_id)
            if existing is not None:
                # Producer reconnect — drop the old socket, keep no stale entries.
                # Producer pushes a fresh snapshot after reconnect anyway.
                existing.entries.clear()
                existing.producer = ws
                existing.last_seen = time.monotonic()
                session = existing
            else:
                session = Session(session_id, ws)
                self.sessions[session_id] = session
        # Broadcast outside the lock — _broadcast_consumers re-acquires it.
        await self._broadcast_consumers({
            "v": PROTOCOL_VERSION,
            "type": "overlay.session.start",
            "sessionId": session_id,
        })
        return session

    async def unregister_producer(self, session_id: str, ws: Any, reason: str) -> None:
        # Only tear down if the registered producer is still our socket. Without
        # this check, a fast reconnect (new producer claims the same session_id
        # before the old socket's finally clause runs) gets wiped by the stale
        # teardown.
        async with self._lock:
            session = self.sessions.get(session_id)
            if session is None or session.producer is not ws:
                return
            del self.sessions[session_id]
        await self._broadcast_consumers({
            "v": PROTOCOL_VERSION,
            "type": "overlay.session.end",
            "sessionId": session_id,
            "reason": reason,
        })

    async def register_consumer(self, ws: Any) -> None:
        snapshots: list[dict] = []
        async with self._lock:
            self.consumers.add(ws)
            for session in self.sessions.values():
                snapshots.append(session.snapshot_message())
        for msg in snapshots:
            try:
                await ws.send(json.dumps(msg))
            except ConnectionClosed:
                return

    async def unregister_consumer(self, ws: Any) -> None:
        async with self._lock:
            self.consumers.discard(ws)

    async def fanout_to_consumers(self, msg: dict) -> None:
        await self._broadcast_consumers(msg)

    async def _broadcast_consumers(self, msg: dict) -> None:
        # Snapshot consumers under lock, then send outside it so a slow
        # consumer doesn't block other producers.
        async with self._lock:
            consumers = list(self.consumers)
        if not consumers:
            return
        text = json.dumps(msg)
        for ws in consumers:
            try:
                await ws.send(text)
            except ConnectionClosed:
                continue
            except Exception as exc:  # pragma: no cover
                logger.warning("consumer send failed: %s", exc)

    async def send_to_producer(self, session_id: str, msg: dict) -> None:
        async with self._lock:
            session = self.sessions.get(session_id)
            ws = session.producer if session else None
        if ws is None:
            return
        try:
            await ws.send(json.dumps(msg))
        except ConnectionClosed:
            return

    async def gc_idle(self) -> None:
        """Drop sessions whose producer has been silent past the timeout."""
        now = time.monotonic()
        stale: list[tuple[str, Any]] = []
        async with self._lock:
            for sid, session in self.sessions.items():
                if now - session.last_seen > IDLE_SESSION_TIMEOUT:
                    stale.append((sid, session.producer))
        for sid, ws in stale:
            await self.unregister_producer(sid, ws, reason="timeout")


HUB = Hub()


def _parse_query(path: str) -> dict[str, str]:
    if "?" not in path:
        return {}
    qs = path.split("?", 1)[1]
    parsed = parse_qs(qs)
    return {k: v[0] for k, v in parsed.items() if v}


def _request_path(websocket: Any) -> str:
    request = getattr(websocket, "request", None)
    if request is not None and hasattr(request, "path"):
        return request.path or ""
    # Older websockets versions expose .path directly.
    return getattr(websocket, "path", "") or ""


def _origin_header(websocket: Any) -> str | None:
    request = getattr(websocket, "request", None)
    headers = getattr(request, "headers", None) if request is not None else None
    if headers is None:
        headers = getattr(websocket, "request_headers", None)
    if headers is None:
        return None
    try:
        return headers.get("Origin")
    except Exception:
        return None


async def _handle_producer(websocket: Any, session_id: str) -> None:
    session = await HUB.register_producer(session_id, websocket)
    logger.info("producer connected: session=%s", session_id)
    try:
        async for raw in websocket:
            session.last_seen = time.monotonic()
            try:
                msg = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if not isinstance(msg, dict):
                continue
            mtype = msg.get("type")
            # Apply state mutations to the snapshot.
            if mtype in ("overlay.set", "overlay.update", "overlay.clear"):
                session.apply_op(msg)
                msg.setdefault("sessionId", session_id)
                msg.setdefault("v", PROTOCOL_VERSION)
                await HUB.fanout_to_consumers(msg)
            elif mtype == "overlay.batch":
                ops = msg.get("ops") or []
                for op in ops:
                    if isinstance(op, dict):
                        op.setdefault("sessionId", session_id)
                        session.apply_op(op)
                msg.setdefault("sessionId", session_id)
                msg.setdefault("v", PROTOCOL_VERSION)
                await HUB.fanout_to_consumers(msg)
            elif mtype == "overlay.snapshot":
                # Producer pushed a full replacement snapshot (e.g. on reconnect).
                entries = msg.get("entries") or []
                session.entries.clear()
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    eid = entry.get("id")
                    if isinstance(eid, str):
                        session.entries[eid] = entry
                msg.setdefault("sessionId", session_id)
                msg.setdefault("v", PROTOCOL_VERSION)
                await HUB.fanout_to_consumers(msg)
            else:
                # Unknown / ignored types pass through to consumers untouched
                # so future protocol additions don't require server changes.
                msg.setdefault("sessionId", session_id)
                msg.setdefault("v", PROTOCOL_VERSION)
                await HUB.fanout_to_consumers(msg)
    except ConnectionClosed:
        pass
    except Exception as exc:
        logger.warning("producer error: %s", exc)
    finally:
        await HUB.unregister_producer(session_id, websocket, reason="disconnect")
        logger.info("producer disconnected: session=%s", session_id)


async def _handle_consumer(websocket: Any) -> None:
    await HUB.register_consumer(websocket)
    logger.info("consumer connected")
    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if not isinstance(msg, dict):
                continue
            mtype = msg.get("type")
            sid = msg.get("sessionId")
            if not isinstance(sid, str):
                continue
            if mtype == "overlay.event":
                msg.setdefault("v", PROTOCOL_VERSION)
                await HUB.send_to_producer(sid, msg)
            elif mtype == "overlay.snapshot.request":
                async with HUB._lock:  # noqa: SLF001 — internal helper
                    session = HUB.sessions.get(sid)
                    snap = session.snapshot_message() if session else None
                if snap is not None:
                    try:
                        await websocket.send(json.dumps(snap))
                    except ConnectionClosed:
                        return
    except ConnectionClosed:
        pass
    except Exception as exc:
        logger.warning("consumer error: %s", exc)
    finally:
        await HUB.unregister_consumer(websocket)
        logger.info("consumer disconnected")


async def overlay_handler(websocket: Any) -> None:
    path = _request_path(websocket)
    parsed = urlsplit(path)
    if parsed.path != "/overlay/ws":
        await websocket.close(code=1008, reason="unknown path")
        return

    params = _parse_query(path)
    role = params.get("role")
    if role == "producer":
        session_id = params.get("session", "")
        if not session_id:
            await websocket.close(code=1008, reason="missing session")
            return
        await _handle_producer(websocket, session_id)
    elif role == "consumer":
        origin = _origin_header(websocket)
        if origin is not None and origin not in ALLOWED_CONSUMER_ORIGINS:
            logger.warning("rejected consumer with origin=%s", origin)
            await websocket.close(code=1008, reason="forbidden origin")
            return
        await _handle_consumer(websocket)
    else:
        await websocket.close(code=1008, reason="missing role")


async def _gc_loop() -> None:
    while True:
        await asyncio.sleep(60)
        try:
            await HUB.gc_idle()
        except Exception as exc:  # pragma: no cover
            logger.warning("gc error: %s", exc)


async def main() -> None:
    host = "0.0.0.0"
    logger.info("listening on ws://%s:%s/overlay/ws", host, PORT)
    asyncio.create_task(_gc_loop())
    async with serve(overlay_handler, host, PORT, ping_interval=20, ping_timeout=20):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
