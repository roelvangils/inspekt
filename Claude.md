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

**Last Updated**: 2025-11-19
**MCP Integration**: Fully supported via Claude Code MCP protocol
