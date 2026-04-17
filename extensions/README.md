# Inspekt - Extensions

Browser extensions for Inspekt that **bypass CSP restrictions** and work on **all websites**.

## Why Extensions?

While the userscript installation is quick and easy, many important websites have **Content Security Policy (CSP)** restrictions that block WebSocket connections and script injection:

### Security Model 🔒

Both extensions now include **explicit opt-in per domain**:
- Permission modal appears on first visit to any domain
- You choose which websites Zen can access
- Manage allowed domains from extension popup
- Revoke access anytime

**You're in control** - Inspekt only works on domains you explicitly allow.

| Website Type | Userscript | Extension |
|--------------|-----------|-----------|
| **GitHub** | ❌ Blocked by CSP | ✅ Works |
| **Gmail** | ❌ Blocked by CSP | ✅ Works |
| **Banking Sites** | ❌ Blocked by CSP | ✅ Works |
| **Government Portals** | ❌ Blocked by CSP | ✅ Works |
| **Most Other Sites** | ✅ Works | ✅ Works |

**Extensions have elevated privileges** that allow them to bypass CSP restrictions safely and securely.

## Available Extensions

### Firefox Extension
✅ **Available Now** - Full CSP bypass support

📖 [Firefox Installation Guide](firefox/README.md)

**Features:**
- Works on all websites including GitHub, Gmail, banking sites
- Built-in settings panel with connection status
- DevTools integration with `inspektStore($0)`
- Auto-reconnect on page navigation
- Version 4.0.0

**Installation:**
1. Download the extension files
2. Navigate to `about:debugging#/runtime/this-firefox`
3. Click "Load Temporary Add-on…"
4. Select `manifest.json` from `extensions/firefox/`

[Read full Firefox guide →](firefox/README.md)

### Chrome Extension
✅ **Available Now** - Full CSP bypass support

📖 [Chrome Installation Guide](chrome/README.md)

**Features:**
- Works on all websites including GitHub, Gmail, banking sites
- Built-in settings panel with connection status
- DevTools integration with `inspektStore($0)`
- Auto-reconnect on page navigation
- Manifest V3 (future-proof)
- Version 4.0.0

**Installation:**
1. Download the extension files
2. Navigate to `chrome://extensions/`
3. Enable "Developer mode"
4. Click "Load unpacked"
5. Select the `extensions/chrome/` directory

[Read full Chrome guide →](chrome/README.md)

**Publishing:** See [Chrome Web Store Submission Guide](chrome/CHROME_WEB_STORE.md)

### Edge Extension
📅 **Planned** - Future release

Microsoft Edge extension support is planned for a future release.

## Choosing Your Installation Method

### Use the Extension If:
- ✅ You need to use Zen on GitHub, Gmail, or banking sites
- ✅ You want maximum compatibility across all websites
- ✅ You don't mind a slightly more complex installation
- ✅ You want a built-in settings panel with status indicator

### Use the Userscript If:
- ✅ You want the quickest installation (one click)
- ✅ You primarily use Zen on sites without strict CSP
- ✅ You prefer userscript managers like Tampermonkey
- ✅ You want automatic updates via Tampermonkey

**Recommendation:** Start with the userscript for quick testing. If you encounter CSP issues on important sites, switch to the extension.

## How CSP Bypass Works

Extensions use the browser's native `tabs.executeScript()` API which has elevated privileges:

```
1. Content script receives execution request via WebSocket
2. Content script sends message to background script
3. Background script uses tabs.executeScript() to bypass CSP
4. Result is sent back to CLI via WebSocket
```

This is **safe and intended** - browser extensions are designed to have elevated privileges for legitimate purposes like browser automation, developer tools, and productivity enhancements.

## Feature Comparison

| Feature | Userscript | Firefox Extension | Chrome Extension |
|---------|-----------|-------------------|------------------|
| **Installation** | ⚡ One click | 🔧 Few steps | 🔧 Few steps |
| **CSP Bypass** | ❌ No | ✅ Yes | ✅ Yes |
| **GitHub** | ❌ Blocked | ✅ Works | ✅ Works |
| **Gmail** | ❌ Blocked | ✅ Works | ✅ Works |
| **Banking Sites** | ❌ Blocked | ✅ Works | ✅ Works |
| **Settings Panel** | ❌ No | ✅ Yes | ✅ Yes |
| **Status Indicator** | ❌ No | ✅ Yes | ✅ Yes |
| **DevTools Integration** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Auto-Update** | ✅ Via Tampermonkey | 🚧 Manual (for now) | 🚧 Manual (for now) |
| **Manifest Version** | N/A | V2 | V3 |
| **Version** | 3.5 | 4.0.0 | 4.0.0 |

## Common Commands (All Methods)

Once installed (via userscript or extension), all Zen commands work the same:

```bash
# Start the server
inspektserver start

# Get page information
inspektinfo

# Execute JavaScript
inspekteval "document.title"

# Natural language actions
inspektdo "click login button"

# AI-powered description
inspektdescribe

# Store element from DevTools
# 1. Right-click element → Inspect
# 2. In console: inspektStore($0)
# 3. In terminal: inspektinspected
```

## Installation Guides

- **Firefox Extension**: [extensions/firefox/README.md](firefox/README.md)
- **Chrome Extension**: [extensions/chrome/README.md](chrome/README.md)
- **Userscript** (Tampermonkey): [See main installation docs](https://roelvangils.github.io/zen-bridge/getting-started/installation/)

## Troubleshooting

### Extension Not Connecting

**Check the browser console** (F12):
- Look for `[Inspekt Extension] Loaded` message
- Look for `[Inspekt] Connected via WebSocket` message

**Verify server is running**:
```bash
inspektserver status
```

**Restart server if needed**:
```bash
inspektserver restart
```

### CSP Issues

If you're using the **userscript** and encountering CSP errors:
- Switch to the **extension** for full CSP bypass
- Read the [CSP Troubleshooting Guide](https://roelvangils.github.io/zen-bridge/troubleshooting/csp-issues/)

### Extension Not Loading

**Reload the extension**:
- Firefox: Go to `about:debugging#/runtime/this-firefox` → Click "Reload"
- Chrome: Go to `chrome://extensions` → Click reload icon

**Check for errors**:
- Firefox: Browser Console (Ctrl+Shift+J)
- Chrome: Extension error console

## Security Notes

**Are extensions safe?**
Yes! Browser extensions from trusted sources are safe. The CSP bypass functionality is:
- ✅ A standard browser extension capability
- ✅ Used by legitimate tools (developer tools, automation, accessibility)
- ✅ Sandboxed by the browser
- ✅ Only works with your local Zen server (localhost:8766)
- ✅ Open source - you can review all code

**Privacy:**
- No data is sent to external servers
- All communication stays between your browser and local CLI
- No tracking or analytics

## Development

### Testing Changes

**Firefox:**
1. Make changes to extension files
2. Go to `about:debugging#/runtime/this-firefox`
3. Click "Reload" next to Inspekt
4. Test on a CSP-protected site like GitHub

### Building for Distribution

Coming soon! We'll add build scripts for:
- Creating signed extension packages
- Packaging for browser stores
- Automated releases

## Links

- 📖 [Main Documentation](https://roelvangils.github.io/zen-bridge/)
- 💻 [GitHub Repository](https://github.com/roelvangils/zen-bridge)
- 🐛 [Report Issue](https://github.com/roelvangils/zen-bridge/issues)
- 📚 [API Reference](https://roelvangils.github.io/zen-bridge/api/overview/)
- 🔧 [Troubleshooting](https://roelvangils.github.io/zen-bridge/troubleshooting/csp-issues/)

## Contributing

We welcome contributions! If you'd like to:
- Add support for other browsers (Chrome, Edge, Safari)
- Improve the extension UI
- Fix bugs or add features

Please open an issue or pull request on GitHub.

## License

Part of Inspekt - see main repository for license.
