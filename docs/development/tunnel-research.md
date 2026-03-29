# Tunnel Feature Research

> Research conducted 2026-03-29. Evaluating approaches for letting users expose their localhost web server to a cloud-hosted Inspekt VM browser.

## Problem Statement

Inspekt VM will run in the cloud. Users need a way to make their local development server (e.g. `localhost:3000`) reachable from within the VM's browser — ideally with a single command and zero signup.

## Key Constraint

True peer-to-peer without any intermediate infrastructure is impossible when both sides are behind NAT. However, since **we control the cloud VM**, the VM itself can serve as the coordination point, eliminating the need for third-party infrastructure.

---

## Tier 1: No Install Required on User's Machine

### SSH Reverse Tunnel (plain SSH)

```bash
ssh -R 8080:localhost:3000 user@inspekt-vm.example.com
```

- **How it works:** User opens SSH connection to VM with reverse port forward. VM browser accesses `localhost:8080`.
- **Intermediate server:** No — the VM is the server
- **Client install:** None (SSH is universal on macOS/Linux)
- **Open source:** Yes (OpenSSH, BSD license)
- **Maturity:** Decades, battle-tested
- **One-command:** Yes
- **Advantages:** Zero install, zero signup, no third-party dependency, encrypted, full control
- **Disadvantages:** Requires SSH access to VM (key management), no automatic reconnection (use `autossh`), Windows users need extra setup, no subdomain routing

### sish (self-hosted ngrok over SSH)

```bash
ssh -R myapp:80:localhost:3000 inspekt-vm.example.com -p 2222
```

- **How it works:** Go binary on VM provides ngrok-like subdomains using standard SSH as client transport.
- **Intermediate server:** Self-hosted on VM
- **Client install:** None (uses SSH)
- **Open source:** Yes — github.com/antoniomika/sish, MIT, 4.6k stars
- **One-command:** Yes
- **Advantages:** Pretty subdomain routing, zero client install, automatic HTTPS via Let's Encrypt, supports TCP/HTTP/WS
- **Disadvantages:** Extra daemon on VM, more moving parts than plain SSH, less mature than OpenSSH

### Pinggy (hosted SSH tunnel service)

```bash
ssh -p 443 -R0:localhost:3000 a.pinggy.io
```

- **Intermediate server:** Yes — Pinggy's servers (third-party)
- **Client install:** None
- **Open source:** No (free tier available)
- **One-command:** Yes
- **Advantages:** Simplest possible UX, zero install, zero signup, HTTPS
- **Disadvantages:** Third-party dependency, free tier has session limits, adds latency

---

## Tier 2: Lightweight Binary Install

### bore

```bash
bore local 3000 --to inspekt-vm.example.com
```

- **How it works:** Ultra-minimal Rust tunnel. Server runs on VM, user installs small static binary.
- **Intermediate server:** Self-hosted on VM
- **Client install:** Yes — single static binary (~3 MB)
- **Open source:** Yes — github.com/ekzhang/bore, MIT, 11k stars
- **One-command:** Yes
- **Advantages:** Extremely simple, tiny binary, fast (Rust), easy to self-host, no config files
- **Disadvantages:** No HTTPS termination, no built-in auth, less mature than SSH

### chisel

```bash
chisel client https://inspekt-vm.example.com R:8080:localhost:3000
```

- **How it works:** HTTP/WebSocket-based tunnel. Looks like normal HTTPS traffic.
- **Intermediate server:** Self-hosted on VM
- **Client install:** Yes — single binary (~11 MB)
- **Open source:** Yes — github.com/jpillora/chisel, MIT, 15.8k stars
- **One-command:** Yes
- **Advantages:** Traverses HTTP proxies and corporate firewalls, supports HTTPS, auth, fingerprint verification
- **Disadvantages:** Larger binary, slightly more complex than bore
- **Note:** Best option for users on restrictive corporate networks that block non-HTTP traffic

### Cloudflare Quick Tunnel

```bash
cloudflared tunnel --url http://localhost:3000
```

- **Intermediate server:** Yes — Cloudflare's edge network
- **Client install:** Yes (`cloudflared` binary)
- **Open source:** Yes (Apache-2.0)
- **One-command:** Yes, no account needed for quick tunnels
- **Advantages:** Free, HTTPS, global edge, no signup for quick tunnels
- **Disadvantages:** Third-party dependency, 200 concurrent request limit, no SSE/WebSocket on free tier, traffic routes through Cloudflare

### frp (Fast Reverse Proxy)

- **Open source:** Yes — Apache-2.0, 105k GitHub stars
- **One-command:** No — requires config files on both sides
- **Advantages:** Extremely mature, feature-rich, dashboards, multiplexing
- **Disadvantages:** Config-file driven (poor one-command UX), heavier setup

---

## Tier 3: Heavier / Requires Accounts

### Tailscale Funnel

```bash
tailscale funnel 3000
```

- **True P2P:** Yes (WireGuard-based, DERP relay fallback)
- **Client install:** Yes + account required on both machines
- **Advantages:** Excellent UX once set up, true mesh networking, encrypted
- **Disadvantages:** Account required, install on both ends, overkill for single port forward

### ngrok

- Industry standard, requires account, interstitial warning on free tier, 2-hour session limits

### ZeroTier / Nebula / WireGuard (raw)

- Full mesh VPN solutions. Excellent technology but far too much setup for a single port forward.

---

## Tier 4: Not Recommended

| Tool | Why not |
|---|---|
| localtunnel | Unmaintained, frequent 502 errors |
| WebRTC tunnels (RTCTunnel) | Experimental, complex signaling, immature |
| serveo | Was down for years, unreliable |

---

## Recommendations

### Default: SSH reverse tunnel

Zero install, we control everything, wrap as `inspekt tunnel <port>`. Best starting point.

### Corporate networks: chisel

HTTP/WebSocket-based — looks like normal HTTPS traffic. Best option when SSH is blocked by firewalls or proxies. Could be offered as `inspekt tunnel <port> --transport chisel`.

### Future consideration: sish

If we want pretty subdomain routing and auto-HTTPS without requiring any client install, sish is the natural upgrade path from plain SSH.

---

## Corporate Network Considerations

Some corporate environments block:
- **Outbound SSH (port 22)** — sish/Pinggy can run on port 443 to work around this
- **All non-HTTP traffic** — chisel is the best option here (tunnels over WebSocket)
- **Unknown domains** — Cloudflare tunnels may be whitelisted already; self-hosted requires domain allowlisting

A `--transport` flag could let users choose the approach that works for their network.
