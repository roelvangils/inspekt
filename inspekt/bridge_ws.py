#!/usr/bin/env python3
"""
WebSocket-based bridge server using aiohttp (more compatible).
"""

import asyncio
import json
import time
import uuid
from typing import Any

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

# Cleanup old requests after 2 minutes (reduced from 5 to catch stuck requests faster)
MAX_REQUEST_AGE = 120

# Warn about requests stuck longer than this (seconds)
STUCK_REQUEST_THRESHOLD = 60

# Script loader service (singleton)
script_loader = ScriptLoader()

# Server tracking
server_start_time = time.time()  # Track server uptime
connection_times: dict = {}  # Track when each connection was established
total_requests_processed = 0  # Lifetime request counter
total_requests_succeeded = 0  # Count of successful requests
total_requests_failed = 0  # Count of failed requests
last_activity_time = time.time()  # Track last request/result activity


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
        import re
        match = re.search(r'Zen/([\d.]+)', ua)
        version = match.group(1) if match else ""
        return ("Zen Browser", version)

    # Detect Firefox
    if "Firefox/" in ua and "Seamonkey" not in ua:
        import re
        match = re.search(r'Firefox/([\d.]+)', ua)
        version = match.group(1) if match else ""
        return ("Firefox", version)

    # Detect Edge (Chromium-based)
    if "Edg/" in ua:
        import re
        match = re.search(r'Edg/([\d.]+)', ua)
        version = match.group(1) if match else ""
        return ("Edge", version)

    # Detect Chrome (but not Edge or other Chromium-based browsers)
    if "Chrome/" in ua and "Edg/" not in ua:
        import re
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
        import re
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
    Background task that proactively cleans up stale requests.
    Runs every 30 seconds and logs warnings for stuck requests.
    """
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
    print("Browser tab connected via WebSocket")
    print(f"Active connections: {len(active_connections)}")

    # Auto-sync domains to newly connected browser
    await sync_domains_to_browser(ws)

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
                            print(f"Received result for request {request_id}")

                            # Notify any waiting HTTP long-poll requests
                            if request_id in pending_events:
                                pending_events[request_id].set()
                                print(f"Notified waiting HTTP request for {request_id}")

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
                            "extensionVersion": data.get("extensionVersion")
                        }
                        browser_name = data.get("browserName", "Unknown")
                        page_title = data.get("title", "")[:50]
                        ext_version = data.get("extensionVersion", "unknown")
                        print(f"Browser info received: {browser_name} v{ext_version} - {page_title}")

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
        browser_info.pop(ws, None)
        connection_times.pop(ws, None)  # Clean up connection time tracking
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
    global most_recent_connection
    request_id = str(uuid.uuid4())
    pending_requests[request_id] = {
        "code": code,
        "timestamp": time.time(),
        "connection": None  # Will be set after selecting target
    }

    # Send to most recent active browser only
    message = json.dumps({"type": "execute", "request_id": request_id, "code": code})

    # Select target browser
    target_ws = None

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

    return request_id


async def handle_http_run(request):
    """HTTP endpoint: Submit code to run."""
    cleanup_old_requests()

    try:
        data = await request.json()
        code = data.get("code", "")
        browser_index = data.get("browser_index")  # Optional: target specific browser

        if not code or not isinstance(code, str):
            return web.json_response({"ok": False, "error": "missing code"}, status=400)

        request_id = await send_code_to_browser(code, browser_index=browser_index)

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
                {"ok": False, "error": "Request timeout. Please ensure the extension is installed in Firefox and/or Chrome, and that the Inspekt Panel is visible."}
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
    # Sort connections by connection time for consistent ordering
    sorted_connections = sorted(active_connections, key=lambda ws: connection_times.get(ws, current_time))

    browsers_list = []
    for ws in sorted_connections:
        info = browser_info.get(ws, {})
        connection_time = connection_times.get(ws, current_time)
        duration = current_time - connection_time

        # Parse User-Agent to get accurate browser name and version
        user_agent = info.get("userAgent", "")
        browser_name, browser_version = parse_user_agent(user_agent)

        browsers_list.append({
            "browser_name": browser_name,
            "browser_version": browser_version,
            "extension_version": info.get("extensionVersion"),
            "url": info.get("url", ""),
            "title": info.get("title", ""),
            "user_agent": user_agent,
            "is_most_recent": (ws == most_recent_connection),
            "connected_duration": duration
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
            "connected_browsers": len(active_connections),
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
                {"ok": False, "error": "No browser connected"},
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
                {"ok": False, "error": "No browser connected"},
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
                {"ok": False, "error": "No browser connected"},
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

        # Send message to extension via WebSocket
        if not most_recent_connection or most_recent_connection not in active_connections:
            return web.json_response(
                {"ok": False, "error": "No browser connected"},
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
                {"ok": False, "error": "No browser connected"},
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
            {"ok": False, "error": "No browser connected"},
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
            {"ok": False, "error": "No browser connected"},
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
            {"ok": False, "error": "No browser connected"},
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


async def main():
    """Start HTTP and WebSocket server."""
    print("Inspekt WebSocket Server (aiohttp)")
    print(f"WebSocket: ws://{HOST}:{PORT + 1}/ws")
    print(f"HTTP API: http://{HOST}:{PORT}")
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
    app = web.Application(middlewares=[cors_middleware])

    # HTTP endpoints for CLI
    app.router.add_post("/run", handle_http_run)
    app.router.add_get("/result", handle_http_result)
    app.router.add_delete("/cancel", handle_http_cancel)
    app.router.add_get("/notifications", handle_http_notifications)
    app.router.add_get("/health", handle_http_health)
    app.router.add_post("/reinit-control", handle_http_reinit_control)

    # Queue management endpoints
    app.router.add_get("/queue/status", handle_http_queue_status)
    app.router.add_post("/queue/clear", handle_http_queue_clear)

    # Domain management endpoints
    app.router.add_post("/domains/add", handle_http_domain_add)
    app.router.add_delete("/domains/remove", handle_http_domain_remove)
    app.router.add_get("/domains/list", handle_http_domain_list)
    app.router.add_post("/domains/bypass", handle_http_domain_bypass)
    app.router.add_post("/domains/sync", handle_http_domain_sync)

    # Network/HAR endpoint
    app.router.add_get("/network/har", handle_http_get_har)

    # Console logs endpoints
    app.router.add_get("/console/logs", handle_http_get_console_logs)
    app.router.add_post("/console/clear", handle_http_clear_console_logs)

    # Static file endpoint for SingleFile library
    app.router.add_get("/static/singlefile.js", handle_static_singlefile)

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
    print("Ready for connections!")

    # Start background cleanup task
    asyncio.create_task(cleanup_watchdog())

    # Keep running
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped")
