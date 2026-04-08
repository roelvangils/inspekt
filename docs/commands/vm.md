# inspekt vm

The `inspekt vm` command manages the **Inspekt Browser VM** - a Docker-based virtual machine with Chromium and the Inspekt extension pre-installed. This provides a complete, isolated browser environment accessible via your web browser.

## Overview

The Browser VM is ideal for:

- **Isolated testing** - Test in a clean browser environment without affecting your local setup
- **AI-assisted browsing** - Let AI agents interact with web pages through MCP tools
- **Recording & replay** - Capture and replay browser interactions with video recording
- **CI/CD pipelines** - Run browser automation in headless Docker environments

## Prerequisites

- **Docker** - Docker Desktop, OrbStack, or Docker Engine must be running
- **Port availability** - Ports 6080, 6081, 8767, 8768, 8889, 9222 must be free

## Commands

### `inspekt vm start`

Build (if needed) and start the VM container.

```bash
# Start the VM (auto-detects dev environment)
inspekt vm start

# Force rebuild the Docker image
inspekt vm start --rebuild

# Start without opening the browser
inspekt vm start --no-open

# Explicitly enable development mode (mounts local source)
inspekt vm start --dev

# Disable auto-detected dev mode
inspekt vm start --no-dev
```

**What happens on start:**

1. Checks for orphaned containers from previous sessions and cleans them up
2. Verifies all required ports are available
3. Builds the Docker image if needed
4. Starts the container with appropriate settings
5. Verifies the VM is serving correct content
6. Opens the control panel in your browser

### `inspekt vm stop`

Stop the running VM container.

```bash
inspekt vm stop
```

### `inspekt vm restart`

Stop and restart the VM.

```bash
# Restart the VM
inspekt vm restart

# Rebuild and restart
inspekt vm restart --rebuild

# Restart with dev mode
inspekt vm restart --dev
```

### `inspekt vm status`

Check the status of the VM.

```bash
# Human-readable output
inspekt vm status

# JSON output for scripting
inspekt vm status --json
```

### `inspekt vm open`

Open the VM control panel in your browser.

```bash
inspekt vm open
```

### `inspekt vm logs`

View the container logs for debugging.

```bash
inspekt vm logs
```

### `inspekt vm shell`

Open an interactive shell inside the VM container.

```bash
inspekt vm shell
```

### `inspekt vm cleanup`

Clean up ALL VM containers, including orphaned ones from previous sessions.

```bash
# Clean up with confirmation prompt
inspekt vm cleanup

# Clean up without confirmation
inspekt vm cleanup --force
```

**When to use cleanup:**

- Port conflicts when starting the VM
- Multiple containers from different image versions
- Stale containers from previous development sessions
- After a Docker image rebuild to ensure fresh start

## Accessing the VM

Once started, the VM is accessible at:

| URL | Purpose |
|-----|---------|
| `http://localhost:6080/control.html` | **Control Panel** - Main interface with browser view, terminal, and tools |
| `http://localhost:6080/vnc.html` | **VNC Viewer** - Direct browser view only |

## Development Mode

When running from the Inspekt source repository, development mode is **automatically enabled**. This mounts local source files into the container:

| Local Path | Container Path |
|------------|----------------|
| `docker/browser-vm/control-panel.html` | `/usr/share/novnc/control.html` |
| `docker/browser-vm/css/` | `/usr/share/novnc/css/` |
| `docker/browser-vm/js/` | `/usr/share/novnc/js/` |
| `docker/browser-vm/fonts/` | `/usr/share/novnc/fonts/` |
| `docker/browser-vm/servers/control-server.py` | `/opt/control-server.py` |
| `docker/browser-vm/servers/terminal-server.py` | `/opt/terminal-server.py` |
| `docker/browser-vm/servers/audio-server.py` | `/opt/audio-server.py` |
| `inspekt/` | `/opt/inspekt/inspekt/` |
| `extensions/` | `/opt/inspekt/extensions/` |

!!! warning "Container restart required for file changes"
    The noVNC websockify server caches files in memory at startup. After modifying mounted files, you must restart the container with `inspekt vm restart` for changes to take effect.

## Safeguards

The `inspekt vm start` command includes several safeguards to prevent common issues:

### 1. Orphan Container Detection

Automatically finds and removes containers from **any version** of the inspekt-browser-vm image, not just the named container. This prevents old containers from occupying ports.

### 2. Port Conflict Check

Before starting, verifies all required ports are available:

- **6080** - noVNC web interface
- **6081** - Audio WebSocket
- **8767** - Inspekt bridge server
- **8768** - Inspekt bridge (fallback)
- **8889** - Terminal WebSocket
- **9222** - Chrome DevTools Protocol

If any ports are in use, you'll see which processes are using them and can run `inspekt vm cleanup` to resolve.

### 3. Content Verification

After starting, the command fetches `control.html` and verifies it contains expected code markers. This catches the rare case where an old container is still serving stale content.

## Troubleshooting

### "Port conflicts detected"

```
⚠ Port conflicts detected:
  • Port 6080 in use (PIDs: 12345)

Run 'inspekt vm cleanup' to stop all VM containers,
or manually stop the conflicting process.
```

**Solution:** Run `inspekt vm cleanup --force` to remove all VM containers.

### "Stale content detected"

```
✗ VM verification failed: Stale content detected (missing expected code)
```

**Solution:** Old containers are still running. Run `inspekt vm cleanup --force` and try again.

### Container keeps crashing

Check the logs for errors:

```bash
inspekt vm logs
```

Common causes:
- Insufficient shared memory (try increasing `--shm-size`)
- Display issues in headless environments

### Extension not loading

If the Inspekt extension isn't appearing in Chrome:

1. Open DevTools in the VM browser
2. Check the Extensions panel
3. Verify `/opt/inspekt/extensions/chrome` is properly mounted

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Container                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Xvfb      │  │  x11vnc     │  │  noVNC (websockify) │  │
│  │  (Display)  │──│  (VNC)      │──│  (Web interface)    │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│         │                                    │               │
│  ┌──────▼──────┐                    ┌───────▼───────┐       │
│  │  Chromium   │                    │ Control Panel │       │
│  │  + Inspekt  │                    │   (HTML/JS)   │       │
│  │  Extension  │                    └───────────────┘       │
│  └─────────────┘                                            │
│         │                                                    │
│  ┌──────▼──────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Inspekt    │  │  Terminal   │  │   Control Server    │  │
│  │  Bridge     │  │  Server     │  │   (REST API)        │  │
│  │  (WS:8767)  │  │  (WS:8889)  │  │   (HTTP:8888)       │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Environment Variables

The container sets these environment variables:

| Variable | Value | Purpose |
|----------|-------|---------|
| `INSPEKT_ISOLATED` | `1` | Enables isolated mode (bypasses domain checks) |
| `INSPEKT_BRIDGE_URL` | `http://localhost:8767` | Bridge server URL |
| `DISPLAY` | `:0` | X11 display for Chromium |

Pass additional variables at runtime:

```bash
docker run -e THOTH_API_KEY=xxx ... inspekt-browser-vm
```
