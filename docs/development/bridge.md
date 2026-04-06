# Window Message Bridge Pattern

The **Window Message Bridge** is a critical architectural pattern that enables communication between JavaScript code executing in the browser's **MAIN world** (page context) and the Chrome extension's privileged APIs.

!!! note "Not the Same as CLI Transport"
    This document covers **browser-side** communication within the extension. For **CLI-to-server** communication (Unix sockets, TCP, HTTP), see [Architecture: Transport Layer](architecture.md).

## The Problem

When the Inspekt Chrome extension executes JavaScript code via `chrome.scripting.executeScript()`, it runs in the **MAIN world** to:

- Access the actual page's JavaScript environment
- Bypass Content Security Policy (CSP) restrictions
- Interact with page variables and DOM directly

However, extension APIs like `chrome.runtime.sendMessage()`, `chrome.cookies`, `chrome.storage`, etc., are **NOT accessible from the MAIN world**. They only work in:

- Content scripts (isolated world)
- Background/service worker scripts
- Extension pages (popup, devtools, options)

## The Solution

The bridge uses `window.postMessage()` to communicate between execution contexts:

```
MAIN World Script          Content Script           Background Script
    (page context)      (extension isolated)      (extension privileged)
         │                       │                        │
         │  postMessage          │                        │
         ├──────────────────────>│                        │
         │                       │  chrome.runtime.       │
         │                       │  sendMessage           │
         │                       ├───────────────────────>│
         │                       │                        │
         │                       │              chrome.cookies.getAll()
         │                       │                        ├──┐
         │                       │                        │<─┘
         │                       │  response              │
         │                       │<───────────────────────┤
         │  postMessage          │                        │
         │<──────────────────────┤                        │
         │                       │                        │
```

## Implementation

### Content Script Bridge (Content Script → Background Script)

**File**: `extensions/chrome/content.js` (lines 28-65)

```javascript
// Window Message Bridge
// Allows MAIN world scripts to communicate with extension APIs
window.addEventListener('message', async (event) => {
    // Only accept messages from same origin (security)
    if (event.source !== window) return;

    const message = event.data;

    // Handle GET_COOKIES_ENHANCED requests from MAIN world
    if (message && message.type === 'INSPEKT_GET_COOKIES_ENHANCED' && message.source === 'inspekt-page') {
        try {
            // Forward to background script
            const response = await chrome.runtime.sendMessage({
                type: 'GET_COOKIES_ENHANCED'
            });

            // Send response back to MAIN world
            window.postMessage({
                type: 'INSPEKT_COOKIES_RESPONSE',
                source: 'inspekt-extension',
                requestId: message.requestId,
                response: response
            }, '*');
        } catch (error) {
            // Send error back to MAIN world
            window.postMessage({
                type: 'INSPEKT_COOKIES_RESPONSE',
                source: 'inspekt-extension',
                requestId: message.requestId,
                response: {
                    ok: false,
                    error: String(error)
                }
            }, '*');
        }
    }
});
```

## Message Format Convention

All window messages follow this naming convention:

**Request Messages** (MAIN world → Content script):

- Type: `INSPEKT_<ACTION>_<RESOURCE>`
- Source: `inspekt-page`
- Include: `requestId` (unique identifier)

**Response Messages** (Content script → MAIN world):

- Type: `INSPEKT_<RESOURCE>_RESPONSE`
- Source: `inspekt-extension`
- Include: `requestId` (matching the request), `response` (data object)

### Example Message Flow

```javascript
// Request (from MAIN world script)
{
    type: 'INSPEKT_GET_COOKIES_ENHANCED',
    source: 'inspekt-page',
    requestId: 'cookie-1234567890-abc123'
}

// Response (from content script)
{
    type: 'INSPEKT_COOKIES_RESPONSE',
    source: 'inspekt-extension',
    requestId: 'cookie-1234567890-abc123',
    response: {
        ok: true,
        cookies: [...],
        count: 5
    }
}
```

## Security Considerations

1. **Origin Verification**: Always check `event.source === window` to ensure messages come from the same window
2. **Message Source Tags**: Use `source` field (`inspekt-page` / `inspekt-extension`) to distinguish message origins
3. **Request ID Matching**: Use unique request IDs to match responses to requests
4. **Timeout Handling**: Always implement timeouts to prevent indefinite waiting
5. **Error Handling**: Gracefully handle errors and provide fallback mechanisms

## Adding a New Bridge Message Type

To add a new message type (e.g., for a new extension API):

### 1. Add handler in content script

**File**: `extensions/chrome/content.js`

```javascript
// In the message event listener
if (message && message.type === 'INSPEKT_NEW_ACTION' && message.source === 'inspekt-page') {
    try {
        const response = await chrome.runtime.sendMessage({
            type: 'NEW_ACTION',
            data: message.data
        });

        window.postMessage({
            type: 'INSPEKT_NEW_ACTION_RESPONSE',
            source: 'inspekt-extension',
            requestId: message.requestId,
            response: response
        }, '*');
    } catch (error) {
        window.postMessage({
            type: 'INSPEKT_NEW_ACTION_RESPONSE',
            source: 'inspekt-extension',
            requestId: message.requestId,
            response: { ok: false, error: String(error) }
        }, '*');
    }
}
```

### 2. Add handler in background script

**File**: `extensions/chrome/background.js`

```javascript
// In the message listener
case 'NEW_ACTION':
    // Call the appropriate chrome.* API
    const result = await chrome.someAPI.someMethod();
    sendResponse({ ok: true, data: result });
    break;
```

### 3. Send message from MAIN world script

```javascript
// Generate unique request ID
const requestId = `new-action-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

// Set up response listener
const responsePromise = new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Timeout')), 5000);

    const handler = (event) => {
        if (event.data?.type === 'INSPEKT_NEW_ACTION_RESPONSE' &&
            event.data?.requestId === requestId) {
            clearTimeout(timeout);
            window.removeEventListener('message', handler);
            resolve(event.data.response);
        }
    };
    window.addEventListener('message', handler);
});

// Send request
window.postMessage({
    type: 'INSPEKT_NEW_ACTION',
    source: 'inspekt-page',
    requestId: requestId,
    data: { /* your data */ }
}, '*');

// Wait for response
const response = await responsePromise;
```
