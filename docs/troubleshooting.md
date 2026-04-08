# Inspekt Troubleshooting Guide

## "No browser connected" Error

### Symptom
Commands fail with error: `Error: Request timeout: No browser connected`

### Cause
The Inspekt bridge server is running, but no browser tab has connected to it via WebSocket.

### Solution

1. **Ensure servers are running:**
   ```bash
   inspekt api start -d
   ```

2. **Open Chrome/Chromium:**
   - The Inspekt extension must be installed and enabled
   - Open **any** web page in a new tab (e.g., https://example.com)
   - The extension's content script automatically connects to ws://127.0.0.1:8766

3. **Verify connection:**
   ```bash
   inspekt info
   ```
   Should return page information without errors.

4. **Check extension is loaded:**
   - Open Chrome DevTools (F12)
   - Go to Console tab
   - Look for: `[Inspekt Extension] Loaded (CSP bypass enabled)`
   - Look for: `[Inspekt] Connected via WebSocket`

### Common Issues

#### Extension Not Installed
- Navigate to `chrome://extensions/`
- Enable "Developer mode"
- Click "Load unpacked"
- Select `/Users/roelvangils/inspekt_bridge/extensions/chrome`

#### Extension Disabled
- Check `chrome://extensions/` and ensure Inspekt is enabled
- If disabled, toggle it back on
- Refresh your tab

#### No Active Tab
- The extension only connects when a tab is **active and visible**
- Background tabs don't maintain connection
- Switch to the tab you want to control

#### Port Blocked
- Ensure no firewall is blocking localhost:8766
- Check server is running: `lsof -i :8766`

## URL Scheme Issues

### "Unknown command" Error
**Wrong:** `inspekt://info&output=both` (using `&` for first param)
**Correct:** `inspekt://info?output=both` (using `?` for first param)

### AppleScript Errors in Log
If you see syntax errors in `~/inspekt_applescript.log`, these are usually harmless logging artifacts. The commands should still execute.

### Commands Timeout
- Same as "No browser connected" - ensure browser is open
- For AI commands (summarize, describe, ask), ensure page has readable content
- Check that `mods` CLI is installed: `which mods`

## Port Conflicts

### Bridge Server (8766)
```bash
# Check what's using the port
lsof -i :8766

# Kill existing process
kill <PID>

# Restart
inspekt api start -d
```

### API Server (8000)
```bash
# Check what's using the port
lsof -i :8000

# Start on different port
inspekt api start --port 8001 -d
```

## Logs

### Check server logs
```bash
# Bridge server output
ps aux | grep bridge_ws

# API server output
ps aux | grep uvicorn
```

### Check URL handler logs
```bash
# macOS URL scheme handler
tail -f ~/inspekt_url_handler.log

# AppleScript app
tail -f ~/inspekt_applescript.log
```

## Testing

### Test bridge connection
```bash
# Should return page info
inspekt info

# Should return page title
inspekt eval "document.title"
```

### Test API
```bash
# Should return current URL
curl -s api:8000/api/info | jq .result.url
```

### Test URL scheme
Open in browser or Terminal:
```bash
open "inspekt://info?output=both"
```

## Getting Help

If issues persist:
1. Collect logs from all sources above
2. Check Chrome DevTools console for errors
3. Verify extension version matches CLI: `inspekt --version`
4. Try reloading the extension and refreshing the browser tab
