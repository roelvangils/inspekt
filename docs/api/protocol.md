# Inspekt Protocol Specification

**Protocol Version**: 3.4 (current userscript version)
**Server Implementation**: aiohttp WebSocket
**Client Implementation**: Browser-side JavaScript (Tampermonkey)
**Last Updated**: 2025-10-27

---

## Table of Contents

- [Overview](#overview)
- [Connection Lifecycle](#connection-lifecycle)
- [Message Format](#message-format)
- [Message Types](#message-types)
- [Error Handling](#error-handling)
- [Versioning](#versioning)
- [Security Considerations](#security-considerations)
- [Future Enhancements](#future-enhancements)

---

## Overview

Inspekt uses a WebSocket-based protocol for bidirectional communication between the CLI (via HTTP), server, and browser. The protocol is JSON-based with typed messages.

### Communication Architecture

```
┌─────────────┐                      ┌──────────────┐
│  CLI Client │                      │   Browser    │
│  (requests) │                      │ (Tampermonkey)│
└──────┬──────┘                      └──────┬───────┘
       │                                    │
       │ HTTP POST /run                    │ WebSocket
       │ HTTP GET /result                  │ ws://127.0.0.1:8766/ws
       │ HTTP GET /health                  │
       │ HTTP GET /notifications           │
       │ HTTP POST /reinit-control         │
       │                                    │
       ▼                                    ▼
┌────────────────────────────────────────────────────┐
│            Bridge Server (aiohttp)                 │
│  HTTP :8765 (CLI ← → Server)                       │
│  WebSocket :8766/ws (Server ← → Browser)           │
└────────────────────────────────────────────────────┘
```

### Protocol Flow

1. **Browser** connects via WebSocket on page load
2. **CLI** sends HTTP POST to server with JavaScript code
3. **Server** generates UUID request_id, stores pending request
4. **Server** broadcasts execute message via WebSocket
5. **Browser** receives message, evaluates JavaScript
6. **Browser** sends result message via WebSocket
7. **Server** moves request from pending to completed
8. **CLI** polls GET /result until complete
9. **CLI** displays result to user

---

## Connection Lifecycle

### Browser WebSocket Connection

```
Page Load
   ↓
Connect to ws://127.0.0.1:8766/ws
   ↓
[Connected] ──→ Listen for messages
   │               ↓
   │            Execute code
   │               ↓
   │            Send result
   │               ↓
   │            (Repeat)
   │
   ↓ (Page navigation)
Disconnect
   ↓
Wait 3 seconds
   ↓
Reconnect (Auto-retry)
```

### Auto-Reconnect Behavior

- **Reconnect delay**: 3 seconds
- **Max retries**: Infinite (continues until page closes)
- **Exponential backoff**: No (fixed 3s delay)
- **Pending requests**: Resent to new connection on reconnect

### Connection States

| State | Description | Actions |
|-------|-------------|---------|
| `CONNECTING` | WebSocket opening | Wait |
| `OPEN` | Connected and ready | Send/receive messages |
| `CLOSING` | Closing gracefully | Finish pending operations |
| `CLOSED` | Disconnected | Trigger reconnect after 3s |

---

## Message Format

All messages are JSON objects with a `type` field.

### General Structure

```json
{
    "type": "message_type",
    "field1": "value1",
    "field2": "value2"
}
```

**Rules**:
- All messages MUST be valid JSON
- All messages MUST have a `type` field (string)
- Unknown `type` values SHOULD be ignored (forward compatibility)
- Field names are kebab-case for consistency (e.g., `request_id`)

---

## Message Types

### 1. Execute Request (Server → Browser)

**Purpose**: Request browser to execute JavaScript code

**Direction**: Server → Browser (via WebSocket)

**Format**:
```json
{
    "type": "execute",
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "code": "document.title"
}
```

**Fields**:
- `type` (string): Always "execute"
- `request_id` (string): UUID v4 identifying this request
- `code` (string): JavaScript code to evaluate

**Example**:
```json
{
    "type": "execute",
    "request_id": "a3f2b1c0-1234-5678-90ab-cdef12345678",
    "code": "Array.from(document.querySelectorAll('a')).map(a => a.href)"
}
```

---

### 2. Result Response (Browser → Server)

**Purpose**: Browser sends execution result back to server

**Direction**: Browser → Server (via WebSocket)

**Format** (Success):
```json
{
    "type": "result",
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "ok": true,
    "result": "Example Domain",
    "url": "https://example.com",
    "title": "Example Domain"
}
```

**Format** (Error):
```json
{
    "type": "result",
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "ok": false,
    "result": null,
    "error": "ReferenceError: foo is not defined",
    "url": "https://example.com",
    "title": "Example Domain"
}
```

**Fields**:
- `type` (string): Always "result"
- `request_id` (string): UUID matching the execute request
- `ok` (boolean): True if execution succeeded, false if error
- `result` (any): Return value from JavaScript (JSON-serializable)
- `error` (string | null): Error message if ok=false
- `url` (string): Current page URL
- `title` (string): Current page title

**Serialization Rules**:
- `result` is JSON.stringify'd automatically
- `undefined` → `null`
- Functions → `null`
- Circular references → Error (cannot serialize)

---

### 3. Reinit Control Request (Browser → Server)

**Purpose**: Browser requests automatic reinitialization of control mode after page reload

**Direction**: Browser → Server (via WebSocket)

**Format**:
```json
{
    "type": "reinit_control",
    "config": {
        "auto-refocus": "only-spa",
        "focus-outline": "custom",
        "navigation-wrap": true,
        "verbose": true
    }
}
```

**Fields**:
- `type` (string): Always "reinit_control"
- `config` (object): Control mode configuration settings

**Response**: Server sends execute message with control.js script

---

### 4. Refocus Notification (Browser → Server)

**Purpose**: Browser notifies server of refocus operation result (for verbose output)

**Direction**: Browser → Server (via WebSocket)

**Format**:
```json
{
    "type": "refocus_notification",
    "success": true,
    "message": "Refocused to element: <button>Submit</button>"
}
```

**Fields**:
- `type` (string): Always "refocus_notification"
- `success` (boolean): Whether refocus succeeded
- `message` (string): Human-readable status message

**Handling**: Server stores notification in `pending_notifications` list for CLI to poll

---

### 5. Ping (Browser → Server)

**Purpose**: Keepalive to detect connection health

**Direction**: Browser → Server (via WebSocket)

**Format**:
```json
{
    "type": "ping"
}
```

**Response**: Server immediately sends pong

---

### 6. Pong (Server → Browser)

**Purpose**: Acknowledge ping keepalive

**Direction**: Server → Browser (via WebSocket)

**Format**:
```json
{
    "type": "pong"
}
```

**Fields**: None (just type)

---

## HTTP API Endpoints

### POST /run

**Purpose**: Submit JavaScript code for execution

**Request**:
```json
{
    "code": "document.title"
}
```

**Response** (Success):
```json
{
    "ok": true,
    "request_id": "a3f2b1c0-1234-5678-90ab-cdef12345678"
}
```

**Response** (Error):
```json
{
    "ok": false,
    "error": "missing code"
}
```

**Status Codes**:
- `200 OK`: Request submitted successfully
- `400 Bad Request`: Invalid request (missing code)
- `500 Internal Server Error`: Server error

---

### GET /result

**Purpose**: Get result of previously submitted request

**Query Parameters**:
- `request_id` (string, required): UUID of request

**Response** (Completed):
```json
{
    "ok": true,
    "result": "Example Domain",
    "url": "https://example.com",
    "title": "Example Domain"
}
```

**Response** (Pending):
```json
{
    "ok": false,
    "status": "pending"
}
```

**Response** (Timeout):
```json
{
    "ok": false,
    "error": "Request timeout: No browser connected"
}
```

**Response** (Not Found):
```json
{
    "ok": false,
    "error": "unknown request_id"
}
```

**Status Codes**:
- `200 OK`: Result available (check `ok` field)
- `400 Bad Request`: Missing request_id
- `404 Not Found`: Unknown request_id

**Polling Strategy**:
- Initial poll: 100ms
- Exponential backoff: Multiply by 1.5 each retry
- Max interval: 1 second
- Timeout: Configurable (default 10s)

---

### GET /health

**Purpose**: Check server health and status

**Response**:
```json
{
    "ok": true,
    "timestamp": 1698765432.123,
    "connected_browsers": 1,
    "pending": 0,
    "completed": 5
}
```

**Fields**:
- `ok` (boolean): Always true if server is running
- `timestamp` (float): Unix timestamp (seconds since epoch)
- `connected_browsers` (int): Number of active WebSocket connections
- `pending` (int): Number of pending requests
- `completed` (int): Number of completed requests in cache

**Use Case**: CLI checks if server is running before submitting requests

---

### GET /notifications

**Purpose**: Get pending notifications (e.g., refocus status)

**Response**:
```json
{
    "ok": true,
    "notifications": [
        {
            "type": "refocus",
            "success": true,
            "message": "Refocused to element: <button>Submit</button>",
            "timestamp": 1698765432.123
        }
    ]
}
```

**Behavior**:
- Returns all pending notifications
- Clears notification list on each request
- Empty array if no notifications

---

### POST /reinit-control

**Purpose**: Request auto-reinitialization of control mode

**Request**:
```json
{
    "config": {
        "auto-refocus": "only-spa",
        "verbose": true
    }
}
```

**Response**:
```json
{
    "ok": true,
    "request_id": "b4e3c2d1-5678-90ab-cdef-1234567890ab"
}
```

**Status Codes**:
- `200 OK`: Request submitted
- `500 Internal Server Error`: control.js not found or error

---

## Error Handling

### Browser-Side Errors

When JavaScript execution fails in browser:

```json
{
    "type": "result",
    "request_id": "...",
    "ok": false,
    "result": null,
    "error": "ReferenceError: foo is not defined",
    "url": "...",
    "title": "..."
}
```

**Common Error Types**:
- `SyntaxError`: Invalid JavaScript syntax
- `ReferenceError`: Undefined variable
- `TypeError`: Invalid type operation
- `SecurityError`: Violates same-origin policy

### Server-Side Errors

**No Browser Connected**:
```json
{
    "ok": false,
    "error": "Request timeout: No browser connected"
}
```

Triggered when:
- Request pending for >60 seconds
- No WebSocket connections active

**Invalid Request**:
```json
{
    "ok": false,
    "error": "missing code"
}
```

Triggered when:
- POST /run without `code` field
- GET /result without `request_id`

### Network Errors

**WebSocket Connection Failed**:
- Browser console: `[Inspekt] Connection failed`
- Auto-reconnect after 3 seconds

**HTTP Request Failed**:
- CLI: `ConnectionError: Failed to submit code`
- Check if server is running: `inspekt server status`

---

## Versioning

### Current Version

**Userscript Version**: 3.4 (defined in `window.__ZEN_BRIDGE_VERSION__`)
**Server Version**: 1.0.0 (defined in `zen/__init__.py`)

### Version Checking

**Mechanism**: CLI reads userscript version on first request

```python
# In client.py
installed_version = client.execute("window.__ZEN_BRIDGE_VERSION__ || 'unknown'")
expected_version = get_expected_userscript_version()  # From userscript_ws.js

if installed_version != expected_version:
    print(f"⚠️  WARNING: Userscript version mismatch!", file=sys.stderr)
```

**Warning** (shown once per CLI session):
```
⚠️  WARNING: Userscript version mismatch!
   Installed: 3.3
   Expected:  3.4
   Please update your userscript from: userscript_ws.js
```

### Protocol Evolution (Future)

**Current State**: No formal protocol versioning
- Breaking changes require manual userscript update
- Version mismatch warning only

**Planned (Phase 1+)**:
- Protocol version in handshake message
- Server rejects incompatible clients
- Graceful degradation for minor version differences

**Versioning Strategy** (To Be Implemented):
```json
{
    "type": "handshake",
    "protocol_version": "2.0",
    "client_version": "3.4",
    "capabilities": ["execute", "ping", "reinit_control"]
}
```

---

## Security Considerations

### Threat Model

**Assumptions**:
- Server runs on localhost only (`127.0.0.1`)
- User trusts their local system
- User trusts websites they visit with Inspekt active

**Security Properties**:
- ✅ Server binds to localhost (not `0.0.0.0`)
- ✅ WebSocket only accepts connections from same machine
- ✅ No authentication required (localhost assumption)
- ⚠️  No origin validation (any localhost page can connect)
- ⚠️  No rate limiting (not needed for local use)

### Attack Vectors (Mitigated)

**Remote Code Execution**:
- ❌ Not possible: Server only accepts localhost connections
- Browser same-origin policy prevents remote exploitation

**Cross-Site WebSocket Hijacking**:
- ⚠️  Possible in theory (no origin check)
- ✅ Mitigated: Localhost-only binding, user must visit malicious page

**Denial of Service**:
- ⚠️  Local DoS possible (flood server with requests)
- ✅ Mitigated: Single-user tool, attacker already has local access

### Best Practices

**For Users**:
1. Only run Inspekt on trusted websites
2. Review JavaScript code before executing
3. Don't expose server to network (keep localhost binding)
4. Keep userscript updated

**For Developers**:
1. Never bind server to `0.0.0.0` by default
2. Sanitize any dynamically generated JavaScript
3. Avoid storing secrets in code or config
4. Document security assumptions in README

---

## Request Lifecycle Examples

### Example 1: Simple Evaluation

```
1. User runs: inspekt eval "document.title"

2. CLI sends POST /run:
   {
     "code": "document.title"
   }

3. Server creates request_id: a3f2b1c0-...
   Stores in pending_requests:
   {
     "a3f2b1c0-...": {
       "code": "document.title",
       "timestamp": 1698765432.123
     }
   }

4. Server broadcasts via WebSocket:
   {
     "type": "execute",
     "request_id": "a3f2b1c0-...",
     "code": "document.title"
   }

5. Browser receives, evaluates:
   result = eval("document.title")  // "Example Domain"

6. Browser sends:
   {
     "type": "result",
     "request_id": "a3f2b1c0-...",
     "ok": true,
     "result": "Example Domain",
     "url": "https://example.com",
     "title": "Example Domain"
   }

7. Server moves to completed_requests:
   {
     "a3f2b1c0-...": {
       "ok": true,
       "result": "Example Domain",
       "url": "https://example.com",
       "title": "Example Domain",
       "timestamp": 1698765432.456
     }
   }

8. CLI polls GET /result?request_id=a3f2b1c0-...
   Receives completed result

9. CLI displays: "Example Domain"
```

### Example 2: Control Mode Refocus

```
1. User runs: inspekt control next

2. CLI sends control.js script with action="next"

3. Browser executes, focuses next element

4. Browser sends refocus_notification:
   {
     "type": "refocus_notification",
     "success": true,
     "message": "Focused: <button>Submit</button>"
   }

5. Server stores in pending_notifications

6. CLI polls GET /notifications

7. CLI displays: "Focused: <button>Submit</button>"
```

### Example 3: Page Reload with Auto-Reinit

```
1. User has control mode active

2. User navigates to new page (or refresh)

3. WebSocket disconnects

4. New page loads, userscript connects

5. Userscript checks localStorage for saved control state

6. If control was active, sends reinit_control:
   {
     "type": "reinit_control",
     "config": {...}
   }

7. Server sends execute with control.js "start" action

8. Control mode reinitialized in new page
```

---

## Future Enhancements (Post-Refactor)

### Phase 1: Validation

- [ ] Pydantic models for all message types
- [ ] JSON schema validation on incoming messages
- [ ] Protocol version in handshake
- [ ] Reject incompatible protocol versions

### Phase 2: Reliability

- [ ] Message acknowledgment system
- [ ] Request timeout configuration per-request
- [ ] Request cancellation mechanism
- [ ] Connection health monitoring (ping/pong interval)

### Phase 3: Features

- [ ] Batch execution (multiple code snippets in one request)
- [ ] Streaming results (for long-running operations)
- [ ] Binary data support (screenshots, files)
- [ ] Compression for large payloads (gzip)

### Security Enhancements (Optional)

- [ ] Token-based authentication (for remote binding)
- [ ] Origin validation (whitelist)
- [ ] Rate limiting (per-client)
- [ ] Request signing (HMAC)

---

## References

- ARCHITECTURE.md - High-level system design
- CONTRIBUTING.md - Development guide
- REFACTOR_PLAN.md - Protocol validation plan (Phase 1)
- userscript_ws.js - Browser-side implementation
- zen/bridge_ws.py - Server-side implementation
- zen/client.py - HTTP client implementation

---

## Changelog

### 3.4 (Current)
- Current userscript version
- Auto-reconnect on page navigation
- Auto-reinit for control mode
- Refocus notifications

### 3.3
- Previous version (details unknown)

### Future (2.0)
- Pydantic validation
- Protocol versioning
- Structured error responses

---

**Document Status**: ✅ Complete (current protocol documented)
**Next Update**: After Phase 1 (add Pydantic schemas)
**Maintainer**: Roel van Gils
**Last Updated**: 2025-10-27
