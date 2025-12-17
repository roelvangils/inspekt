# Inspekt - Firefox Extension

> ⚠️ **Note:** The Firefox extension is currently **not actively maintained**. The Chrome extension has more features including VM support, replay mode, and screencast integration. We recommend using Chrome/Chromium for the best Inspekt experience. Firefox support may be revisited in a future release.

The Firefox extension for Inspekt that **bypasses CSP restrictions** and works on **all websites** including GitHub, Gmail, banking sites, and more.

## Features

✨ **CSP Bypass** - Works on all websites, no restrictions
🔒 **Explicit Opt-In** - You control which domains Zen can access
🚀 **Automatic Connection** - Connects to localhost:8766 automatically
🛠️ **DevTools Integration** - Use `inspektStore($0)` in console
📊 **Status Panel** - Built-in settings panel with connection status and domain management
🔄 **Auto-Reconnect** - Maintains connection across page reloads
⚡ **Manifest V2** - Uses latest Chrome extension architecture

## Installation

### Method 1: Developer Mode (Temporary)

This is the quickest way to test the extension, but you'll need to reload it after browser restarts.

1. **Download the extension**:
   ```bash
   cd /path/to/inspekt
   cd extensions/chrome
   ```

2. **Open Firefox Extensions page**:
   - Navigate to `about:debugging#/runtime/this-firefox/`
   - Or click the puzzle icon (⚙️) → **Manage Extensions**

3. **Enable Developer Mode**:
   - Toggle the **"Developer mode"** switch in the top right corner

4. **Load the extension**:
   - Click **"Load unpacked"**
   - Select the `extensions/chrome` directory (the folder containing `manifest.json`)

5. **Verify installation**:
   - Look for the ⚡ **Inspekt** extension in your list
   - Click the puzzle icon and pin it to your toolbar for easy access
   - Click the ⚡ icon to see the status panel

### Method 2: Packaged Extension (.crx or .zip)

For easier distribution and installation:

1. **Build the extension** (see [Building](#building) section below)

2. **Install the packaged extension**:
   - Open `about:debugging#/runtime/this-firefox/`
   - Enable **Developer mode**
   - Drag and drop the `.zip` file onto the page
   - Or use **"Load unpacked"** and select the extracted folder

### Method 3: Chrome Web Store (Coming Soon)

Once published to the Chrome Web Store, you'll be able to install with one click. See [CHROME_WEB_STORE.md](../chrome/CHROME_WEB_STORE.md) for our publication roadmap.

## Usage

### 1. Start the Zen Server

```bash
inspektserver start
```

### 2. Open Any Website and Allow It

When you first visit a website, you'll see a permission modal:

1. **Navigate to a website** (e.g., github.com, gmail.com)
2. **Permission modal appears** - "Allow CLI control of this website?"
3. **Click "Allow [domain]"** to grant permission for that entire domain
4. **Connection established** - Inspekt is now active on that site

The extension remembers your choice, so you only need to allow each domain once. You can manage allowed domains from the extension popup.

**Security:** You must explicitly allow each domain before Inspekt can control it. This prevents unauthorized access and gives you full control.

### 3. Run Zen Commands

```bash
# Get page info
inspektinfo

# Extract title
inspekteval "document.title"

# Natural language actions
inspektdo "click login button"

# AI-powered description
inspektdescribe

# And any other inspektcommand!
```

### 4. Manage Domains via Status Panel

Click the ⚡ icon in your toolbar to:
- **View connection status** (green = connected, yellow = connecting, red = disconnected)
- **See current domain status** - Allowed or not allowed
- **Allow/remove current domain** - One-click permission management
- **View all allowed domains** - See everywhere Inspekt has access
- **Remove domains** - Revoke access anytime
- **Quick start guide** and common commands

## Advantages Over Userscript

| Feature | Userscript | Extension |
|---------|-----------|-----------|
| **Works on GitHub** | ❌ Blocked by CSP | ✅ Yes |
| **Works on Gmail** | ❌ Blocked by CSP | ✅ Yes |
| **Works on Banking Sites** | ❌ Blocked by CSP | ✅ Yes |
| **Installation** | Easier (one click) | Slightly more steps |
| **Auto-Update** | Via Tampermonkey | Via Chrome Web Store (when published) |
| **Settings Panel** | ❌ No | ✅ Yes |
| **Status Indicator** | ❌ No | ✅ Yes |

**Recommendation**: Use the extension for full compatibility on all websites!

## Security Model

### Explicit Opt-In Per Domain

**You're in control.** Inspekt requires explicit permission before it can access any website:

1. **First Visit** - Permission modal appears
2. **You Decide** - Allow or deny access for that domain
3. **Saved Choice** - Extension remembers your decision
4. **Manage Anytime** - View and revoke permissions from the popup

**Why this matters:**
- Prevents unauthorized access to your sensitive sites
- You choose exactly which domains Zen can control
- Permissions persist across sessions but can be revoked anytime
- Transparent - see all allowed domains in the settings panel

### Localhost-Only Communication

All communication stays between:
- Your browser (extension)
- Your local CLI (localhost:8766)

**No external servers. No tracking. No data collection.**

### How CSP Bypass Works

The extension uses Chrome's `tabs.executeScript()` API (Manifest V2) which has elevated privileges:

1. **Content script** receives execution request from WebSocket
2. **Sends message** to background background script
3. **Background script** uses `tabs.executeScript()` to bypass CSP
4. **Result** is sent back via WebSocket

This is **safe and intended** - browser extensions can bypass CSP for legitimate purposes like developer tools, automation, and accessibility features.

## DevTools Integration

The extension includes the same DevTools integration as the userscript:

```javascript
// In browser console:
// 1. Inspect element (Right-click → Inspect)
// 2. Store it:
inspektStore($0)

// 3. In terminal:
inspektinspected
```

## Building

### Create a ZIP Package

To create a distributable ZIP file:

```bash
cd extensions/chrome
zip -r zen-browser-bridge-chrome-4.0.0.zip . -x "*.git*" "*.DS_Store" "build.sh" "CHROME_WEB_STORE.md"
```

This creates a ZIP file that can be:
- Shared with others for manual installation
- Uploaded to Chrome Web Store for distribution

### Build Script (Coming Soon)

We'll add an automated build script similar to Firefox's:

```bash
./build.sh
```

This will:
- Validate manifest.json
- Create optimized ZIP package
- Generate checksums
- Prepare for Chrome Web Store submission

## Troubleshooting

### Extension Not Connecting

**Check the console** (F12):
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

### Extension Not Loading

**Reload extension**:
- Go to `about:debugging#/runtime/this-firefox/`
- Click the refresh icon (↻) on the Inspekt card

**Check for errors**:
- Look in the extension's "Errors" section on `about:debugging#/runtime/this-firefox/`
- Check the background background script console
- Check the browser console (F12) on any page

### CSP Still Blocking?

If you're still seeing CSP errors:

1. **Verify extension is active**:
   - Go to `about:debugging#/runtime/this-firefox/`
   - Make sure Inspekt is enabled
   - Check that it has all required permissions

2. **Check permissions**:
   - The extension needs `activeTab`, `scripting`, and `<all_urls>` permissions
   - If prompted, click "Allow" for all permissions

3. **Reload the page**:
   - The content script loads when the page loads
   - Try refreshing the page after enabling the extension

### "Service worker (inactive)" Warning

This is normal! Chrome's Manifest V2 background scripts sleep when not in use to save resources. They wake up automatically when needed.

### Still Not Working?

1. Check [Troubleshooting Guide](https://roelvangils.github.io/inspekt/troubleshooting/csp-issues/)
2. Open an issue: https://github.com/roelvangils/inspekt/issues

## Development

### File Structure

```
chrome/
├── manifest.json          # Extension manifest (Manifest V2)
├── background.js          # Background background script (CSP bypass)
├── content.js             # Content script (WebSocket)
├── popup/
│   ├── popup.html         # Settings panel
│   ├── popup.css          # Styling
│   └── popup.js           # Panel logic
├── icons/                 # Extension icons
├── README.md              # This file
└── CHROME_WEB_STORE.md    # Web Store submission guide
```

### Testing Changes

1. Make your changes to the extension files
2. Go to `about:debugging#/runtime/this-firefox/`
3. Click the **refresh icon (↻)** next to Inspekt
4. Test on a CSP-protected site like GitHub or Gmail

### Debugging

**Background Service Worker**:
- Go to `about:debugging#/runtime/this-firefox/`
- Click "background script" link under Inspekt
- This opens DevTools for the background script

**Content Script**:
- Open DevTools on any page (F12)
- Check the Console tab for Inspekt messages

**Popup**:
- Right-click the ⚡ icon → "Inspect popup"
- This opens DevTools for the popup

## Differences from Firefox Extension

The Chrome extension uses **Manifest V2** while Firefox uses Manifest V2:

| Feature | Firefox (Manifest V2) | Chrome (Manifest V2) |
|---------|---------------------|---------------------|
| **Background** | Persistent background page | Service worker (event-driven) |
| **API Namespace** | `browser.*` | `chrome.*` |
| **Script Execution** | `tabs.executeScript()` | `tabs.executeScript()` |
| **Permissions** | Combined in `permissions` | Split into `permissions` and `host_permissions` |

Both versions provide the same functionality and CSP bypass capabilities.

## Version History

### 4.0.0 (Current)
- ✅ Initial Chrome extension release
- ✅ Manifest V2 implementation
- ✅ CSP bypass using tabs.executeScript()
- ✅ Settings panel with status indicator
- ✅ DevTools integration
- ✅ Works on all websites

## FAQ

**Q: Why an extension instead of just a userscript?**
A: Userscripts are blocked by CSP on many important sites (GitHub, Gmail, banking). Extensions have elevated privileges and can bypass CSP.

**Q: Is it safe to bypass CSP?**
A: Yes! Browser extensions are designed to have elevated privileges. CSP restrictions apply to web content, not to trusted browser extensions.

**Q: Why Manifest V2?**
A: Chrome is phasing out Manifest V2 extensions. Manifest V2 is the future-proof standard for Chrome extensions.

**Q: Will this work on Edge, Brave, or other Chromium browsers?**
A: Yes! This extension should work on any Chromium-based browser (Edge, Brave, Opera, Vivaldi, etc.). Just load it in developer mode.

**Q: Can I use both userscript and extension?**
A: It's recommended to use only one at a time to avoid conflicts. The extension is the better choice for compatibility.

**Q: When will it be on Chrome Web Store?**
A: We're preparing for submission! See [CHROME_WEB_STORE.md](../chrome/CHROME_WEB_STORE.md) for our publication roadmap and how you can help.

## Publishing to Chrome Web Store

See [CHROME_WEB_STORE.md](../chrome/CHROME_WEB_STORE.md) for detailed instructions on how to publish this extension to the Chrome Web Store.

## License

Part of Inspekt - see main repository for license.

## Links

- 📖 [Documentation](https://roelvangils.github.io/inspekt/)
- 💻 [GitHub](https://github.com/roelvangils/inspekt)
- 🐛 [Report Issue](https://github.com/roelvangils/inspekt/issues)
- 🌐 [Chrome Web Store](../chrome/CHROME_WEB_STORE.md) (Coming Soon)
