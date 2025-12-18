# Inspekt UI Components Development Guide

A comprehensive guide for editing and developing the HTML/CSS-based UI components in Inspekt with hot-reloading workflows.

**Last Updated**: 2025-11-24

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Component Overview](#component-overview)
3. [Development Workflows](#development-workflows)
4. [Hot-Reloading Setup](#hot-reloading-setup)
5. [File Locations Reference](#file-locations-reference)
6. [Common Issues & Solutions](#common-issues--solutions)
7. [CSS Architecture](#css-architecture)
8. [Testing Checklist](#testing-checklist)

---

## Quick Start

### Install Development Dependencies

```bash
npm install
```

This installs:
- `web-ext` - Auto-reload browser extensions on file changes
- `chokidar-cli` - File watching for manual reload workflow

### Start Development Environment

**Option 1: Auto-Reload (Recommended for Popup)**
```bash
npm run dev:chrome   # Opens Chrome with auto-reloading extension
npm run dev:firefox  # Opens Firefox with auto-reloading extension
```

**Option 2: Manual Reload with File Watcher**
```bash
npm run watch:extensions  # Shows notifications when files change
```

**Option 3: Axe Popover Development**
```bash
npm run watch:axe        # Watch for Axe popover file changes
inspekt axe --interactive  # Test changes immediately
```

---

## Component Overview

Inspekt has three main UI components, all using **vanilla HTML/CSS/JavaScript** with no build process:

### 1. Floating Accessibility (Axe) Popover

**Purpose**: Interactive accessibility testing badges and popovers injected into web pages

**Files**:
- `inspekt/scripts/run_axe.js` (1,417 lines) - Main logic, popover creation, navigation
- `inspekt/scripts/axe_popover.css` (1,202 lines) - Complete styling
- `inspekt/scripts/vendor/` - Dependencies (axe-core, CSS anchor positioning polyfill)

**Loading Mechanism**:
- Injected via CLI command into browser's MAIN world execution context
- CSS embedded inline as `<style>` tag by JavaScript

**Features**:
- Numbered badges at violation locations
- Interactive popovers with prev/next navigation
- "Skip similar" to filter by rule type
- Detach mode with drag-and-drop
- Tabbed interface (Default view / Markdown export)
- Dark mode support

### 2. Browser Extension Popup

**Purpose**: Toolbar extension popup for managing connection status and permissions

**Chrome Files**:
- `extensions/chrome/popup/popup.html`
- `extensions/chrome/popup/popup.css` (10,057 bytes)
- `extensions/chrome/popup/popup.js` (8,931 bytes)

**Firefox Files** (shared):
- `extensions/shared/popup/popup-base.html`
- `extensions/shared/popup/popup-base.css` (6,526 bytes)
- `extensions/shared/popup/popup-base.js` (11,904 bytes)

**Loading Mechanism**:
- Defined in `manifest.json` as `action.default_popup` (Chrome) or `browser_action.default_popup` (Firefox)
- Loads when user clicks extension icon in toolbar

**Features**:
- Connection status indicator (WebSocket bridge)
- Domain permissions management
- Quick access toggle (temporary bypass)
- Links to documentation

### 3. DevTools Advanced Panel

**Purpose**: Full-featured panel inside Chrome DevTools for element inspection and quick actions

**Core Files**:
- `extensions/chrome/devtools.html` - Panel registration entry point
- `extensions/chrome/devtools.js` (81 lines) - Creates panel via Chrome API
- `extensions/chrome/panel.html` (189 lines) - Panel UI structure
- `extensions/chrome/panel.css` (24,963 bytes) - Complete styling
- `extensions/chrome/panel.js` - ES6 module entry point

**Modular Architecture** (ES6 Modules):
```
extensions/chrome/
├── modules/
│   ├── connection-manager.js     (4,162 bytes)
│   ├── element-display.js        (10,919 bytes)
│   ├── element-monitor.js        (4,381 bytes)
│   ├── history-manager.js        (6,793 bytes)
│   ├── quick-actions-manager.js  (12,620 bytes)
│   ├── settings-manager.js       (2,241 bytes)
│   └── theme-manager.js          (2,521 bytes)
├── components/
│   ├── element-highlighter.js
│   ├── element-picker.js
│   └── quick-actions/
│       ├── action-tile.js
│       ├── drag-handler.js
│       ├── keyboard-handler.js
│       └── manage-panel.js
└── handlers/ (various element navigation handlers)
```

**Loading Mechanism**:
1. `devtools.html` specified in manifest.json as `devtools_page`
2. Chrome loads `devtools.js` when DevTools opens
3. `devtools.js` calls `chrome.devtools.panels.create()` to register panel
4. Panel displays `panel.html` which loads `panel.js` as ES6 module
5. `panel.js` imports and initializes all managers/components

**Features**:
- Currently inspected element display (syncs with Elements panel)
- Quick actions grid (configurable, draggable tiles)
- Element history tracking
- Connection status to Python bridge server
- Theme switcher (Auto/Light/Dark)
- Element picker with highlighting
- Settings persistence via chrome.storage

---

## Development Workflows

### Workflow 1: Axe Popover (Simplest)

The Axe popover has the **simplest development workflow** because it's injected fresh each time you run the CLI command.

**Steps:**
```bash
# Terminal 1: Watch for file changes (optional)
npm run watch:axe

# Terminal 2: Edit files
vim inspekt/scripts/axe_popover.css
vim inspekt/scripts/run_axe.js

# Terminal 3: Test changes immediately
inspekt axe --interactive
```

**Why it's simple:**
- No extension reload required
- Fresh injection every time
- Changes appear instantly
- No caching issues

**Iteration time:** ~5 seconds (edit → run command → see result)

### Workflow 2: Extension Popup (Auto-Reload)

The popup benefits most from auto-reload because it's quick to open and test.

**Steps:**
```bash
# Terminal 1: Start auto-reloading browser
npm run dev:chrome

# Terminal 2: Edit files
vim extensions/chrome/popup/popup.css
vim extensions/chrome/popup/popup.js

# Browser: Extension auto-reloads on save
# Click extension icon in toolbar → See changes
```

**Iteration time:** ~3 seconds (edit → save → click icon)

**Alternative (Manual Reload):**
```bash
# 1. Setup keyboard shortcut once
# Go to chrome://extensions/shortcuts
# Set Ctrl+Shift+R for "Reload extension"

# 2. Edit files
vim extensions/chrome/popup/popup.css

# 3. Press Ctrl+Shift+R
# 4. Click extension icon
```

### Workflow 3: DevTools Panel (Most Complex)

The DevTools panel requires the most steps because Chrome doesn't reload panels automatically.

**Steps:**
```bash
# Terminal 1: Watch for file changes
npm run watch:extensions

# Terminal 2: Edit files
vim extensions/chrome/panel.css
vim extensions/chrome/modules/element-display.js

# Browser: Per change iteration:
# 1. See file change notification in terminal
# 2. Go to chrome://extensions or press Ctrl+Shift+R
# 3. Click reload icon on Inspekt extension
# 4. Close DevTools (Ctrl+Shift+I or F12)
# 5. Reopen DevTools (Ctrl+Shift+I or F12)
# 6. Click "Inspekt" panel tab
```

**Iteration time:** ~10-15 seconds (edit → reload → close/reopen DevTools)

**CSS-Only Changes (Faster):**
For pure CSS changes, you might be able to skip the extension reload:
```bash
# 1. Edit CSS
vim extensions/chrome/panel.css

# 2. Close DevTools
# 3. Reopen DevTools
# 4. Click "Inspekt" tab
```

**Iteration time:** ~5 seconds (edit → close/reopen DevTools)

---

## Hot-Reloading Setup

### web-ext Auto-Reload (Installed)

The `web-ext` tool automatically reloads extensions when files change.

**Available Commands:**

```bash
# Chrome development (auto-reload)
npm run dev:chrome

# Firefox development (auto-reload)
npm run dev:firefox

# File watcher with manual reload
npm run watch:extensions

# Axe popover file watcher
npm run watch:axe
```

**What `web-ext` Does:**
- Opens a new browser instance with a clean profile
- Loads your extension automatically
- Watches for file changes
- Reloads extension when files change
- Opens useful URLs (chrome://extensions, about:debugging)

**Limitations:**
- DevTools panels still require manual close/reopen (Chrome API limitation)
- Creates a new browser profile (not your main profile)
- Can't preserve logged-in state from your main browser

### Keyboard Shortcut Setup (Optional but Recommended)

**Chrome:**
1. Go to `chrome://extensions/shortcuts`
2. Find "Inspekt" extension
3. Set a keyboard shortcut (e.g., `Ctrl+Shift+R`)
4. Now you can reload the extension without opening the extensions page

**Firefox:**
1. Go to `about:addons`
2. Click gear icon → Manage Extension Shortcuts
3. Find "Inspekt" and set shortcut

### File Watcher Script

The `watch-extensions.js` script provides intelligent notifications:

**Features:**
- Monitors all extension HTML/CSS/JS files
- Detects which component changed (popup, panel, module)
- Provides context-specific reload instructions
- Color-coded terminal output
- Shows file type (HTML, CSS, JS)

**Usage:**
```bash
npm run watch:extensions
```

**Example Output:**
```
✨ File changed: extensions/chrome/panel.css
Component: panel (CSS)

📝 Reload Steps (DevTools Panel):
  1. Go to chrome://extensions (or press Ctrl+Shift+R if shortcut configured)
  2. Click reload icon on Inspekt extension card
  3. Close DevTools completely (Ctrl+Shift+I)
  4. Reopen DevTools (Ctrl+Shift+I)
  5. Click "Inspekt" panel tab

  Note: CSS-only changes might work with just DevTools close/reopen
```

---

## File Locations Reference

### Axe Popover
| File | Location | Size | Description |
|------|----------|------|-------------|
| Main JS | `inspekt/scripts/run_axe.js` | 1,417 lines | Popover logic, navigation, badge injection |
| CSS | `inspekt/scripts/axe_popover.css` | 1,202 lines | Complete styling, animations, dark mode |
| Axe Core | `inspekt/scripts/vendor/axe-core.min.js` | Vendor | Accessibility testing engine |
| Polyfill | `inspekt/scripts/vendor/css-anchor-positioning.js` | Vendor | CSS Anchor Positioning for Firefox |

### Chrome Extension Popup
| File | Location | Size | Description |
|------|----------|------|-------------|
| HTML | `extensions/chrome/popup/popup.html` | - | Popup structure |
| CSS | `extensions/chrome/popup/popup.css` | 10,057 bytes | Popup styling |
| JS | `extensions/chrome/popup/popup.js` | 8,931 bytes | Popup logic, connection status |

### Firefox Extension Popup (Shared)
| File | Location | Size | Description |
|------|----------|------|-------------|
| HTML | `extensions/shared/popup/popup-base.html` | - | Popup structure |
| CSS | `extensions/shared/popup/popup-base.css` | 6,526 bytes | Popup styling |
| JS | `extensions/shared/popup/popup-base.js` | 11,904 bytes | Popup logic |

### DevTools Panel
| File | Location | Size | Description |
|------|----------|------|-------------|
| Entry | `extensions/chrome/devtools.html` | Minimal | Loads devtools.js |
| Registration | `extensions/chrome/devtools.js` | 81 lines | Panel registration |
| Panel HTML | `extensions/chrome/panel.html` | 189 lines | Panel structure |
| Panel CSS | `extensions/chrome/panel.css` | 24,963 bytes | Complete styling |
| Panel JS | `extensions/chrome/panel.js` | ES6 module | Entry point, imports managers |

### DevTools Panel Modules
| Module | Location | Size | Purpose |
|--------|----------|------|---------|
| Connection Manager | `extensions/chrome/modules/connection-manager.js` | 4,162 bytes | WebSocket bridge connection |
| Element Display | `extensions/chrome/modules/element-display.js` | 10,919 bytes | Inspected element rendering |
| Element Monitor | `extensions/chrome/modules/element-monitor.js` | 4,381 bytes | Selection monitoring |
| History Manager | `extensions/chrome/modules/history-manager.js` | 6,793 bytes | Element history tracking |
| Quick Actions | `extensions/chrome/modules/quick-actions-manager.js` | 12,620 bytes | Action grid management |
| Settings Manager | `extensions/chrome/modules/settings-manager.js` | 2,241 bytes | Persistent settings |
| Theme Manager | `extensions/chrome/modules/theme-manager.js` | 2,521 bytes | Theme switching |

---

## Common Issues & Solutions

### Issue: DevTools Panel Not Updating After Extension Reload

**Cause**: Chrome DevTools panels are loaded once when DevTools opens. Reloading the extension doesn't reload already-open panels.

**Solution**:
1. Reload the extension in `chrome://extensions`
2. **Close DevTools completely** (not just the tab, the entire DevTools window)
3. Reopen DevTools
4. Navigate to "Inspekt" panel tab

**Quick tip**: For CSS-only changes, try just closing/reopening DevTools without reloading the extension.

### Issue: Extension Popup Changes Not Visible

**Cause**: Extension not reloaded after file changes.

**Solution**:
- If using `npm run dev:chrome`: Extension should reload automatically (wait a few seconds)
- If editing manually: Go to `chrome://extensions` and click reload icon
- If using keyboard shortcut: Press your configured shortcut (e.g., `Ctrl+Shift+R`)

### Issue: Axe Popover Styling Broken

**Cause**: CSS is embedded as inline `<style>` tag in JavaScript. Template literal escaping issues or syntax errors.

**Solution**:
1. Check `axe_popover.css` for CSS syntax errors
2. Check `run_axe.js` around line 663-1173 where CSS is embedded
3. Ensure proper escaping of backticks and `${}`
4. Run `inspekt axe --interactive` to see error messages in browser console

### Issue: ES6 Module Import Errors in Panel

**Cause**: Incorrect relative path or missing `.js` extension.

**Solution**:
1. All imports must include `.js` extension: `import { Foo } from './foo.js';`
2. Check paths are relative to the importing file
3. Check file exists at the specified location
4. Open DevTools console in the Inspekt panel itself (right-click panel → Inspect) to see errors

### Issue: Anchor Positioning Not Working in Firefox

**Cause**: Firefox doesn't yet support CSS Anchor Positioning API natively.

**Solution**:
The polyfill is automatically applied at `run_axe.js:1179`. Ensure:
1. Polyfill is loaded before popover creation
2. `CSS.supports('anchor-name', '--foo')` check works correctly
3. Check browser console for polyfill errors

### Issue: web-ext Can't Find Browser

**Cause**: Firefox or Chrome not in default installation path.

**Solution**:
```bash
# Specify custom Firefox path
npm run dev:firefox -- --firefox=/path/to/firefox

# Specify custom Chromium path
npm run dev:chrome -- --chromium-binary=/path/to/chrome
```

### Issue: Changes Not Reflecting in Main Browser Profile

**Cause**: `web-ext` uses a clean temporary profile, not your main profile.

**Solution**:
- Use manual reload workflow instead of `web-ext`
- Load extension as "unpacked" in your main browser profile
- Use `npm run watch:extensions` and manual reload

---

## CSS Architecture

### Axe Popover CSS (`axe_popover.css`)

**Structure** (1,202 lines):
1. **Font imports** (line 4) - Material Icons
2. **Popover container** (line 7-50) - Base popover styling, positioning
3. **Position fallbacks** (line 52-63) - Manual fallback for anchor positioning
4. **Header & impact badges** (line 65-100) - Severity indicators (critical, serious, etc.)
5. **Tabs** (line 112-160) - Default view / Markdown export tabs
6. **Content sections** (line 187-391) - Issue info, help text, related nodes
7. **Interactive badges** (line 428-460) - Numbered badges on page
8. **Animations** (line 479-736) - Direction-based entrance animations
9. **Navigation strip** (line 738-917) - Prev/next/skip controls
10. **Detach mode** (line 919-985) - Draggable popover
11. **Dark mode** (line 998-1201) - Dark theme overrides

**Naming Convention**: BEM-style
```css
.inspekt-axe-popover { }                          /* Block */
.inspekt-axe-popover__header { }                  /* Element */
.inspekt-axe-popover__impact-badge--critical { }  /* Modifier */
```

**Key Features**:
- Uses CSS Anchor Positioning API (`anchor-name`, `position-anchor`)
- Directional animations based on badge position
- Dark mode using `prefers-color-scheme` media query
- Material Icons font for UI icons

### Panel CSS (`panel.css`)

**Structure** (24,963 bytes) - Large file, could benefit from splitting:

**Suggested Module Split**:
```css
panel-base.css        /* Layout, typography, CSS variables, root styles */
panel-header.css      /* Header, status indicator, theme toggle */
panel-actions.css     /* Quick actions grid, tiles, drag-and-drop */
panel-element.css     /* Inspected element display, properties */
panel-history.css     /* Element history list, navigation */
panel-reference.css   /* Quick reference section, collapsible */
panel-themes.css      /* Light/dark theme variables */
```

**Current Structure** (all in one file):
- CSS custom properties (colors, spacing, transitions)
- Base layout (flexbox, grid)
- Component-specific styles
- Theme-specific overrides
- Responsive adjustments

**Naming Convention**: Mix of BEM and utility classes
```css
.inspekt-panel { }
.quick-actions-grid { }
.status-indicator--connected { }
```

### Popup CSS

**Chrome** (`popup.css` - 10,057 bytes):
- Material Design inspired
- Connection status colors
- Permission toggle switches
- Responsive layout

**Firefox** (`popup-base.css` - 6,526 bytes):
- Simpler styling
- Browser-specific adjustments
- Shared color scheme

---

## CSS Editing Best Practices

### Use Browser DevTools for Live Editing

**Best Workflow**:
1. Open component in browser (popup, panel, or page with Axe popover)
2. Open DevTools on the component (right-click → Inspect)
3. Edit CSS in DevTools Styles pane (live preview)
4. Copy working CSS back to source file
5. Reload to verify

**For Axe Popover**:
```bash
# 1. Run Axe with interactive mode
inspekt axe --interactive

# 2. Right-click on popover → Inspect
# 3. Edit styles in DevTools
# 4. Copy changes to inspekt/scripts/axe_popover.css
# 5. Run inspekt axe --interactive again to verify
```

**For Extension Popup**:
```bash
# 1. Click extension icon
# 2. Right-click on popup → Inspect
# 3. Edit styles in DevTools
# 4. Copy changes to extensions/chrome/popup/popup.css
# 5. Reload extension
```

**For DevTools Panel**:
```bash
# 1. Open DevTools → Inspekt panel
# 2. Right-click on panel → Inspect (opens DevTools-in-DevTools!)
# 3. Edit styles in nested DevTools
# 4. Copy changes to extensions/chrome/panel.css
# 5. Reload extension + close/reopen DevTools
```

### CSS Variables and Theming

All components use CSS custom properties for consistency:

```css
/* Common pattern in panel.css and popup.css */
:root {
  --color-primary: #1976d2;
  --color-success: #4caf50;
  --color-error: #f44336;
  --spacing-unit: 8px;
}

.status-indicator--connected {
  color: var(--color-success);
}
```

**Dark mode** (using prefers-color-scheme):
```css
@media (prefers-color-scheme: dark) {
  :root {
    --color-primary: #64b5f6;
    --background-primary: #1e1e1e;
  }
}
```

### Avoid Over-Specificity

**Good**:
```css
.popover__header { }
.badge--critical { }
```

**Bad**:
```css
.inspekt-axe-popover .popover-container .header .title span { }
```

### Test in Both Light and Dark Modes

```bash
# macOS: System Preferences → General → Appearance
# Toggle between Light and Dark

# Or use DevTools:
# DevTools → Rendering → Emulate prefers-color-scheme
```

---

## Testing Checklist

### Axe Popover Testing
- [ ] Edit `run_axe.js` or `axe_popover.css`
- [ ] Run `inspekt axe --interactive` on test page with accessibility issues
- [ ] Verify badge positions (should align with violations)
- [ ] Test popover navigation (prev/next buttons)
- [ ] Test "Skip similar" button (should dim related violations)
- [ ] Test detach mode (click detach button, drag popover)
- [ ] Test in light mode
- [ ] Test in dark mode (`prefers-color-scheme: dark`)
- [ ] Test with 50+ violations (badge counter should show "50+")
- [ ] Test tab switching (Default view / Markdown export)
- [ ] Test animations (should slide from badge direction)

### Extension Popup Testing
- [ ] Edit popup HTML/CSS/JS files
- [ ] Reload extension (`chrome://extensions` or `Ctrl+Shift+R`)
- [ ] Click extension icon in toolbar
- [ ] Verify connection status indicator (green = connected, red = disconnected)
- [ ] Test domain permission toggles (should persist)
- [ ] Test "Quick Access" timer (should show countdown)
- [ ] Test documentation links (should open in new tabs)
- [ ] Test in light mode
- [ ] Test in dark mode
- [ ] Test in both Chrome and Firefox (if editing shared files)

### DevTools Panel Testing
- [ ] Edit panel HTML/CSS/JS or module files
- [ ] Reload extension in `chrome://extensions`
- [ ] **Close DevTools completely**
- [ ] Reopen DevTools (`Ctrl+Shift+I` or `F12`)
- [ ] Click "Inspekt" panel tab
- [ ] Select element in Elements panel (should update Inspekt panel)
- [ ] Test element picker button (should highlight on hover)
- [ ] Test quick actions (should execute commands)
- [ ] Test quick actions drag-and-drop (should reorder tiles)
- [ ] Test theme switcher (Auto/Light/Dark - should persist)
- [ ] Test element history (should track selections)
- [ ] Test settings persistence (should survive browser restart)
- [ ] Test connection status indicator
- [ ] Inspect the panel itself (right-click → Inspect) to check for console errors
- [ ] Test with panel detached (drag tab out of DevTools)
- [ ] Test with panel in bottom/side/separate window positions

---

## Advanced Topics

### Building for Distribution

When you're ready to package extensions for Chrome Web Store or Firefox Add-ons:

**Chrome**:
```bash
cd extensions/chrome
./build.sh
# Creates: build/zen-browser-bridge-chrome-{version}.zip
```

**Firefox**:
```bash
cd extensions/firefox
./build.sh
# Creates: build/inspekt-{version}.zip
```

**What build scripts do**:
- Create clean build directory
- Copy necessary files
- Exclude development files (.git, node_modules, etc.)
- Create ZIP/XPI archive
- Do NOT transpile or bundle (vanilla files copied as-is)

### ES6 Module Loading

The DevTools panel uses native ES6 modules:

**panel.js** (entry point):
```javascript
import { ConnectionManager } from './modules/connection-manager.js';
import { ElementPicker } from './components/element-picker.js';

// Initialize managers
const connectionManager = new ConnectionManager();
const elementPicker = new ElementPicker();
```

**Important**:
- Always include `.js` extension in imports
- Use relative paths (`./`, `../`)
- Modules load asynchronously
- Errors appear in browser console (not terminal)

### Debugging Panel Modules

The panel runs in its own context. To debug:

1. Open DevTools (`Ctrl+Shift+I`)
2. Click "Inspekt" panel tab
3. Right-click anywhere in panel → "Inspect"
4. A second DevTools opens (DevTools-in-DevTools)
5. Check Console tab for errors
6. Check Sources tab to set breakpoints in modules
7. Check Network tab to see if modules loaded

### CSS Anchor Positioning

The Axe popover uses the **CSS Anchor Positioning API**:

```css
/* Badge acts as anchor */
.inspekt-axe-badge {
  anchor-name: --badge-1;
}

/* Popover positions relative to badge */
.inspekt-axe-popover {
  position: absolute;
  position-anchor: --badge-1;
  bottom: anchor(top);
  left: anchor(center);
}
```

**Browser Support**:
- ✅ Chrome 125+ (native support)
- ⚠️  Firefox (needs polyfill - automatically applied)
- ⚠️  Safari (needs polyfill - automatically applied)

**Polyfill** (`css-anchor-positioning.js`):
- Automatically loaded if browser doesn't support API
- Provides complete anchor positioning functionality
- No code changes needed

---

## Additional Resources

### Documentation
- [Chrome Extension Development](https://developer.chrome.com/docs/extensions/)
- [Firefox Extension Development](https://extensionworkshop.com/)
- [web-ext Documentation](https://extensionworkshop.com/documentation/develop/getting-started-with-web-ext/)
- [CSS Anchor Positioning](https://developer.chrome.com/blog/anchor-positioning-api)

### Inspekt-Specific
- `COMMAND_DEVELOPMENT_GUIDE.md` - Guide for adding new CLI commands
- `MCP_INTEGRATION.md` - MCP server integration details
- `CLAUDE.md` - Instructions for Claude Code development

### Tools
- [Chrome Extensions Reloader](https://chromewebstore.google.com/detail/extensions-reloader/fimgfedafeadlieiabdeeaodndnlbhid) - Alternative to web-ext
- [Firefox DevTools](https://firefox-source-docs.mozilla.org/devtools-user/) - Debugging extensions
- [Chrome DevTools](https://developer.chrome.com/docs/devtools/) - Debugging extensions

---

## Summary

### Component Complexity (Easiest → Hardest)

1. **Axe Popover** (Easiest)
   - Edit → Run CLI → See changes
   - No extension reload needed
   - Iteration time: ~5 seconds

2. **Extension Popup** (Easy)
   - Edit → Auto-reload → Click icon → See changes
   - Works great with `web-ext`
   - Iteration time: ~3 seconds

3. **DevTools Panel** (Most Complex)
   - Edit → Reload extension → Close/reopen DevTools → See changes
   - Can't auto-reload due to Chrome API limitations
   - Iteration time: ~10-15 seconds

### Key Takeaways

- **No build process** = Simple, maintainable, accessible codebase
- **Vanilla JavaScript** = No transpilation, works in all modern browsers
- **web-ext** helps with popup, less helpful for panel
- **DevTools panels** require manual close/reopen (Chrome limitation)
- **CSS-only changes** sometimes work without full reload
- **File watcher** provides context-aware reload instructions

### Recommended Setup

```bash
# Terminal 1: File watcher (for all components)
npm run watch:extensions

# Terminal 2: Editor
vim extensions/chrome/panel.css

# Browser: Manual reload workflow
# Press Ctrl+Shift+R to reload extension
# Close and reopen DevTools for panel changes
```

---

**Happy developing!** If you encounter issues not covered here, check the browser console for errors and the `watch:extensions` output for reload instructions.
