---
name: vm
description: "Manages the Inspekt Browser VM Docker deployment. Use when building, starting, stopping, or debugging the VM container, or when working on control-panel.html, control-server.py, terminal-server.py, Dockerfile, supervisord.conf, or entrypoint.sh."
allowed-tools: Read, Bash, Grep, Glob
user-invocable: true
---

# Inspekt Browser VM — Deployment Workflow

## 1. Decision Tree: "I changed X, what do I do?"

| What changed | Action | Command |
|---|---|---|
| Python code (`inspekt/`) | Nothing (dev mode hot-reloads) | — |
| `control-server.py` | Restart service | `make vm-restart-control` |
| `terminal-server.py` | Restart service | `make vm-restart-terminal` |
| `control-panel.html`, fonts, static assets | Restart container | `make vm-restart` |
| Chrome extension files | Restart Chromium | `make vm-restart-chromium` |
| `Dockerfile`, `supervisord.conf`, `entrypoint.sh`, system packages, `pyproject.toml` | Full rebuild | `make vm-rebuild` |

## 2. Port Map

| Port | Service | Host-accessible? | Test from host |
|---|---|---|---|
| 5900 | VNC (x11vnc) | No (internal) | — |
| 6080 | noVNC web UI | Yes | `curl -s http://localhost:6080/` |
| 6081 | Audio WebSocket | Yes | — |
| 8767 | Inspekt Bridge HTTP | No (internal, 127.0.0.1) | `docker exec $C curl -s http://127.0.0.1:8767/health` |
| 8768 | Inspekt Bridge WS | No (internal) | — |
| 8888 | Control Server REST API | **Yes** | `curl -s "http://localhost:8888/health"` |
| 8889 | Terminal WebSocket | Yes | — (WebSocket only) |
| 9222 | Chrome CDP | Yes | `curl -s http://localhost:9222/json/version` |

## 3. Container Name Detection

Two workflows produce different container names:
- **Compose** (`docker compose -f vm/docker-compose.yml up -d`): creates `inspekt-browser`
- **CLI** (`inspekt vm start`): creates `inspekt-browser-vm`

Before running `docker exec`, always detect which is running:
```bash
docker ps --format '{{.Names}}' --filter 'name=inspekt-browser'
```

The Makefile targets handle this automatically via a `VM_CONTAINER` variable.

## 4. Commands — Use These

| Command | Make target | Description |
|---|---|---|
| `inspekt vm start` | `make vm-start` | Start (auto-detects dev mode) |
| `inspekt vm stop` | `make vm-stop` | Stop and remove |
| `inspekt vm restart` | `make vm-restart` | Restart container |
| `inspekt vm restart --rebuild` | `make vm-rebuild` | Full rebuild |
| `inspekt vm status` | `make vm-status` | Check status |
| `inspekt vm logs` | `make vm-logs` | Container logs |
| `inspekt vm shell` | `make vm-shell` | Shell into container |
| — | `make vm-services` | List all supervised processes |
| — | `make vm-health` | Check all endpoints |

**Never use** raw `docker compose build/up/down` — different container name, no safeguards (orphan detection, port checks, content verification).

## 5. Supervisord Service Names

Exact names for `supervisorctl restart <name>`:

| Service | Description |
|---|---|
| `xorg` | X11 display server |
| `pulseaudio` | Audio daemon |
| `x11vnc` | VNC server |
| `novnc` | noVNC web proxy |
| `audio-websocket` | Audio WebSocket proxy |
| `openbox` | Window manager |
| `chromium` | Browser |
| `inspekt-bridge` | Bridge WS server |
| `inspekt-api` | Uvicorn HTTP API |
| `control-server` | Browser control REST API (port 8888) |
| `terminal-server` | PTY WebSocket (port 8889) |

## 6. Dev Mode

Auto-detected when running from source repo (checks for `pyproject.toml`). Volume-mounts source files as `:ro`. `PYTHONDONTWRITEBYTECODE=1` prevents stale `.pyc`.

**Important**: noVNC caches files in memory at startup. Changes to `control-panel.html` require full container removal + restart (not just `docker stop`/`docker start`). The `inspekt vm restart` command handles this correctly.

## 7. Common Pitfalls

- Control server is port **8888**, NOT 8889 (terminal) or 6080 (noVNC)
- Always quote URLs with `&` in bash: `curl -s "http://localhost:8888/foo?x=1&y=2"`
- Never hardcode port 8765 for bridge inside VM code — use `get_bridge_port()` from `inspekt/config.py`
- Container name depends on how it was started — always detect, don't assume
- After editing `control-panel.html`, you must do a full `make vm-restart` (not just restart the control-server service) because noVNC caches static files in memory
