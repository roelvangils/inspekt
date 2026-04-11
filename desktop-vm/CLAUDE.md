# Claude Development Guide for Desktop VM (Tauri)

The Tauri app is a thin native wrapper around the Browser VM control panel. It loads `http://localhost:6080/control.html` (served by the Docker container) in a webview. **Almost all logic lives in the control panel HTML/JS/CSS, not in Rust.**

---

## Architecture: External URL in a Webview

The VM window loads an **external URL** (`localhost:6080`), not a bundled frontend. This has critical implications:

### What works
- `window.__TAURI_INTERNALS__` IS available (Tauri injects it via init scripts)
- `window.__TAURI__` and `window.isTauri` are available
- Tauri plugin commands work (e.g. `plugin:clipboard-manager|write_text`, `plugin:window|start_dragging`)

### What doesn't work
- `initialization_script()` and `on_page_load` `eval()` do **NOT** execute on the external URL
- `data-tauri-drag-region` attribute does **NOT** work (it relies on init script injection)
- Any JS that needs to run must be added directly to `control-panel.html` or its JS files

### Remote Capabilities (CRITICAL)

Tauri's permission system distinguishes between **local** (bundled frontend) and **remote** (external URL) origins. The VM window is remote.

- **`capabilities/default.json`** — `"local": true` — only applies to the bundled launcher/preferences pages
- **`capabilities/clipboard-remote.json`** — has `"remote": { "urls": ["http://localhost:6080/*"] }` — applies to the VM window

**Any new Tauri API permission for the VM window MUST go in `clipboard-remote.json`**, not `default.json`. Putting it in `default.json` will silently fail with "not allowed on window vm".

---

## The Bridge (Control Server)

The control server (`docker/browser-vm/servers/control-server.py`) on port **8888** is the bridge between the control panel JS and the Inspekt CLI running inside the Docker container.

### Pattern: Running Inspekt commands
```javascript
// JS fetches from the control server, which runs the command in Docker
const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/inspekt/${encodeURIComponent(command)}`);
const data = await response.json();
// data = { ok: true, output: "...", error: null }
```

### Pattern: Clipboard operations
```javascript
// 1. Fetch output via the bridge
const data = await fetch(`http://localhost:8888/inspekt/selection text --raw`).then(r => r.json());

// 2. Write to clipboard via Tauri plugin (or navigator.clipboard fallback)
if (window.__TAURI_INTERNALS__) {
    await window.__TAURI_INTERNALS__.invoke('plugin:clipboard-manager|write_text', { text: data.output });
} else {
    await navigator.clipboard.writeText(data.output);
}
```

**NEVER write custom Rust commands for operations that can go through the bridge.** The bridge already handles all Inspekt CLI operations. Only use Rust/Tauri for things that require native OS access (clipboard write, window management, notifications).

---

## Window Dragging

Window dragging uses `__TAURI_INTERNALS__.invoke('plugin:window|start_dragging')` called from a mousedown handler on `.control-bar` in `control-panel.html`. The handler uses event delegation to skip interactive elements (buttons, inputs, URL bar).

The `core:window:allow-start-dragging` permission is in `clipboard-remote.json` (the remote capability).

Previous failed approaches (for reference):
- `data-tauri-drag-region` — doesn't work on external URLs
- `-webkit-app-region: drag` — Electron-only, no effect in Tauri/WKWebView
- `NSWindow.setMovableByWindowBackground(true)` — makes entire window draggable including VNC canvas

---

## Tauri Plugin Commands vs Custom Commands

- **Plugin commands**: `plugin:<name>|<method>` — built into Tauri or its plugins. Need permission in capabilities JSON.
- **Custom commands**: Registered via `invoke_handler` in Rust. Need both the Rust handler AND a permission entry.

For the VM window, prefer plugin commands over custom commands since they just need a permission entry in `clipboard-remote.json`.

---

## Development Workflow

| Changed | Action needed |
|---------|--------------|
| `control-panel.html`, CSS, JS | `make vm-restart` (from repo root) |
| `src-tauri/src/*.rs` | Restart `bun run tauri dev` |
| `capabilities/*.json` | Restart `bun run tauri dev` |
| `Cargo.toml` | Restart `bun run tauri dev` |

Note: `make vm-restart` must be run from `/Users/demo/Repos/inspekt` (repo root), not from `desktop-vm/`.
