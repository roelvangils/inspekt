# Inspekt Browser VM

A self-contained Docker image that runs Chromium browser with the Inspekt extension, accessible via noVNC in a webpage. Perfect for automated testing, demos, and running Inspekt in isolated environments.

## Features

- **Self-contained**: Chromium + Inspekt extension + bridge server all in one container
- **Fast boot**: ~3-5 seconds to full browser
- **Web accessible**: View and control via any browser (noVNC)
- **Native performance**: Real Chromium, not emulated
- **Embeddable**: Works in iframes for web integration
- **Configurable**: Resolution, password, home URL via env vars

## Quick Start

```bash
# Build the image
cd docker/browser-vm
docker build -t inspekt-browser .

# Run with host networking (recommended for macOS/OrbStack)
docker run -d --network host --shm-size=2g --name inspekt-browser-vm inspekt-browser

# Open in your browser
open http://localhost:6080
```

## Full Setup with Inspekt

To run Inspekt inside the container (extension + bridge server):

```bash
# 1. Start the container
docker run -d --network host --shm-size=2g --name inspekt-browser-vm inspekt-browser

# 2. Install dependencies
docker exec inspekt-browser-vm apt-get update -qq
docker exec inspekt-browser-vm apt-get install -y -qq git python3-pip python3-venv

# 3. Clone Inspekt
docker exec inspekt-browser-vm git clone https://github.com/roelvangils/inspekt.git /opt/inspekt

# 4. Install Python dependencies
docker exec inspekt-browser-vm bash -c "cd /opt/inspekt && python3 -m venv .venv && . .venv/bin/activate && pip install -e . && pip install -r requirements.txt pillow aiofiles rich"

# 5. Start the bridge server
docker exec -d inspekt-browser-vm bash -c "cd /opt/inspekt && . .venv/bin/activate && python inspekt/bridge_ws.py"

# 6. Restart Chromium with the extension
docker exec inspekt-browser-vm pkill -f chromium || true
docker exec -d -e DISPLAY=:0 inspekt-browser-vm /usr/bin/chromium \
    --no-sandbox --disable-gpu --disable-dev-shm-usage \
    --no-first-run --start-maximized \
    --load-extension=/opt/inspekt/extensions/chrome \
    https://example.com
```

## Executing Commands in the VM

### Open a Terminal Window

```bash
# Install xterm (first time only)
docker exec inspekt-browser-vm apt-get install -y -qq xterm

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

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VNC_PASSWORD` | *(empty)* | VNC password (optional) |
| `VNC_RESOLUTION` | `1280x720` | Screen resolution |
| `VNC_DEPTH` | `24` | Color depth |
| `HOME_URL` | `about:blank` | Initial URL to load |
| `NOVNC_PORT` | `6080` | noVNC web port |

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
│  Docker Container (Debian 12 "Bookworm")                    │
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
# Update package list
docker exec inspekt-browser-vm apt-get update

# Install packages
docker exec inspekt-browser-vm apt-get install -y <package>

# Examples:
docker exec inspekt-browser-vm apt-get install -y vim
docker exec inspekt-browser-vm apt-get install -y htop
docker exec inspekt-browser-vm apt-get install -y pcmanfm  # file manager
docker exec inspekt-browser-vm apt-get install -y xfce4-terminal  # nicer terminal
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

## Security Considerations

- **Use VNC_PASSWORD** in production
- **Use HTTPS** (terminate at reverse proxy)
- **Network isolation**: Don't expose to public internet without auth
- **Resource limits**: Set memory/CPU limits to prevent abuse
- **Chromium runs with --no-sandbox**: Required in containers but reduces security

## License

MIT
