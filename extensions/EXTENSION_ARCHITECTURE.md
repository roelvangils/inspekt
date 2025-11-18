# Inspekt Extension Architecture

## Overview

The Inspekt project now uses a **shared code architecture** that allows the Chrome and Firefox extensions to benefit from common functionality while maintaining browser-specific optimizations.

**Status**: Firefox extension has been modernized to v4.2.1 and now uses shared code. Chrome extension still uses direct imports but can be refactored.

---

## Directory Structure

```
extensions/
├── shared/                          # ✅ Cross-browser shared code
│   ├── core/
│   │   ├── permissions.js           # Domain permission manager
│   │   ├── websocket-client.js      # WebSocket connection handler
│   │   └── message-bridge.js        # Window message bridge pattern
│   └── popup/
│       ├── popup-base.html          # Popup UI template
│       ├── popup-base.css           # Popup styling (cross-browser)
│       └── popup-base.js            # Popup logic with browser adapters
│
├── chrome/                          # Chrome MV3 extension
│   ├── manifest.json                # Chrome Manifest V3
│   ├── background.js                # Service worker (CSP bypass)
│   ├── content.js                   # Content script (WebSocket client)
│   ├── permissions.js               # TODO: Remove, use shared version
│   ├── devtools.html/js             # DevTools panel (Chrome only)
│   ├── panel.html/js/css            # DevTools panel UI (Chrome only)
│   ├── offscreen.html/js            # Offscreen document (Chrome MV3 only)
│   ├── popup/
│   │   ├── popup.html               # Chrome popup (uses shared)
│   │   ├── popup.js                 # Chrome popup logic
│   │   └── popup.css                # Chrome popup styling
│   └── icons/
│
└── firefox/                         # Firefox MV2 extension ✅ Modernized
    ├── manifest.json                # Firefox Manifest V2 (v4.2.1)
    ├── background.js                # Persistent background page
    ├── content.js                   # Content script (uses shared modules)
    ├── permissions.js               # Backwards compat link to shared
    ├── popup/
    │   ├── popup.html               # Firefox popup (modern)
    │   ├── popup.js                 # Firefox popup logic (fixed!)
    │   └── popup.css                # Firefox popup styling
    └── icons/
```

---

## Key Components

### 1. Shared Core Modules

#### `shared/core/permissions.js`
- **Purpose**: Cross-browser domain permission management
- **Features**:
  - Domain whitelisting
  - Opt-in permission modal
  - Storage via `chrome.storage.sync` / `browser.storage.sync`
- **Usage**: Both extensions include this in manifest.json
- **API**:
  ```javascript
  await InspektPermissions.isAllowed(domain)
  await InspektPermissions.allowDomain(domain)
  await InspektPermissions.removeDomain(domain)
  await InspektPermissions.getAllowedDomains()
  await InspektPermissions.checkAndRequest()
  ```

#### `shared/core/websocket-client.js`
- **Purpose**: WebSocket connection management
- **Features**:
  - Auto-reconnection with exponential backoff
  - Keepalive ping/pong
  - Visibility-based connect/disconnect
  - Updates `window.__INSPEKT_WS_CONNECTED__`
- **Usage**: Injected via manifest.json content_scripts
- **API**:
  ```javascript
  InspektWebSocketClient.initialize()
  InspektWebSocketClient.connect()
  InspektWebSocketClient.disconnect()
  InspektWebSocketClient.isConnected()
  ```

#### `shared/core/message-bridge.js`
- **Purpose**: Window message bridge for MAIN world ↔ content script communication
- **Features**:
  - Enables MAIN world scripts to access extension APIs
  - Cookie API access via `chrome.cookies` / `browser.cookies`
  - Request/response correlation with IDs
  - Timeout handling (1 second default)
- **Security**:
  - `event.source === window` verification
  - Message source tagging (`inspekt-page` vs `inspekt-extension`)
- **Usage**: Injected via manifest.json, auto-initializes

### 2. Shared Popup Components

#### `shared/popup/popup-base.html`
- Responsive popup UI with emoji icons
- Sections: Status, Quick Start, Features, Domains, Commands
- Links to: Documentation, GitHub
- Compatible with both Chrome and Firefox (uses emojis instead of Material Icons for Firefox)

#### `shared/popup/popup-base.css`
- Single stylesheet for both extensions
- Responsive design (400px width)
- Status indicator animations
- Domain management UI

#### `shared/popup/popup-base.js`
- **BrowserAPI abstraction**: Detects `chrome` vs `browser` namespace
- **checkConnectionStatus()**: Uses appropriate executeScript API
  - Chrome: `chrome.scripting.executeScript()`
  - Firefox: `browser.tabs.executeScript()`
- **loadAllowedDomains()**: Manages domain whitelisting UI

---

## Browser-Specific Differences

### Chrome (MV3)
- **Service Worker**: Background script runs as service worker
- **Permissions**: Split into `permissions` and `host_permissions`
- **Script Execution**: `chrome.scripting.executeScript()` with function serialization
- **DevTools**: Full DevTools panel with element inspection
- **Content Scripts**: Run in isolated world (unless `world: 'MAIN'` specified)
- **Popup**: Uses Material Icons font

### Firefox (MV2)
- **Persistent Background**: Background script runs as persistent page
- **Permissions**: Combined in single `permissions` array
- **Script Execution**: `browser.tabs.executeScript()` with code strings
- **DevTools**: Minimal (no custom panel in MV2)
- **Content Scripts**: Always run in isolated world
- **Popup**: Uses emoji icons for broader compatibility

---

## Firefox Modernization (v4.2.1)

### ✅ Completed Updates

1. **manifest.json**
   - Version: 4.0.0 → 4.2.1
   - Content scripts: Now reference shared modules
   - Removed unused permissions (webRequest, webRequestBlocking)

2. **content.js**
   - Variable names: `__ZEN_BRIDGE__` → `__INSPEKT_BRIDGE__`
   - Added window message bridge for cookie API access
   - Uses shared WebSocket client (`InspektWebSocketClient`)
   - Simplified from ~200 lines to ~90 lines

3. **popup.html**
   - Title: "Zen Browser Bridge" → "Inspekt"
   - Commands: "zen" → "inspekt"
   - Links: Updated to github.com/roelvangils/inspekt
   - Features: Removed DevTools-specific features

4. **popup.js** ✅ CRITICAL BUG FIX
   - **Before**: Used `chrome.scripting.executeScript()` (doesn't exist in Firefox MV2)
   - **After**: Uses `browser.tabs.executeScript()` with code string
   - API updates: `browser.tabs.*` instead of `chrome.tabs.*`
   - Permissions check: Uses `InspektPermissions` instead of `ZenPermissions`

5. **background.js**
   - Variable consistency: `__zenEval` → `__inspektEval`
   - Comment updates for clarity

### Dependencies
Firefox now includes shared modules in manifest.json:
```json
"content_scripts": [
  {
    "js": [
      "../shared/core/permissions.js",
      "../shared/core/websocket-client.js",
      "../shared/core/message-bridge.js",
      "content.js"
    ]
  }
]
```

---

## Chrome Extension Refactoring (TODO)

The Chrome extension can be refactored to use shared code. Key changes would be:

### Option 1: Immediate Refactor (Recommended)
Update `extensions/chrome/manifest.json`:
```json
"content_scripts": [
  {
    "matches": ["<all_urls>"],
    "js": [
      "../shared/core/permissions.js",
      "../shared/core/websocket-client.js",
      "../shared/core/message-bridge.js",
      "content.js"
    ]
  }
]
```

Then simplify `chrome/content.js` and `chrome/popup/popup.js`:
- Remove WebSocket logic (use `InspektWebSocketClient`)
- Remove message bridge code (use shared)
- Update popup to use shared base

### Option 2: Gradual Migration
- Keep current code as-is for now
- Use shared modules alongside existing code
- Gradually migrate features over time

---

## Testing Checklist

### Firefox Extension (v4.2.1)
- [ ] Install in Firefox (test or production)
- [ ] Verify popup displays correctly
- [ ] Check WebSocket connection to localhost:8766
- [ ] Test domain whitelisting (modal appears)
- [ ] Test permission modal styling (no Material Icons dependency)
- [ ] Verify CSS bypass on strict CSP sites
- [ ] Test cookie API bridge (if needed)
- [ ] Verify status indicator updates correctly

### Chrome Extension (Regression)
- [ ] Verify existing functionality still works
- [ ] Check DevTools panel loads correctly
- [ ] Test element inspection feature
- [ ] Verify popup displays correctly
- [ ] Check WebSocket connection
- [ ] Test domain whitelisting
- [ ] Test CSS bypass

---

## Future Improvements

### Phase 1: Chrome Refactor
- Refactor Chrome extension to use shared modules
- Update Chrome popup to use shared base
- Benefits:
  - Reduced code duplication
  - Easier maintenance
  - Shared bug fixes benefit both

### Phase 2: Advanced Shared Features
- Implement shared background module
  - Extract common CSP bypass logic
  - Create browser-specific adapters
- Share more utilities

### Phase 3: Build System
- Create build script to:
  - Copy shared files to both extensions
  - Generate browser-specific manifests
  - Minify and package
- Benefits:
  - Single source of truth for shared code
  - Automatic dependency management
  - Consistent versioning

---

## Code Quality & Security

### Security Practices
- ✅ Origin verification in message bridge (`event.source === window`)
- ✅ Message source tagging to distinguish message origins
- ✅ Request ID correlation to prevent response mismatches
- ✅ Timeout handling to prevent indefinite waiting
- ✅ No direct eval (uses AsyncFunction or script injection)
- ✅ CSP bypass only for authorized domains

### Cross-Browser Testing
- Chrome on Windows/Mac/Linux
- Firefox on Windows/Mac/Linux
- Edge (uses Chrome MV3 extensions)

### Performance
- WebSocket keepalive: 30 second interval
- Reconnection backoff: 3 second delay
- Visibility-based connection: Closes hidden tabs
- Minimal popup overhead: ~2KB gzipped

---

## Contributing

When making changes to shared code:

1. **Test both extensions** after modifying shared files
2. **Maintain API compatibility** for existing functions
3. **Document browser differences** in code comments
4. **Update both extensions' manifests** if adding new shared modules

When adding browser-specific features:

1. Use clear comments to indicate browser-specific code
2. Consider if feature could be abstracted to shared code
3. Test on the target browser before committing

---

## Version History

- **v4.2.1**: Firefox modernized with shared code, popup.js bug fix
- **v4.2.0**: Chrome extension feature parity, DevTools panel improvements
- **v4.0.0**: Firefox initial release (outdated, now v4.2.1)

---

## References

- [Chrome Extension MV3 Docs](https://developer.chrome.com/docs/extensions/mv3/)
- [Firefox WebExtensions Docs](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/)
- [Window Message Bridge Pattern](../CLAUDE.md#window-message-bridge-pattern)
