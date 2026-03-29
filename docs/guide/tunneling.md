# Tunneling Local Sites to the VM

The `inspekt tunnel` command lets you access a website running on your local machine from within the Inspekt Browser VM. This is essential when the VM runs in the cloud and can't directly reach your `localhost`.

## Why tunneling?

When the Inspekt VM runs locally (via Docker), it shares your machine's network, so the browser inside it can already reach `localhost`. But when the VM runs in the cloud — as a shared developer tool accessible from any browser — there's no direct path from the cloud VM back to your laptop.

Tunneling solves this by creating a secure, authenticated connection from your machine to the VM, making your local port appear as `localhost` inside the VM.

```
Your machine                              Cloud VM
─────────────                             ────────────
localhost:3000  ──── tunnel ────►  localhost:3000
(your dev server)    (bore)         (VM browser sees this)
```

## Quick start

### 1. Start your local development server

Any web server works:

```bash
# Python
python -m http.server 3000

# Node.js (Vite, Next.js, etc.)
npm run dev -- --port 3000

# PHP
php -S localhost:3000

# Ruby
ruby -run -e httpd . -p 3000
```

### 2. Start the tunnel

```bash
inspekt tunnel 3000
```

That's it. On first run, the bore tunnel client (~3 MB) is automatically downloaded and cached. The command auto-detects the VM's tunnel secret — no manual configuration needed.

You'll see:

```
  ╭─ Tunnel Active ─────────────────────────────╮
  │ Local       http://localhost:3000            │
  │ VM          http://localhost:3000            │
  │ Transport   bore                             │
  ╰──────────────────────────────────────────────╯

  💡 Press Ctrl+C to stop the tunnel
```

### 3. Browse in the VM

Navigate to `http://localhost:3000` in the VM's Chromium browser. Your local site appears as if it were running inside the VM.

## Options

### Different port on the VM side

If port 3000 is already in use inside the VM, map to a different port:

```bash
inspekt tunnel 3000 --remote-port 8080
```

The VM browser then accesses `http://localhost:8080`, which maps to your local port 3000.

### Cloud VM

When connecting to a cloud-hosted VM, specify the host:

```bash
inspekt tunnel 3000 --host vm.example.com
```

The command fetches the tunnel secret automatically from the VM's control server. If the control server isn't reachable (e.g., behind a firewall), provide the secret manually:

```bash
inspekt tunnel 3000 --host vm.example.com --secret <your-secret>
```

### Verbose output

For debugging connection issues:

```bash
inspekt tunnel 3000 -v
```

This shows the exact bore command being executed and additional connection details.

## How it works

The tunnel is powered by [bore](https://github.com/ekzhang/bore), a minimal open-source TCP tunnel tool written in Rust.

### Architecture

The system has two components:

1. **bore server** — runs inside the VM as a supervised service (port 7835). It listens for incoming tunnel connections and exposes them as local ports inside the container.

2. **bore client** — runs on your machine (managed by `inspekt tunnel`). It connects to the bore server and forwards traffic from the VM back to your local port.

### Authentication

A random shared secret is generated each time the VM starts. Both the bore server and client use this secret to authenticate the tunnel connection. The secret is:

- Generated in the VM's entrypoint script (`/tmp/.bore_secret`)
- Served via the control server API (`GET /api/tunnel-info`)
- Automatically fetched by `inspekt tunnel` — you never need to copy it manually

### Traffic flow

```
VM Browser                Your Machine
──────────                ────────────
Request to localhost:3000
        │
        ▼
bore server (:7835)
        │
        │  (TCP tunnel, authenticated)
        │
        ▼
bore client
        │
        ▼
Your dev server (:3000)
        │
        ▼
Response flows back
through the tunnel
```

### Security

- All tunnel traffic is authenticated with a shared secret
- The bore server only accepts connections with the correct secret
- The tunnel exposes only the specific port you choose — nothing else on your machine is accessible
- The bore client binary is downloaded from official GitHub releases and cached locally

## Use cases

### Testing responsive designs

Run your local site in the VM to test it in a controlled Chromium environment with a specific viewport size, without installing anything extra.

### Accessibility auditing local sites

Tunnel your local site, then run inspekt's accessibility tools against it:

```bash
# In one terminal
inspekt tunnel 3000

# In the VM terminal
inspekt axe                    # Run accessibility audit
inspekt screenshot --full      # Capture full page
inspekt outline                # Check heading structure
```

### Demoing to others

When the VM runs in the cloud, you can share the VM's URL with colleagues. They see your local site in the VM browser without needing access to your machine or network.

### Testing behind authentication

Since the tunnel forwards raw TCP, it works with any protocol — HTTP, HTTPS, WebSocket. This means you can tunnel sites that require authentication, session cookies, or other state that wouldn't work with a simple URL share.

## Troubleshooting

### "Could not connect to VM control server"

The VM isn't running or isn't reachable. Start it with:

```bash
inspekt vm start
```

### "port already in use"

The bore server has a stale port allocation from a previous tunnel session. Either:

- Use a different remote port: `inspekt tunnel 3000 --remote-port 3001`
- Restart the bore server inside the VM: the stale allocation will clear automatically after a timeout

### "Failed to download bore"

The bore client binary couldn't be downloaded from GitHub. Check your internet connection, or install bore manually:

```bash
# macOS
brew install ekzhang/bore/bore

# Or download from https://github.com/ekzhang/bore/releases
```

Then `inspekt tunnel` will find it in your PATH.

### Tunnel disconnects frequently

This can happen on unstable networks. The bore client will exit when the connection drops. Simply re-run `inspekt tunnel` to reconnect. For long-running sessions, consider wrapping it in a loop:

```bash
while true; do inspekt tunnel 3000; sleep 2; done
```

## Technical reference

| Component | Location | Port |
|-----------|----------|------|
| bore server | VM container (supervisord) | 7835 |
| bore client | User's machine (`~/.config/inspekt/bin/bore`) | — |
| Tunnel info API | VM control server | 8888 (`/api/tunnel-info`) |
| Default remote port | Same as local port | configurable via `--remote-port` |

### bore client binary

The bore binary is automatically downloaded to `~/.config/inspekt/bin/bore` (or `~/.inspekt/bin/bore` on legacy setups). Version metadata is stored alongside it in `bore.version.json`.

Supported platforms:

- macOS (Intel and Apple Silicon)
- Linux (x86_64 and ARM64)
- Windows (x86_64)
