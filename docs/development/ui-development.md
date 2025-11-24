# UI Component Development

This guide covers how to edit and develop the HTML/CSS-based UI components in Inspekt with hot-reloading workflows.

## Overview

Inspekt has three main UI components, all using **vanilla HTML/CSS/JavaScript**:

| Component | Purpose | Complexity |
|-----------|---------|------------|
| **Axe Popover** | Accessibility testing badges and popovers | Easiest |
| **Extension Popup** | Toolbar popup for connection status and permissions | Easy |
| **DevTools Panel** | Full-featured panel for element inspection | Complex |

---

## 1. Axe Popover Development

The floating accessibility popover appears when running `inspekt axe --interactive`. This is the **easiest** component to develop because changes can be tested with a simple CLI command.

### File Locations

**CSS (modular):**

| File | Description |
|------|-------------|
| `inspekt/scripts/axe-popover/index.css` | Entry point (imports all modules) |
| `inspekt/scripts/axe-popover/tokens.css` | Design tokens (colors, spacing, typography) |
| `inspekt/scripts/axe-popover/base.css` | Popover container, anchor positioning |
| `inspekt/scripts/axe-popover/nav.css` | Navigation bar |
| `inspekt/scripts/axe-popover/content.css` | Header, tabs, body, sections |
| `inspekt/scripts/axe-popover/badges.css` | Interactive page badges |
| `inspekt/scripts/axe-popover/animations.css` | Keyframe animations |
| `inspekt/scripts/axe-popover/themes.css` | Dark mode, high contrast |

**JavaScript:**

| File | Description |
|------|-------------|
| `inspekt/scripts/run_axe.js` | Logic, HTML structure, embedded production CSS |

### How CSS Loading Works

The Axe popover CSS can be loaded in two ways:

| Mode | How CSS is loaded | Use case |
|------|-------------------|----------|
| **Production** | CSS is minified and embedded inline in `run_axe.js` | Normal usage |
| **Development** | CSS is fetched from `localhost:8000` with hot-reload | Editing CSS |

In **production mode** (`inspekt axe --interactive`), the CSS is baked into the JavaScript file. This means users don't need a dev server, but you need to rebuild after making changes.

In **development mode** (`inspekt axe --interactive --dev-css`), the CSS is loaded from a local server and automatically reloads when you save changes.

### Development Workflow (Recommended)

This workflow provides **automatic CSS hot-reloading** - edit your CSS, save, and see changes instantly in the browser without refreshing.

> **Note:** The axe command works even when your terminal has focus (unlike most Inspekt commands). See [Tab Visibility and Focus](#tab-visibility-and-focus) for details.

---

#### Step 1: Open three windows

You'll need:

| Window | Purpose |
|--------|---------|
| **Terminal 1** | CSS dev server |
| **Terminal 2** | Run inspekt commands |
| **VS Code** | Edit the CSS files |
| **Browser** | View the results |

---

#### Step 2: Start the CSS dev server (Terminal 1)

```bash
npm run dev:axe-css
```

You'll see:

```
🚀 CORS-enabled server running at http://localhost:8000
📁 Serving files from: /path/to/inspekt/scripts
🔗 CSS URL: http://localhost:8000/axe-popover/index.css
🔄 Hot-reload: Detects changes in ANY .css file in axe-popover/

💡 Press Ctrl+C to stop and build CSS for production
```

The server:
- Serves CSS files with CORS headers (so the browser can fetch them)
- Tracks the newest modification time across ALL CSS files in `axe-popover/`
- Automatically builds production CSS when you press Ctrl+C

---

#### Step 3: Open a test page in your browser

Either navigate to any website, or create a simple test page with accessibility issues:

```bash
cat > /tmp/test-a11y.html << 'EOF'
<!DOCTYPE html>
<html>
<head><title>A11y Test</title></head>
<body>
  <img src="hero.jpg">
  <button></button>
  <a href="#"></a>
  <input type="text">
</body>
</html>
EOF

open /tmp/test-a11y.html
```

---

#### Step 4: Run axe with dev CSS mode (Terminal 2)

```bash
inspekt axe --interactive --dev-css
```

This:
- Runs the accessibility audit
- Injects badges on the page
- Loads CSS from `http://localhost:8000/axe-popover/index.css` (instead of embedding inline)
- **Starts CSS hot-reload polling** (checks for changes every 1.5 seconds)

You'll see in the browser console:

```
[Inspekt Dev Mode] CSS loaded from http://localhost:8000/axe-popover/index.css
[Inspekt Dev Mode] Start server: npm run dev:axe-css
[Inspekt Dev Mode] Hot-reload enabled - save CSS to see changes automatically
[Inspekt Dev Mode] CSS hot-reload started (checking every 1.5s)
```

---

#### Step 5: Edit CSS in VS Code

Open the CSS directory:

```bash
code inspekt/scripts/axe-popover/
```

Edit any file - the hot-reload detects changes in **all** CSS files in the directory, not just `index.css`.

---

#### Step 6: Make changes and save

1. Edit any CSS property (e.g., change a color, spacing, or border radius)
2. Save the file (`Cmd+S` / `Ctrl+S`)
3. **Watch the browser** - changes appear automatically within ~1.5 seconds!

When CSS reloads, you'll see in the console:

```
[Inspekt Dev Mode] CSS reloaded at 3:45:12 PM
```

---

#### Step 7: Stop the server and build

When you're done editing, press **Ctrl+C** in Terminal 1. The server will:

1. Stop serving files
2. **Automatically build the production CSS**
3. Embed the minified CSS into `run_axe.js`

```
👋 Stopping server...

📦 Building CSS for production...
   Building Axe Popover CSS...
   Original: 12.3 KB (7 files)
   Minified: 9.2 KB
   Reduction: 25%
   Updated: inspekt/scripts/run_axe.js
✅ CSS built successfully!
```

Your changes are now ready for production use and can be committed.

---

#### Summary: The Complete Loop

```
┌─────────────────────────────────────────────────────────┐
│  1. npm run dev:axe-css        (start server)           │
│  2. inspekt axe --interactive --dev-css                 │
│  3. Edit CSS in VS Code                                 │
│  4. Save (Cmd+S) → see changes in ~1.5s                 │
│  5. Repeat steps 3-4 as needed                          │
│  6. Ctrl+C in server terminal → auto-builds CSS         │
│  7. Commit your changes                                 │
└─────────────────────────────────────────────────────────┘
```

**No manual build step required** - Ctrl+C handles it automatically.

### Alternative: Browser DevTools (Quick Prototyping)

For quick CSS experiments without setting up the dev server:

1. Run `inspekt axe --interactive`
2. Click a badge to open the popover
3. Right-click the popover → "Inspect"
4. Edit CSS in the Styles panel (changes appear instantly!)
5. Copy working CSS back to the appropriate file in `axe-popover/`

### Building CSS Manually

If you need to build CSS without the dev server (e.g., after pulling changes):

```bash
npm run build:axe-css
```

This:
- Concatenates all CSS files in correct order (following `@import` statements)
- Minifies the result (~25% smaller)
- Updates the embedded CSS in `run_axe.js`

**Output:**
```
Building Axe Popover CSS...
  Original: 12.3 KB (7 files)
  Minified: 9.2 KB
  Reduction: 25%
  Updated: inspekt/scripts/run_axe.js
Done!
```

> **Important:** Always build CSS before committing changes, otherwise users without `--dev-css` won't see your updates. The dev server does this automatically on Ctrl+C.

### Command Reference

| Command | Description |
|---------|-------------|
| `npm run dev:axe-css` | Start CSS dev server (auto-builds on Ctrl+C) |
| `npm run build:axe-css` | Manually build and embed minified CSS |
| `inspekt axe --interactive` | Production mode (CSS embedded inline) |
| `inspekt axe --interactive --dev-css` | Dev mode (CSS from localhost:8000) |

---

## 2. Extension Popup Development

The browser extension popup appears when clicking the Inspekt icon in the toolbar.

### File Locations

**Chrome:**

| File | Description |
|------|-------------|
| `extensions/chrome/popup/popup.html` | HTML structure |
| `extensions/chrome/popup/popup.css` | Styling (~10KB) |
| `extensions/chrome/popup/popup.js` | Logic (~9KB) |

**Firefox (shared):**

| File | Description |
|------|-------------|
| `extensions/shared/popup/popup-base.html` | HTML structure |
| `extensions/shared/popup/popup-base.css` | Styling (~6.5KB) |
| `extensions/shared/popup/popup-base.js` | Logic (~12KB) |

### Development Workflow

#### Option A: Auto-Reload with web-ext (Recommended)

```bash
# Install dependencies (if not already done)
npm install

# Start Chrome with auto-reloading extension
npm run dev:chrome

# Or Firefox
npm run dev:firefox
```

Edit files → Save → Extension auto-reloads → Click icon to see changes.

**Note:** This opens a fresh browser profile, not your main profile.

#### Option B: Manual Reload (Use Main Profile)

1. Load extension as "unpacked" in `chrome://extensions`
2. Set up keyboard shortcut in `chrome://extensions/shortcuts` (e.g., `Cmd+Shift+R`)
3. Edit files → Press shortcut → Click extension icon

### File Watcher

Run the file watcher for context-aware reload instructions:

```bash
npm run watch:extensions
```

When you save a file, it shows exactly what to do:

```
✨ File changed: extensions/chrome/popup/popup.css
Component: popup (CSS)

📝 Reload Steps:
  1. Go to chrome://extensions (or press Cmd+Shift+R if shortcut configured)
  2. Click reload icon on Inspekt extension card
  3. Click extension icon in toolbar to see changes
```

---

## 3. DevTools Panel Development

The DevTools panel is the most complex component with a modular ES6 architecture.

### File Locations

**Core Files:**

| File | Description |
|------|-------------|
| `extensions/chrome/panel.html` | Panel HTML structure |
| `extensions/chrome/panel.css` | Panel styling (~25KB) |
| `extensions/chrome/panel.js` | Entry point (ES6 module) |

**Modules** (`extensions/chrome/modules/`):

| Module | Purpose |
|--------|---------|
| `connection-manager.js` | WebSocket bridge connection |
| `element-display.js` | Inspected element rendering |
| `element-monitor.js` | Selection monitoring |
| `history-manager.js` | Element history tracking |
| `quick-actions-manager.js` | Action grid management |
| `settings-manager.js` | Persistent settings |
| `theme-manager.js` | Theme switching |

### Development Workflow

DevTools panels require the most steps because **Chrome doesn't auto-reload panels**.

```bash
# Start file watcher
npm run watch:extensions
```

After editing files:

1. Reload extension (`chrome://extensions` or keyboard shortcut)
2. **Close DevTools** (`Cmd+Option+I`)
3. **Reopen DevTools** (`Cmd+Option+I`)
4. Click "Inspekt" panel tab

**CSS-Only Changes:** Sometimes work with just close/reopen DevTools (skip step 1).

### Debugging the Panel

The panel runs in its own context. To debug:

1. Open DevTools → Click "Inspekt" tab
2. Right-click anywhere in the panel → "Inspect"
3. A second DevTools opens (DevTools-in-DevTools!)
4. Check Console for errors, Sources for breakpoints

---

## Quick Reference

### npm Scripts

| Script | Purpose |
|--------|---------|
| `npm run dev:chrome` | Auto-reload Chrome extension |
| `npm run dev:firefox` | Auto-reload Firefox extension |
| `npm run dev:axe-css` | Start CSS dev server (auto-builds on Ctrl+C) |
| `npm run build:axe-css` | Manually build and embed minified CSS |
| `npm run watch:extensions` | File watcher with reload instructions |

### Iteration Times

| Component | Workflow | Time |
|-----------|----------|------|
| Axe Popover | Edit → Save → Auto hot-reload | ~1.5 sec |
| Popup | Edit → Auto-reload → Click icon | ~3 sec |
| DevTools Panel | Edit → Reload extension → Close/reopen DevTools | ~10-15 sec |

### Setting Up Keyboard Shortcut

To quickly reload the extension:

1. Go to `chrome://extensions/shortcuts`
2. Find "Inspekt" extension
3. Set a keyboard shortcut (e.g., `Cmd+Shift+R`)

---

## CSS Architecture

### Axe Popover CSS Structure

The CSS is split into modular files in `inspekt/scripts/axe-popover/`:

| File | Contents |
|------|----------|
| `tokens.css` | Design tokens (colors, spacing, typography, shadows) |
| `base.css` | Popover container, anchor positioning, scrollbar |
| `nav.css` | Navigation bar (prev/next, counter, close, detach) |
| `content.css` | Header, tabs, body, sections, code blocks, tags |
| `badges.css` | Interactive violation badges on page |
| `animations.css` | Entrance/exit keyframe animations |
| `themes.css` | Dark mode and high contrast overrides |

### CSS Nesting

The CSS uses **native CSS nesting** for pseudo-classes and pseudo-elements:

```css
/* This works - pseudo-classes/elements */
.inspekt-axe-nav__prev {
  &:hover { background: white; }
  &:focus-visible { outline: 2px solid blue; }
  &::before { content: "→"; }
}

/* This does NOT work - BEM element concatenation */
.inspekt-axe-nav {
  &__prev { }  /* ❌ Won't produce .inspekt-axe-nav__prev */
}
```

Native CSS nesting supports `&:pseudo`, `&.class`, `& element`, but NOT Sass-style string concatenation like `&__element` or `&--modifier`.

### Design Tokens

Edit `tokens.css` to customize the look and feel:

```css
:root {
  /* Colors */
  --blue: #2563eb;
  --green: #10b981;
  --red: #dc2626;

  /* Spacing (3 values) */
  --space-sm: 4px;
  --space-md: 8px;
  --space-lg: 16px;

  /* Border Radius (3 values) */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;

  /* Typography */
  --font-sans: "Inter", system-ui, sans-serif;
  --text-sm: 13px;
  --text-base: 14px;
}
```

### Naming Convention

We use BEM-style naming with full class names (not Sass nesting):

```css
.inspekt-axe-popover { }                          /* Block */
.inspekt-axe-popover__header { }                  /* Element */
.inspekt-axe-popover__impact-badge--critical { }  /* Modifier */
```

### CSS Variables

Components use CSS custom properties for theming:

```css
:root {
  --color-primary: #2563eb;
  --color-success: #22c55e;
  --color-error: #dc2626;
}

@media (prefers-color-scheme: dark) {
  :root {
    --color-primary: #60a5fa;
  }
}
```

---

## Testing Checklist

### Axe Popover

- [ ] Badge positions align with violations
- [ ] Popover navigation works (prev/next)
- [ ] "Skip similar" dims related badges
- [ ] Detach mode allows dragging
- [ ] Tab switching works (Default/Markdown)
- [ ] Animations play correctly
- [ ] Light mode looks correct
- [ ] Dark mode looks correct

### Extension Popup

- [ ] Connection status shows correctly
- [ ] Domain permissions toggle works
- [ ] "Quick Access" timer counts down
- [ ] Links open in new tabs
- [ ] Light/dark mode renders correctly

### DevTools Panel

- [ ] Element display updates when selecting
- [ ] Quick actions execute correctly
- [ ] Drag-and-drop reorders tiles
- [ ] Theme toggle persists
- [ ] Element history tracks selections
- [ ] Settings persist across sessions

---

## Troubleshooting

### DevTools Panel Not Updating

**Cause:** Chrome caches DevTools panels.

**Solution:** Close DevTools completely, then reopen.

### CSS Changes Not Visible in Axe Popover

**Cause:** CSS is embedded inline in production mode.

**Solution:** Use `--dev-css` flag: `inspekt axe --interactive --dev-css`

### CSS Server Not Working

**Cause:** Server not running or port conflict.

**Solution:**

1. Start the server: `npm run dev:axe-css`
2. Verify it's running: `curl http://localhost:8000/axe-popover/index.css`
3. If port 8000 is busy, kill the process: `lsof -ti:8000 | xargs kill`
4. Check browser console for CORS errors

### ES6 Module Import Errors

**Cause:** Missing `.js` extension or wrong path.

**Solution:** All imports must include `.js`: `import { Foo } from './foo.js'`

---

## Technical Notes

### Tab Visibility and Focus

Inspekt's Chrome extension has a **tab visibility check** that prevents most commands from executing when the browser tab is not visible or active. This is intentional—it ensures commands run on the tab the user is actually looking at.

**Commands that work regardless of tab focus:**

| Command Type | Why |
|--------------|-----|
| `inspekt axe` | Accessibility audits should work from terminal |
| `inspekt identify` | Element identification overlays |
| Domain management | Permission changes |
| Ping/pong | Connection health checks |

**Commands that require tab focus:**

All other commands (e.g., `inspekt eval`, `inspekt extract-*`, `inspekt click`) require the browser tab to be visible and active.

**Why this matters for development:**

When running `inspekt axe --interactive --dev-css` from your terminal, the terminal typically steals focus from the browser. The axe command is specifically exempted from the visibility check, so it works even when your terminal has focus.

If you're adding new commands that should work without tab focus, you'll need to add an exception in `extensions/chrome/content.js` (search for `isAxeCommand`).

### After Modifying Extension Files

When you modify extension source files (`.js`, `.html`, `.css` in `extensions/`), you must reload the extension:

1. Go to `chrome://extensions`
2. Find the Inspekt extension card
3. Click the reload icon (circular arrow)

For DevTools panel changes, you must also close and reopen DevTools after reloading the extension.
