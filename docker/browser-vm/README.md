# Inspekt Browser VM

A complete browser testing environment in Docker: Chromium with visual access via noVNC, remote Chrome DevTools debugging, and built-in accessibility testing tools.

## What Makes This Unique

| Feature | Inspekt VM | Chromote | BrowserStack | LambdaTest |
|---------|-----------|----------|--------------|------------|
| Visual browser (noVNC) | Yes | Yes | Yes | Yes |
| Remote CDP to **local** DevTools | Yes | Yes | No | No |
| Built-in accessibility testing | Yes | No | No | No |
| MCP server for AI control | Yes | No | No | No |
| Self-hosted | Yes | Yes | No | No |

**The killer combination:** See the browser visually AND debug from your local DevTools, with accessibility testing and AI integration built in.

## Features

- **Visual browser access**: View and control via any browser (noVNC)
- **Remote DevTools debugging**: Connect your local Chrome DevTools via CDP (port 9222)
- **Built-in accessibility testing**: axe-core audits, autocomplete checks, link extraction
- **MCP server integration**: AI-assisted browser control via Claude
- **Web terminal**: Access a terminal inside the VM
- **Tab management**: Multiple tabs with thumbnails and auto-scan
- **Self-contained**: Chromium + Inspekt extension + bridge server all in one container
- **Fast boot**: ~3-5 seconds to full browser
- **Configurable**: Resolution, theme, home URL via env vars

## Requirements

- **Docker** (Docker Desktop or Docker Engine)
- **Browser**: Google Chrome (recommended). The control panel uses advanced web APIs (WebSocket RFB, capture-phase pointer events, MediaSource) that are tested and optimized for Chrome. Safari has known issues (see [#11](https://github.com/roelvangils/inspekt/issues/11)).

## Quick Start

### Using the CLI (Recommended)

The easiest way to use the Browser VM is through the `inspekt vm` commands:

```bash
inspekt vm start    # Build (if needed) and start the VM
inspekt vm open     # Open the control panel
inspekt vm stop     # Stop the VM
inspekt vm restart  # Restart the VM
```

When running from the Inspekt source repository, dev mode is **automatically enabled** - this mounts local source files so code changes are reflected immediately without rebuilding.

```bash
inspekt vm start           # Auto-detects dev environment
inspekt vm start --no-dev  # Disable dev mode (use frozen image code)
inspekt vm restart         # Same auto-detection on restart
```

### Using Docker Directly

```bash
# Build the image (from project root)
docker build -t inspekt-browser-vm -f docker/browser-vm/Dockerfile .

# Run with host networking (recommended for macOS/OrbStack)
docker run -d --network host --shm-size=2g --name inspekt-vm inspekt-browser-vm

# Open the control panel
open http://localhost:6080/control.html
```

## Remote DevTools Debugging

Connect your **local** Chrome DevTools to the VM browser. Click the **DevTools** button in the control panel for a setup guide, or follow these steps:

### Option 1: Direct Connection (Local/Trusted Network)

1. Open `chrome://inspect/#devices` in your local Chrome
2. Click "Configure..." next to "Discover network targets"
3. Add `localhost:9222` (or `<vm-host>:9222`)
4. Click "inspect" on the VM browser target

### Option 2: SSH Tunnel (Secure Remote Access)

```bash
# On your local machine
ssh -L 9222:localhost:9222 user@your-server

# Then in Chrome, add localhost:9222 as the target
```

### Security Note

CDP has no authentication. Only expose port 9222 on trusted networks or use SSH tunneling for remote access.

## Control Panel Features

The control panel at `http://localhost:6080/control.html` provides:

- **Navigation**: Back, forward, reload, URL bar
- **DevTools**: Setup guide for remote debugging
- **Terminal**: Web-based terminal access
- **Inspekt Commands**: Run accessibility audits, extract links, page outline, screenshots
- **Tab Management**: Create, switch, close tabs with thumbnail previews
- **Auto-scan**: Automatic accessibility scanning of tabs
- **Theme Toggle**: Switch between dark and light modes

## Executing Commands in the VM

### Open a Terminal Window

```bash
# Install xterm (first time only)
docker exec inspekt-browser-vm apk add --no-cache xterm

# Open terminal in the VM display
docker exec -d -e DISPLAY=:0 inspekt-browser-vm xterm -fa 'Monospace' -fs 12
```

### Run Shell Commands

```bash
# Run any command
docker exec inspekt-browser-vm <command>

# Run a command with output
docker exec inspekt-browser-vm ls -la /opt/inspekt

# Interactive bash shell
docker exec -it inspekt-browser-vm bash
```

### Run GUI Applications

```bash
# Launch any GUI app (requires DISPLAY=:0)
docker exec -d -e DISPLAY=:0 inspekt-browser-vm <app>

# Examples:
docker exec -d -e DISPLAY=:0 inspekt-browser-vm xterm
docker exec -d -e DISPLAY=:0 inspekt-browser-vm pcmanfm  # file manager (install first)
docker exec -d -e DISPLAY=:0 inspekt-browser-vm chromium https://google.com
```

### Run Inspekt Commands

```bash
# Activate venv and run inspekt
docker exec inspekt-browser-vm bash -c "cd /opt/inspekt && . .venv/bin/activate && inspekt info"
docker exec inspekt-browser-vm bash -c "cd /opt/inspekt && . .venv/bin/activate && inspekt url"
docker exec inspekt-browser-vm bash -c "cd /opt/inspekt && . .venv/bin/activate && inspekt screenshot"

# Check bridge health
docker exec inspekt-browser-vm curl -s http://localhost:8765/health | python3 -m json.tool
```

### Use the HTTP API

```bash
# From your host machine, talk to the bridge inside the container

# Health check
curl http://localhost:8765/health

# Execute JavaScript in the browser
curl -X POST http://localhost:8765/run \
  -H "Content-Type: application/json" \
  -d '{"code": "document.title"}'

# Get current URL
curl -X POST http://localhost:8765/run \
  -H "Content-Type: application/json" \
  -d '{"code": "window.location.href"}'
```

## Ports

| Port | Service | Description |
|------|---------|-------------|
| 6080 | noVNC | Visual browser access (control panel) |
| 8888 | Control Server | REST API for browser control |
| 8889 | Terminal | WebSocket terminal server |
| 9222 | CDP | Chrome DevTools Protocol (remote debugging) |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VNC_RESOLUTION` | `1920x1080` | Screen resolution |
| `VNC_DEPTH` | `24` | Color depth |
| `HOME_URL` | `http://inspekt/status` | Initial URL to load |
| `VNC_PASSWORD` | *(empty)* | VNC password (optional) |
| `INSPEKT_ISOLATED` | `1` | Enable isolated mode (safe in VM) |

## Usage Examples

### Basic Usage

```bash
docker run -d --network host --shm-size=2g inspekt-browser
```

### With Password Protection

```bash
docker run -d --network host --shm-size=2g \
  -e VNC_PASSWORD=mysecret \
  inspekt-browser
```

### Custom Resolution and Home Page

```bash
docker run -d --network host --shm-size=2g \
  -e VNC_RESOLUTION=1920x1080 \
  -e HOME_URL=https://example.com \
  inspekt-browser
```

## Embedding in a Web Page

### Basic iframe

```html
<iframe
  src="http://localhost:6080/vnc.html?autoconnect=true&resize=scale"
  width="1280"
  height="720"
  allow="clipboard-read; clipboard-write"
></iframe>
```

### noVNC URL Parameters

| Parameter | Values | Description |
|-----------|--------|-------------|
| `autoconnect` | `true/false` | Connect automatically |
| `resize` | `scale/remote/off` | Scaling mode |
| `reconnect` | `true/false` | Auto-reconnect |
| `reconnect_delay` | `ms` | Delay before reconnect |
| `view_only` | `true/false` | Disable input |
| `show_dot` | `true/false` | Show dot cursor |
| `bell` | `true/false` | Enable bell sound |
| `password` | `string` | VNC password |

### Full Example

```html
<iframe
  src="http://localhost:6080/vnc.html?autoconnect=true&resize=scale&reconnect=true&reconnect_delay=1000"
  style="width: 100%; height: 600px; border: none;"
  allow="clipboard-read; clipboard-write"
></iframe>
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Your Browser                                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  noVNC Client (HTML5/WebSocket) ← localhost:6080      │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼ WebSocket
┌─────────────────────────────────────────────────────────────┐
│  Docker Container (Alpine Linux 3.20)                       │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  noVNC + websockify (:6080)                           │  │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                 │
│                           ▼ VNC                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  x11vnc (:5900)                                       │  │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                 │
│                           ▼ X11                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Xvfb (Virtual framebuffer :0)                        │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │  Openbox (Window manager)                       │  │  │
│  │  │  ┌───────────────────────────────────────────┐  │  │  │
│  │  │  │  Chromium + Inspekt Extension             │  │  │  │
│  │  │  └───────────────────────────────────────────┘  │  │  │
│  │  │  ┌───────────────────────────────────────────┐  │  │  │
│  │  │  │  xterm / other GUI apps                   │  │  │  │
│  │  │  └───────────────────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Inspekt Bridge Server                                │  │
│  │  HTTP API: :8765  |  WebSocket: :8766                 │  │
│  └───────────────────────────────────────────────────────┘  │
│                           ↑                                 │
│                           │ WebSocket                       │
│                           └── Chromium Extension connects   │
└─────────────────────────────────────────────────────────────┘
```

## Container Management

```bash
# Start container
docker start inspekt-browser-vm

# Stop container
docker stop inspekt-browser-vm

# Restart container
docker restart inspekt-browser-vm

# View logs
docker logs -f inspekt-browser-vm

# Remove container
docker rm -f inspekt-browser-vm

# List running containers
docker ps

# Execute command in running container
docker exec inspekt-browser-vm <command>

# Interactive shell
docker exec -it inspekt-browser-vm bash
```

## Installing Additional Software

```bash
# Install packages (Alpine uses apk, no need to update first)
docker exec inspekt-browser-vm apk add --no-cache <package>

# Examples:
docker exec inspekt-browser-vm apk add --no-cache vim
docker exec inspekt-browser-vm apk add --no-cache htop
docker exec inspekt-browser-vm apk add --no-cache pcmanfm  # file manager
docker exec inspekt-browser-vm apk add --no-cache xfce4-terminal  # nicer terminal
```

## Deployment Options

### Fly.io (Recommended for Low Cost)

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Launch
fly launch --name inspekt-browser --region ams
fly deploy
```

**fly.toml**:
```toml
app = "inspekt-browser"
primary_region = "ams"

[build]
  dockerfile = "Dockerfile"

[env]
  VNC_RESOLUTION = "1280x720"
  HOME_URL = "about:blank"

[http_service]
  internal_port = 6080
  force_https = true

[[vm]]
  memory = "1gb"
  cpu_kind = "shared"
  cpus = 1
```

### Railway

```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

### Docker Compose (Local/Self-hosted)

```yaml
version: '3.8'
services:
  browser:
    build: .
    network_mode: host
    shm_size: 2g
    environment:
      - VNC_RESOLUTION=1920x1080
      - HOME_URL=https://example.com
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
```

## Estimated Costs

| Provider | Specs | Monthly Cost |
|----------|-------|--------------|
| Fly.io | 1 shared CPU, 1GB RAM | ~$5-7 |
| Railway | Usage-based | ~$5-10 |
| DigitalOcean | 1 vCPU, 1GB RAM | $6 |
| Render | 0.5 CPU, 512MB RAM | $7 |
| AWS Fargate | 0.25 vCPU, 512MB | ~$10 |

## Troubleshooting

### Chromium crashes immediately

Add `--shm-size=2g` to docker run:
```bash
docker run -d --network host --shm-size=2g inspekt-browser
```

### Slow/laggy interaction

1. Reduce resolution: `-e VNC_RESOLUTION=1024x768`
2. Check network latency to server
3. Use `resize=scale` in noVNC URL

### Can't type special characters

noVNC may have keyboard layout issues. Try:
- Use on-screen keyboard in browser
- Set correct locale in container

### Connection refused

```bash
# Check container is running
docker ps

# Check logs
docker logs inspekt-browser-vm

# Verify port is open
curl http://localhost:6080
```

### OrbStack: Port forwarding not working

If using OrbStack on macOS and `localhost:6080` isn't accessible, use host networking:

```bash
docker run -d --network host --shm-size=2g --name browser-vm inspekt-browser
```

### Bridge server not running

```bash
# Check if bridge is running
docker exec inspekt-browser-vm ps aux | grep bridge

# Start it manually
docker exec -d inspekt-browser-vm bash -c "cd /opt/inspekt && . .venv/bin/activate && python inspekt/bridge_ws.py"

# Check health
docker exec inspekt-browser-vm curl -s http://localhost:8765/health
```

### Extension not connecting

1. Check if Chromium was started with `--load-extension`:
   ```bash
   docker exec inspekt-browser-vm ps aux | grep chromium
   ```

2. Restart Chromium with the extension:
   ```bash
   docker exec inspekt-browser-vm pkill -f chromium || true
   docker exec -d -e DISPLAY=:0 inspekt-browser-vm /usr/bin/chromium \
       --no-sandbox --disable-gpu --disable-dev-shm-usage \
       --no-first-run --start-maximized \
       --load-extension=/opt/inspekt/extensions/chrome \
       https://example.com
   ```

## Control Server API

The control server (port 8888) provides a REST API for browser control:

### Browser Navigation

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/back` | GET | Navigate back |
| `/forward` | GET | Navigate forward |
| `/reload-page` | GET | Reload current page |
| `/navigate?url=...` | GET | Navigate to URL |
| `/url` | GET | Get current URL |

### Tab Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/tabs` | GET | List all tabs |
| `/tabs/new?url=...` | GET | Create new tab |
| `/tabs/{id}/activate` | GET | Switch to tab |
| `/tabs/{id}/close` | GET | Close tab |
| `/tabs/{id}/screenshot` | GET | Capture tab screenshot |

### DevTools

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/devtools/toggle` | GET | Toggle DevTools in VM |
| `/devtools/status` | GET | Get DevTools state |
| `/devtools/connection-info` | GET | Get CDP connection details |

### Inspekt Commands

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/inspekt/info` | GET | Page information |
| `/inspekt/axe` | GET | Accessibility audit |
| `/inspekt/links` | GET | Extract links |
| `/inspekt/outline` | GET | Page outline |
| `/inspekt/screenshot` | GET | Take screenshot |

## Comparison to Alternatives

### vs [Chromote](https://github.com/igolaizola/chromote)
Chromote provides Chrome + noVNC + CDP, but without any testing tools. Inspekt VM adds accessibility testing, MCP integration, and a polished control panel.

### vs BrowserStack / LambdaTest
Cloud platforms offer DevTools *inside* their VM, but you can't connect your local DevTools to their browser. Inspekt VM exposes CDP so you can use your familiar local DevTools.

### vs Docker Selenium
Selenium containers use noVNC for debugging automated tests. Inspekt VM is designed for interactive testing and debugging, with accessibility tools built in.

### vs Playwright / Puppeteer
These are headless automation tools. Inspekt VM provides visual access - you can see what's happening and interact manually while also having programmatic control via CDP.

## Security Considerations

> **Warning**: The Inspekt VM is designed for local development and trusted networks only. It exposes multiple services without authentication. **Never expose the VM directly to the internet.**

### Network Exposure

When running with `--network host`, the following services are exposed to your local network:

| Port | Service | Risk | Mitigation |
|------|---------|------|------------|
| 6080 | noVNC | Medium - Full browser control | Use VNC_PASSWORD |
| 8767 | Bridge HTTP | Low - Browser automation API | Localhost only recommended |
| 8889 | Terminal | **High** - Shell access | Localhost only (default) |
| 9222 | CDP | **High** - Full browser control | SSH tunnel for remote access |

### Best Practices

- **Use VNC_PASSWORD** in production: `-e VNC_PASSWORD=mysecret`
- **Use HTTPS** (terminate at reverse proxy like nginx/Caddy)
- **Network isolation**: Don't expose to public internet without auth
- **Resource limits**: Set memory/CPU limits to prevent abuse
- **Chromium runs with --no-sandbox**: Required in containers but reduces security
- **CDP has no auth**: Only expose port 9222 on trusted networks or use SSH tunneling
- **API keys at runtime**: Pass sensitive keys via environment variables, not in Dockerfile:
  ```bash
  docker run -e THOTH_API_KEY=xxx -e OTHER_SECRET=yyy ...
  ```

### For Remote/Cloud Deployment

If deploying to a remote server:

1. **Use SSH tunneling** for all services:
   ```bash
   ssh -L 6080:localhost:6080 -L 9222:localhost:9222 user@server
   ```

2. **Use a reverse proxy** with authentication (nginx, Caddy, Traefik)

3. **Firewall rules**: Block external access to ports 6080, 8767, 8889, 9222

## License

Part of the Inspekt project.
