# Modularize control-panel.html into Separate JS Files

## Background

The Inspekt Browser VM control panel (`docker/browser-vm/control-panel.html`) is a single 15,382-line HTML file containing all CSS, HTML, and JavaScript. Three modules are already successfully extracted into separate files (`toolbar.js`, `vision-sim.js`, `motor-sim.js`), proving the pattern works. The goal is to extract more self-contained modules to improve maintainability.

**No behavior changes.** This is a pure refactoring task — move code, verify it still works.

---

## Extraction Pattern (must match existing modules)

Existing extracted files follow this pattern:

- Plain `.js` files in `docker/browser-vm/`
- Loaded with `<script defer>` in `<head>` (after CodeMirror, before `<style>`)
- **No module bundler** — plain `<script>` tags, shared global scope
- Access globals from the main script (e.g., `VNC_HOST`, `showToast`)
- Expose their own globals that the main script calls (e.g., `initToolbar()`)
- All scripts execute in order after HTML parsing (due to `defer`)

Check existing files for reference:

- `docker/browser-vm/toolbar.js` (881 lines)
- `docker/browser-vm/vision-sim.js` (1447 lines)
- `docker/browser-vm/motor-sim.js` (350 lines)

---

## What to Extract (in order)

### 1. `context-menu.js` (~733 lines) — HIGHEST PRIORITY

**NOTE:** This file has already been created at `docker/browser-vm/context-menu.js` but is NOT yet loaded or wired up. The code still lives in both places (control-panel.html AND context-menu.js). Your job is to:

1. Verify the `context-menu.js` file matches the code in control-panel.html (lines ~13090-13737)
2. Add `<script src="/context-menu.js" defer></script>` to the `<head>`
3. Remove the code from control-panel.html and replace with `// See context-menu.js`
4. Test that all context menus still work

**What's in context-menu.js:**

- Menu stack state (`_menuStack`, `_submenuTimer`)
- Core functions: `_activeMenu`, `_isMenuOpen`, `_menuStackEntry`, `_getMenuItemsOf`
- Build: `_buildMenuElement`, `_wireMenuItemEvents`
- Submenu lifecycle: `_openSubmenu`, `_closeSubmenusBelow`, `_closeDeepestSubmenu`
- Keyboard: `handleMenuKeydown`
- Triangle safe zone: `_pointInTriangle`, `_isInSubmenuSafeZone`, debug visualization
- Scroll lock: `_lockScroll`, `_unlockScroll`, `_applyMenuScrollConstraint`
- Flicker animation: `_flickerAndDismiss`
- Public API: `showContextMenu`, `dismissContextMenu`
- Event handlers: `onMenuOutsideClick`, `onMenuBlur`

**What stays in control-panel.html:**

- `showVNCContextMenu` — uses many control-panel-specific functions
- `showTabContextMenu` — uses tab-specific state
- `showTabBarContextMenu` — uses tab-specific state
- `_showDummyTestMenu` — debug test menu
- Terminal/output panel context menu handlers
- All CSS (stays in `<style>`)

**Globals context-menu.js reads from control-panel.html:**

- `_lastMouseX`, `_lastMouseY` — mouse position (declared at ~line 4763)
- `_platform` — OS detection, `'macos'`/`'windows'`/`'other'` (declared in `<head>` at line 19)
- `showToast(message, type)` — declared at ~line 5151

**Globals context-menu.js exposes:**

- `showContextMenu(e, items)` — called from everywhere
- `dismissContextMenu()` — called from everywhere
- `_isMenuOpen()` — used by capture-phase keyboard handlers
- `_activeMenu()` — used by capture-phase Escape handler
- `handleMenuKeydown(e)` — registered as document event listener
- `_DEBUG_TRIANGLE` — debug flag
- `_DEBUG_DUMMY_MENU` — debug flag

### 2. `vnc-overlay.js` (~259 lines)

**Lines in control-panel.html:** ~12831-13089

**What moves:**

- `vncOverlay` object with methods: `show`, `dismiss`, `dismissAll`
- DOM creation for overlay highlight boxes
- Coordinate conversion helpers (`_clientToVm`, `_vmToClient`)

**Globals it reads:** `document.getElementById('vncContainer')`, screen resolution state
**Globals it exposes:** `vncOverlay` object

### 3. `audio.js` (~212 lines)

**Lines:** ~9924-10135

**What moves:**

- `toggleAudio()` function
- WebSocket audio streaming setup
- Web Audio API context management
- `isAudioEnabled` state flag

**Globals it reads:** `VNC_HOST`, `CONTROL_PORT`, `showToast()`
**Globals it exposes:** `toggleAudio()`, `isAudioEnabled`

### 4. `zoom.js` (~57 lines)

**Lines:** ~15123-15179

**What moves:** `handleZoom(delta, key)` function
**Globals it reads:** `VNC_HOST`, `CONTROL_PORT`, `showToast()`
**Globals it exposes:** `handleZoom()`

### 5. `scrollbar.js` (~203 lines)

**Lines:** ~15180-15382

**What moves:** Virtual scrollbar overlay creation, mouse drag handling
**Globals it reads:** `document.getElementById('vncContainer')`
**Globals it exposes:** Init function

---

## File Loading Order

Add `<script defer>` tags in `<head>`, after existing scripts, before `<style>`:

```html
<script src="/vendor/codemirror.min.js"></script>
<script>/* OS detection (_platform) — must stay inline */</script>
<!-- Extracted modules -->
<script src="/context-menu.js" defer></script>
<script src="/vnc-overlay.js" defer></script>
<script src="/audio.js" defer></script>
<script src="/zoom.js" defer></script>
<script src="/scrollbar.js" defer></script>
<!-- Existing extracted modules -->
<script src="/toolbar.js" defer></script>
<script src="/vision-sim.js" defer></script>
<script src="/motor-sim.js" defer></script>
<style>
```

`defer` ensures scripts execute in document order, after HTML parsing.

---

## For Each Module Extraction

1. Read the code block in control-panel.html
2. Create the `.js` file in `docker/browser-vm/`
3. Add the `<script defer>` tag in `<head>`
4. Remove the code block from control-panel.html, replace with: `// See {filename}.js`
5. `make vm-restart`
6. Test: right-click canvas, tabs, terminal; keyboard nav; submenus; all toolbar buttons
7. Check browser console for `ReferenceError` (missing globals)

---

## What NOT to Extract

- **CSS** — all stays in `<style>` in control-panel.html
- **HTML markup** — stays in control-panel.html
- **OS detection script** (`<head>` inline) — must run before CSS renders
- **Initialization** (`window.addEventListener('load', ...)`) — stays as orchestrator
- **Capture-phase keyboard handlers** — stay in control-panel.html (they're the glue)
- **Domain-specific context menus** (VNC, tab, terminal) — they depend on too many control-panel internals

---

## Verification

After extracting each module:

1. `make vm-restart`
2. Right-click VNC canvas → real context menu appears with all sections
3. Right-click tab → tab context menu with all options
4. Right-click tab bar → tab bar context menu
5. Right-click terminal → terminal context menu (Copy, Paste, etc.)
6. Submenus work (hover with 225ms delay, keyboard ArrowRight/Left)
7. Triangle safe zone works (diagonal movement toward submenu)
8. macOS flicker animation on item click
9. Keyboard: Escape, ArrowDown/Up, Enter, Home/End, type-ahead
10. Keyboard context menu: Shift+F10, Control+Return, ContextMenu key
11. Scroll arrows on long menus
12. All toolbar buttons still function
13. Audio toggle, zoom, virtual scrollbar
14. No `ReferenceError` in browser console
