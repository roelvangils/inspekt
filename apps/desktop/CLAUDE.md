# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Claude Development Guide for Desktop VM (Tauri)

The Tauri app is a thin native wrapper around the Browser VM control panel running in a Docker container. Almost all UI logic lives in the control panel HTML/JS/CSS (inside `inspekt/vm/`, not here) — this app's job is to launch/manage the VM container and host the webview that loads it.

---

## Commands

Run from `apps/desktop/`:

| Command | Purpose |
|---|---|
| `bun run tauri dev` | Primary dev loop. Starts Vite (port 1421) and builds/runs the Rust binary. Clears WKWebView cache first via `clean-cache`. |
| `bun run dev:app` | Dev build packaged as a minimal `.app` bundle. Needed when testing anything that triggers macOS TCC prompts (microphone, speech recognition) — bare `tauri dev` has no Info.plist so those prompts don't fire. Script in `scripts/dev-app-bundle.sh`. |
| `bun run check` | `svelte-check` type-check over the launcher Svelte code. |
| `bun run build` | Vite build of `../dist` (the bundled launcher/preferences frontend). |
| `bun run tauri build` | Full release `.app` bundle. |
| `bun run clean-cache` | Clear `~/Library/WebKit/be.fronteers.inspekt-browser-vm` + Caches dir. See "WKWebView cache" below. |

There is no test suite here.

---

## Two-surface architecture

The app has **two distinct frontends** living in one Tauri process. Confusing them is the most common source of bugs.

### 1. Local launcher (bundled Svelte frontend)

- **Windows:** `main` (the launcher) and `preferences`
- **Code:** `src/App.svelte`, `src/lib/components/*.svelte`, `preferences.html`
- **Served from:** Vite dev server (`http://localhost:1421`) in dev, `../dist` at runtime in prod
- **Capabilities:** `capabilities/default.json` (`"local": true`)
- **What it does:** Checks Docker, calls `start_vm`/`stop_vm`, polls health, opens the VM window when ready. Emits/receives events via `@tauri-apps/api`.

### 2. VM window (external URL)

- **Windows:** `vm` (main VM window) and `vm-*` (tab tear-off windows, labels generated from `SystemTime`)
- **Code:** lives in the Python repo at `vm/servers/control-panel.html` — **not in this app**
- **Served from:** `http://localhost:6080/control.html` via WebSockify/noVNC in the Docker container
- **Capabilities:** `capabilities/clipboard-remote.json` (`"remote": { "urls": ["http://localhost:6080/*"] }`)
- **What it does:** hosts the VNC canvas, command palette, URL bar, popouts, toasts — the entire day-to-day UI.

### Why the distinction matters

Tauri's permission system is origin-scoped. A permission in `default.json` only works for the bundled launcher; the VM window sees "not allowed on window vm" silently. **Any new Tauri API permission for the VM window MUST go in `clipboard-remote.json`.**

Similarly, init scripts and `on_page_load` eval only run on bundled frontends. For the VM window:

- `initialization_script()` / `on_page_load` `eval()` do **NOT** execute
- `data-tauri-drag-region` attribute does **NOT** work (depends on init script injection)
- Any JS that needs to run must be added directly to `control-panel.html` (in the `inspekt/` repo)

What DOES work on the VM window: `window.__TAURI_INTERNALS__`, `window.__TAURI__`, `window.isTauri`, and any plugin command whose permission is in `clipboard-remote.json`.

---

## The Bridge (control server on port 8888)

The control server (`vm/servers/control-server.py` in the `inspekt/` repo) is the backbone for everything. Both the Rust side and the JS side call it to run Inspekt CLI commands, fetch page info, etc. Rust also polls it for health checks and clipboard relay.

**From JS (control panel):**
```javascript
const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/inspekt/${encodeURIComponent(command)}`);
const data = await response.json(); // { ok, output, error }
```

**From Rust:** see `api_get`, `api_post`, `copy_inspekt_output`, `poll_clipboard_relay` in `src-tauri/src/lib.rs`.

**NEVER write a custom Rust command for an operation the bridge can do.** Only use Rust/Tauri for things that require native OS access: clipboard write, window management, notifications, native file dialogs (`rfd`), Docker lifecycle.

---

## Rust ↔ JS communication patterns

- **Launcher → Rust:** `invoke<T>("command_name", args)` from `@tauri-apps/api/core`. Commands registered in `tauri::Builder::default().invoke_handler(...)` in `lib.rs::run()`.
- **Rust → launcher:** `app.emit("event-name", payload)` on the Rust side; `listen<T>("event-name", cb)` in Svelte. Example lifecycle: `vm-progress`, `vm-ready`, `vm-error`, `vm-stopped`.
- **Rust → VM window:** `window.eval("...")` to run arbitrary JS, or `CustomEvent('tauri-menu', { detail: { action, value } })` dispatched via eval — see `emit_to_vm` / `emit_to_vm_with_payload`. Used heavily by the native menu (`src-tauri/src/menu.rs`).
- **Rust toasts in VM window:** `show_vm_toast(app, msg, type)` evals a call to the global `showToast(...)` JS function defined in `control-panel.html`.

---

## Window Dragging

Dragging uses `__TAURI_INTERNALS__.invoke('plugin:window|start_dragging')` called from a mousedown handler on `.control-bar` in `control-panel.html` (upstream repo). Event delegation skips interactive elements (buttons, inputs, URL bar).

The `core:window:allow-start-dragging` permission is in `clipboard-remote.json`.

Previous failed approaches (don't re-try):
- `data-tauri-drag-region` — doesn't work on external URLs
- `-webkit-app-region: drag` — Electron-only, no effect in WKWebView
- `NSWindow.setMovableByWindowBackground(true)` — makes the entire window draggable including VNC canvas

---

## Tauri plugin commands vs custom commands

- **Plugin commands:** `plugin:<name>|<method>` — built into Tauri or its plugins. Only need a permission entry in capabilities JSON.
- **Custom commands:** registered via `invoke_handler` in Rust. Need both the Rust handler AND a permission entry.

For the VM window, prefer plugin commands — capability entry is all that's needed.

---

## GUI PATH gotcha

macOS GUI apps only inherit the minimal system PATH (`/usr/bin:/bin:/usr/sbin:/sbin`), so `docker`, `inspekt`, and tools in `~/.local/bin` or Homebrew are invisible. `fix_path_env()` in `lib.rs` runs `/bin/zsh -ilc 'echo $PATH'` at startup and sets `PATH` from the user's login shell. If you see "command not found" for a tool that clearly exists in Terminal, suspect this and check that `fix_path_env()` is still called first in `run()`.

---

## WKWebView cache

WKWebView caches JS/CSS from WebSockify (port 6080) aggressively because WebSockify sends no Cache-Control headers. Changes to `control-panel.html` / CSS / JS may not appear even after `make vm-restart`.

**Workaround:** `bun run clean-cache` (runs `rm -rf ~/Library/WebKit/be.fronteers.inspekt-browser-vm ~/Library/Caches/be.fronteers.inspekt-browser-vm`). This is automatically called by `bun run dev`, but the Tauri app must be **fully quit first** — cache files are locked while it's running.

When the JS/CSS edits aren't taking effect, suspect this cache before anything else.

---

## Development Workflow

| Changed | Action needed |
|---------|--------------|
| `control-panel.html`, CSS, JS (upstream) | `make vm-restart` (from `/Users/demo/Repos/inspekt`, the repo root), then quit + relaunch Tauri app if cache is sticky |
| `src/**/*.svelte`, launcher CSS/TS | Vite HMR — no restart needed |
| `src-tauri/src/*.rs` | Restart `bun run tauri dev` |
| `capabilities/*.json` | Restart `bun run tauri dev` |
| `Cargo.toml` | Restart `bun run tauri dev` |
| `tauri.conf.json` | Restart `bun run tauri dev` |

`make vm-restart` is in the upstream repo's Makefile and must be run from the repo root, not from `apps/desktop/`.
