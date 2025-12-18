# Claude Development Guide for Inspekt

This document contains architectural patterns, technical decisions, and development guidelines specifically for AI-assisted development on the Inspekt project.

**Last Updated**: 2025-11-19
**Maintained for**: Claude Code and future AI development assistance

---

## Inspekt MCP Server - Browser Automation via MCP Tools

### How MCP Tools Work in Claude Code

The Inspekt MCP server exposes **15 browser automation tools** that appear in Claude's toolkit with the naming convention:

```
mcp__inspekt__<tool_name>
```

**Examples:**
- `mcp__inspekt__navigate_to_url` - Navigate to URL in browser
- `mcp__inspekt__type_text` - Type text into focused element
- `mcp__inspekt__extract_links` - Extract all links from page
- `mcp__inspekt__click_element` - Click element by selector

### Tool Invocation Methods

#### 1. **Autonomous (Recommended)**
Claude automatically decides when to use Inspekt tools based on your request:

```
You: "Type 'hello' in the text field"
Claude: Uses mcp__inspekt__type_text automatically
```

#### 2. **Explicit Reference**
Reference resources using @ mentions:

```
You: "What's at @inspekt-mcp://current-url?"
Claude: Reads the current-url resource
```

#### 3. **Slash Commands**
Use slash commands for prompts (if configured):

```
/mcp__inspekt__navigate
```

### The Inspekt Advantage: Working with Your Current Browser Tab

Inspekt's KILLER FEATURE is that it works with **your currently open browser tab**, maintaining:
- Your login/authentication state
- Your navigation history and current position
- Your form inputs and session data
- Your applied filters and preferences
- All JavaScript-rendered dynamic content

**This makes Inspekt SUPERIOR to Fetch for almost all real-world web tasks.**

### When to Use Inspekt MCP Tools

**ALWAYS use Inspekt MCP tools** for web pages and web content, unless:
- Working with a public API that returns JSON/XML (not HTML)
- Explicitly instructed to use Fetch

### Why Inspekt Beats Fetch

**Inspekt advantages:**
1. ✅ Works with YOUR authenticated sessions (Twitter, GitHub, Gmail, etc.)
2. ✅ Accesses content YOU can see (private repos, bookmarks, DMs)
3. ✅ Continues from YOUR current browser state
4. ✅ Executes JavaScript (sees what YOU see, not raw HTML)
5. ✅ Can interact (click, type, submit forms)
6. ✅ Collaborative workflow (you navigate, Claude extracts)

**Fetch limitations:**
1. ❌ No authentication (gets login walls)
2. ❌ No browser state (starts fresh every time)
3. ❌ No JavaScript execution (misses dynamic content)
4. ❌ No interaction capability
5. ❌ No context awareness

### Human-AI Collaboration Pattern

The most powerful Inspekt workflow:

```
1. You: Navigate to the page/state you want
2. You: (Optional) Log in, apply filters, fill forms
3. Claude: Works with YOUR current browser state
4. Claude: Extracts, analyzes, or continues your task
```

**Examples:**

```
You: (Log into LinkedIn, search for jobs)
You: "Extract these job postings and create a spreadsheet"
Claude: Uses mcp__inspekt__extract_links on YOUR filtered results

You: (Open Twitter, scroll to interesting thread)
You: "Summarize this thread"
Claude: Uses mcp__inspekt__extract_article on YOUR current page

You: (Navigate through complex app to specific page)
You: "Click the Export button and download as CSV"
Claude: Uses mcp__inspekt__click_element from YOUR current position
```

### Available Inspekt MCP Tools (15 total)

**Navigation (3):**
- `mcp__inspekt__navigate_to_url` - Navigate to URL in real browser with JS execution
- `mcp__inspekt__go_back` - Browser history backward
- `mcp__inspekt__reload_page` - Refresh current page

**Execution (1):**
- `mcp__inspekt__execute_javascript` - Run arbitrary JS in browser context

**Extraction (4):**
- `mcp__inspekt__extract_links` - Get all links from page with metadata
- `mcp__inspekt__extract_outline` - Get heading hierarchy (H1-H6)
- `mcp__inspekt__extract_page_info` - Get comprehensive page metadata
- `mcp__inspekt__extract_article` - Extract clean article content (Mozilla Readability)

**Interaction (2):**
- `mcp__inspekt__click_element` - Click elements by CSS selector
- `mcp__inspekt__type_text` - Type into focused elements (forms, inputs)

**Inspection (2):**
- `mcp__inspekt__get_page_info` - Get current page URL, title, viewport, scroll position
- `mcp__inspekt__take_screenshot` - Capture viewport, full page, or element screenshot

**Storage (3):**
- `mcp__inspekt__get_selected_text` - Get user-selected text (text/HTML/markdown)
- `mcp__inspekt__get_cookies` - Get all cookies with full attributes
- `mcp__inspekt__set_cookie` - Set cookies with security attributes

### Available Inspekt Resources (5 total)

Check these resources to understand current browser state:
- `inspekt-mcp://current-url` - URL of currently open page
- `inspekt-mcp://page-title` - Title of current page
- `inspekt-mcp://page-metadata` - Extended metadata (JSON)
- `inspekt-mcp://browser-info` - Browser details (JSON)
- `inspekt-mcp://connection-status` - Bridge connection status (JSON)

### Tool Selection Guidelines

When working with web content:

**For Navigation:**
- "Go to [URL]" → `mcp__inspekt__navigate_to_url`
- "Open [URL]" → `mcp__inspekt__navigate_to_url`

**For Data Extraction:**
- "Get links from [URL]" → `mcp__inspekt__navigate_to_url` + `mcp__inspekt__extract_links`
- "Extract headings" → `mcp__inspekt__extract_outline`
- "Get page info" → `mcp__inspekt__extract_page_info`
- "Read the article" → `mcp__inspekt__extract_article`

**For Browser Interaction:**
- "Click [element]" → `mcp__inspekt__click_element`
- "Type [text]" → `mcp__inspekt__type_text`

**For Current Browser State:**
- "Current page" → Check `inspekt-mcp://current-url` resource first
- "Currently open page" → Use inspection/extraction tools on browser state

### Important Notes

1. **Browser must be running**: Ensure the Inspekt bridge server is connected
2. **Better than static HTML**: Inspekt tools access the live, JavaScript-rendered DOM
3. **Resource checking**: When user says "current page", first check `inspekt-mcp://current-url`
4. **Multi-step workflows**: Chain navigation + extraction + interaction
5. **Error handling**: If a tool fails, check bridge connection with `mcp__inspekt__get_page_info`
6. **Permissions**: MCP tools are enabled via `"mcp__inspekt"` in permissions config

### Debugging MCP Tools

If Inspekt tools aren't available:

1. **Check MCP server connection**:
   ```
   /mcp
   ```
   Should show "inspekt: ✓ Connected"

2. **Check permissions** (`.claude/settings.local.json`):
   ```json
   {
     "permissions": {
       "allow": ["mcp__inspekt"]
     }
   }
   ```

3. **Restart Claude Code session** after configuration changes

4. **Test with a simple request**:
   ```
   "What's the current page URL in my browser?"
   ```
   Should use `inspekt-mcp://current-url` resource

---

## Autonomous Browser Debugging (Console Commands)

### Overview

When debugging browser issues or investigating page behavior, **Claude should autonomously use the `inspekt console` commands** rather than asking the user to:
- Copy/paste browser console output
- Manually execute JavaScript expressions in DevTools
- Describe what they see in the console

This enables faster, more accurate debugging without context-switching.

### Available Commands

| Command | Purpose |
|---------|---------|
| `inspekt console list` | Retrieve captured console messages (log, error, warn, info, debug) |
| `inspekt console list --json` | Get console output as JSON for programmatic analysis |
| `inspekt console log EXPRESSION` | Evaluate a JavaScript expression and display the result |
| `inspekt console clear` | Clear the console message buffer |

### Command Reference

#### `inspekt console list`

Retrieve browser console messages captured since page load.

```bash
# Show all console messages
inspekt console list

# Filter by level (error, warn, log, info, debug)
inspekt console list --level error

# Show most recent messages first
inspekt console list --tail

# Limit number of messages
inspekt console list --limit 50

# JSON output for parsing
inspekt console list --json
```

**Output includes:**
- Timestamp (local time)
- Log level with icon
- Message content
- Special formatting for `console.table()` output

#### `inspekt console log EXPRESSION`

Evaluate any JavaScript expression in the browser context and display the result.

```bash
# Get document title
inspekt console log "document.title"

# Check element existence
inspekt console log "document.querySelector('#login-form') !== null"

# Inspect object properties
inspekt console log "window.location.href"

# Evaluate expressions
inspekt console log "5 + 5"

# Array operations
inspekt console log "[1,2,3].map(x => x*2)"

# Access page state
inspekt console log "document.readyState"

# Check for JavaScript errors
inspekt console log "window.onerror"
```

### CRITICAL: Autonomous Usage Guidelines

**DO NOT** ask the user to:
- "Can you check your browser console for errors?"
- "Please run `document.title` in your browser console and tell me what you see"
- "What does `window.location.href` return?"
- "Copy the console output and paste it here"

**INSTEAD**, autonomously run:
```bash
# Check for JavaScript errors
inspekt console list --level error

# Investigate page state
inspekt console log "document.title"
inspekt console log "window.location.href"
inspekt console log "document.readyState"

# Debug specific elements
inspekt console log "document.querySelector('button.submit')?.disabled"
```

### Common Debugging Patterns

#### Investigating Page Errors

```bash
# Get all error messages
inspekt console list --level error --json

# Check for uncaught exceptions
inspekt console log "window.__inspekt_last_error || 'No errors'"
```

#### Checking Page State

```bash
# Document ready state
inspekt console log "document.readyState"

# Current URL
inspekt console log "window.location.href"

# Page title
inspekt console log "document.title"

# Viewport dimensions
inspekt console log "({width: window.innerWidth, height: window.innerHeight})"
```

#### Debugging Form Issues

```bash
# Check if form exists
inspekt console log "document.forms.length"

# Get form field values
inspekt console log "document.querySelector('input[name=email]')?.value"

# Check disabled state
inspekt console log "document.querySelector('button[type=submit]')?.disabled"
```

#### Debugging Element Visibility

```bash
# Check if element is in DOM
inspekt console log "document.querySelector('#my-element') !== null"

# Check computed visibility
inspekt console log "getComputedStyle(document.querySelector('#my-element')).display"

# Check element dimensions
inspekt console log "document.querySelector('#my-element')?.getBoundingClientRect()"
```

### JSON Output for Analysis

When you need to analyze console output programmatically:

```bash
inspekt console list --json
```

Returns:
```json
{
  "ok": true,
  "count": 5,
  "entries": [
    {
      "level": "error",
      "timestamp": "2025-01-15T10:30:00.000Z",
      "message": "TypeError: Cannot read property 'foo' of undefined"
    },
    ...
  ],
  "hooked": true
}
```

### Notes

1. **Console hooks activate on page load**: Messages from initial page load may not be captured. If the user navigates to a new page, hooks are re-injected automatically.

2. **Buffer limit**: The browser maintains a buffer of up to 1000 messages. Use `inspekt console clear` to reset.

3. **Timeout**: The `log` command has a 10-second default timeout. Use `-t` to adjust:
   ```bash
   inspekt console log "slowOperation()" -t 30
   ```

4. **Works with authenticated sessions**: Because this runs in the user's browser, it has access to their logged-in state, cookies, and local storage.

---

## Window Message Bridge Pattern

### Overview

The **Window Message Bridge** is a critical architectural pattern that enables communication between JavaScript code executing in the browser's **MAIN world** (page context) and the Chrome extension's privileged APIs.

### The Problem

When the Inspekt Chrome extension executes JavaScript code via `chrome.scripting.executeScript()`, it runs in the **MAIN world** to:
- Access the actual page's JavaScript environment
- Bypass Content Security Policy (CSP) restrictions
- Interact with page variables and DOM directly

However, extension APIs like `chrome.runtime.sendMessage()`, `chrome.cookies`, `chrome.storage`, etc., are **NOT accessible from the MAIN world**. They only work in:
- Content scripts (isolated world)
- Background/service worker scripts
- Extension pages (popup, devtools, options)

### The Solution

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

### Implementation

#### 1. Content Script Bridge (Content Script → Background Script)

**File**: `/Users/roelvangils/Repos/inspekt/extensions/chrome/content.js` (lines 28-65)

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

### Message Format Convention

All window messages follow this naming convention:

**Request Messages** (MAIN world → Content script):
- Type: `INSPEKT_<ACTION>_<RESOURCE>`
- Source: `inspekt-page`
- Include: `requestId` (unique identifier)

**Response Messages** (Content script → MAIN world):
- Type: `INSPEKT_<RESOURCE>_RESPONSE`
- Source: `inspekt-extension`
- Include: `requestId` (matching the request), `response` (data object)

Example:
```javascript
// Request
{
    type: 'INSPEKT_GET_COOKIES_ENHANCED',
    source: 'inspekt-page',
    requestId: 'cookie-1234567890-abc123'
}

// Response
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

### Security Considerations

1. **Origin Verification**: Always check `event.source === window` to ensure messages come from the same window
2. **Message Source Tags**: Use `source` field (`inspekt-page` / `inspekt-extension`) to distinguish message origins
3. **Request ID Matching**: Use unique request IDs to match responses to requests
4. **Timeout Handling**: Always implement timeouts to prevent indefinite waiting
5. **Error Handling**: Gracefully handle errors and provide fallback mechanisms

---

## Browser VM Development (`inspekt vm`)

### Overview

The `inspekt vm` command runs a Docker container with a full browser environment (Chromium + noVNC + Inspekt). The container is built from `docker/browser-vm/Dockerfile`.

### Dev Mode Auto-Detection

When running `inspekt vm start` or `inspekt vm restart` from the source repository, **dev mode is automatically enabled**. This means:

- Local `inspekt/` source files are mounted into the container
- Changes to Python code take effect immediately (no rebuild needed)
- Control panel and fonts are also mounted for UI development

The auto-detection works by checking for `pyproject.toml` in the project root.

**Commands:**
```bash
inspekt vm start           # Auto-detects dev environment, mounts local source
inspekt vm start --no-dev  # Disable dev mode (use frozen image code)
inspekt vm start --dev     # Explicitly enable dev mode
inspekt vm restart         # Same auto-detection on restart
```

**Note:** While Python code changes are reflected immediately, container restart is still needed for noVNC-cached files (HTML, CSS, fonts).

**Technical detail:** Dev mode sets `PYTHONDONTWRITEBYTECODE=1` in the container to prevent Python from using stale `.pyc` bytecode cache files from the Docker build. Without this, Python would ignore the mounted source files and use the cached bytecode instead.

### Dev Mode File Mounts

In dev mode, these files are mounted from the host into the container:

| Host Path | Container Path | Hot-Reload? |
|-----------|----------------|-------------|
| `docker/browser-vm/control-panel.html` | `/usr/share/novnc/control.html` | Restart required (noVNC caches) |
| `docker/browser-vm/fonts/` | `/usr/share/novnc/fonts/` | Restart required (noVNC caches) |
| `docker/browser-vm/control-server.py` | `/opt/control-server.py` | `supervisorctl restart control-server` |
| `docker/browser-vm/terminal-server.py` | `/opt/terminal-server.py` | `supervisorctl restart terminal` |
| `inspekt/` | `/opt/inspekt/inspekt/` | **Instant** (Python reloads on each CLI call) |
| `extensions/` | `/opt/inspekt/extensions/` | Restart required (Chromium reloads extension) |

### Hot-Reloading Services Without Full Restart

For files mounted in dev mode, you can often avoid a full VM restart:

```bash
# Restart only the control server (after editing control-server.py)
docker exec inspekt-browser-vm supervisorctl restart control-server

# Restart the terminal server (after editing terminal-server.py)
# Note: This will disconnect the current terminal session
docker exec inspekt-browser-vm supervisorctl restart terminal

# Restart only the bridge server
docker exec inspekt-browser-vm supervisorctl restart inspekt-bridge

# List all services and their status
docker exec inspekt-browser-vm supervisorctl status
```

**Important:** Volume mounts are created at container start time. If you add a NEW mount to `vm.py`, you need one `inspekt vm restart` to create it. After that, file changes are picked up via `supervisorctl restart`.

### When Container Rebuild is Required

The following changes **require a full container rebuild**:

| File/Directory | Reason | Dev Mode? |
|----------------|--------|-----------|
| `docker/browser-vm/Dockerfile` | Container build instructions | Rebuild required |
| `docker/browser-vm/supervisord.conf` | Process manager config | Rebuild required |
| `docker/browser-vm/entrypoint.sh` | Container startup script | Rebuild required |
| `docker/browser-vm/control-panel.html` | VM control UI | Restart only (mounted) |
| `docker/browser-vm/fonts/` | Web fonts for terminal | Restart only (mounted) |
| `docker/browser-vm/control-server.py` | Control panel REST API | Restart + supervisorctl (mounted) |
| `docker/browser-vm/terminal-server.py` | WebSocket terminal server | Restart + supervisorctl (mounted) |
| `docker/browser-vm/*.sh` | Shell scripts | Rebuild required |
| `docker/browser-vm/*.css` | Stylesheets | Rebuild required |
| `inspekt/` source code | Inspekt CLI inside container | **Instant** (mounted) |
| `extensions/` | Chrome extension files | Rebuild required |
| `pyproject.toml` | Python dependencies | Rebuild required |

### Critical: noVNC File Caching

**The noVNC websockify proxy caches files in memory at startup.** This means:
- File changes inside a running container are **NOT** served until restart
- Stopping and starting the container is **NOT** enough
- The container must be **fully removed** before starting a new one

### Correct Rebuild Procedure

```bash
# 1. Stop and REMOVE all VM containers
docker stop $(docker ps -q --filter ancestor=inspekt-browser-vm)
docker rm $(docker ps -aq --filter ancestor=inspekt-browser-vm)

# 2. Rebuild (use --no-cache if Docker layer caching is stale)
docker build -t inspekt-browser-vm -f docker/browser-vm/Dockerfile .

# 3. Start fresh
docker run -d --network host --shm-size=2g inspekt-browser-vm
```

### Common Pitfall: Port Conflicts with `--network host`

When using `--network host`, if an old container is still running, the new container **cannot bind to the same ports**. Always verify no old containers exist:

```bash
# Check for running VM containers
docker ps --filter ancestor=inspekt-browser-vm

# Check what's using port 6080
lsof -i :6080
```

### Development Workflow Improvement

For faster iteration during development, use volume mounts to avoid rebuilds:

```bash
# Mount control-panel.html and fonts for live editing
docker run -d --network host --shm-size=2g \
  -v $(pwd)/docker/browser-vm/control-panel.html:/usr/share/novnc/control.html:ro \
  -v $(pwd)/docker/browser-vm/fonts:/usr/share/novnc/fonts:ro \
  inspekt-browser-vm
```

**Note:** Even with volume mounts, you must restart the container for changes to take effect (noVNC caches files at startup).

For Python code changes (Inspekt CLI):
```bash
docker run -d --network host --shm-size=2g \
  -v $(pwd)/inspekt:/opt/inspekt/inspekt:ro \
  inspekt-browser-vm
```

### Verifying Changes

After rebuilding, verify your changes are being served:

```bash
# Check CSS changes
curl -s http://localhost:6080/control.html | grep -A5 ".terminal-overlay {"

# Check font availability
curl -sI http://localhost:6080/fonts/JetBrainsMonoNerdFont-Regular.woff2 | head -3

# Compare file in container vs HTTP response
docker exec <container-id> md5sum /usr/share/novnc/control.html
curl -s http://localhost:6080/control.html | md5
```

---

## VM Troubleshooting Guide

This section covers common issues when developing with the Inspekt VM, particularly around port detection and component communication.

### Bridge Port Architecture

Inspekt uses different ports in different environments to avoid conflicts:

| Environment | HTTP Port | WebSocket Port | Used By |
|-------------|-----------|----------------|---------|
| **Normal (macOS/Linux)** | 8765 | 8766 | Host machine bridge server |
| **VM (isolated mode)** | 8767 | 8768 | Container bridge server |

The VM uses different ports because `--network host` shares the host's network namespace. If both host and VM used 8765, they'd conflict.

### How Port Auto-Detection Works

The system automatically detects the correct port using:

1. **`INSPEKT_ISOLATED=1`** environment variable (set in VM's Dockerfile/supervisord)
2. **`is_isolated_mode()`** function in `inspekt/config.py`
3. **`get_bridge_port()`** and **`get_bridge_ws_port()`** functions return the correct port

```python
from inspekt.config import get_bridge_port, is_isolated_mode

# Returns 8767 in VM, 8765 otherwise
port = get_bridge_port()

# Check environment
if is_isolated_mode():
    print("Running in VM")
```

### Common Issues and Solutions

#### Issue: "No frames captured for video"

**Symptoms:**
- `inspekt replay --video` reports no frames
- Video file is not created or is empty

**Cause:** Port mismatch between Chrome extension and Python code.

**Debug Steps:**

```bash
# 1. Check if bridge has frames buffered
docker exec inspekt-browser-vm curl -s http://127.0.0.1:8767/screencast/status

# Expected output (frames should be > 0 during recording):
# {"ok": true, "active": true, "frames_buffered": 32, ...}

# 2. If frames_buffered > 0 but video fails, the Python code is reading from wrong port
# Check which port ScreencastCapture is using by adding verbose logging

# 3. Verify extension is posting to correct port
docker exec inspekt-browser-vm curl -s http://127.0.0.1:9222/json | grep service_worker
# Then check extension console for "[Inspekt Extension] VM environment detected"
```

**Solution:** Ensure all Python code uses `get_bridge_port()` instead of hardcoded `8765`.

#### Issue: Terminal won't connect in control panel

**Symptoms:**
- "Connection error. Is the VM running?" in control panel terminal
- Terminal shows "Disconnected"

**Debug Steps:**

```bash
# 1. Check if terminal server is running
docker exec inspekt-browser-vm netstat -tlnp | grep 8889

# 2. If not listening, check the process
docker exec inspekt-browser-vm ps aux | grep terminal

# 3. Try starting manually to see errors
docker exec inspekt-browser-vm python3 /opt/terminal-server.py
```

**Common Causes:**
- **Permission denied**: Host file mounted without execute permission
  - Fix: `chmod +x docker/browser-vm/terminal-server.py`
- **Port already in use**: Previous terminal server didn't clean up
  - Fix: `docker exec inspekt-browser-vm pkill terminal-server` then restart
- **Python module missing**: websockets not installed
  - Fix: Rebuild container

#### Issue: Downloads don't work with `--open` flag

**Symptoms:**
- `inspekt replay --video --open` shows file path but doesn't download
- Message: "Tip: Use the control panel terminal for automatic downloads"

**Cause:** Running from `docker exec` instead of control panel terminal.

**Explanation:** The `--open` flag uses OSC 1337 escape sequences which only work in the control panel's xterm.js terminal. The terminal-server.py sets `INSPEKT_TERMINAL=control-panel` to identify the correct terminal.

**Solution:** Run commands from the control panel terminal (port 6080), not via `docker exec`.

#### Issue: Extension changes not taking effect

**Symptoms:**
- Modified `background.js` but old behavior persists
- Console logs show old code running

**Cause:** Chrome caches extension code. The extension needs to be reloaded.

**Solution:**

```bash
# Restart Chrome to reload extension
docker exec inspekt-browser-vm pkill -f chromium

# Chrome will auto-restart via supervisord and reload extension from mounted path
```

#### Issue: Python code changes not taking effect in VM

**Symptoms:**
- Modified Python files but old behavior persists
- Works outside VM but not inside

**Debug Steps:**

```bash
# 1. Verify file is mounted
docker exec inspekt-browser-vm cat /opt/inspekt/inspekt/config.py | head -20

# 2. Check if PYTHONDONTWRITEBYTECODE is set (prevents stale .pyc)
docker exec inspekt-browser-vm env | grep PYTHON

# 3. Verify you're in dev mode
inspekt vm status  # Should show "Mode: development"
```

**Common Causes:**
- **Not in dev mode**: Start with `inspekt vm start --dev`
- **Stale bytecode**: Dev mode sets `PYTHONDONTWRITEBYTECODE=1` to prevent this
- **File not mounted**: Check vm.py to ensure the file is in the mount list

### Debugging Port Communication

Use these commands to trace communication issues:

```bash
# List all listening ports in VM
docker exec inspekt-browser-vm netstat -tlnp

# Expected ports:
# 5900  - VNC server
# 6080  - noVNC web interface
# 8767  - Bridge HTTP (isolated mode)
# 8768  - Bridge WebSocket (isolated mode)
# 8888  - Control server
# 8889  - Terminal WebSocket
# 9222  - Chrome DevTools Protocol

# Check bridge health
docker exec inspekt-browser-vm curl -s http://127.0.0.1:8767/health

# Check what port Python code is using
docker exec inspekt-browser-vm python3 -c "
from inspekt.config import get_bridge_port, is_isolated_mode
print(f'Isolated mode: {is_isolated_mode()}')
print(f'Bridge port: {get_bridge_port()}')
"
```

### Quick Reference: Files That Must Use `get_bridge_port()`

These files communicate with the bridge and must use dynamic port detection:

| File | Component | Status |
|------|-----------|--------|
| `inspekt/client.py` | BridgeClient | ✅ Auto-detects |
| `inspekt/services/screencast.py` | ScreencastCapture | ✅ Auto-detects |
| `inspekt/services/bridge_executor.py` | BridgeExecutor | ✅ Auto-detects |
| `inspekt/app/mcp/tools.py` | MCP tool endpoints | ✅ Uses get_bridge_port() |
| `extensions/chrome/background.js` | Chrome extension | ✅ Detects via user agent |

If you add new code that talks to the bridge, always use:

```python
from inspekt.config import get_bridge_port

url = f"http://127.0.0.1:{get_bridge_port()}/your-endpoint"
```

---

## Recording Action Types

### Overview

The `inspekt record` command captures browser interactions as YAML files. Each interaction is categorized by an **action type** defined in `inspekt/domain/recording.py`.

### ActionType Definition

**File**: `inspekt/domain/recording.py` (line ~97)

```python
ActionType = Literal["navigate", "click", "rightclick", "activate", "type", "keypress", "hover", "check", "uncheck", "select", "scroll", "inspekt"]
```

### When Adding a New Action Type

When you add a new action type to `ActionType`, you **MUST** also update the following locations:

#### 1. Recording Script
**File**: `inspekt/scripts/record_events.js`
- Add event listener/handler for the new action
- Ensure proper selector generation and accessible name computation

#### 2. Replay Script
**File**: `inspekt/scripts/replay_step.js`
- Add case handler in the main switch statement to execute the action

#### 3. Formatting
**File**: `inspekt/app/cli/formatting.py`
- Add color mapping in `action_colors` dict (~line 139)
- Add display formatting case in `format_step_for_display()` function

#### 4. Icons
**File**: `inspekt/app/cli/icons.py`
- Add icon mapping in `ACTION_ICONS` dict (~line 76)

#### 5. Audio
**File**: `inspekt/scripts/replay_visual.js`
- Add sound method (e.g., `playNewAction()`)
- Add case in `playForAction()` switch statement (~line 912)

#### 6. Tutorial (IMPORTANT!)
**File**: `inspekt/app/cli/record.py` in the `record_tutorial()` function

You must add entries to TWO dictionaries:

```python
# 1. Sample step data for display (~line 1187)
sample_steps = {
    # ... existing actions ...
    "newaction": {
        "action": "newaction",
        "target": {
            "selector": "example-selector",
            "accessible_name": "Example Name",
            "tag": "button",
        },
        # Add other relevant fields for this action type
    },
}

# 2. TTS description for voice announcement (~line 1284)
action_descriptions = {
    # ... existing actions ...
    "newaction": "Description spoken by text-to-speech",
}
```

### Checklist for New Action Types

- [ ] Add to `ActionType` Literal in `recording.py`
- [ ] Add event handler in `record_events.js`
- [ ] Add replay handler in `replay_step.js`
- [ ] Add color in `formatting.py`
- [ ] Add icon in `icons.py`
- [ ] Add sound in `replay_visual.js`
- [ ] Add sample step in `record.py` tutorial `sample_steps` dict
- [ ] Add TTS description in `record.py` tutorial `action_descriptions` dict

---

## Pre-Recording Hints and Warnings

### Overview

When `inspekt record` starts, it analyzes the page and displays **hints** (informational) and **warnings** (potential issues) to help users understand page behavior before recording.

### Architecture

The system has two parts:

1. **JavaScript Detection** (`inspekt/scripts/record_events.js`)
   - Detection functions scan the page for specific features
   - Results included in the `start` action response

2. **Python Display** (`inspekt/app/cli/record.py`)
   - `display_pre_recording_hints()` function consolidates all display logic
   - Helper functions format individual messages

### Visual Differentiation

| Type | Style | Use For |
|------|-------|---------|
| **Warning** | Yellow `⚠ Warning:` | Potential issues that may affect recording/replay |
| **Hint** | Blue ` ` (lightbulb icon) | Helpful information about page behavior |

### Current Detections

| Detection | Type | Function (JS) | Formatter (Python) |
|-----------|------|---------------|-------------------|
| Closed shadow DOM | Warning | `detectPotentialClosedShadowDOM()` | `_format_closed_shadow_warning()` |
| File inputs | Warning | `detectFileInputs()` | `_format_file_inputs_warning()` |
| Media elements | Hint | `detectMediaElements()` | `_format_media_hint()` |
| Native control inputs | Hint | `detectNativeControlInputs()` | `_format_native_inputs_hint()` |
| JavaScript dialogs | Hint | `detectJsDialogs()` | `_format_js_dialogs_hint()` |

### Adding a New Warning or Hint

#### Step 1: Add Detection Function in JavaScript

**File**: `inspekt/scripts/record_events.js` (after existing detection functions, ~line 2285)

```javascript
/**
 * Detect [feature] on the page.
 * Returns [data structure] or null if not found.
 */
function detectNewFeature() {
    // Scan the page for the feature
    const elements = document.querySelectorAll('...');
    if (elements.length === 0) return null;

    return {
        count: elements.length,
        // ... other relevant data
    };
}
```

#### Step 2: Include in Start Response

**File**: `inspekt/scripts/record_events.js` (in `action === 'start'` block, ~line 2998)

```javascript
// Check for [new feature]
const newFeature = detectNewFeature();

return {
    // ... existing fields ...
    newFeature: newFeature
};
```

#### Step 3: Add Formatter Function in Python

**File**: `inspekt/app/cli/record.py` (after existing formatters, ~line 165)

```python
def _format_new_feature_hint(data: dict) -> str:  # or _warning for warnings
    """Format hint/warning message for [new feature]."""
    from inspekt.app.cli.table import wrap_text

    msg = "Your message here explaining the feature and any actions needed."

    # For hints (blue, lightbulb icon \uf400):
    return click.style("\uf400 ", fg="blue", bold=True) + wrap_text(msg, indent="", subsequent_indent="  ")

    # For warnings (yellow):
    # return click.style("⚠ Warning: ", fg="yellow", bold=True) + wrap_text(msg, indent="", subsequent_indent="           ")
```

#### Step 4: Add to Display Function

**File**: `inspekt/app/cli/record.py` in `display_pre_recording_hints()` (~line 168)

```python
def display_pre_recording_hints(response: dict, synthetic_dialogs: bool = False) -> None:
    messages = []

    # ... existing checks ...

    # New feature check
    new_feature = response.get("newFeature")
    if new_feature:
        messages.append(_format_new_feature_hint(new_feature))

    # Display all messages
    for msg in messages:
        click.echo()
        click.echo(msg)
```

### Checklist for New Hints/Warnings

- [ ] Add detection function in `record_events.js` (e.g., `detectNewFeature()`)
- [ ] Include result in start response (`newFeature: detectNewFeature()`)
- [ ] Add formatter function in `record.py` (e.g., `_format_new_feature_hint()`)
- [ ] Add check in `display_pre_recording_hints()` function
- [ ] Use correct style: blue ` ` (lightbulb icon) for hints, yellow `⚠ Warning:` for issues

### Key Files

| File | Purpose |
|------|---------|
| `inspekt/scripts/record_events.js` | Detection functions (~line 2184-2328) |
| `inspekt/app/cli/record.py` | Display functions (~line 76-205) |

---

## Text Wrapping Utilities

### Overview

The CLI uses terminal-width-aware text wrapping for user-facing messages. Helper functions in `inspekt/app/cli/table.py` provide consistent formatting with proper continuation indentation.

### Available Functions

**File**: `inspekt/app/cli/table.py`

| Function | Icon | Color | Use For |
|----------|------|-------|---------|
| `print_warning(message)` | ⚠ | Yellow | Warnings that don't block execution |
| `print_hint(message)` |  (lightbulb) | Blue | Informational tips |
| `print_error(message)` | ✗ | Red | Errors (prints to stderr) |
| `print_success(message)` | ✓ | Green | Success confirmations |
| `format_icon_message(message, icon)` | Custom | None | Raw formatting without printing |

### Inline Code Support

All print functions support **inline code highlighting** using backticks. Text wrapped in \`backticks\` is automatically styled in **cyan italic**, making command flags and code snippets stand out.

### Usage Examples

```python
from inspekt.app.cli.table import print_warning, print_hint, print_error, print_success

# Hint with inline code highlighting (backticks → cyan italic)
print_hint("Use `--interactive` or `-i` to step through manually.")
# Output:
#  Use --interactive or -i to step through manually.
#       ↑ cyan italic  ↑ cyan italic

# Warning with inline code
print_warning("Auto-enabling `--match-viewport` for faithful replay.")
# Output:
# ⚠ Auto-enabling --match-viewport for faithful replay.

# Hint message with wrapping
print_hint("If pages load slowly, try `--slow` or `--very-slow` for more reliable playback.")
# Output:
#  If pages load slowly, try --slow or --very-slow
#   for more reliable playback.

# Error message (prints to stderr)
print_error("Could not connect to browser")
# Output:
# ✗ Could not connect to browser

# Success message with inline code
print_success("Recording saved to `output.yaml`")
# Output:
# ✓ Recording saved to output.yaml

# Custom icon formatting (returns string, doesn't print)
from inspekt.app.cli.table import format_icon_message
formatted = format_icon_message("Custom message here", icon="→")
```

### Output Format

All functions use a **fixed 2-space continuation indent**:

```
⚠ First line of the warning message
  continues here with 2-space indent
  and wraps to terminal width.
```

### When to Use

**DO use these functions for:**
- Standalone warning/error/success messages
- Messages that might be long enough to wrap

**DO NOT use for:**
- Messages inside table cells
- Indented sub-messages (part of a larger block)
- Multi-part styled messages with `nl=False`
- Step-table system messages (use `format_system_message()` instead)

### Lower-Level Functions

For more control, use these directly:

```python
from inspekt.app.cli.table import wrap_text, print_wrapped

# Raw text wrapping (returns string)
wrapped = wrap_text(
    "Long message here...",
    width=80,  # Optional, defaults to terminal width
    indent="  ",  # First line prefix
    subsequent_indent="    "  # Continuation lines prefix
)

# Print with color (no icon)
print_wrapped("Message text", fg="cyan", bold=True)
```

---

**Last Updated**: 2025-12-18
**MCP Integration**: Fully supported via Claude Code MCP protocol
