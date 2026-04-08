# Updating Inspekt

Keep Inspekt up to date to get the latest features, bug fixes, and improvements.

---

## Updating the CLI

The Inspekt CLI is installed via pip and can be updated with a single command.

### Check Current Version

```bash
inspekt--version
```

### Update to Latest Version

```bash
pip install --upgrade inspekt-bridge
```

Or with pipx:

```bash
pipx upgrade inspekt-bridge
```

### Verify Update

```bash
inspekt--version
# Should show the new version

inspektserver restart
# Restart the server to use the new version
```

---

## Updating the Userscript

The userscript runs in your browser and needs to be updated separately from the CLI.

### Automatic Updates (Recommended)

**Since version 3.5**, the userscript supports automatic updates:

1. **Tampermonkey/Violentmonkey will check for updates** periodically (usually daily)
2. **You'll be prompted** when an update is available
3. **Click "Update"** to install the new version

**To check manually:**

1. Open Tampermonkey/Violentmonkey dashboard
2. Find "Inspekt (WebSocket)"
3. Click the "Check for updates" button
4. Install if an update is available

### Manual Update

If you have version 3.4 or earlier (without auto-update):

1. **Open Tampermonkey/Violentmonkey dashboard**
2. **Delete the old "Inspekt" script**
3. **Visit the raw userscript file:**
   ```
   https://raw.githubusercontent.com/roelvangils/inspekt-bridge/main/userscript_ws.js
   ```
4. **Tampermonkey/Violentmonkey will prompt to install** the new version
5. **Click "Install"**
6. **Reload any open tabs** to activate the new version

### Verify Userscript Version

Open the browser console (F12) and check:

```javascript
window.__INSPEKT_BRIDGE_VERSION__
// Should show "3.5" or higher
```

Or look for the version in the console on page load:

```
[Inspekt] Connected via WebSocket
```

---

## What's New in Each Version

### Version 3.5 (Latest)

**New Features:**
- ✅ CSP (Content Security Policy) detection
- ✅ User-friendly warnings when CSP blocks Zen
- ✅ Automatic update support via @updateURL
- ✅ Better error handling for connection failures

**Changes:**
- Prevents unnecessary reconnection attempts on CSP-blocked sites
- Exposes `__INSPEKT_BRIDGE_CSP_BLOCKED__` flag for CLI integration

**Documentation:**
- New troubleshooting guide for CSP issues
- Comprehensive explanation of CSP limitations

### Version 3.4

**Features:**
- WebSocket-based communication
- DevTools integration with `inspektStore($0)`
- Keepalive ping/pong
- Auto-reconnection on disconnect
- Visibility-based connection management

---

## Breaking Changes

### Version 3.x → 4.x (If/When Released)

Future major versions may include breaking changes. Check the changelog before updating.

### Version 2.x → 3.x (Historical)

- Switched from HTTP polling to WebSocket
- Changed server ports (8765 HTTP API, 8766 WebSocket)
- Improved reconnection logic

---

## Troubleshooting Updates

### CLI Update Issues

**Issue: "Command not found" after update**

```bash
# If using pip
which inspekt
# Should show path to inspekt

# If it's missing, reinstall
pip install --force-reinstall inspekt-bridge

# If using pipx
pipx reinstall inspekt-bridge
```

**Issue: Old version still showing**

```bash
# Clear pip cache
pip cache purge

# Reinstall
pip install --upgrade --force-reinstall --no-cache-dir inspekt-bridge

# Verify
inspekt--version
```

### Userscript Update Issues

**Issue: Auto-update not working**

You may have version 3.4 or earlier without auto-update support. Use the manual update method above.

**Issue: Two versions installed**

1. Open Tampermonkey/Violentmonkey dashboard
2. Look for duplicate "Inspekt" entries
3. Delete the older version (check version number in script header)
4. Keep only the latest version

**Issue: "Script already installed" error**

1. Delete the existing script first
2. Then install the new version
3. Reload browser tabs

---

## Checking for Updates

### CLI

Check the [GitHub Releases](https://github.com/roelvangils/inspekt-bridge/releases) page for new versions:

```bash
# Check PyPI for latest version
pip index versions inspekt-bridge

# Compare with your version
inspekt--version
```

### Userscript

The userscript version is in the file header:

```javascript
// @version      3.5
```

Check the [latest version on GitHub](https://github.com/roelvangils/inspekt-bridge/blob/main/userscript_ws.js).

---

## Update Notifications

### Stay Informed

- **Watch the repository** on GitHub for release notifications
- **Star the repo** to follow development
- **Check the changelog** regularly: [CHANGELOG.md](https://github.com/roelvangils/inspekt-bridge/blob/main/CHANGELOG.md)

### Automatic Checks

The CLI doesn't currently check for updates automatically. This may be added in a future version.

The userscript (v3.5+) automatically checks for updates via Tampermonkey/Violentmonkey.

---

## Downgrading

If you need to downgrade due to issues:

### CLI

```bash
# Downgrade to specific version
pip install inspekt-bridge==2.0.0

# Or use pipx
pipx install inspekt-bridge==2.0.0 --force
```

### Userscript

1. Visit the [commit history](https://github.com/roelvangils/inspekt-bridge/commits/main/userscript_ws.js)
2. Find the version you want
3. Click "View file" on that commit
4. Click "Raw" to get the direct URL
5. Install from that URL

---

## Best Practices

1. **Always update both CLI and userscript together** for compatibility
2. **Restart the server** after CLI updates: `inspektserver restart`
3. **Reload browser tabs** after userscript updates
4. **Check the changelog** before updating for breaking changes
5. **Test after updates** to ensure everything works

---

## Need Help?

If you encounter issues during updates:

1. Check the [Troubleshooting Guide](../troubleshooting/csp-issues.md)
2. Visit [GitHub Issues](https://github.com/roelvangils/inspekt-bridge/issues)
3. Include your version numbers when reporting problems:
   ```bash
   inspekt--version
   # And userscript version from console
   ```
