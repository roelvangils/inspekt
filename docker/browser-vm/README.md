# Inspekt Browser VM

A minimal Docker image that runs Chromium browser accessible via noVNC in a webpage.

## Features

- **Fast boot**: ~3-5 seconds to full browser
- **Lightweight**: Based on Debian slim (~500MB compressed)
- **Native performance**: Real Chromium, not emulated
- **Web accessible**: View and control via any browser
- **Embeddable**: Works in iframes for web integration
- **Configurable**: Resolution, password, home URL via env vars

## Quick Start

```bash
# Build the image
docker build -t inspekt-browser .

# Run it
docker run -d -p 6080:6080 --name browser-vm inspekt-browser

# Open in your browser
open http://localhost:6080
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
docker run -d -p 6080:6080 inspekt-browser
```

### With Password Protection

```bash
docker run -d -p 6080:6080 \
  -e VNC_PASSWORD=mysecret \
  inspekt-browser
```

### Custom Resolution and Home Page

```bash
docker run -d -p 6080:6080 \
  -e VNC_RESOLUTION=1920x1080 \
  -e HOME_URL=https://example.com \
  inspekt-browser
```

### For Inspekt Testing

```bash
docker run -d -p 6080:6080 \
  -e HOME_URL=https://your-test-site.com \
  -e VNC_RESOLUTION=1920x1080 \
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
# Install Railway CLI
npm install -g @railway/cli

# Deploy
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
    ports:
      - "6080:6080"
    environment:
      - VNC_RESOLUTION=1920x1080
      - HOME_URL=https://example.com
    restart: unless-stopped
    # Optional: resource limits
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 1G
```

## Architecture

```
┌─────────────────────────────────────────────┐
│  Your Browser                               │
│  ┌───────────────────────────────────────┐  │
│  │  noVNC Client (HTML5/WebSocket)       │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
                      │
                      ▼ WebSocket :6080
┌─────────────────────────────────────────────┐
│  Docker Container                           │
│  ┌───────────────────────────────────────┐  │
│  │  websockify (WebSocket → VNC proxy)   │  │
│  └───────────────────────────────────────┘  │
│                     │                       │
│                     ▼ VNC :5900             │
│  ┌───────────────────────────────────────┐  │
│  │  x11vnc (VNC server)                  │  │
│  └───────────────────────────────────────┘  │
│                     │                       │
│                     ▼ X11 :0                │
│  ┌───────────────────────────────────────┐  │
│  │  Xvfb (Virtual framebuffer)           │  │
│  │  ┌─────────────────────────────────┐  │  │
│  │  │  Openbox (Window manager)       │  │  │
│  │  │  ┌───────────────────────────┐  │  │  │
│  │  │  │  Chromium Browser         │  │  │  │
│  │  │  └───────────────────────────┘  │  │  │
│  │  └─────────────────────────────────┘  │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
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
docker run -d -p 6080:6080 --shm-size=2g inspekt-browser
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
docker logs browser-vm

# Verify port is open
curl http://localhost:6080
```

### OrbStack: Port forwarding not working

If using OrbStack on macOS and `localhost:6080` isn't accessible, use host networking:

```bash
docker run -d --network host --shm-size=2g --name browser-vm inspekt-browser
```

## Security Considerations

- **Use VNC_PASSWORD** in production
- **Use HTTPS** (terminate at reverse proxy)
- **Network isolation**: Don't expose to public internet without auth
- **Resource limits**: Set memory/CPU limits to prevent abuse

## License

MIT
