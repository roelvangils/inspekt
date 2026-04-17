#!/usr/bin/env python3
"""
WebSocket-based bridge server using aiohttp (more compatible).
"""

import asyncio
import json
import os
import re
import struct
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from pydantic import ValidationError

try:
    from aiohttp import web
except ImportError:
    print("Error: aiohttp library not installed")
    print("Install with: pip install aiohttp")
    exit(1)

from inspekt.domain.models import (
    ExecuteRequest,
    HealthResponse,
    Notification,
    NotificationsResponse,
    RunRequest,
    RunResponse,
    parse_incoming_message,
)
from inspekt.services.script_loader import ScriptLoader
from inspekt.transport.unix_socket import get_socket_path

HOST = "127.0.0.1"
PORT = 8765

# Store active WebSocket connections (browser clients)
active_connections: set = set()

# Track the most recently active connection
most_recent_connection = None

# Store browser info for each connection
browser_info: dict = {}

# Pending requests from CLI
pending_requests: dict[str, dict[str, Any]] = {}

# Completed requests
completed_requests: dict[str, dict[str, Any]] = {}

# Pending notifications (for control mode messages)
pending_notifications: list = []

# Events for long polling - notifies waiting HTTP requests when results arrive
pending_events: dict[str, asyncio.Event] = {}

# Events for execute acknowledgments - notifies /run endpoint when browser received request
ack_events: dict[str, asyncio.Event] = {}

# Cleanup old requests after 2 minutes (reduced from 5 to catch stuck requests faster)
MAX_REQUEST_AGE = 120

# Timeout for browser to acknowledge receiving a request (seconds)
# Note: Browser tabs in the background are heavily throttled by Chrome/Firefox,
# so we need a generous timeout. 30 seconds allows for throttled tabs to wake up.
# If no ack within this time, the browser is likely truly frozen/unresponsive.
ACK_TIMEOUT = 30.0

# Warn about requests stuck longer than this (seconds)
STUCK_REQUEST_THRESHOLD = 60

# Time window for browser_info message before connection is considered a ghost
BROWSER_INFO_TTL = 5

# Stale connection threshold (no activity for 120 seconds = ~4 missed pings)
# Background tabs are heavily throttled, so we need a generous threshold
STALE_CONNECTION_THRESHOLD = 120

# Long idle connection threshold (1 hour) - for connections that are alive but unused
IDLE_CONNECTION_THRESHOLD = 3600

# Script loader service (singleton)
script_loader = ScriptLoader()

# Screencast state (for video recording)
screencast_active: bool = False
screencast_frames: list[dict] = []  # List of {timestamp, data} dicts
screencast_max_frames: int = 10000  # Max frames to buffer (prevent memory overflow)
screencast_settings: dict = {}  # fps, quality, format
screencast_interrupted: dict | None = None  # Set when recording is interrupted (e.g., user opens DevTools)

# Audio cue state (for video audio effects)
audio_cues: list[dict] = []  # List of {timestamp_ms, action} dicts
audio_recording_active: bool = False
audio_recording_start_time: float = 0.0  # time.time() when recording started


# Server tracking
server_start_time = time.time()  # Track server uptime
connection_times: dict = {}  # Track when each connection was established
total_requests_processed = 0  # Lifetime request counter
total_requests_succeeded = 0  # Count of successful requests
total_requests_failed = 0  # Count of failed requests
last_activity_time = time.time()  # Track last request/result activity
last_activity_per_connection: dict = {}  # Track last activity time per connection
last_command_per_connection: dict = {}  # Track last command execution time per connection

# Instance tracking for browser targeting
instance_ids: dict[str, Any] = {}  # Maps instance_id (str) -> WebSocket
instance_aliases: dict[str, str] = {}  # Maps alias (str) -> instance_id
instance_id_to_ws: dict[str, Any] = {}  # Reverse lookup: instance_id -> WebSocket


async def _run_autorun_plugins(ws, url: str) -> None:
    """Run autorun plugins for a page load event."""
    try:
        if ws.closed or ws not in active_connections:
            return

        from inspekt.services.plugin_service import get_plugin_service, matches_autorun_pattern

        plugin_service = get_plugin_service()
        autorun_plugins = plugin_service.get_autorun_plugins()

        if not autorun_plugins:
            return

        for plugin in autorun_plugins:
            if not matches_autorun_pattern(url, plugin.get("autorun_domains")):
                continue

            try:
                request_id = str(uuid.uuid4())
                msg = json.dumps({
                    "type": "execute",
                    "requestId": request_id,
                    "code": plugin["code"],
                })
                await ws.send_str(msg)
                plugin_service.increment_run_count(plugin["id"])
                print(f"[Autorun] Executed plugin '{plugin['name']}' on {url[:60]}")
            except Exception as e:
                print(f"[Autorun] Failed to execute plugin '{plugin['name']}': {e}")

    except Exception as e:
        print(f"[Autorun] Error: {e}")


def generate_instance_id() -> str:
    """Generate a short unique instance ID like 'b7x2' or 'k9m4'.

    Uses lowercase letters and digits to create a 4-character ID that is:
    - Easy to type and remember
    - Unique enough for typical use (36^4 = 1.6M combinations)
    - Session-scoped (regenerated on server restart)
    """
    import random
    import string
    chars = string.ascii_lowercase + string.digits
    # Ensure uniqueness by checking against existing IDs
    while True:
        new_id = ''.join(random.choices(chars, k=4))
        if new_id not in instance_ids:
            return new_id


def cleanup_instance_for_ws(ws: Any) -> str | None:
    """Remove instance tracking for a disconnected WebSocket.

    Returns the instance_id that was removed, or None if not found.
    Also cleans up any aliases pointing to this instance.
    """
    # Find and remove instance ID for this WebSocket
    instance_id_to_remove = None
    for iid, stored_ws in list(instance_ids.items()):
        if stored_ws == ws:
            instance_id_to_remove = iid
            break

    if instance_id_to_remove:
        instance_ids.pop(instance_id_to_remove, None)
        instance_id_to_ws.pop(instance_id_to_remove, None)

        # Remove any aliases pointing to this instance
        aliases_to_remove = [
            alias for alias, iid in instance_aliases.items()
            if iid == instance_id_to_remove
        ]
        for alias in aliases_to_remove:
            del instance_aliases[alias]

    return instance_id_to_remove


def get_instance_id_for_ws(ws: Any) -> str | None:
    """Get the instance ID for a WebSocket connection."""
    for iid, stored_ws in instance_ids.items():
        if stored_ws == ws:
            return iid
    return None


def get_alias_for_instance(instance_id: str) -> str | None:
    """Get the alias for an instance ID, if one exists."""
    for alias, iid in instance_aliases.items():
        if iid == instance_id:
            return alias
    return None


# Socket server state
socket_server: Optional[asyncio.Server] = None
socket_path: Optional[Path] = None


# ============================================================================
# Socket Protocol Handler
# ============================================================================


class SocketProtocolHandler:
    """Handles the length-prefixed JSON protocol for socket clients.

    Protocol:
    - Messages are framed with a 4-byte big-endian length prefix
    - Payload is UTF-8 encoded JSON
    """

    def __init__(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self.reader = reader
        self.writer = writer

    async def read_request(self) -> Optional[dict]:
        """Read a length-prefixed JSON request.

        Returns:
            Parsed JSON dict, or None if connection closed
        """
        try:
            # Read 4-byte length prefix
            length_data = await self.reader.readexactly(4)
            length = struct.unpack(">I", length_data)[0]

            # Read payload
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


async def dispatch_socket_method(method: str, params: dict) -> dict:
    """Dispatch socket method to internal handlers.

    Maps socket methods to the same logic used by HTTP endpoints.

    Args:
        method: Method name (e.g., "run", "health", "result")
        params: Method parameters

    Returns:
        Response dict with success/data/error fields
    """
    global total_requests_processed, total_requests_succeeded, total_requests_failed
    global last_activity_time

    total_requests_processed += 1
    last_activity_time = time.time()

    try:
        if method == "run":
            # Execute code in browser
            code = params.get("code", "")
            browser_index = params.get("browser_index")
            instance = params.get("instance")  # New: ID, alias, or index string

            if not code or not isinstance(code, str):
                return {"success": False, "error": "missing code"}

            if not active_connections:
                return {"success": False, "error": "no_browser_connected"}

            # Resolve target browser instance
            target_ws = None
            if instance:
                target_ws = resolve_instance(instance)
                if target_ws is None:
                    return {
                        "success": False,
                        "error": "instance_not_found",
                        "message": f"No browser instance found for '{instance}'"
                    }

            # Create ack event before sending
            request_id = str(uuid.uuid4())
            ack_event = asyncio.Event()
            ack_events[request_id] = ack_event

            try:
                await send_code_to_browser_with_id(code, request_id, browser_index=browser_index, target_ws=target_ws)

                # Wait for browser acknowledgment
                await asyncio.wait_for(ack_event.wait(), timeout=ACK_TIMEOUT)
                total_requests_succeeded += 1
                return {"success": True, "data": {"ok": True, "request_id": request_id}}

            except asyncio.TimeoutError:
                pending_requests.pop(request_id, None)
                total_requests_failed += 1
                return {
                    "success": False,
                    "error": "browser_not_responding",
                    "message": "Browser tab not responding. Try clicking on the tab or refreshing the page."
                }
            finally:
                ack_events.pop(request_id, None)

        elif method == "result":
            # Get execution result (with optional waiting)
            request_id = params.get("request_id")
            timeout = params.get("timeout", 30.0)

            if not request_id:
                return {"success": False, "error": "missing request_id"}

            # If already completed, return immediately
            if request_id in completed_requests:
                result = completed_requests[request_id]
                total_requests_succeeded += 1
                return {"success": True, "data": result}

            # If pending, wait for result
            elif request_id in pending_requests:
                if request_id not in pending_events:
                    pending_events[request_id] = asyncio.Event()

                event = pending_events[request_id]

                if len(active_connections) == 0:
                    del pending_requests[request_id]
                    pending_events.pop(request_id, None)
                    total_requests_failed += 1
                    return {"success": False, "error": "no_browser_connected"}

                try:
                    await asyncio.wait_for(event.wait(), timeout=timeout)

                    if request_id in completed_requests:
                        pending_events.pop(request_id, None)
                        result = completed_requests[request_id]
                        total_requests_succeeded += 1
                        return {"success": True, "data": result}
                    else:
                        total_requests_failed += 1
                        return {"success": False, "error": "result_not_ready"}

                except asyncio.TimeoutError:
                    total_requests_failed += 1
                    return {"success": True, "data": {"status": "pending"}}

            else:
                total_requests_failed += 1
                return {"success": False, "error": "request_not_found"}

        elif method == "health":
            # Health check - return same fields as HTTP /health endpoint
            uptime = int(time.time() - server_start_time)
            # Note: browser_info is keyed by WebSocket object, not id(ws)
            valid_connections = [
                ws for ws in active_connections
                if ws in browser_info and is_valid_browser_info(browser_info.get(ws))
            ]

            # Build browser list with full details (same as HTTP /health)
            # Sort by connection time for consistent ordering
            sorted_connections = sorted(valid_connections, key=lambda ws: connection_times.get(ws, time.time()))
            most_recent = most_recent_connection if most_recent_connection in active_connections else None

            browsers = []
            for ws in sorted_connections:
                info = browser_info.get(ws, {})
                inst_id = get_instance_id_for_ws(ws)
                alias = get_alias_for_instance(inst_id) if inst_id else None

                # Parse browser name and version from user agent
                ua = info.get("userAgent", "")
                browser_name = "Unknown"
                browser_version = ""
                if "Firefox" in ua:
                    browser_name = "Firefox"
                    match = re.search(r"Firefox/(\d+\.?\d*)", ua)
                    if match:
                        browser_version = match.group(1)
                elif "Edg" in ua:
                    browser_name = "Edge"
                    match = re.search(r"Edg/(\d+\.?\d*\.?\d*\.?\d*)", ua)
                    if match:
                        browser_version = match.group(1)
                elif "Chrome" in ua:
                    browser_name = "Chrome"
                    match = re.search(r"Chrome/(\d+\.?\d*\.?\d*\.?\d*)", ua)
                    if match:
                        browser_version = match.group(1)
                elif "Safari" in ua:
                    browser_name = "Safari"
                    match = re.search(r"Version/(\d+\.?\d*)", ua)
                    if match:
                        browser_version = match.group(1)

                browsers.append({
                    "instance_id": inst_id,
                    "alias": alias,
                    "browser_name": browser_name,
                    "browser_version": browser_version,
                    "extension_version": info.get("extensionVersion"),
                    "url": info.get("url", ""),
                    "title": info.get("title", ""),
                    "user_agent": ua,
                    "is_most_recent": ws == most_recent,
                    "connected_duration": time.time() - connection_times.get(ws, time.time()),
                    "visible": info.get("visible", True),
                    "last_command_time": last_command_per_connection.get(ws),
                })

            total_requests_succeeded += 1
            return {
                "success": True,
                "data": {
                    "ok": True,
                    "connected_browsers": len(valid_connections),
                    "browsers": browsers,
                    "pending": len(pending_requests),
                    "completed": len(completed_requests),
                    "uptime_seconds": uptime,
                    "total_requests": total_requests_processed,
                }
            }

        elif method == "status":
            # Detailed server status
            uptime = int(time.time() - server_start_time)
            # Note: browser_info is keyed by WebSocket object, not id(ws)
            valid_connections = [
                ws for ws in active_connections
                if ws in browser_info and is_valid_browser_info(browser_info.get(ws))
            ]

            browsers = []
            for ws in valid_connections:
                info = browser_info.get(ws, {})
                inst_id = get_instance_id_for_ws(ws)
                alias = get_alias_for_instance(inst_id) if inst_id else None
                browsers.append({
                    "instance_id": inst_id,
                    "alias": alias,
                    "userAgent": info.get("userAgent", "Unknown"),
                    "url": info.get("url", ""),
                    "title": info.get("title", ""),
                    "extensionVersion": info.get("extensionVersion"),
                })

            total_requests_succeeded += 1
            return {
                "success": True,
                "data": {
                    "status": "ok",
                    "browsers": browsers,
                    "pending_requests": len(pending_requests),
                    "completed_requests": len(completed_requests),
                    "uptime_seconds": uptime,
                    "socket_path": str(socket_path) if socket_path else None,
                }
            }

        elif method == "console_logs":
            # Get console logs from browser (same as HTTP endpoint)
            if most_recent_connection is None:
                total_requests_failed += 1
                return {"success": False, "error": "no_browser_connected"}

            request_id = str(uuid.uuid4())
            message = {"type": "GET_CONSOLE_LOGS", "requestId": request_id}

            pending_requests[request_id] = {
                "timestamp": time.time(),
                "type": "GET_CONSOLE_LOGS"
            }

            await most_recent_connection.send_json(message)

            event = asyncio.Event()
            pending_events[request_id] = event

            try:
                timeout = params.get("timeout", 10.0)
                await asyncio.wait_for(event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pending_requests.pop(request_id, None)
                pending_events.pop(request_id, None)
                total_requests_failed += 1
                return {"success": False, "error": "timeout"}

            result = completed_requests.pop(request_id, None)
            pending_events.pop(request_id, None)

            if result is None:
                total_requests_failed += 1
                return {"success": False, "error": "no_response"}

            total_requests_succeeded += 1
            return {"success": True, "data": result.get("response", result)}

        elif method == "console_clear":
            # Clear console logs in browser (same as HTTP endpoint)
            if most_recent_connection is None:
                total_requests_failed += 1
                return {"success": False, "error": "no_browser_connected"}

            request_id = str(uuid.uuid4())
            message = {"type": "CLEAR_CONSOLE_LOGS", "requestId": request_id}

            pending_requests[request_id] = {
                "timestamp": time.time(),
                "type": "CLEAR_CONSOLE_LOGS"
            }

            await most_recent_connection.send_json(message)

            event = asyncio.Event()
            pending_events[request_id] = event

            try:
                timeout = params.get("timeout", 10.0)
                await asyncio.wait_for(event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pending_requests.pop(request_id, None)
                pending_events.pop(request_id, None)
                total_requests_failed += 1
                return {"success": False, "error": "timeout"}

            result = completed_requests.pop(request_id, None)
            pending_events.pop(request_id, None)

            total_requests_succeeded += 1
            return {"success": True, "data": {"cleared": True}}

        else:
            total_requests_failed += 1
            return {"success": False, "error": f"unknown method: {method}"}

    except Exception as e:
        total_requests_failed += 1
        return {"success": False, "error": str(e)}


async def handle_socket_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    """Handle a Unix socket client connection.

    Each connection is handled in a loop, processing requests until
    the client disconnects.
    """
    handler = SocketProtocolHandler(reader, writer)
    peer = writer.get_extra_info("peername") or "unknown"

    try:
        while True:
            request = await handler.read_request()
            if request is None:
                # Connection closed
                break

            method = request.get("method", "")
            params = request.get("params", {})
            request_id = request.get("id")

            # Dispatch to handler
            result = await dispatch_socket_method(method, params)

            # Add request_id to response
            result["id"] = request_id

            await handler.write_response(result)

    except Exception as e:
        # Log error but don't crash
        print(f"Socket client error ({peer}): {e}")

    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def start_socket_server(socket_path_arg: Optional[Path] = None) -> Optional[asyncio.Server]:
    """Start the Unix socket server.

    Args:
        socket_path_arg: Optional explicit socket path (uses default if None)

    Returns:
        The asyncio.Server instance, or None if socket creation failed
    """
    global socket_server, socket_path

    socket_path = socket_path_arg or get_socket_path()

    # Ensure parent directory exists
    socket_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove stale socket file if it exists
    if socket_path.exists():
        try:
            socket_path.unlink()
        except OSError as e:
            print(f"Warning: Could not remove stale socket {socket_path}: {e}")
            return None

    try:
        server = await asyncio.start_unix_server(
            handle_socket_client,
            path=str(socket_path),
        )

        # Set socket permissions (owner read/write only for security)
        socket_path.chmod(0o600)

        socket_server = server
        return server

    except OSError as e:
        print(f"Error: Could not create socket server at {socket_path}: {e}")
        return None


def is_valid_browser_info(info: dict) -> bool:
    """
    Check if browser_info contains enough data to be considered valid.

    A valid browser connection MUST have:
    - A non-empty userAgent string (not empty, not just "Unknown", at least 10 chars), AND
    - A valid extensionVersion

    Connections without both are considered orphaned and will be filtered out.
    """
    if not info:
        return False

    user_agent = info.get("userAgent", "")
    extension_version = info.get("extensionVersion")

    # Must have a real user agent (not empty, not just "Unknown")
    has_valid_ua = bool(user_agent and user_agent != "Unknown" and len(user_agent) > 10)

    # Must have an extension version
    has_extension = bool(extension_version)

    # Require BOTH for a valid connection
    return has_valid_ua and has_extension


def parse_user_agent(user_agent: str) -> tuple[str, str]:
    """
    Parse User-Agent string to extract browser name and version.

    Args:
        user_agent: User-Agent header string

    Returns:
        Tuple of (browser_name, version)
    """
    if not user_agent:
        return ("Unknown", "")

    ua = user_agent

    # Detect Zen Browser (based on Firefox)
    if "Zen/" in ua:
        match = re.search(r'Zen/([\d.]+)', ua)
        version = match.group(1) if match else ""
        return ("Zen Browser", version)

    # Detect Firefox
    if "Firefox/" in ua and "Seamonkey" not in ua:
        match = re.search(r'Firefox/([\d.]+)', ua)
        version = match.group(1) if match else ""
        return ("Firefox", version)

    # Detect Edge (Chromium-based)
    if "Edg/" in ua:
        match = re.search(r'Edg/([\d.]+)', ua)
        version = match.group(1) if match else ""
        return ("Edge", version)

    # Detect Chrome (but not Edge or other Chromium-based browsers)
    if "Chrome/" in ua and "Edg/" not in ua:
        # Check if it's a Chromium-based browser with a different identity
        if "OPR/" in ua or "Opera/" in ua:
            match = re.search(r'(?:OPR|Opera)/([\d.]+)', ua)
            version = match.group(1) if match else ""
            return ("Opera", version)

        # Generic Chromium detection
        match = re.search(r'Chrome/([\d.]+)', ua)
        version = match.group(1) if match else ""

        # Check if it's actually Chrome or just Chromium
        if "Google Chrome" in ua or ("Chrome/" in ua and "Chromium" not in ua):
            return ("Chrome", version)
        else:
            return ("Chromium", version)

    # Detect Safari (but not Chrome on iOS which also has Safari in UA)
    if "Safari/" in ua and "Chrome" not in ua and "Chromium" not in ua:
        # Try to get version from Version/ token first
        match = re.search(r'Version/([\d.]+)', ua)
        if match:
            version = match.group(1)
        else:
            # Fallback to Safari/ version
            match = re.search(r'Safari/([\d.]+)', ua)
            version = match.group(1) if match else ""
        return ("Safari", version)

    return ("Unknown", "")


def cleanup_old_requests():
    """Remove requests older than MAX_REQUEST_AGE seconds."""
    now = time.time()
    expired = [
        req_id
        for req_id, req in pending_requests.items()
        if now - req["timestamp"] > MAX_REQUEST_AGE
    ]
    for req_id in expired:
        del pending_requests[req_id]
        # Clean up any associated events
        pending_events.pop(req_id, None)

    expired = [
        req_id
        for req_id, req in completed_requests.items()
        if now - req["timestamp"] > MAX_REQUEST_AGE
    ]
    for req_id in expired:
        del completed_requests[req_id]
        # Clean up any associated events
        pending_events.pop(req_id, None)


async def cleanup_watchdog():
    """
    Background task that proactively cleans up stale requests and ghost connections.
    Runs every 30 seconds and logs warnings for stuck requests.
    """
    global most_recent_connection

    while True:
        await asyncio.sleep(30)

        now = time.time()
        stuck_count = 0
        oldest_age = 0
        cleaned_count = 0

        # Check and clean pending requests
        for req_id, req in list(pending_requests.items()):
            age = now - req["timestamp"]
            if age > MAX_REQUEST_AGE:
                # Auto-cleanup old requests
                del pending_requests[req_id]
                if req_id in pending_events:
                    pending_events[req_id].set()  # Wake any waiters
                    del pending_events[req_id]
                cleaned_count += 1
            elif age > STUCK_REQUEST_THRESHOLD:
                stuck_count += 1
                oldest_age = max(oldest_age, age)

        # Log warning if requests are stuck
        if stuck_count > 0:
            print(f"[Warning] {stuck_count} request(s) pending for >{int(oldest_age)}s")

        if cleaned_count > 0:
            print(f"[Cleanup] Removed {cleaned_count} stale request(s)")

        # Clean up ghost connections (no browser_info received within TTL)
        ghost_count = 0
        for ws in list(active_connections):
            connection_time = connection_times.get(ws, now)
            age = now - connection_time
            if ws not in browser_info and age > BROWSER_INFO_TTL:
                ghost_count += 1
                print(f"[Cleanup] Closing ghost connection (no browser_info after {age:.1f}s)")
                try:
                    await ws.close()
                except Exception:
                    pass
                active_connections.discard(ws)
                cleanup_instance_for_ws(ws)  # Clean up instance tracking
                connection_times.pop(ws, None)
                last_activity_per_connection.pop(ws, None)
                last_command_per_connection.pop(ws, None)
                if most_recent_connection == ws:
                    most_recent_connection = None

        if ghost_count > 0:
            print(f"[Cleanup] Removed {ghost_count} ghost connection(s)")

        # Clean up connections with incomplete/invalid browser_info
        incomplete_count = 0
        for ws in list(active_connections):
            info = browser_info.get(ws)
            connection_time = connection_times.get(ws, now)
            age = now - connection_time
            # Give connections 10 seconds to send complete info, then close if invalid
            if info is not None and age > 10 and not is_valid_browser_info(info):
                incomplete_count += 1
                print(f"[Cleanup] Closing connection with incomplete browser_info after {age:.1f}s")
                try:
                    await ws.close()
                except Exception:
                    pass
                active_connections.discard(ws)
                cleanup_instance_for_ws(ws)  # Clean up instance tracking
                browser_info.pop(ws, None)
                connection_times.pop(ws, None)
                last_activity_per_connection.pop(ws, None)
                last_command_per_connection.pop(ws, None)
                if most_recent_connection == ws:
                    most_recent_connection = None

        if incomplete_count > 0:
            print(f"[Cleanup] Removed {incomplete_count} connection(s) with incomplete info")

        # Clean up stale connections (no activity for STALE_CONNECTION_THRESHOLD seconds)
        stale_count = 0
        for ws in list(active_connections):
            last_activity = last_activity_per_connection.get(ws, connection_times.get(ws, now))
            if now - last_activity > STALE_CONNECTION_THRESHOLD:
                stale_count += 1
                print(f"[Cleanup] Closing stale connection (no activity for {now - last_activity:.0f}s)")
                try:
                    await ws.close()
                except Exception:
                    pass
                active_connections.discard(ws)
                cleanup_instance_for_ws(ws)  # Clean up instance tracking
                browser_info.pop(ws, None)
                connection_times.pop(ws, None)
                last_activity_per_connection.pop(ws, None)
                last_command_per_connection.pop(ws, None)
                if most_recent_connection == ws:
                    most_recent_connection = None

        if stale_count > 0:
            print(f"[Cleanup] Removed {stale_count} stale connection(s)")

        # Clean up long-idle connections (connected for over 1 hour with no recent activity)
        idle_count = 0
        for ws in list(active_connections):
            last_activity = last_activity_per_connection.get(ws, connection_times.get(ws, now))
            idle_time = now - last_activity
            if idle_time > IDLE_CONNECTION_THRESHOLD:
                idle_count += 1
                hours = idle_time / 3600
                print(f"[Cleanup] Closing idle connection (no activity for {hours:.1f} hours)")
                try:
                    await ws.close()
                except Exception:
                    pass
                active_connections.discard(ws)
                cleanup_instance_for_ws(ws)  # Clean up instance tracking
                browser_info.pop(ws, None)
                connection_times.pop(ws, None)
                last_activity_per_connection.pop(ws, None)
                last_command_per_connection.pop(ws, None)
                if most_recent_connection == ws:
                    most_recent_connection = None

        if idle_count > 0:
            print(f"[Cleanup] Removed {idle_count} idle connection(s)")


def get_queue_stats() -> dict:
    """Get current queue statistics."""
    now = time.time()
    pending_ages = [now - r["timestamp"] for r in pending_requests.values()]

    return {
        "pending_count": len(pending_requests),
        "completed_count": len(completed_requests),
        "oldest_pending_age": max(pending_ages) if pending_ages else 0,
        "pending_requests": [
            {
                "request_id": rid,
                "age_seconds": round(now - r["timestamp"], 1),
                "type": r.get("type", "execute")
            }
            for rid, r in pending_requests.items()
        ]
    }


def clear_queue(older_than: float = 0) -> dict:
    """
    Clear pending requests from the queue.

    Args:
        older_than: Only clear requests older than this many seconds (0 = all)

    Returns:
        Dict with cleared count and remaining count
    """
    now = time.time()
    cleared = 0

    for req_id, req in list(pending_requests.items()):
        age = now - req["timestamp"]
        if age >= older_than:
            del pending_requests[req_id]
            if req_id in pending_events:
                pending_events[req_id].set()  # Wake any waiters
                del pending_events[req_id]
            cleared += 1

    return {
        "ok": True,
        "cleared": cleared,
        "remaining": len(pending_requests)
    }


async def sync_domains_to_browser(ws):
    """Send current domains from SQLite to browser on connection."""
    try:
        from inspekt.services.domain_service import get_domain_service

        domain_service = get_domain_service()
        domains = domain_service.get_domains_for_browser_sync()

        if domains:
            request_id = str(uuid.uuid4())
            message = {
                "type": "SYNC_ALLOWED_DOMAINS",
                "requestId": request_id,
                "domains": domains
            }
            await ws.send_json(message)
            print(f"✓ Auto-synced {len(domains)} domain(s) to browser")
    except Exception as e:
        # Don't fail connection if sync fails
        print(f"Domain auto-sync skipped: {e}")


async def enable_permanent_bypass_if_isolated(ws):
    """Enable permanent bypass and global CSP bypass in browser if running in isolated mode."""
    from inspekt.config import is_isolated_mode

    if is_isolated_mode():
        # Enable permanent domain bypass
        try:
            request_id = str(uuid.uuid4())
            message = {
                "type": "PERMANENT_BYPASS",
                "requestId": request_id,
                "enabled": True
            }
            await ws.send_json(message)
            print("✓ Enabled permanent bypass in browser (isolated mode)")
        except Exception as e:
            print(f"Failed to enable permanent bypass: {e}")

        # Enable global CSP bypass
        try:
            request_id = str(uuid.uuid4())
            message = {
                "type": "CSP_BYPASS_GLOBAL",
                "requestId": request_id,
                "enabled": True
            }
            await ws.send_json(message)
            print("✓ Enabled global CSP bypass in browser (isolated mode)")
        except Exception as e:
            print(f"Failed to enable global CSP bypass: {e}")


async def websocket_handler(request):
    """Handle WebSocket connection from browser (userscript)."""
    global most_recent_connection, last_activity_time
    # Increase max message size to 100MB for large page saves (default is 4MB)
    ws = web.WebSocketResponse(max_msg_size=100 * 1024 * 1024)
    await ws.prepare(request)

    active_connections.add(ws)
    # Set this as the most recent connection
    most_recent_connection = ws
    # Track connection time
    connection_times[ws] = time.time()
    last_activity_time = time.time()

    # Generate and assign a unique instance ID for this browser
    instance_id = generate_instance_id()
    instance_ids[instance_id] = ws
    instance_id_to_ws[instance_id] = ws

    print(f"Browser tab connected via WebSocket (instance: {instance_id})")
    print(f"Active connections: {len(active_connections)}")

    # Auto-sync domains to newly connected browser
    await sync_domains_to_browser(ws)

    # Enable permanent bypass if running in isolated mode (Docker VM)
    await enable_permanent_bypass_if_isolated(ws)

    # Resend any pending requests to the newly connected browser
    # This handles the case where a page navigation disconnected mid-request
    if pending_requests:
        print(f"Resending {len(pending_requests)} pending request(s) to new connection")
        for request_id, req_data in list(pending_requests.items()):
            try:
                message = json.dumps(
                    {"type": "execute", "request_id": request_id, "code": req_data["code"]}
                )
                await ws.send_str(message)
                print(f"Resent pending request {request_id}")
            except Exception as e:
                print(f"Error resending request {request_id}: {e}")

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)

                    # Validate incoming message with Pydantic
                    try:
                        validated_msg = parse_incoming_message(data)
                    except (ValidationError, ValueError) as e:
                        print(f"Invalid message from browser: {e}")
                        continue

                    message_type = validated_msg.type

                    # Track activity for this connection (for stale detection)
                    last_activity_per_connection[ws] = time.time()

                    # Mark this connection as most recent when it sends any message (except ping)
                    if message_type != "ping":
                        most_recent_connection = ws

                    if message_type == "result":
                        # Browser sending back result of executed code
                        # This connection is responding, so it's the active one
                        most_recent_connection = ws

                        request_id = data.get("request_id")
                        if request_id and request_id in pending_requests:
                            global total_requests_processed, total_requests_succeeded, total_requests_failed
                            del pending_requests[request_id]

                            request_ok = data.get("ok", False)
                            completed_requests[request_id] = {
                                "ok": request_ok,
                                "result": data.get("result"),
                                "error": data.get("error"),
                                "url": data.get("url"),
                                "title": data.get("title"),
                                "timestamp": time.time(),
                            }
                            total_requests_processed += 1
                            if request_ok:
                                total_requests_succeeded += 1
                            else:
                                total_requests_failed += 1
                            last_activity_time = time.time()
                            last_command_per_connection[ws] = time.time()  # Track last command for this connection
                            print(f"Received result for request {request_id}")

                            # Notify any waiting HTTP long-poll requests
                            if request_id in pending_events:
                                pending_events[request_id].set()
                                print(f"Notified waiting HTTP request for {request_id}")

                    elif message_type == "execute_ack":
                        # Browser acknowledging it received the execute request
                        # This confirms the browser is alive and processing the request
                        request_id = data.get("request_id")
                        if request_id and request_id in ack_events:
                            ack_events[request_id].set()

                    elif message_type == "reinit_control":
                        # Browser requesting automatic reinitialization after page reload
                        config = data.get("config", {})
                        print("[Server] Auto-reinit requested from browser via WebSocket")

                        try:
                            # Use ScriptLoader service (async, cached)
                            placeholders = {
                                "ACTION_PLACEHOLDER": "start",
                                "KEY_DATA_PLACEHOLDER": "{}",
                                "CONFIG_PLACEHOLDER": json.dumps(config),
                            }
                            start_code = await script_loader.load_with_substitution_async(
                                "control.js", placeholders, use_cache=True
                            )

                            # Send back as an execute message
                            request_id = str(uuid.uuid4())
                            execute_msg = json.dumps(
                                {"type": "execute", "request_id": request_id, "code": start_code}
                            )
                            await ws.send_str(execute_msg)
                            print(f"[Server] Sent auto-reinit code (request {request_id[:8]})")

                        except FileNotFoundError:
                            print("[Server] ERROR: control.js not found")
                        except Exception as e:
                            print(f"[Server] Error in auto-reinit: {e}")

                    elif message_type == "refocus_notification":
                        # Browser sending refocus result notification
                        notification = {
                            "type": "refocus",
                            "success": data.get("success", False),
                            "message": data.get("message", ""),
                            "timestamp": time.time(),
                        }
                        pending_notifications.append(notification)
                        print(f"[Server] Refocus notification: {notification['message']}")

                    elif message_type == "ping":
                        # Browser keepalive
                        await ws.send_str(json.dumps({"type": "pong"}))

                    elif message_type == "browser_info":
                        # Store browser information
                        browser_info[ws] = {
                            "userAgent": data.get("userAgent", "Unknown"),
                            "browserName": data.get("browserName", "Unknown"),
                            "url": data.get("url", ""),
                            "title": data.get("title", ""),
                            "extensionVersion": data.get("extensionVersion"),
                            "visible": data.get("visible", True)
                        }
                        browser_name = data.get("browserName", "Unknown")
                        page_title = data.get("title", "")[:50]
                        ext_version = data.get("extensionVersion", "unknown")
                        visible_status = "visible" if data.get("visible", True) else "hidden"
                        print(f"Browser info received: {browser_name} v{ext_version} ({visible_status}) - {page_title}")

                        # Trigger autorun plugins after a short delay
                        page_url = data.get("url", "")
                        if page_url.startswith("http"):
                            loop = asyncio.get_running_loop()
                            loop.call_later(
                                0.5, lambda w=ws, u=page_url: asyncio.ensure_future(_run_autorun_plugins(w, u))
                            )

                    elif message_type == "visibility_change":
                        # Update visibility state for this browser
                        if ws in browser_info:
                            browser_info[ws]["visible"] = data.get("visible", True)
                            visible_status = "visible" if data.get("visible", True) else "hidden"
                            browser_name = browser_info[ws].get("browserName", "Unknown")
                            print(f"Visibility changed: {browser_name} is now {visible_status}")

                    elif message_type == "response":
                        # Extension sending back response for domain management commands
                        request_id = data.get("requestId")

                        if request_id and request_id in pending_requests:
                            # Store the response
                            completed_requests[request_id] = {
                                "response": data.get("response"),
                                "timestamp": time.time()
                            }

                            # Remove from pending
                            del pending_requests[request_id]

                            # Notify waiting HTTP request
                            if request_id in pending_events:
                                pending_events[request_id].set()

                    elif message_type == "screencast_frame":
                        # Browser sending a screencast frame (video recording)
                        handle_screencast_frame(data)

                    elif message_type == "screencast_ack":
                        # Browser acknowledging screencast start/stop
                        request_id = data.get("requestId")

                        if request_id and request_id in pending_requests:
                            # Store the acknowledgment
                            completed_requests[request_id] = {
                                "ok": data.get("ok", True),
                                "error": data.get("error"),
                                "timestamp": time.time()
                            }

                            # Remove from pending
                            del pending_requests[request_id]

                            # Notify waiting HTTP request
                            if request_id in pending_events:
                                pending_events[request_id].set()

                except json.JSONDecodeError:
                    print(f"Invalid JSON from browser: {msg.data}")
                except Exception as e:
                    print(f"Error handling browser message: {e}")

            elif msg.type == web.WSMsgType.ERROR:
                print(f"WebSocket connection closed with exception {ws.exception()}")

    finally:
        # Cancel all pending requests for this connection
        cancelled_count = 0
        for req_id, req_data in list(pending_requests.items()):
            if req_data.get('connection') == ws:
                del pending_requests[req_id]
                # Notify any waiting HTTP clients
                if req_id in pending_events:
                    pending_events[req_id].set()
                    del pending_events[req_id]
                cancelled_count += 1

        active_connections.discard(ws)
        removed_instance = cleanup_instance_for_ws(ws)  # Clean up instance tracking
        browser_info.pop(ws, None)
        connection_times.pop(ws, None)  # Clean up connection time tracking
        last_activity_per_connection.pop(ws, None)  # Clean up activity tracking
        last_command_per_connection.pop(ws, None)  # Clean up command tracking
        if most_recent_connection == ws:
            most_recent_connection = None

        if cancelled_count > 0:
            print(f"Browser tab disconnected - cancelled {cancelled_count} pending request(s)")
        else:
            print("Browser tab disconnected")
        print(f"Active connections: {len(active_connections)}")

    return ws


async def send_code_to_browser(code: str, browser_index: int = None) -> str:
    """Send code to browser for execution. Returns request_id.

    Args:
        code: JavaScript code to execute
        browser_index: Optional index of specific browser to target (0-based)
    """
    request_id = str(uuid.uuid4())
    await send_code_to_browser_with_id(code, request_id, browser_index)
    return request_id


async def send_code_to_browser_with_id(
    code: str,
    request_id: str,
    browser_index: int = None,
    target_ws: Any = None
) -> None:
    """Send code to browser for execution with a pre-generated request_id.

    Args:
        code: JavaScript code to execute
        request_id: Pre-generated request ID (for ack tracking)
        browser_index: Optional index of specific browser to target (0-based)
        target_ws: Optional specific WebSocket to target (overrides browser_index)
    """
    global most_recent_connection
    pending_requests[request_id] = {
        "code": code,
        "timestamp": time.time(),
        "connection": None  # Will be set after selecting target
    }

    # Send to most recent active browser only
    message = json.dumps({"type": "execute", "request_id": request_id, "code": code})

    # Select target browser - explicit target_ws has highest priority
    if target_ws is None:
        if browser_index is not None:
            # Target specific browser by index
            # Sort by connection time for consistent ordering (matches /health endpoint)
            connections_list = sorted(active_connections, key=lambda ws: connection_times.get(ws, time.time()))
            if 0 <= browser_index < len(connections_list):
                target_ws = connections_list[browser_index]
            else:
                print(f"[Server] WARNING: Invalid browser_index {browser_index}, only {len(connections_list)} browsers connected")
        else:
            # Use most recent connection if available, otherwise use any active connection
            target_ws = most_recent_connection if most_recent_connection in active_connections else None

            if not target_ws and active_connections:
                # Fallback to first available connection
                target_ws = next(iter(active_connections))
                most_recent_connection = target_ws

    if target_ws:
        # Track which connection owns this request
        pending_requests[request_id]["connection"] = target_ws

        try:
            await target_ws.send_str(message)
            # Get browser info if available
            info = browser_info.get(target_ws, {})
            browser_name = info.get("browserName", "Unknown browser")
            page_title = info.get("title", "")
            if page_title:
                print(f"[Server] Sent request {request_id[:8]} to {browser_name} - {page_title[:50]}")
            else:
                print(f"[Server] Sent request {request_id[:8]} to {browser_name}")
        except Exception as e:
            print(f"Error sending to browser: {e}")
            active_connections.discard(target_ws)
            browser_info.pop(target_ws, None)
            if most_recent_connection == target_ws:
                most_recent_connection = None
    else:
        print(f"[Server] WARNING: No browsers connected for request {request_id[:8]}")


async def handle_http_run(request):
    """HTTP endpoint: Submit code to run.

    Now waits for browser acknowledgment before returning to ensure the browser
    is alive and received the request. Returns error within ACK_TIMEOUT seconds
    if no acknowledgment is received (browser frozen/unresponsive).

    Supports targeting specific browser instances via:
    - instance: ID, alias, or index string (e.g., "b7x2", "homepage", "0")
    - browser_index: Numeric index (legacy, for backwards compatibility)
    """
    cleanup_old_requests()

    try:
        data = await request.json()
        code = data.get("code", "")
        browser_index = data.get("browser_index")  # Legacy: target by numeric index
        instance = data.get("instance")  # New: target by ID, alias, or index string

        if not code or not isinstance(code, str):
            return web.json_response({"ok": False, "error": "missing code"}, status=400)

        # Check if any browsers are connected before sending
        if not active_connections:
            return web.json_response(
                {"ok": False, "error": "no_browser_connected"},
                status=503
            )

        # Resolve target browser instance
        target_ws = None
        if instance:
            # New instance resolution: supports ID, alias, or index string
            target_ws = resolve_instance(instance)
            if target_ws is None:
                return web.json_response(
                    {"ok": False, "error": f"instance_not_found", "message": f"No browser instance found for '{instance}'"},
                    status=404
                )

        request_id = str(uuid.uuid4())

        # Send code to browser
        await send_code_to_browser_with_id(code, request_id, browser_index=browser_index, target_ws=target_ws)

        # Return immediately — the client polls /result for the outcome
        return web.json_response({"ok": True, "request_id": request_id})

    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_http_result(request):
    """HTTP endpoint: Get result of request (with long polling support)."""
    request_id = request.query.get("request_id")

    if not request_id:
        return web.json_response({"ok": False, "error": "missing request_id"}, status=400)

    # If already completed, return immediately
    if request_id in completed_requests:
        return web.json_response(completed_requests[request_id])

    # If pending, wait for result with long polling
    elif request_id in pending_requests:
        # Create event for this request if it doesn't exist
        if request_id not in pending_events:
            pending_events[request_id] = asyncio.Event()

        event = pending_events[request_id]

        # Calculate timeout based on request age (allow up to 180s for large operations like page save)
        req_age = time.time() - pending_requests[request_id]["timestamp"]
        remaining_timeout = max(180.0 - req_age, 0.1)  # At least 100ms

        # Check if no browser connected
        if len(active_connections) == 0:
            # Don't wait, return error immediately
            del pending_requests[request_id]
            pending_events.pop(request_id, None)
            return web.json_response(
                {"ok": False, "error": "no_browser_connected"}
            )

        try:
            # Wait for result with timeout (long polling)
            await asyncio.wait_for(event.wait(), timeout=remaining_timeout)

            # Event was set, result should be ready
            if request_id in completed_requests:
                # Clean up event
                pending_events.pop(request_id, None)
                return web.json_response(completed_requests[request_id])
            else:
                # Edge case: event set but no result (shouldn't happen)
                pending_events.pop(request_id, None)
                return web.json_response({"ok": False, "status": "pending"})

        except asyncio.TimeoutError:
            # Timeout waiting for result
            pending_events.pop(request_id, None)

            # Check if still pending or if it completed during cleanup
            if request_id in completed_requests:
                return web.json_response(completed_requests[request_id])
            elif request_id in pending_requests:
                # Still pending after timeout
                return web.json_response({"ok": False, "status": "pending"})
            else:
                return web.json_response({"ok": False, "error": "Request timeout"})

    else:
        return web.json_response({"ok": False, "error": "unknown request_id"}, status=404)


async def handle_http_cancel(request):
    """HTTP endpoint: Cancel a pending request."""
    request_id = request.query.get("request_id")

    if not request_id:
        return web.json_response({"ok": False, "error": "missing request_id"}, status=400)

    # Check if request is pending
    if request_id in pending_requests:
        # Remove from pending
        del pending_requests[request_id]

        # Notify any waiting HTTP clients
        if request_id in pending_events:
            pending_events[request_id].set()
            del pending_events[request_id]

        print(f"[Server] Cancelled pending request {request_id[:8]}")
        return web.json_response({"ok": True, "cancelled": True})

    # Already completed
    elif request_id in completed_requests:
        return web.json_response({
            "ok": False,
            "error": "Request already completed",
            "cancelled": False
        }, status=400)

    # Unknown request
    else:
        return web.json_response({
            "ok": False,
            "error": "Unknown request_id",
            "cancelled": False
        }, status=404)


async def handle_http_reinit_control(request):
    """HTTP endpoint: Auto-reinitialize control mode after page reload."""
    try:
        data = await request.json()
        config = data.get("config", {})

        print("[Server] Auto-reinitialization requested from browser")

        # Use ScriptLoader service (async, cached)
        placeholders = {
            "ACTION_PLACEHOLDER": "start",
            "KEY_DATA_PLACEHOLDER": "{}",
            "CONFIG_PLACEHOLDER": json.dumps(config),
        }
        start_code = await script_loader.load_with_substitution_async(
            "control.js", placeholders, use_cache=True
        )

        # Send to browser via WebSocket
        request_id = await send_code_to_browser(start_code)

        print(f"[Server] Sent auto-reinit request {request_id[:8]}")

        return web.json_response({"ok": True, "request_id": request_id})

    except FileNotFoundError:
        return web.json_response({"ok": False, "error": "control.js not found"}, status=500)
    except Exception as e:
        print(f"[Server] Error in auto-reinit: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def handle_http_notifications(request):
    """HTTP endpoint: Get pending notifications."""
    global pending_notifications

    # Get all pending notifications
    notifications = pending_notifications.copy()
    # Clear the list
    pending_notifications = []

    return web.json_response({"ok": True, "notifications": notifications})


async def handle_http_health(request):
    """HTTP endpoint: Health check."""
    from inspekt import __version__

    cleanup_old_requests()

    # Calculate uptime
    current_time = time.time()
    uptime = current_time - server_start_time

    # Build browser connection list
    # Filter out ghost connections (those without browser_info or with incomplete info)
    valid_connections = [
        ws for ws in active_connections
        if ws in browser_info and is_valid_browser_info(browser_info.get(ws))
    ]
    # Sort connections by connection time for consistent ordering
    sorted_connections = sorted(valid_connections, key=lambda ws: connection_times.get(ws, current_time))

    browsers_list = []
    for ws in sorted_connections:
        info = browser_info.get(ws, {})
        connection_time = connection_times.get(ws, current_time)
        duration = current_time - connection_time

        # Parse User-Agent to get accurate browser name and version
        user_agent = info.get("userAgent", "")
        browser_name, browser_version = parse_user_agent(user_agent)

        # Fallback to extension-provided browserName if parsing failed
        if browser_name == "Unknown":
            extension_browser_name = info.get("browserName", "")
            if extension_browser_name and extension_browser_name != "Unknown":
                # Normalize common names
                name_map = {
                    "Google Chrome": "Chrome",
                    "Microsoft Edge": "Edge",
                }
                browser_name = name_map.get(extension_browser_name, extension_browser_name)

        # Get instance ID and alias for this connection
        inst_id = get_instance_id_for_ws(ws)
        alias = get_alias_for_instance(inst_id) if inst_id else None

        browsers_list.append({
            "instance_id": inst_id,
            "alias": alias,
            "browser_name": browser_name,
            "browser_version": browser_version,
            "extension_version": info.get("extensionVersion"),
            "url": info.get("url", ""),
            "title": info.get("title", ""),
            "user_agent": user_agent,
            "is_most_recent": (ws == most_recent_connection),
            "connected_duration": duration,
            "visible": info.get("visible", True),
            "last_command_time": last_command_per_connection.get(ws),  # None if never commanded
        })

    # Get cached scripts from script loader
    cached = list(script_loader.get_cached_scripts())

    # Check if API server is running and get its stats
    api_server_info = None
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get("http://127.0.0.1:8000/health", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                if resp.status == 200:
                    api_data = await resp.json()
                    api_server_info = {
                        "running": True,
                        "port": 8000,
                        "uptime_seconds": api_data.get("api_uptime_seconds", 0),
                        "total_requests": api_data.get("api_total_requests", 0),
                        "succeeded": api_data.get("api_succeeded", 0),
                        "failed": api_data.get("api_failed", 0),
                    }
                else:
                    api_server_info = {
                        "running": False,
                        "port": 8000,
                    }
    except Exception:
        # API server not running or not reachable
        api_server_info = {
            "running": False,
            "port": 8000,
        }

    return web.json_response(
        {
            "ok": True,
            "timestamp": current_time,
            "server_version": __version__,
            "uptime_seconds": uptime,
            "host": HOST,
            "port": PORT,
            "websocket_port": PORT + 1,
            "connected_browsers": len(valid_connections),
            "browsers": browsers_list,
            "pending": len(pending_requests),
            "completed": len(completed_requests),
            "total_processed": total_requests_processed,
            "total_succeeded": total_requests_succeeded,
            "total_failed": total_requests_failed,
            "last_activity": last_activity_time,
            "cached_scripts": cached,
            "api_server": api_server_info,
        },
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
    )


async def handle_http_queue_status(request):
    """HTTP endpoint: Get queue statistics."""
    stats = get_queue_stats()
    return web.json_response(stats)


async def handle_http_queue_clear(request):
    """HTTP endpoint: Clear pending requests from the queue."""
    try:
        if request.body_exists:
            data = await request.json()
            older_than = data.get("older_than", 0)
        else:
            older_than = 0

        result = clear_queue(older_than)
        return web.json_response(result)

    except Exception as e:
        return web.json_response(
            {"ok": False, "error": str(e)},
            status=500
        )


# ============================================================================
# INSTANCE MANAGEMENT ENDPOINTS
# ============================================================================


async def handle_http_instances_list(request):
    """HTTP endpoint: List all connected browser instances with details."""
    current_time = time.time()

    # Get valid connections
    valid_connections = [
        ws for ws in active_connections
        if ws in browser_info and is_valid_browser_info(browser_info.get(ws))
    ]

    # Sort by connection time for consistent ordering
    sorted_connections = sorted(
        valid_connections,
        key=lambda ws: connection_times.get(ws, current_time)
    )

    instances = []
    for index, ws in enumerate(sorted_connections):
        info = browser_info.get(ws, {})
        connection_time = connection_times.get(ws, current_time)
        duration = current_time - connection_time

        # Get instance ID and alias
        inst_id = get_instance_id_for_ws(ws)
        alias = get_alias_for_instance(inst_id) if inst_id else None

        # Parse browser info
        user_agent = info.get("userAgent", "")
        browser_name, browser_version = parse_user_agent(user_agent)
        if browser_name == "Unknown":
            browser_name = info.get("browserName", "Unknown")

        # Format duration
        if duration < 60:
            duration_str = f"{int(duration)}s"
        elif duration < 3600:
            duration_str = f"{int(duration / 60)}m {int(duration % 60)}s"
        else:
            hours = int(duration / 3600)
            minutes = int((duration % 3600) / 60)
            duration_str = f"{hours}h {minutes}m"

        # Format last command time
        last_cmd_time = last_command_per_connection.get(ws)
        if last_cmd_time is None:
            last_cmd_str = "never"
        else:
            ago = current_time - last_cmd_time
            if ago < 60:
                last_cmd_str = f"{int(ago)}s ago"
            elif ago < 3600:
                last_cmd_str = f"{int(ago / 60)}m ago"
            else:
                last_cmd_str = f"{int(ago / 3600)}h ago"

        instances.append({
            "id": inst_id,
            "alias": alias,
            "index": index,
            "browser": f"{browser_name} {browser_version}".strip(),
            "browser_name": browser_name,
            "browser_version": browser_version,
            "url": info.get("url", ""),
            "title": info.get("title", ""),
            "is_active": (ws == most_recent_connection),
            "connected_duration": duration,
            "connected_duration_str": duration_str,
            "last_command_time": last_cmd_time,
            "last_command_time_str": last_cmd_str,
            "visible": info.get("visible", True),
        })

    return web.json_response({
        "ok": True,
        "instances": instances,
        "count": len(instances),
    })


async def handle_http_instance_alias_set(request):
    """HTTP endpoint: Set an alias for a browser instance."""
    try:
        data = await request.json()
        instance_id = data.get("instance_id")
        alias = data.get("alias", "").strip().lower()

        if not instance_id:
            return web.json_response(
                {"ok": False, "error": "Missing 'instance_id' parameter"},
                status=400
            )

        if not alias:
            return web.json_response(
                {"ok": False, "error": "Missing 'alias' parameter"},
                status=400
            )

        # Validate instance exists
        if instance_id not in instance_ids:
            return web.json_response(
                {"ok": False, "error": f"Instance '{instance_id}' not found"},
                status=404
            )

        # Check if alias is already used by another instance
        if alias in instance_aliases and instance_aliases[alias] != instance_id:
            existing_id = instance_aliases[alias]
            return web.json_response(
                {"ok": False, "error": f"Alias '{alias}' is already used by instance '{existing_id}'"},
                status=409
            )

        # Remove any existing alias for this instance
        for old_alias, iid in list(instance_aliases.items()):
            if iid == instance_id:
                del instance_aliases[old_alias]
                break

        # Set new alias
        instance_aliases[alias] = instance_id

        print(f"[Instances] Set alias '{alias}' for instance {instance_id}")

        return web.json_response({
            "ok": True,
            "instance_id": instance_id,
            "alias": alias,
            "message": f"Alias '{alias}' set for instance {instance_id}",
        })

    except Exception as e:
        return web.json_response(
            {"ok": False, "error": str(e)},
            status=500
        )


async def handle_http_instance_alias_remove(request):
    """HTTP endpoint: Remove an alias from a browser instance."""
    try:
        alias = request.query.get("alias", "").strip().lower()

        if not alias:
            # Try to get from JSON body
            if request.body_exists:
                data = await request.json()
                alias = data.get("alias", "").strip().lower()

        if not alias:
            return web.json_response(
                {"ok": False, "error": "Missing 'alias' parameter"},
                status=400
            )

        if alias not in instance_aliases:
            return web.json_response(
                {"ok": False, "error": f"Alias '{alias}' not found"},
                status=404
            )

        instance_id = instance_aliases.pop(alias)

        print(f"[Instances] Removed alias '{alias}' from instance {instance_id}")

        return web.json_response({
            "ok": True,
            "alias": alias,
            "instance_id": instance_id,
            "message": f"Alias '{alias}' removed from instance {instance_id}",
        })

    except Exception as e:
        return web.json_response(
            {"ok": False, "error": str(e)},
            status=500
        )


def resolve_instance(identifier: str) -> Any:
    """Resolve a browser instance by ID, alias, or numeric index.

    Args:
        identifier: Instance ID (e.g., 'b7x2'), alias (e.g., 'homepage'),
                   or numeric index (e.g., '0', '1')

    Returns:
        WebSocket connection for the instance, or None if not found.
    """
    if not identifier:
        return None

    identifier = identifier.strip().lower()

    # Try as instance ID first
    if identifier in instance_ids:
        ws = instance_ids[identifier]
        if ws in active_connections:
            return ws

    # Try as alias
    if identifier in instance_aliases:
        instance_id = instance_aliases[identifier]
        if instance_id in instance_ids:
            ws = instance_ids[instance_id]
            if ws in active_connections:
                return ws

    # Try as numeric index
    if identifier.isdigit():
        index = int(identifier)
        valid_connections = [
            ws for ws in active_connections
            if ws in browser_info and is_valid_browser_info(browser_info.get(ws))
        ]
        sorted_connections = sorted(
            valid_connections,
            key=lambda ws: connection_times.get(ws, time.time())
        )
        if 0 <= index < len(sorted_connections):
            return sorted_connections[index]

    return None


async def handle_http_domain_add(request):
    """HTTP endpoint: Add a domain to allowed list."""
    try:
        data = await request.json()
        domain = data.get("domain")

        if not domain:
            return web.json_response(
                {"ok": False, "error": "Missing 'domain' parameter"},
                status=400
            )

        # Send message to extension via WebSocket
        if not most_recent_connection or most_recent_connection not in active_connections:
            return web.json_response(
                {"ok": False, "error": "No browser connected. If Chrome is open, make sure you're on a regular webpage (not chrome://, new tab, or extension pages where content scripts can't run)."},
                status=503
            )

        request_id = str(uuid.uuid4())
        message = {
            "type": "DOMAIN_ADD",
            "requestId": request_id,
            "domain": domain
        }

        # Store pending request
        pending_requests[request_id] = {
            "timestamp": time.time(),
            "type": "DOMAIN_ADD"
        }

        # Send to browser
        await most_recent_connection.send_json(message)

        # Wait for response (with timeout)
        event = asyncio.Event()
        pending_events[request_id] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=10.0)
            result = completed_requests.get(request_id, {})
            return web.json_response(result.get("response", {"ok": False, "error": "No response"}))
        except asyncio.TimeoutError:
            return web.json_response(
                {"ok": False, "error": "Request timed out"},
                status=504
            )
        finally:
            pending_events.pop(request_id, None)
            completed_requests.pop(request_id, None)

    except Exception as e:
        return web.json_response(
            {"ok": False, "error": str(e)},
            status=500
        )


async def handle_http_domain_remove(request):
    """HTTP endpoint: Remove a domain from allowed list."""
    try:
        data = await request.json()
        domain = data.get("domain")

        if not domain:
            return web.json_response(
                {"ok": False, "error": "Missing 'domain' parameter"},
                status=400
            )

        # Send message to extension via WebSocket
        if not most_recent_connection or most_recent_connection not in active_connections:
            return web.json_response(
                {"ok": False, "error": "No browser connected. If Chrome is open, make sure you're on a regular webpage (not chrome://, new tab, or extension pages where content scripts can't run)."},
                status=503
            )

        request_id = str(uuid.uuid4())
        message = {
            "type": "DOMAIN_REMOVE",
            "requestId": request_id,
            "domain": domain
        }

        # Store pending request
        pending_requests[request_id] = {
            "timestamp": time.time(),
            "type": "DOMAIN_REMOVE"
        }

        # Send to browser
        await most_recent_connection.send_json(message)

        # Wait for response (with timeout)
        event = asyncio.Event()
        pending_events[request_id] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=10.0)
            result = completed_requests.get(request_id, {})
            return web.json_response(result.get("response", {"ok": False, "error": "No response"}))
        except asyncio.TimeoutError:
            return web.json_response(
                {"ok": False, "error": "Request timed out"},
                status=504
            )
        finally:
            pending_events.pop(request_id, None)
            completed_requests.pop(request_id, None)

    except Exception as e:
        return web.json_response(
            {"ok": False, "error": str(e)},
            status=500
        )


async def handle_http_domain_list(request):
    """HTTP endpoint: List all allowed domains."""
    try:
        # Send message to extension via WebSocket
        if not most_recent_connection or most_recent_connection not in active_connections:
            return web.json_response(
                {"ok": False, "error": "No browser connected. If Chrome is open, make sure you're on a regular webpage (not chrome://, new tab, or extension pages where content scripts can't run)."},
                status=503
            )

        request_id = str(uuid.uuid4())
        message = {
            "type": "DOMAIN_LIST",
            "requestId": request_id
        }

        # Store pending request
        pending_requests[request_id] = {
            "timestamp": time.time(),
            "type": "DOMAIN_LIST"
        }

        # Send to browser
        await most_recent_connection.send_json(message)

        # Wait for response (with timeout)
        event = asyncio.Event()
        pending_events[request_id] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=10.0)
            result = completed_requests.get(request_id, {})
            return web.json_response(result.get("response", {"ok": False, "error": "No response"}))
        except asyncio.TimeoutError:
            return web.json_response(
                {"ok": False, "error": "Request timed out"},
                status=504
            )
        finally:
            pending_events.pop(request_id, None)
            completed_requests.pop(request_id, None)

    except Exception as e:
        return web.json_response(
            {"ok": False, "error": str(e)},
            status=500
        )


async def handle_http_domain_bypass(request):
    """HTTP endpoint: Set temporary bypass for all domains."""
    try:
        data = await request.json()
        duration = data.get("duration")

        if duration is None:
            return web.json_response(
                {"ok": False, "error": "Missing 'duration' parameter"},
                status=400
            )

        # Status queries (duration=-1) and disable requests (duration=0)
        # are answerable without a browser: if nothing is connected, no
        # bypass can be active, and there's nothing to disable. Returning
        # a sensible 200 here avoids flooding the API log with 503s when
        # the control panel polls these endpoints on an empty bridge.
        if not most_recent_connection or most_recent_connection not in active_connections:
            if duration in (-1, 0):
                return web.json_response({"ok": True, "enabled": False})
            return web.json_response(
                {"ok": False, "error": "No browser connected. If Chrome is open, make sure you're on a regular webpage (not chrome://, new tab, or extension pages where content scripts can't run)."},
                status=503
            )

        request_id = str(uuid.uuid4())
        message = {
            "type": "DOMAIN_BYPASS",
            "requestId": request_id,
            "duration": duration
        }

        # Store pending request
        pending_requests[request_id] = {
            "timestamp": time.time(),
            "type": "DOMAIN_BYPASS"
        }

        # Send to browser
        await most_recent_connection.send_json(message)

        # Wait for response (with timeout)
        event = asyncio.Event()
        pending_events[request_id] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=10.0)
            result = completed_requests.get(request_id, {})
            return web.json_response(result.get("response", {"ok": False, "error": "No response"}))
        except asyncio.TimeoutError:
            return web.json_response(
                {"ok": False, "error": "Request timed out"},
                status=504
            )
        finally:
            pending_events.pop(request_id, None)
            completed_requests.pop(request_id, None)

    except Exception as e:
        return web.json_response(
            {"ok": False, "error": str(e)},
            status=500
        )


async def handle_http_domain_sync(request):
    """HTTP endpoint: Sync domains from SQLite to browser extension storage.

    IMPORTANT: This broadcasts the sync to ALL connected browsers, not just the most recent.
    This ensures that when the CLI retries a command after adding a domain, it works
    regardless of which browser tab/window receives the retry request.
    """
    try:
        from inspekt.services.domain_service import get_domain_service
        from datetime import datetime, timezone

        # Get domains from SQLite if not provided in request
        data = await request.json() if request.can_read_body and request.content_length else {}
        domains = data.get("domains")

        if not domains:
            # Fetch from SQLite
            domain_service = get_domain_service()
            domains_list = domain_service.get_all_domains()

            # Convert to browser storage format
            domains = {}
            for item in domains_list:
                dt = datetime.fromtimestamp(item["added_at"], tz=timezone.utc)
                iso_timestamp = dt.isoformat().replace("+00:00", "Z")

                domains[item["domain"]] = {
                    "addedAt": iso_timestamp,
                    "permanent": item["permanent"]
                }

        # Check if any browsers are connected
        if not active_connections:
            return web.json_response(
                {"ok": False, "error": "No browser connected. If Chrome is open, make sure you're on a regular webpage (not chrome://, new tab, or extension pages where content scripts can't run)."},
                status=503
            )

        # Broadcast sync to ALL connected browsers
        # This ensures all browsers have the updated domain list
        synced_count = 0
        errors = []
        events = []

        for ws in list(active_connections):
            request_id = str(uuid.uuid4())
            message = {
                "type": "SYNC_ALLOWED_DOMAINS",
                "requestId": request_id,
                "domains": domains
            }

            # Store pending request
            pending_requests[request_id] = {
                "timestamp": time.time(),
                "type": "SYNC_ALLOWED_DOMAINS"
            }

            try:
                await ws.send_json(message)

                # Create event for this request
                event = asyncio.Event()
                pending_events[request_id] = event
                events.append((request_id, event, ws))
            except Exception as e:
                errors.append(f"Failed to send to browser: {e}")
                pending_requests.pop(request_id, None)

        if not events:
            return web.json_response(
                {"ok": False, "error": "Failed to send sync to any browser"},
                status=500
            )

        # Wait for at least one response (with timeout)
        # We don't need ALL browsers to respond, just confirmation from at least one
        try:
            # Wait for first response
            done, pending_tasks = await asyncio.wait(
                [asyncio.create_task(e.wait()) for _, e, _ in events],
                timeout=10.0,
                return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel remaining waits
            for task in pending_tasks:
                task.cancel()

            # Count successful syncs
            for request_id, event, ws in events:
                result = completed_requests.get(request_id, {})
                response = result.get("response", {})
                if response.get("ok"):
                    synced_count += 1

                # Clean up
                pending_events.pop(request_id, None)
                completed_requests.pop(request_id, None)

            if synced_count > 0:
                return web.json_response({
                    "ok": True,
                    "synced": len(domains),
                    "browsers_synced": synced_count
                })
            else:
                return web.json_response({
                    "ok": False,
                    "error": "No browser confirmed sync"
                })

        except asyncio.TimeoutError:
            # Clean up all pending
            for request_id, _, _ in events:
                pending_events.pop(request_id, None)
                completed_requests.pop(request_id, None)

            return web.json_response(
                {"ok": False, "error": "Request timed out"},
                status=504
            )

    except Exception as e:
        return web.json_response(
            {"ok": False, "error": str(e)},
            status=500
        )


# ============================================================================
# Navigation Endpoint
# ============================================================================

async def handle_http_navigate(request):
    """HTTP endpoint: Navigate browser to a URL.

    Uses chrome.tabs.update() in the extension background script instead of
    window.location.href JavaScript, which properly handles navigation without
    destroying the execution context.
    """
    try:
        data = await request.json()
        url = data.get("url")
        wait_for = data.get("waitFor")
        timeout = data.get("timeout", 30)

        if not url:
            return web.json_response(
                {"ok": False, "error": "Missing 'url' parameter"},
                status=400
            )

        if not url.startswith(("http://", "https://")):
            return web.json_response(
                {"ok": False, "error": "URL must start with http:// or https://"},
                status=400
            )

        # Send message to extension via WebSocket
        if not most_recent_connection or most_recent_connection not in active_connections:
            print(f"[Bridge /navigate] No browser connected - user may be on a Chrome internal page")
            return web.json_response(
                {"ok": False, "error": "No browser connected. If Chrome is open, make sure you're on a regular webpage (not chrome://, new tab, or extension pages where content scripts can't run)."},
                status=503
            )

        request_id = str(uuid.uuid4())
        message = {
            "type": "NAVIGATE",
            "requestId": request_id,
            "url": url,
            "waitFor": wait_for,
            "timeout": timeout,
        }

        print(f"[Bridge /navigate] Sending NAVIGATE message: {url} (requestId: {request_id}, timeout: {timeout}s)")

        # Store pending request
        pending_requests[request_id] = {
            "timestamp": time.time(),
            "type": "NAVIGATE"
        }

        # Send to browser
        await most_recent_connection.send_json(message)
        print(f"[Bridge /navigate] Message sent, waiting for callback…")

        # Wait for response (with timeout - navigation can take longer)
        event = asyncio.Event()
        pending_events[request_id] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=float(timeout))
            result = completed_requests.get(request_id, {})
            return web.json_response(result.get("response", {"ok": False, "error": "No response"}))
        except asyncio.TimeoutError:
            return web.json_response(
                {"ok": False, "error": f"Navigation timed out after {timeout}s"},
                status=504
            )
        finally:
            pending_events.pop(request_id, None)
            completed_requests.pop(request_id, None)

    except Exception as e:
        return web.json_response(
            {"ok": False, "error": str(e)},
            status=500
        )


async def handle_http_navigate_callback(request):
    """HTTP endpoint: Receive navigation result callback from extension background script.

    This endpoint receives the navigation result directly from the extension's background
    script, bypassing the content script which gets destroyed during page navigation.
    """
    global most_recent_connection

    try:
        data = await request.json()
        request_id = data.get("requestId")
        response = data.get("response", {})

        if not request_id:
            return web.json_response(
                {"ok": False, "error": "Missing 'requestId' parameter"},
                status=400
            )

        # Check if there's a pending request waiting for this callback
        if request_id in pending_events:
            # Navigation completed - wait a moment for new content script to connect
            # This ensures the next command will have a valid WebSocket connection
            if response.get("ok"):
                # Wait up to 2 seconds for a new WebSocket connection
                for _ in range(20):
                    await asyncio.sleep(0.1)
                    if most_recent_connection and most_recent_connection in active_connections:
                        # Check if it's a fresh connection (connected after navigation started)
                        break

            # Store the response and signal the waiting coroutine
            completed_requests[request_id] = {"response": response}
            pending_events[request_id].set()
            return web.json_response({"ok": True, "message": "Callback received"})
        else:
            # Request might have already timed out
            return web.json_response(
                {"ok": False, "error": "No pending request found for this requestId"},
                status=404
            )

    except Exception as e:
        return web.json_response(
            {"ok": False, "error": str(e)},
            status=500
        )


# ============================================================================
# CSP Bypass Endpoints
# ============================================================================

async def handle_http_csp_bypass_enable(request):
    """HTTP endpoint: Enable CSP bypass for a domain."""
    try:
        data = await request.json()
        domain = data.get("domain")

        if not domain:
            return web.json_response(
                {"ok": False, "error": "Missing 'domain' parameter"},
                status=400
            )

        # Send message to extension via WebSocket
        if not most_recent_connection or most_recent_connection not in active_connections:
            return web.json_response(
                {"ok": False, "error": "No browser connected. If Chrome is open, make sure you're on a regular webpage (not chrome://, new tab, or extension pages where content scripts can't run)."},
                status=503
            )

        request_id = str(uuid.uuid4())
        message = {
            "type": "CSP_BYPASS_ENABLE",
            "requestId": request_id,
            "domain": domain
        }

        # Store pending request
        pending_requests[request_id] = {
            "timestamp": time.time(),
            "type": "CSP_BYPASS_ENABLE"
        }

        # Send to browser
        await most_recent_connection.send_json(message)

        # Wait for response (with timeout)
        event = asyncio.Event()
        pending_events[request_id] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=10.0)
            result = completed_requests.get(request_id, {})
            return web.json_response(result.get("response", {"ok": False, "error": "No response"}))
        except asyncio.TimeoutError:
            return web.json_response(
                {"ok": False, "error": "Request timed out"},
                status=504
            )
        finally:
            pending_events.pop(request_id, None)
            completed_requests.pop(request_id, None)

    except Exception as e:
        return web.json_response(
            {"ok": False, "error": str(e)},
            status=500
        )


async def handle_http_csp_bypass_disable(request):
    """HTTP endpoint: Disable CSP bypass for a domain."""
    try:
        data = await request.json()
        domain = data.get("domain")

        if not domain:
            return web.json_response(
                {"ok": False, "error": "Missing 'domain' parameter"},
                status=400
            )

        # Send message to extension via WebSocket
        if not most_recent_connection or most_recent_connection not in active_connections:
            return web.json_response(
                {"ok": False, "error": "No browser connected. If Chrome is open, make sure you're on a regular webpage (not chrome://, new tab, or extension pages where content scripts can't run)."},
                status=503
            )

        request_id = str(uuid.uuid4())
        message = {
            "type": "CSP_BYPASS_DISABLE",
            "requestId": request_id,
            "domain": domain
        }

        # Store pending request
        pending_requests[request_id] = {
            "timestamp": time.time(),
            "type": "CSP_BYPASS_DISABLE"
        }

        # Send to browser
        await most_recent_connection.send_json(message)

        # Wait for response (with timeout)
        event = asyncio.Event()
        pending_events[request_id] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=10.0)
            result = completed_requests.get(request_id, {})
            return web.json_response(result.get("response", {"ok": False, "error": "No response"}))
        except asyncio.TimeoutError:
            return web.json_response(
                {"ok": False, "error": "Request timed out"},
                status=504
            )
        finally:
            pending_events.pop(request_id, None)
            completed_requests.pop(request_id, None)

    except Exception as e:
        return web.json_response(
            {"ok": False, "error": str(e)},
            status=500
        )


async def handle_http_csp_bypass_status(request):
    """HTTP endpoint: Get CSP bypass status for a domain."""
    try:
        # Get domain from query string or JSON body
        domain = request.query.get("domain")

        if not domain:
            try:
                data = await request.json()
                domain = data.get("domain")
            except Exception:
                pass

        if not domain:
            return web.json_response(
                {"ok": False, "error": "Missing 'domain' parameter"},
                status=400
            )

        # Send message to extension via WebSocket
        if not most_recent_connection or most_recent_connection not in active_connections:
            return web.json_response(
                {"ok": False, "error": "No browser connected. If Chrome is open, make sure you're on a regular webpage (not chrome://, new tab, or extension pages where content scripts can't run)."},
                status=503
            )

        request_id = str(uuid.uuid4())
        message = {
            "type": "CSP_BYPASS_STATUS",
            "requestId": request_id,
            "domain": domain
        }

        # Store pending request
        pending_requests[request_id] = {
            "timestamp": time.time(),
            "type": "CSP_BYPASS_STATUS"
        }

        # Send to browser
        await most_recent_connection.send_json(message)

        # Wait for response (with timeout)
        event = asyncio.Event()
        pending_events[request_id] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=10.0)
            result = completed_requests.get(request_id, {})
            return web.json_response(result.get("response", {"ok": False, "error": "No response"}))
        except asyncio.TimeoutError:
            return web.json_response(
                {"ok": False, "error": "Request timed out"},
                status=504
            )
        finally:
            pending_events.pop(request_id, None)
            completed_requests.pop(request_id, None)

    except Exception as e:
        return web.json_response(
            {"ok": False, "error": str(e)},
            status=500
        )


async def handle_http_csp_bypass_global(request):
    """HTTP endpoint: Enable/disable CSP bypass for ALL domains globally."""
    try:
        data = await request.json()
        enabled = data.get("enabled")

        if enabled is None:
            return web.json_response(
                {"ok": False, "error": "Missing 'enabled' parameter (true/false)"},
                status=400
            )

        # Send message to extension via WebSocket
        if not most_recent_connection or most_recent_connection not in active_connections:
            return web.json_response(
                {"ok": False, "error": "No browser connected. If Chrome is open, make sure you're on a regular webpage (not chrome://, new tab, or extension pages where content scripts can't run)."},
                status=503
            )

        request_id = str(uuid.uuid4())
        message = {
            "type": "CSP_BYPASS_GLOBAL",
            "requestId": request_id,
            "enabled": bool(enabled)
        }

        # Store pending request
        pending_requests[request_id] = {
            "timestamp": time.time(),
            "type": "CSP_BYPASS_GLOBAL"
        }

        # Send to browser
        await most_recent_connection.send_json(message)

        # Wait for response (with timeout)
        event = asyncio.Event()
        pending_events[request_id] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=10.0)
            result = completed_requests.get(request_id, {})
            return web.json_response(result.get("response", {"ok": False, "error": "No response"}))
        except asyncio.TimeoutError:
            return web.json_response(
                {"ok": False, "error": "Request timed out"},
                status=504
            )
        finally:
            pending_events.pop(request_id, None)
            completed_requests.pop(request_id, None)

    except Exception as e:
        return web.json_response(
            {"ok": False, "error": str(e)},
            status=500
        )


async def handle_http_csp_bypass_global_status(request):
    """HTTP endpoint: Get global CSP bypass status."""
    try:
        # Status query: if no browser is connected, there's no CSP bypass
        # active by definition. Return 200 instead of 503 so UI clients
        # that poll this on an empty bridge don't spam the log.
        if not most_recent_connection or most_recent_connection not in active_connections:
            return web.json_response({"ok": True, "enabled": False})

        request_id = str(uuid.uuid4())
        message = {
            "type": "CSP_BYPASS_GLOBAL_STATUS",
            "requestId": request_id
        }

        # Store pending request
        pending_requests[request_id] = {
            "timestamp": time.time(),
            "type": "CSP_BYPASS_GLOBAL_STATUS"
        }

        # Send to browser
        await most_recent_connection.send_json(message)

        # Wait for response (with timeout)
        event = asyncio.Event()
        pending_events[request_id] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=10.0)
            result = completed_requests.get(request_id, {})
            return web.json_response(result.get("response", {"ok": False, "error": "No response"}))
        except asyncio.TimeoutError:
            return web.json_response(
                {"ok": False, "error": "Request timed out"},
                status=504
            )
        finally:
            pending_events.pop(request_id, None)
            completed_requests.pop(request_id, None)

    except Exception as e:
        return web.json_response(
            {"ok": False, "error": str(e)},
            status=500
        )


@web.middleware
async def cors_middleware(request, handler):
    """CORS middleware to allow cross-origin requests from dashboard."""
    # Handle preflight OPTIONS requests
    if request.method == "OPTIONS":
        response = web.Response()
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    # Process the request
    response = await handler(request)

    # Add CORS headers to response
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"

    return response


async def handle_http_get_har(request):
    """HTTP endpoint: Get HAR (HTTP Archive) data from DevTools.

    This requires the Chrome DevTools panel to be open for the active tab.
    Returns full network request data including status codes, headers, and timing.

    If DevTools is not open, returns an error with a hint to use `inspekt network`
    for basic network data via the Performance API.
    """
    global most_recent_connection

    if most_recent_connection is None:
        return web.json_response(
            {"ok": False, "error": "No browser connected. If Chrome is open, make sure you're on a regular webpage (not chrome://, new tab, or extension pages where content scripts can't run)."},
            status=503
        )

    request_id = str(uuid.uuid4())
    message = {
        "type": "GET_HAR",
        "requestId": request_id
    }

    # Store pending request
    pending_requests[request_id] = {
        "timestamp": time.time(),
        "type": "GET_HAR"
    }

    # Send to browser
    await most_recent_connection.send_json(message)

    # Wait for response (with timeout)
    event = asyncio.Event()
    pending_events[request_id] = event

    try:
        await asyncio.wait_for(event.wait(), timeout=15.0)
    except asyncio.TimeoutError:
        pending_requests.pop(request_id, None)
        pending_events.pop(request_id, None)
        return web.json_response(
            {
                "ok": False,
                "error": "HAR request timed out. Is Chrome DevTools open?",
                "hint": "Open DevTools (F12) and refresh the page, then try again."
            },
            status=504
        )

    # Get result
    result = completed_requests.pop(request_id, None)
    pending_events.pop(request_id, None)

    if result is None:
        return web.json_response(
            {"ok": False, "error": "No response received"},
            status=500
        )

    return web.json_response(result.get("response", result))


async def handle_http_get_console_logs(request):
    """HTTP endpoint: Get captured console logs from browser.

    Returns console.log/error/warn/info/debug messages that were captured
    since the page loaded (or since last clear).
    """
    global most_recent_connection

    if most_recent_connection is None:
        return web.json_response(
            {"ok": False, "error": "No browser connected. If Chrome is open, make sure you're on a regular webpage (not chrome://, new tab, or extension pages where content scripts can't run)."},
            status=503
        )

    request_id = str(uuid.uuid4())
    message = {
        "type": "GET_CONSOLE_LOGS",
        "requestId": request_id
    }

    # Store pending request
    pending_requests[request_id] = {
        "timestamp": time.time(),
        "type": "GET_CONSOLE_LOGS"
    }

    # Send to browser
    await most_recent_connection.send_json(message)

    # Wait for response (with timeout)
    event = asyncio.Event()
    pending_events[request_id] = event

    try:
        await asyncio.wait_for(event.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        pending_requests.pop(request_id, None)
        pending_events.pop(request_id, None)
        return web.json_response(
            {"ok": False, "error": "Console logs request timed out"},
            status=504
        )

    # Get result
    result = completed_requests.pop(request_id, None)
    pending_events.pop(request_id, None)

    if result is None:
        return web.json_response(
            {"ok": False, "error": "No response received"},
            status=500
        )

    return web.json_response(result.get("response", result))


async def handle_http_clear_console_logs(request):
    """HTTP endpoint: Clear the console logs buffer in browser."""
    global most_recent_connection

    if most_recent_connection is None:
        return web.json_response(
            {"ok": False, "error": "No browser connected. If Chrome is open, make sure you're on a regular webpage (not chrome://, new tab, or extension pages where content scripts can't run)."},
            status=503
        )

    request_id = str(uuid.uuid4())
    message = {
        "type": "CLEAR_CONSOLE_LOGS",
        "requestId": request_id
    }

    # Store pending request
    pending_requests[request_id] = {
        "timestamp": time.time(),
        "type": "CLEAR_CONSOLE_LOGS"
    }

    # Send to browser
    await most_recent_connection.send_json(message)

    # Wait for response (with timeout)
    event = asyncio.Event()
    pending_events[request_id] = event

    try:
        await asyncio.wait_for(event.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        pending_requests.pop(request_id, None)
        pending_events.pop(request_id, None)
        return web.json_response(
            {"ok": False, "error": "Clear console logs request timed out"},
            status=504
        )

    # Get result
    result = completed_requests.pop(request_id, None)
    pending_events.pop(request_id, None)

    if result is None:
        return web.json_response(
            {"ok": False, "error": "No response received"},
            status=500
        )

    return web.json_response(result.get("response", result))


# ============================================================================
# REPLAY MODE
# ============================================================================

async def handle_replay_mode_enable(request):
    """Enable replay mode in the browser extension.

    When enabled, the extension auto-injects the visual script on every page load.
    This eliminates the need for Python to poll and inject after navigation.
    """
    if most_recent_connection is None:
        return web.json_response(
            {"ok": False, "error": "No browser connected. If Chrome is open, make sure you're on a regular webpage (not chrome://, new tab, or extension pages where content scripts can't run)."},
            status=503
        )

    # Get the visual script from request body
    try:
        data = await request.json()
        visual_script = data.get("visualScript")
        if not visual_script:
            return web.json_response(
                {"ok": False, "error": "visualScript is required"},
                status=400
            )
    except Exception as e:
        return web.json_response(
            {"ok": False, "error": f"Invalid JSON: {e}"},
            status=400
        )

    request_id = str(uuid.uuid4())
    message = {
        "type": "REPLAY_MODE_ENABLE",
        "requestId": request_id,
        "visualScript": visual_script
    }

    # Store pending request
    pending_requests[request_id] = {
        "timestamp": time.time(),
        "type": "REPLAY_MODE_ENABLE"
    }

    # Send to browser
    print(f"[Bridge] Sending REPLAY_MODE_ENABLE to browser (script length: {len(visual_script)})")
    await most_recent_connection.send_json(message)

    # Wait for response (with timeout)
    event = asyncio.Event()
    pending_events[request_id] = event

    try:
        await asyncio.wait_for(event.wait(), timeout=10.0)
        print("[Bridge] REPLAY_MODE_ENABLE response received")
    except asyncio.TimeoutError:
        print("[Bridge] REPLAY_MODE_ENABLE timed out!")
        pending_requests.pop(request_id, None)
        pending_events.pop(request_id, None)
        return web.json_response(
            {"ok": False, "error": "Replay mode enable request timed out"},
            status=504
        )

    # Get result
    result = completed_requests.pop(request_id, None)
    pending_events.pop(request_id, None)

    if result is None:
        return web.json_response(
            {"ok": False, "error": "No response received"},
            status=500
        )

    return web.json_response(result.get("response", result))


async def handle_replay_mode_disable(request):
    """Disable replay mode in the browser extension."""
    if most_recent_connection is None:
        return web.json_response(
            {"ok": False, "error": "No browser connected. If Chrome is open, make sure you're on a regular webpage (not chrome://, new tab, or extension pages where content scripts can't run)."},
            status=503
        )

    request_id = str(uuid.uuid4())
    message = {
        "type": "REPLAY_MODE_DISABLE",
        "requestId": request_id
    }

    # Store pending request
    pending_requests[request_id] = {
        "timestamp": time.time(),
        "type": "REPLAY_MODE_DISABLE"
    }

    # Send to browser
    await most_recent_connection.send_json(message)

    # Wait for response (with timeout)
    event = asyncio.Event()
    pending_events[request_id] = event

    try:
        await asyncio.wait_for(event.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        pending_requests.pop(request_id, None)
        pending_events.pop(request_id, None)
        return web.json_response(
            {"ok": False, "error": "Replay mode disable request timed out"},
            status=504
        )

    # Get result
    result = completed_requests.pop(request_id, None)
    pending_events.pop(request_id, None)

    if result is None:
        return web.json_response(
            {"ok": False, "error": "No response received"},
            status=500
        )

    return web.json_response(result.get("response", result))


async def handle_replay_mode_status(request):
    """Get replay mode status from the browser extension."""
    if most_recent_connection is None:
        return web.json_response(
            {"ok": False, "error": "No browser connected. If Chrome is open, make sure you're on a regular webpage (not chrome://, new tab, or extension pages where content scripts can't run)."},
            status=503
        )

    request_id = str(uuid.uuid4())
    message = {
        "type": "REPLAY_MODE_STATUS",
        "requestId": request_id
    }

    # Store pending request
    pending_requests[request_id] = {
        "timestamp": time.time(),
        "type": "REPLAY_MODE_STATUS"
    }

    # Send to browser
    await most_recent_connection.send_json(message)

    # Wait for response (with timeout)
    event = asyncio.Event()
    pending_events[request_id] = event

    try:
        await asyncio.wait_for(event.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        pending_requests.pop(request_id, None)
        pending_events.pop(request_id, None)
        return web.json_response(
            {"ok": False, "error": "Replay mode status request timed out"},
            status=504
        )

    # Get result
    result = completed_requests.pop(request_id, None)
    pending_events.pop(request_id, None)

    if result is None:
        return web.json_response(
            {"ok": False, "error": "No response received"},
            status=500
        )

    return web.json_response(result.get("response", result))


async def handle_static_singlefile(request):
    """Serve the combined SingleFile library as a single JavaScript file."""
    from pathlib import Path

    vendor_dir = Path(__file__).parent / "scripts" / "vendor" / "singlefile"

    # Files must be loaded in this order
    library_files = [
        "single-file-bootstrap.js",
        "single-file-hooks-frames.js",
        "single-file.js",
    ]

    try:
        scripts = []
        for filename in library_files:
            filepath = vendor_dir / filename
            if not filepath.exists():
                return web.Response(
                    text=f"// Error: {filename} not found",
                    content_type="application/javascript",
                    status=404
                )
            with open(filepath, encoding='utf-8') as f:
                scripts.append(f"// === {filename} ===\n{f.read()}")

        combined = "\n\n".join(scripts)

        return web.Response(
            text=combined,
            content_type="application/javascript",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=86400",  # Cache for 1 day
            }
        )
    except Exception as e:
        return web.Response(
            text=f"// Error loading SingleFile: {e}",
            content_type="application/javascript",
            status=500
        )


# ============================================================================
# SCREENCAST (VIDEO RECORDING) ENDPOINTS
# ============================================================================

async def handle_screencast_start(request):
    """HTTP endpoint: Start screencast recording.

    Initiates CDP Page.startScreencast on the browser to stream frames.
    Frames are buffered on the server until retrieved via /screencast/frames.
    """
    global most_recent_connection, screencast_active, screencast_frames, screencast_settings, screencast_interrupted

    # Clear any previous interrupt state
    screencast_interrupted = None

    if most_recent_connection is None:
        return web.json_response(
            {"ok": False, "error": "No browser connected. If Chrome is open, make sure you're on a regular webpage (not chrome://, new tab, or extension pages where content scripts can't run)."},
            status=503
        )

    if screencast_active:
        return web.json_response(
            {"ok": True, "message": "Screencast already active", "active": True}
        )

    # Get settings from request body
    try:
        body = await request.json()
    except Exception:
        body = {}

    fps = body.get("fps", 10)
    quality = body.get("quality", 80)
    format = body.get("format", "jpeg")

    # Store settings
    screencast_settings = {
        "fps": fps,
        "quality": quality,
        "format": format,
    }

    # Clear any existing frames
    screencast_frames = []

    # Send start command to browser
    request_id = str(uuid.uuid4())
    message = {
        "type": "START_SCREENCAST",
        "requestId": request_id,
        "settings": screencast_settings
    }

    pending_requests[request_id] = {
        "timestamp": time.time(),
        "type": "START_SCREENCAST"
    }

    print(f"[Bridge] Sending START_SCREENCAST to browser, requestId={request_id[:8]}…")
    await most_recent_connection.send_json(message)
    print(f"[Bridge] START_SCREENCAST sent, waiting for acknowledgment…")

    # Wait for acknowledgment
    event = asyncio.Event()
    pending_events[request_id] = event

    try:
        await asyncio.wait_for(event.wait(), timeout=10.0)
        print(f"[Bridge] START_SCREENCAST acknowledgment received")
    except asyncio.TimeoutError:
        print(f"[Bridge] START_SCREENCAST timed out after 10s - no acknowledgment received")
        pending_requests.pop(request_id, None)
        pending_events.pop(request_id, None)
        return web.json_response(
            {"ok": False, "error": "Screencast start timed out"},
            status=504
        )

    result = completed_requests.pop(request_id, None)
    pending_events.pop(request_id, None)

    if result and result.get("ok"):
        screencast_active = True
        return web.json_response({
            "ok": True,
            "message": "Screencast started",
            "settings": screencast_settings
        })
    else:
        error = result.get("error", "Unknown error") if result else "No response"
        return web.json_response(
            {"ok": False, "error": f"Failed to start screencast: {error}"},
            status=500
        )


async def handle_screencast_stop(request):
    """HTTP endpoint: Stop screencast recording.

    Stops CDP Page.stopScreencast on the browser.
    Any buffered frames can still be retrieved via /screencast/frames.
    Also clears the frame buffer to prevent memory leaks between sessions.
    """
    global most_recent_connection, screencast_active, screencast_frames

    if most_recent_connection is None:
        screencast_active = False
        frames_count = len(screencast_frames)
        # Don't clear buffer - let Python side collect remaining frames
        return web.json_response(
            {"ok": True, "message": "No browser connected, screencast marked inactive", "frames_buffered": frames_count}
        )

    if not screencast_active:
        frames_count = len(screencast_frames)
        # Don't clear buffer - let Python side collect remaining frames
        return web.json_response(
            {"ok": True, "message": "Screencast not active", "active": False, "frames_buffered": frames_count}
        )

    # Send stop command to browser
    request_id = str(uuid.uuid4())
    message = {
        "type": "STOP_SCREENCAST",
        "requestId": request_id
    }

    pending_requests[request_id] = {
        "timestamp": time.time(),
        "type": "STOP_SCREENCAST"
    }

    await most_recent_connection.send_json(message)

    # Wait for acknowledgment (short timeout - don't block if browser disconnected)
    event = asyncio.Event()
    pending_events[request_id] = event

    try:
        await asyncio.wait_for(event.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        # Stop anyway on timeout - browser may have disconnected
        print("[Bridge] Screencast stop acknowledgment timed out (browser may be disconnected)")

    pending_requests.pop(request_id, None)
    pending_events.pop(request_id, None)
    completed_requests.pop(request_id, None)

    screencast_active = False

    # Return frame count - buffer is NOT cleared here to allow collection after stop
    # The Python ScreencastCapture.stop() method will collect remaining frames
    # Buffer is cleared when frames are retrieved via /screencast/frames
    frames_count = len(screencast_frames)

    return web.json_response({
        "ok": True,
        "message": "Screencast stopped",
        "frames_buffered": frames_count
    })


async def handle_screencast_frames(request):
    """HTTP endpoint: Get buffered screencast frames.

    Returns all buffered frames and clears the buffer.
    Call this periodically during long recordings to prevent memory overflow.
    """
    global screencast_frames

    frames_to_return = screencast_frames.copy()
    screencast_frames = []  # Clear buffer after retrieval

    return web.json_response({
        "ok": True,
        "frames": frames_to_return,
        "count": len(frames_to_return),
        "active": screencast_active
    })


async def handle_screencast_status(request):
    """HTTP endpoint: Get screencast status."""
    return web.json_response({
        "ok": True,
        "active": screencast_active,
        "frames_buffered": len(screencast_frames),
        "settings": screencast_settings if screencast_active else None,
        "interrupted": screencast_interrupted
    })


async def handle_screencast_interrupted(request):
    """HTTP endpoint: Receive notification that screencast was interrupted.

    Called by background.js when the debugger is detached (e.g., user opens DevTools).
    This allows the CLI to know the recording was interrupted and inform the user.
    """
    global screencast_interrupted, screencast_active

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    reason = data.get("reason", "unknown")
    frames_captured = data.get("framesCaptured", 0)

    print(f"[Bridge] Screencast interrupted: {reason} (captured {frames_captured} frames)")

    screencast_interrupted = {
        "reason": reason,
        "frames_captured": frames_captured,
        "timestamp": time.time()
    }
    screencast_active = False

    return web.json_response({
        "ok": True,
        "message": f"Interrupt notification received: {reason}"
    })


async def handle_screencast_frame_post(request):
    """HTTP endpoint: Receive a single screencast frame via POST.

    This endpoint is used by the background.js to post frames directly,
    bypassing the content script WebSocket (which gets replaced on navigation).

    Auto-activates screencast on first frame received - this allows JavaScript
    postMessage path to start screencast without needing HTTP /screencast/start.
    """
    global screencast_frames, screencast_active

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    # Auto-activate on first frame (supports JavaScript postMessage start path)
    if not screencast_active:
        screencast_active = True
        print("[Bridge] Screencast auto-activated on first frame")

    if len(screencast_frames) >= screencast_max_frames:
        # Buffer full - drop oldest frame
        screencast_frames.pop(0)

    screencast_frames.append({
        "timestamp": data.get("timestamp", time.time()),
        "data": data.get("data", ""),  # Base64 encoded image
    })

    return web.json_response({"ok": True, "frames_buffered": len(screencast_frames)})


# Global storage for captured video (MediaRecorder output)
captured_video_data = None


async def handle_video_captured(request):
    """HTTP endpoint: Receive captured video data from MediaRecorder.

    This endpoint receives the complete WebM video data captured by the
    offscreen document using tabCapture + MediaRecorder.
    """
    global captured_video_data

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    captured_video_data = {
        "data": data.get("data", ""),  # Base64 encoded video
        "mimeType": data.get("mimeType", "video/webm"),
        "size": data.get("size", 0),
        "duration": data.get("duration", 0),
        "timestamp": time.time()
    }

    print(f"[Bridge] Received captured video: {captured_video_data['size']} bytes, {captured_video_data['duration']:.1f}s")

    return web.json_response({
        "ok": True,
        "size": captured_video_data["size"],
        "duration": captured_video_data["duration"]
    })


async def handle_video_get(request):
    """HTTP endpoint: Retrieve the captured video data.

    Returns the video data captured by MediaRecorder and clears the buffer.
    """
    global captured_video_data

    if not captured_video_data:
        return web.json_response({"ok": False, "error": "No captured video available"}, status=404)

    # Return and clear
    data = captured_video_data
    captured_video_data = None

    return web.json_response({
        "ok": True,
        "data": data["data"],
        "mimeType": data["mimeType"],
        "size": data["size"],
        "duration": data["duration"]
    })


def handle_screencast_frame(data: dict):
    """Handle incoming screencast frame from browser.

    Called by websocket_handler when a SCREENCAST_FRAME message arrives.
    """
    global screencast_frames

    if not screencast_active:
        return  # Ignore frames if not actively capturing

    if len(screencast_frames) >= screencast_max_frames:
        # Buffer full - drop oldest frame
        screencast_frames.pop(0)

    screencast_frames.append({
        "timestamp": data.get("timestamp", time.time()),
        "data": data.get("data", ""),  # Base64 encoded image
    })


# ============================================================================
# Audio Cue Endpoints (for video audio effects)
# ============================================================================


async def handle_audio_start(request):
    """HTTP endpoint: Start audio cue recording.

    Clears any existing cues and marks recording as active.
    Called when video recording starts with --include-effects.
    """
    global audio_cues, audio_recording_active, audio_recording_start_time

    audio_cues = []
    audio_recording_active = True
    audio_recording_start_time = time.time()

    return web.json_response({
        "ok": True,
        "message": "Audio cue recording started",
        "start_time": audio_recording_start_time
    })


async def handle_audio_stop(request):
    """HTTP endpoint: Stop audio cue recording.

    Marks recording as inactive. Cues are preserved for retrieval.
    """
    global audio_recording_active

    audio_recording_active = False
    cue_count = len(audio_cues)

    return web.json_response({
        "ok": True,
        "message": "Audio cue recording stopped",
        "cues_recorded": cue_count
    })


async def handle_audio_cue(request):
    """HTTP endpoint: Record an audio cue.

    Called by JavaScript when a sound effect plays during replay.
    Stores the timestamp and action type for later audio generation.
    """
    global audio_cues

    if not audio_recording_active:
        return web.json_response({
            "ok": False,
            "error": "Audio recording not active"
        })

    try:
        data = await request.json()
    except Exception:
        return web.json_response({
            "ok": False,
            "error": "Invalid JSON"
        })

    timestamp_ms = data.get("timestamp_ms", 0)
    action = data.get("action", "unknown")

    audio_cues.append({
        "timestamp_ms": timestamp_ms,
        "action": action
    })

    return web.json_response({
        "ok": True,
        "cues_buffered": len(audio_cues)
    })


async def handle_audio_cues(request):
    """HTTP endpoint: Get all recorded audio cues.

    Returns all cues and clears the buffer.
    Called after video encoding to generate the audio track.
    """
    global audio_cues

    cues_to_return = audio_cues.copy()
    audio_cues = []  # Clear buffer after retrieval

    return web.json_response({
        "ok": True,
        "cues": cues_to_return,
        "count": len(cues_to_return)
    })


async def handle_audio_status(request):
    """HTTP endpoint: Get audio recording status."""
    return web.json_response({
        "ok": True,
        "active": audio_recording_active,
        "cues_buffered": len(audio_cues),
        "start_time": audio_recording_start_time if audio_recording_active else None
    })


async def handle_http_proxy(request):
    """Proxy HTTP requests for the restricted VM terminal.

    Accepts a JSON payload with:
        url: Target URL (required)
        method: HTTP method (default: GET)
        headers: Request headers (default: {})
        body: Request body — dict for JSON or str for raw (default: None)
        timeout: Request timeout in seconds (default: 30)

    Only requests to domains in PROXY_ALLOWED_DOMAINS are permitted.
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)

    url = data.get("url")
    method = data.get("method", "GET").upper()
    headers = data.get("headers", {})
    body = data.get("body")
    timeout = data.get("timeout", 30)
    max_bytes = data.get("max_bytes")  # Optional: limit response body size

    if not url:
        return web.json_response({"ok": False, "error": "missing url"}, status=400)

    try:
        import aiohttp as _aiohttp

        ct = _aiohttp.ClientTimeout(total=timeout)
        async with _aiohttp.ClientSession(timeout=ct) as session:
            kwargs = {"headers": headers}
            if body is not None:
                if isinstance(body, dict):
                    kwargs["json"] = body
                else:
                    kwargs["data"] = body

            async with session.request(method, url, **kwargs) as resp:
                content_type = resp.headers.get("Content-Type", "")
                is_binary = not (
                    content_type.startswith("text/")
                    or "json" in content_type
                    or "xml" in content_type
                    or "javascript" in content_type
                )

                resp_headers = {k: v for k, v in resp.headers.items()}

                final_url = str(resp.url)

                if is_binary:
                    import base64
                    if max_bytes:
                        chunks = []
                        total = 0
                        while total < max_bytes:
                            chunk = await resp.content.read(min(65536, max_bytes - total))
                            if not chunk:
                                break
                            chunks.append(chunk)
                            total += len(chunk)
                        raw = b"".join(chunks)
                    else:
                        raw = await resp.read()
                    return web.json_response({
                        "ok": True,
                        "status": resp.status,
                        "headers": resp_headers,
                        "body": base64.b64encode(raw).decode(),
                        "binary": True,
                        "url": final_url,
                    })
                else:
                    if max_bytes:
                        # Read up to max_bytes — loop because chunked responses
                        # may return partial data from a single read() call
                        chunks = []
                        total = 0
                        while total < max_bytes:
                            chunk = await resp.content.read(min(65536, max_bytes - total))
                            if not chunk:
                                break
                            chunks.append(chunk)
                            total += len(chunk)
                        raw = b"".join(chunks)
                        text = raw.decode(resp.get_encoding() or "utf-8", errors="replace")
                    else:
                        text = await resp.text()
                    return web.json_response({
                        "ok": True,
                        "status": resp.status,
                        "headers": resp_headers,
                        "body": text,
                        "binary": False,
                        "url": final_url,
                    })

    except asyncio.TimeoutError:
        return web.json_response(
            {"ok": False, "error": "upstream timeout", "error_type": "timeout"},
            status=504,
        )
    except Exception as e:
        return web.json_response(
            {"ok": False, "error": str(e), "error_type": "connection"},
            status=502,
        )


async def main(enable_socket: bool = True, socket_path_override: Optional[str] = None):
    """Start HTTP, WebSocket, and Unix socket servers.

    Args:
        enable_socket: Whether to start the Unix socket server
        socket_path_override: Optional explicit socket path
    """
    print("Inspekt WebSocket Server (aiohttp)")
    print(f"WebSocket: ws://{HOST}:{PORT + 1}/ws")
    print(f"HTTP API: http://{HOST}:{PORT}")

    # Start Unix socket server
    sock_server = None
    if enable_socket:
        sock_path = Path(socket_path_override) if socket_path_override else None
        sock_server = await start_socket_server(sock_path)
        if sock_server:
            print(f"Socket: {socket_path}")
        else:
            print("Socket: disabled (failed to create)")
    else:
        print("Socket: disabled")

    print("")

    # Preload control.js into cache (async, no blocking!)
    try:
        await script_loader.preload_script_async("control.js")
        cached_scripts = script_loader.get_cached_scripts()
        print(f"✓ Preloaded {len(cached_scripts)} script(s): {', '.join(cached_scripts)}")
    except FileNotFoundError as e:
        print(f"✗ WARNING: {e}")
        print("  Auto-refocus will not work until file is available")
    print("")

    # Setup aiohttp app with CORS middleware
    # Increase client_max_size to 100MB for large video uploads from MediaRecorder
    app = web.Application(middlewares=[cors_middleware], client_max_size=100 * 1024 * 1024)

    # HTTP endpoints for CLI
    app.router.add_post("/run", handle_http_run)
    app.router.add_get("/result", handle_http_result)
    app.router.add_delete("/cancel", handle_http_cancel)
    app.router.add_get("/notifications", handle_http_notifications)
    app.router.add_get("/health", handle_http_health)
    app.router.add_post("/reinit-control", handle_http_reinit_control)

    # Instance management endpoints
    app.router.add_get("/instances", handle_http_instances_list)
    app.router.add_post("/instances/alias", handle_http_instance_alias_set)
    app.router.add_delete("/instances/alias", handle_http_instance_alias_remove)

    # Queue management endpoints
    app.router.add_get("/queue/status", handle_http_queue_status)
    app.router.add_post("/queue/clear", handle_http_queue_clear)

    # Domain management endpoints
    app.router.add_post("/domains/add", handle_http_domain_add)
    app.router.add_delete("/domains/remove", handle_http_domain_remove)
    app.router.add_get("/domains/list", handle_http_domain_list)
    app.router.add_post("/domains/bypass", handle_http_domain_bypass)
    app.router.add_post("/domains/sync", handle_http_domain_sync)

    # Navigation endpoint (uses chrome.tabs.update instead of JS injection)
    app.router.add_post("/navigate", handle_http_navigate)
    app.router.add_post("/navigate/callback", handle_http_navigate_callback)

    # CSP bypass endpoints
    app.router.add_post("/csp/enable", handle_http_csp_bypass_enable)
    app.router.add_post("/csp/disable", handle_http_csp_bypass_disable)
    app.router.add_get("/csp/status", handle_http_csp_bypass_status)
    app.router.add_post("/csp/status", handle_http_csp_bypass_status)  # Also support POST
    app.router.add_post("/csp/global", handle_http_csp_bypass_global)
    app.router.add_get("/csp/global", handle_http_csp_bypass_global_status)

    # Network/HAR endpoint
    app.router.add_get("/network/har", handle_http_get_har)

    # Console logs endpoints
    app.router.add_get("/console/logs", handle_http_get_console_logs)
    app.router.add_post("/console/clear", handle_http_clear_console_logs)

    # Replay mode endpoints
    app.router.add_post("/replay/enable", handle_replay_mode_enable)
    app.router.add_post("/replay/disable", handle_replay_mode_disable)
    app.router.add_get("/replay/status", handle_replay_mode_status)

    # Static file endpoint for SingleFile library
    app.router.add_get("/static/singlefile.js", handle_static_singlefile)

    # Screencast (video recording) endpoints
    app.router.add_post("/screencast/start", handle_screencast_start)
    app.router.add_post("/screencast/stop", handle_screencast_stop)
    app.router.add_get("/screencast/frames", handle_screencast_frames)
    app.router.add_get("/screencast/status", handle_screencast_status)
    app.router.add_post("/screencast/frame", handle_screencast_frame_post)  # Direct frame POST from background.js
    app.router.add_post("/screencast/interrupted", handle_screencast_interrupted)  # DevTools interrupt notification

    # Video capture endpoints (MediaRecorder output from tabCapture)
    app.router.add_post("/video/captured", handle_video_captured)  # Receive captured video from offscreen document
    app.router.add_get("/video/get", handle_video_get)  # Retrieve captured video

    # Audio cue endpoints (for video audio effects)
    app.router.add_post("/audio/start", handle_audio_start)
    app.router.add_post("/audio/stop", handle_audio_stop)
    app.router.add_post("/audio/cue", handle_audio_cue)
    app.router.add_get("/audio/cues", handle_audio_cues)
    app.router.add_get("/audio/status", handle_audio_status)

    # HTTP proxy for restricted VM terminal
    app.router.add_post("/proxy", handle_http_proxy)

    # WebSocket endpoint for browser
    app.router.add_get("/ws", websocket_handler)

    # Start server
    runner = web.AppRunner(app)
    await runner.setup()

    # HTTP server
    http_site = web.TCPSite(runner, HOST, PORT)
    await http_site.start()
    print(f"HTTP server running on http://{HOST}:{PORT}")

    # WebSocket server (same port, different path)
    ws_site = web.TCPSite(runner, HOST, PORT + 1)
    await ws_site.start()
    print(f"WebSocket server running on ws://{HOST}:{PORT + 1}/ws")

    # HTTPS server (if certificates are available)
    ssl_context = None
    cert_paths = [
        ("/opt/certs/cert.pem", "/opt/certs/key.pem"),  # Docker VM
        (os.path.expanduser("~/.inspekt/cert.pem"), os.path.expanduser("~/.inspekt/key.pem")),  # Local
    ]
    for cert_path, key_path in cert_paths:
        if os.path.exists(cert_path) and os.path.exists(key_path):
            import ssl
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(cert_path, key_path)
            break

    if ssl_context:
        https_site = web.TCPSite(runner, HOST, 443, ssl_context=ssl_context)
        await https_site.start()
        print(f"HTTPS server running on https://{HOST}:443")

    print("Ready for connections!")

    # Start background cleanup task
    asyncio.create_task(cleanup_watchdog())

    # Keep running until interrupted
    try:
        await asyncio.Event().wait()
    finally:
        # Clean up socket server
        if sock_server:
            sock_server.close()
            await sock_server.wait_closed()
            # Remove socket file
            if socket_path and socket_path.exists():
                try:
                    socket_path.unlink()
                except OSError:
                    pass


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(
        description="Inspekt WebSocket Bridge Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python bridge_ws.py                    # Start with defaults (socket enabled)
  python bridge_ws.py --no-socket        # Disable Unix socket transport
  python bridge_ws.py --socket /tmp/x.sock  # Use custom socket path
  python bridge_ws.py --isolated         # Docker VM mode (bypass all protections)
  python bridge_ws.py --host 0.0.0.0     # Allow external connections
  python bridge_ws.py --port 9000        # Use custom port
        """
    )
    parser.add_argument(
        "--isolated",
        action="store_true",
        help="Enable isolated mode (bypass all privacy protections). For Docker VM use only."
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to bind to (default: 8765)"
    )
    parser.add_argument(
        "--socket",
        type=str,
        default=None,
        metavar="PATH",
        help="Unix socket path (default: ~/.inspekt/inspekt.sock)"
    )
    parser.add_argument(
        "--no-socket",
        action="store_true",
        help="Disable Unix socket transport (HTTP only)"
    )

    args = parser.parse_args()

    # Set environment variable for isolated mode
    if args.isolated:
        os.environ["INSPEKT_ISOLATED"] = "1"
        print("=" * 50)
        print("ISOLATED MODE ENABLED")
        print("All privacy protections bypassed (Docker VM mode)")
        print("=" * 50)

    # Update global HOST/PORT
    HOST = args.host
    PORT = args.port

    # Determine socket settings
    enable_socket = not args.no_socket
    socket_path_arg = args.socket

    try:
        asyncio.run(main(enable_socket=enable_socket, socket_path_override=socket_path_arg))
    except KeyboardInterrupt:
        print("\nServer stopped")
