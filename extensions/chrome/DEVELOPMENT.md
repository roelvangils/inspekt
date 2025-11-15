# Chrome Extension Development Guide

## Testing Extension Changes

After making changes to any extension files, follow these steps to test:

### 1. Reload the Extension

1. Navigate to `chrome://extensions/`
2. Locate the "Inspekt" extension
3. Click the **Reload** button (circular arrow icon)
4. Verify no errors appear in the extension card

### 2. Refresh the Webpage

1. Go to the tab with your test webpage
2. Perform a **hard refresh**:
   - Mac: `Cmd + Shift + R`
   - Windows/Linux: `Ctrl + Shift + F5`
3. This clears cached scripts and ensures fresh content loads

### 3. Restart DevTools

1. Close DevTools completely (`Cmd + Option + I` or click X)
2. Reopen DevTools (`F12` or `Cmd + Option + I`)
3. Navigate to the **Inspekt** panel

### 4. Verify Connection Status

1. Check the connection indicator in the Inspekt panel header
2. Should show **"Connected"** (green dot) when server is running
3. If showing "Checking..." or "Disconnected", check:
   - Server is running (`inspekt server start`)
   - No JavaScript errors in DevTools console
   - Check page console for WebSocket connection logs

## Debugging Extension Issues

### Opening DevTools for the DevTools Panel

To debug the Inspekt panel itself:

1. Open DevTools (`F12`)
2. **Right-click** anywhere in the DevTools interface
3. Select **"Inspect"** from context menu
4. A new DevTools window opens - this is "DevTools for DevTools"
5. Check Console tab for JavaScript errors in the panel code

### Common Issues

#### "Checking..." Status Persists

**Cause**: Extension not reloaded or cached version still active

**Fix**:
1. Reload extension in `chrome://extensions/`
2. Hard refresh webpage (`Cmd + Shift + R`)
3. Close and reopen DevTools
4. Check DevTools console for errors

#### JavaScript Syntax Errors

**Cause**: Template literal syntax errors (escaped backticks/dollar signs)

**Fix**:
1. Run ESLint: `cd extensions/chrome && npm run lint`
2. Fix reported errors
3. Follow reload procedure above

#### WebSocket Connection Failed

**Cause**: Server not running or wrong port

**Fix**:
1. Start server: `inspekt server start`
2. Check server logs in terminal
3. Verify WebSocket connection in page console

### Checking Connection Status Variable

In the **page console** (not DevTools console):

```javascript
// Check connection status
window.__INSPEKT_WS_CONNECTED__
// Should return: true (connected), 'connecting', or false (disconnected)
```

## Development Workflow

### Before Making Changes

1. Create a feature branch: `git checkout -b feature/my-change`
2. Run linter: `npm run lint`
3. Fix any existing issues

### After Making Changes

1. Run linter: `npm run lint:fix`
2. Fix any errors manually if needed
3. Test extension following steps above
4. Commit changes with descriptive message

### ESLint Configuration

The extension uses ESLint to catch common errors:

- Template literal syntax errors
- Useless escape characters
- Undefined variables
- Code style issues

**Run linter**:
```bash
cd extensions/chrome
npm install  # First time only
npm run lint
```

**Auto-fix issues**:
```bash
npm run lint:fix
```

## File Structure

```
extensions/chrome/
├── manifest.json           # Extension configuration
├── background.js           # Service worker (privileged APIs)
├── content.js             # Content script (page bridge)
├── devtools.html          # DevTools integration entry
├── panel.html             # Main DevTools panel UI
├── panel.js               # Panel initialization
├── components/            # Reusable components
│   ├── element-highlighter.js
│   ├── element-picker.js
│   └── quick-actions/
├── modules/               # Core functionality modules
│   ├── connection-manager.js
│   ├── element-display.js
│   └── quick-actions-manager.js
├── handlers/              # Action handlers
│   ├── copy-*.js
│   ├── navigate-*.js
│   └── utils/
└── utils/                 # Utility functions
    ├── devtools.js
    └── quick-actions-config.js
```

## Chrome Extension Contexts

The extension operates in multiple JavaScript contexts:

### 1. Service Worker (background.js)
- **Purpose**: Handle extension logic, privileged APIs
- **APIs**: Full `chrome.*` API access
- **No Access**: DOM, page variables

### 2. Content Script (content.js)
- **Purpose**: Bridge between page and extension
- **APIs**: Limited `chrome.*` APIs, DOM access
- **No Access**: Page JavaScript variables

### 3. DevTools Panel (panel.html/panel.js)
- **Purpose**: UI and interaction
- **APIs**: `chrome.devtools.*` APIs
- **Access**: Can eval code in page context

### 4. Page Context (via injection)
- **Purpose**: Execute in page's JavaScript environment
- **APIs**: Page variables, DOM
- **No Access**: Extension APIs

## Troubleshooting

### Module Not Loading

**Symptom**: Module fails to import, console shows module errors

**Check**:
1. File path is correct (case-sensitive)
2. File has `.js` extension in import
3. Module uses `export` keyword
4. No syntax errors in the file

### Event Handlers Not Working

**Symptom**: Clicks, keyboard shortcuts don't respond

**Check**:
1. Event listener registered after DOM ready
2. Element ID matches between HTML and JavaScript
3. No errors in console preventing script execution
4. Event propagation not stopped by another handler

### Connection Status Not Updating

**Symptom**: Shows "Checking..." despite WebSocket connected

**Check**:
1. Extension reloaded in `chrome://extensions/`
2. DevTools reopened after reload
3. `window.__INSPEKT_WS_CONNECTED__` is `true` in page console
4. `connection-manager.js` logging shows status checks
5. No JavaScript errors in DevTools console

## Best Practices

1. **Always reload extension** after JavaScript changes
2. **Hard refresh page** after extension reload
3. **Reopen DevTools** after page refresh
4. **Check both consoles**: Page console AND DevTools console
5. **Use logging**: Add `console.log()` for debugging
6. **Run ESLint** before committing changes
7. **Test in multiple tabs** to verify WebSocket handling

## Resources

- [Chrome Extension APIs](https://developer.chrome.com/docs/extensions/reference/)
- [DevTools Extension Guide](https://developer.chrome.com/docs/extensions/mv3/devtools/)
- [WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
