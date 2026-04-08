# Browser VM Development

The `inspekt vm` command runs a Docker container with a full browser environment (Chromium + noVNC + Inspekt). The container is built from `docker/browser-vm/Dockerfile`.

## Quick Start

```bash
bun run build          # Bundle assets, rebuild Docker image, and start VM
bun run dev            # Restart VM in dev mode (mounts source files for live editing)
bun run start          # Start VM (uses existing image)
bun run bundle         # Generate dist/ files only (no Docker build)
inspekt vm stop        # Stop the VM
inspekt vm status      # Check status and mode
```

| Command | What it does | Use when |
|---------|-------------|----------|
| `bun run build` | Bundles CSS/JS, rebuilds the Docker image, starts the VM | First time setup, or after changing Dockerfile / entrypoint / supervisord |
| `bun run dev` | Restarts the VM with source files mounted (no bundling) | Day-to-day development — edits to CSS, JS, HTML, or Python |
| `bun run start` | Starts the VM using the existing Docker image | Starting the VM after a stop |
| `bun run bundle` | Generates `dist/` files without touching Docker | Testing the bundle output |

**Typical workflow:**

1. `bun run build` — once, to create the Docker image
2. `bun run dev` — for daily development (mounts source files from your repo)
3. After editing CSS/JS/HTML: `bun run dev` again to pick up changes

Once running, open **`http://127.0.0.1:6080/control.html`** in your browser.

### Production vs Dev Mode

- **Production** (`bun run build`): CSS and JS are bundled into `dist/app.min.css` and `dist/app.min.js`, baked into the Docker image. Smaller, faster, no source files needed.
- **Dev mode** (`bun run dev`): Your local source files (`css/`, `js/`, `control-panel.html`) are mounted into the container. Changes are picked up on restart without rebuilding the image.

!!! warning "Use `127.0.0.1`, not `localhost`"
    On some systems, `localhost` resolves to IPv6 (`::1`) which may not reach the container. Always use `http://127.0.0.1:6080/control.html`.

### Alternative: Docker Compose

You can also start the VM with Docker Compose from the **repo root**:

```bash
docker compose -f docker/browser-vm/docker-compose.yml up --build -d
```

### Required Ports

The VM exposes multiple services. **All of these ports must be accessible from the host** for the control panel to function correctly:

| Port | Service | Purpose |
|------|---------|---------|
| **6080** | noVNC | Web UI — the page you open in your browser |
| **8888** | Control server | Navigation, tab management, CDP proxy, screenshots |
| **8889** | Terminal server | WebSocket terminal in the control panel |

`inspekt vm start` uses `--network host`, which makes all ports available automatically. If you use `docker compose` or `docker run`, ensure all three ports are published — otherwise navigation, tab creation, and the terminal will silently fail.

## Dev Mode Auto-Detection

When running `inspekt vm start` or `inspekt vm restart` from the source repository, **dev mode is automatically enabled**. This means:

- Local `inspekt/` source files are mounted into the container
- Changes to Python code take effect immediately (no rebuild needed)
- Control panel and fonts are also mounted for UI development

The auto-detection works by checking for `pyproject.toml` in the project root.

**Commands:**
```bash
inspekt vm start           # Auto-detects dev environment, mounts local source
inspekt vm start --no-dev  # Disable dev mode (use frozen image code)
inspekt vm start --dev     # Explicitly enable dev mode
inspekt vm restart         # Same auto-detection on restart
```

!!! note
    While Python code changes are reflected immediately, container restart is still needed for noVNC-cached files (HTML, CSS, fonts).

!!! info "Technical detail"
    Dev mode sets `PYTHONDONTWRITEBYTECODE=1` in the container to prevent Python from using stale `.pyc` bytecode cache files from the Docker build. Without this, Python would ignore the mounted source files and use the cached bytecode instead.

## Dev Mode File Mounts

In dev mode, these files are mounted from the host into the container:

| Host Path | Container Path | Hot-Reload? |
|-----------|----------------|-------------|
| `docker/browser-vm/control-panel.html` | `/usr/share/novnc/control.html` | Restart required (noVNC caches) |
| `docker/browser-vm/css/` | `/usr/share/novnc/css/` | Restart required (noVNC caches) |
| `docker/browser-vm/js/` | `/usr/share/novnc/js/` | Restart required (noVNC caches) |
| `docker/browser-vm/fonts/` | `/usr/share/novnc/fonts/` | Restart required (noVNC caches) |
| `docker/browser-vm/servers/control-server.py` | `/opt/control-server.py` | `supervisorctl restart control-server` |
| `docker/browser-vm/servers/terminal-server.py` | `/opt/terminal-server.py` | `supervisorctl restart terminal-server` |
| `docker/browser-vm/servers/audio-server.py` | `/opt/audio-server.py` | `supervisorctl restart audio-server` |
| `inspekt/` | `/opt/inspekt/inspekt/` | **Instant** (Python reloads on each CLI call) |
| `extensions/` | `/opt/inspekt/extensions/` | Restart required (Chromium reloads extension) |

## Hot-Reloading Services Without Full Restart

For files mounted in dev mode, you can often avoid a full VM restart:

```bash
# Restart only the control server (after editing control-server.py)
docker exec inspekt-browser-vm supervisorctl restart control-server

# Restart the terminal server (after editing terminal-server.py)
# Note: This will disconnect the current terminal session
docker exec inspekt-browser-vm supervisorctl restart terminal-server

# Restart only the bridge server
docker exec inspekt-browser-vm supervisorctl restart inspekt-bridge

# List all services and their status
docker exec inspekt-browser-vm supervisorctl status
```

!!! warning
    Volume mounts are created at container start time. If you add a NEW mount to `vm.py`, you need one `inspekt vm restart` to create it. After that, file changes are picked up via `supervisorctl restart`.

## When Container Rebuild is Required

The following changes **require a full container rebuild**:

| File/Directory | Dev Mode | Production |
|----------------|----------|------------|
| `docker/browser-vm/Dockerfile` | Rebuild required (`bun run build`) | Rebuild required |
| `docker/browser-vm/supervisord.conf` | Rebuild required | Rebuild required |
| `docker/browser-vm/entrypoint.sh` | Rebuild required | Rebuild required |
| `docker/browser-vm/scripts/*.sh` | Rebuild required | Rebuild required |
| `pyproject.toml` | Rebuild required | Rebuild required |
| `docker/browser-vm/control-panel.html` | Restart only (`bun run dev`) | Rebuild required |
| `docker/browser-vm/css/` | Restart only | Rebuild required |
| `docker/browser-vm/js/` | Restart only | Rebuild required |
| `docker/browser-vm/fonts/` | Restart only | Rebuild required |
| `docker/browser-vm/servers/control-server.py` | `supervisorctl restart control-server` | Rebuild required |
| `docker/browser-vm/servers/terminal-server.py` | `supervisorctl restart terminal-server` | Rebuild required |
| `docker/browser-vm/servers/audio-server.py` | `supervisorctl restart audio-server` | Rebuild required |
| `inspekt/` source code | **Instant** (mounted) | Rebuild required |
| `extensions/` | Restart only (Chromium reloads) | Rebuild required |

## Critical: noVNC File Caching

**The noVNC websockify proxy caches files in memory at startup.** This means:

- File changes inside a running container are **NOT** served until restart
- Stopping and starting the container is **NOT** enough
- The container must be **fully removed** before starting a new one

## Correct Rebuild Procedure

!!! important "Build context must be the repo root"
    The Dockerfile uses `COPY` paths relative to the repo root (e.g., `COPY inspekt /opt/inspekt/inspekt`). Always run builds from the repo root — **not** from `docker/browser-vm/`.

**Using `inspekt vm` (recommended):**
```bash
inspekt vm restart     # Rebuilds and restarts, preserves dev mode
```

**Using Docker Compose:**
```bash
# From the repo root
docker compose -f docker/browser-vm/docker-compose.yml up --build -d
```

**Manual build:**
```bash
# 1. Stop and REMOVE the VM container
docker rm -f inspekt-browser-vm

# 2. Rebuild from repo root (use --no-cache if Docker layer caching is stale)
docker build -t inspekt-browser-vm -f docker/browser-vm/Dockerfile .

# 3. Start fresh — note: all 3 ports must be published!
docker run -d --name inspekt-browser-vm \
  -p 6080:6080 -p 8888:8888 -p 8889:8889 \
  --shm-size=2g inspekt-browser-vm
```

!!! note "Container names"
    `inspekt vm start` names the container `inspekt-browser-vm`. Docker Compose names it `inspekt-browser`. The `docker exec` examples in this doc use `inspekt-browser-vm` (the CLI name). Adjust if you started via Compose.

!!! danger "Don't forget ports 8888 and 8889"
    If you only publish port 6080, the control panel UI will load but **navigation, tab creation, and the terminal will all fail silently**. The control panel's JavaScript makes API calls to port 8888 (control server) and 8889 (terminal) from your host browser. Using `--network host` (as `inspekt vm start` does) avoids this issue entirely.

## Common Pitfall: Port Conflicts

When using `--network host` or published ports, an old container may still hold the ports. Always verify no old containers exist:

```bash
# Check for running VM containers
docker ps --filter name=inspekt-browser

# Check what's using port 6080
lsof -i :6080
```

## Development Workflow

For faster iteration, use `inspekt vm start` from the source repo — it auto-enables dev mode with volume mounts. See [Dev Mode File Mounts](#dev-mode-file-mounts) above for the full list.

!!! note
    Even with volume mounts, you must restart the container for noVNC-cached file changes (HTML, CSS, fonts) to take effect.

## Verifying Changes

After restarting, verify your changes are being served:

```bash
# Check that CSS/JS modules load (should return 200)
curl -s -o /dev/null -w "%{http_code}" http://localhost:6080/css/tokens.css
curl -s -o /dev/null -w "%{http_code}" http://localhost:6080/js/config.js

# Check font availability
curl -sI http://localhost:6080/fonts/JetBrainsMonoNerdFont-Regular.woff2 | head -3

# In production mode, check bundled assets
curl -s -o /dev/null -w "%{http_code}" http://localhost:6080/dist/app.min.css
curl -s -o /dev/null -w "%{http_code}" http://localhost:6080/dist/app.min.js
```

## Dynamic VNC Viewport Resize

The VM resolution dynamically matches the host browser's viewport. When you resize the browser window, the VM re-renders at the new resolution within ~500ms — no blur, pixel-perfect output.

### Architecture

```
Host browser resize → ResizeObserver (300ms debounce)
  → POST /resize {width, height} (× devicePixelRatio for HiDPI)
  → resize-display.sh (cvt + xrandr)
  → x11vnc auto-detects RandR change (-xrandr flag)
  → noVNC renders at native resolution (resize: 'remote')
```

### Key Components

| Component | File | Role |
|-----------|------|------|
| Xorg + dummy driver | `xorg.conf` | Virtual display with RandR support (max 3840×2160) |
| Resize script | `resize-display.sh` | Generates modelines via `cvt`, applies via `xrandr`, resizes Chromium |
| Control server | `control-server.py` | `GET /resolution` and `POST /resize` API endpoints |
| Frontend | `control-panel.html` | `ResizeObserver` + debounced API calls |

### API Endpoints

**`GET /resolution`** — Returns the current X display resolution:

```json
{"ok": true, "resolution": "1440x900", "width": 1440, "height": 900}
```

**`POST /resize`** — Resize the X display:

```bash
curl -X POST http://localhost:8888/resize \
  -H 'Content-Type: application/json' \
  -d '{"width": 1440, "height": 900}'
```

```json
{"ok": true, "changed": true, "resolution": "1440x900"}
```

Dimensions are clamped to 640×480 minimum, 3840×2160 maximum, and rounded to even numbers.

### `VNC_RESOLUTION` Environment Variable

`VNC_RESOLUTION` (default `1920x1080`) now sets the **initial** resolution only. After the control panel loads, the frontend dynamically overrides it to match the host viewport. Clients connecting directly to noVNC (without the control panel) still get the initial resolution.

---

# VM Troubleshooting Guide

This section covers common issues when developing with the Inspekt VM, particularly around port detection and component communication.

## Bridge Port Architecture

Inspekt uses different ports in different environments to avoid conflicts:

| Environment | HTTP Port | WebSocket Port | Used By |
|-------------|-----------|----------------|---------|
| **Normal (macOS/Linux)** | 8765 | 8766 | Host machine bridge server |
| **VM (isolated mode)** | 8767 | 8768 | Container bridge server |

The VM uses different ports because `--network host` shares the host's network namespace. If both host and VM used 8765, they'd conflict.

## How Port Auto-Detection Works

The system automatically detects the correct port using:

1. **`INSPEKT_ISOLATED=1`** environment variable (set in VM's Dockerfile/supervisord)
2. **`is_isolated_mode()`** function in `inspekt/config.py`
3. **`get_bridge_port()`** and **`get_bridge_ws_port()`** functions return the correct port

```python
from inspekt.config import get_bridge_port, is_isolated_mode

# Returns 8767 in VM, 8765 otherwise
port = get_bridge_port()

# Check environment
if is_isolated_mode():
    print("Running in VM")
```

## Common Issues and Solutions

### Issue: "No frames captured for video"

**Symptoms:**

- `inspekt replay --video` reports no frames
- Video file is not created or is empty

**Cause:** Port mismatch between Chrome extension and Python code.

**Debug Steps:**

```bash
# 1. Check if bridge has frames buffered
docker exec inspekt-browser-vm curl -s http://127.0.0.1:8767/screencast/status

# Expected output (frames should be > 0 during recording):
# {"ok": true, "active": true, "frames_buffered": 32, ...}

# 2. If frames_buffered > 0 but video fails, the Python code is reading from wrong port
# Check which port ScreencastCapture is using by adding verbose logging

# 3. Verify extension is posting to correct port
docker exec inspekt-browser-vm curl -s http://127.0.0.1:9222/json | grep service_worker
# Then check extension console for "[Inspekt Extension] VM environment detected"
```

**Solution:** Ensure all Python code uses `get_bridge_port()` instead of hardcoded `8765`.

### Issue: Terminal won't connect in control panel

**Symptoms:**

- "Connection error. Is the VM running?" in control panel terminal
- Terminal shows "Disconnected"

**Debug Steps:**

```bash
# 1. Check if terminal server is running
docker exec inspekt-browser-vm netstat -tlnp | grep 8889

# 2. If not listening, check the process
docker exec inspekt-browser-vm ps aux | grep terminal

# 3. Try starting manually to see errors
docker exec inspekt-browser-vm python3 /opt/terminal-server.py
```

**Common Causes:**

- **Permission denied**: Host file mounted without execute permission
  - Fix: `chmod +x docker/browser-vm/servers/terminal-server.py`
- **Port already in use**: Previous terminal server didn't clean up
  - Fix: `docker exec inspekt-browser-vm pkill terminal-server` then restart
- **Python module missing**: websockets not installed
  - Fix: Rebuild container

### Issue: Downloads don't work with `--open` flag

**Symptoms:**

- `inspekt replay --video --open` shows file path but doesn't download
- Message: "Tip: Use the control panel terminal for automatic downloads"

**Cause:** Running from `docker exec` instead of control panel terminal.

**Explanation:** The `--open` flag uses OSC 1337 escape sequences which only work in the control panel's xterm.js terminal. The terminal-server.py sets `INSPEKT_TERMINAL=control-panel` to identify the correct terminal.

**Solution:** Run commands from the control panel terminal (port 6080), not via `docker exec`.

### Issue: Extension changes not taking effect

**Symptoms:**

- Modified `background.js` but old behavior persists
- Console logs show old code running

**Cause:** Chrome caches extension code. The extension needs to be reloaded.

**Solution:**

```bash
# Restart Chrome to reload extension
docker exec inspekt-browser-vm pkill -f chromium

# Chrome will auto-restart via supervisord and reload extension from mounted path
```

### Issue: Python code changes not taking effect in VM

**Symptoms:**

- Modified Python files but old behavior persists
- Works outside VM but not inside

**Debug Steps:**

```bash
# 1. Verify file is mounted
docker exec inspekt-browser-vm cat /opt/inspekt/inspekt/config.py | head -20

# 2. Check if PYTHONDONTWRITEBYTECODE is set (prevents stale .pyc)
docker exec inspekt-browser-vm env | grep PYTHON

# 3. Verify you're in dev mode
inspekt vm status  # Should show "Mode: development"
```

**Common Causes:**

- **Not in dev mode**: Start with `inspekt vm start --dev`
- **Stale bytecode**: Dev mode sets `PYTHONDONTWRITEBYTECODE=1` to prevent this
- **File not mounted**: Check vm.py to ensure the file is in the mount list

## Debugging Port Communication

Use these commands to trace communication issues:

```bash
# List all listening ports in VM
docker exec inspekt-browser-vm netstat -tlnp

# Expected ports:
# 5900  - VNC server
# 6080  - noVNC web interface
# 8767  - Bridge HTTP (isolated mode)
# 8768  - Bridge WebSocket (isolated mode)
# 8888  - Control server
# 8889  - Terminal WebSocket
# 9222  - Chrome DevTools Protocol

# Check bridge health
docker exec inspekt-browser-vm curl -s http://127.0.0.1:8767/health

# Check what port Python code is using
docker exec inspekt-browser-vm python3 -c "
from inspekt.config import get_bridge_port, is_isolated_mode
print(f'Isolated mode: {is_isolated_mode()}')
print(f'Bridge port: {get_bridge_port()}')
"
```

## Quick Reference: Files That Must Use `get_bridge_port()`

These files communicate with the bridge and must use dynamic port detection:

| File | Component | Status |
|------|-----------|--------|
| `inspekt/client.py` | BridgeClient | Auto-detects |
| `inspekt/services/screencast.py` | ScreencastCapture | Auto-detects |
| `inspekt/services/bridge_executor.py` | BridgeExecutor | Auto-detects |
| `inspekt/app/mcp/tools.py` | MCP tool endpoints | Uses get_bridge_port() |
| `extensions/chrome/background.js` | Chrome extension | Detects via user agent |

If you add new code that talks to the bridge, always use:

```python
from inspekt.config import get_bridge_port

url = f"http://127.0.0.1:{get_bridge_port()}/your-endpoint"
```
