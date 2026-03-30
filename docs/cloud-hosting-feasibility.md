# Inspekt VM as a Cloud-Hosted Paid Service — Feasibility Analysis

## Context

This document analyzes the feasibility, infrastructure options, cost considerations, and beta launch strategy for offering the Inspekt Browser VM as a cloud-hosted paid service. The current VM is designed as a single-tenant, localhost-only Docker container running ~11 services (Xorg, Chromium, noVNC, bridge, API server, terminal server, control server, etc.) with 2 CPU cores and 2GB RAM per instance.

---

## 1. Is It Feasible?

**Yes, but it requires meaningful architectural work.** The current VM is well-architected for single-user local deployment. The main gaps for cloud hosting are:

- **No authentication** — the bridge accepts any local connection
- **No tenant isolation** — all state (pending requests, connections, plugins) is global
- **Localhost-only networking** — `HOST = "127.0.0.1"` is hardcoded, no TLS
- **Host network mode** — `--network host` won't work with multiple containers on one host

None of these are showstoppers — they're engineering work, not fundamental design problems.

---

## 2. What Runs Inside vs Outside Docker?

### Inside the container (all self-contained):
| Service | Port | Purpose |
|---------|------|---------|
| Xorg (dummy driver) | — | Virtual display |
| x11vnc | 5900 | VNC server |
| noVNC + websockify | 6080 | Web-based VNC client |
| Chromium | 9222 | Browser + CDP |
| Openbox | — | Window manager |
| PulseAudio | — | Audio |
| inspekt-bridge | 8767/8768 | WebSocket bridge |
| inspekt-api (FastAPI) | 80 | HTTP API |
| control-server | 8888 | Tab/resolution management |
| terminal-server | 8889 | WebSocket PTY shell |
| bore-server | 7835 | Tunnel server |

### Outside Docker (currently needed on host):
- Docker engine itself
- Port forwarding (6080, 8888, 8889, 7835)
- Optional: the `inspekt` CLI for management commands

**Key insight:** The VM is remarkably self-contained. Everything a user needs runs inside the container. The only external dependency is Docker itself, which makes cloud deployment straightforward.

---

## 3. Multi-User Architecture: One Container Per User

**Yes, each user needs their own container.** Here's why:

- Chromium runs as a single instance with one user profile
- The bridge maintains per-tab WebSocket connections with no tenant scoping
- The terminal server drops to a single restricted user
- Plugin data is stored in a single SQLite DB
- The X11 display is shared — only one "screen" per container

### Resource per user:
| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 0.5 cores | 2 cores |
| RAM | 512MB | 2GB |
| Shared memory | 512MB | 2GB |
| Disk | ~1GB (image) + ~100MB runtime | Same |
| Startup time | — | ~15-20 seconds |

---

## 4. Infrastructure Options

### Option A: Kubernetes (Best for Scale)

```
Internet → Load Balancer (nginx/Traefik)
              ↓
         Ingress Controller
              ↓
    ┌─────────┼─────────┐
    ↓         ↓         ↓
  Pod-1     Pod-2     Pod-N
  (user-a)  (user-b)  (user-n)

  Each pod = 1 Inspekt VM container
  + sidecar for auth/proxy
```

**Pros:** Auto-scaling, health checks, rolling updates, resource quotas per pod
**Cons:** Complex setup, needs shared memory config (`emptyDir: medium: Memory`), security contexts for iptables

**Managed options:** GKE, EKS, AKS, DigitalOcean Kubernetes

### Option B: Docker Swarm / Compose (Simpler)

Run on a few large VMs (e.g., 32-core, 64GB RAM machines), each hosting ~16-32 containers.

**Pros:** Simpler than K8s, familiar Docker tooling, faster to ship
**Cons:** Less auto-scaling, manual capacity planning

### Option C: Fly.io / Railway (Easiest to Start)

These platforms run Docker containers with per-instance billing.

**Pros:** Zero infrastructure management, pay-per-use, WebSocket support, global edge
**Cons:** Potentially more expensive at scale, less control, may not support `--shm-size` or `NET_ADMIN` capability

### Option D: Self-Hosted with Proxmox (Most Cost-Effective)

**Yes, Proxmox is viable and potentially ideal for beta:**

```
Proxmox Host (bare metal)
  ├── VM 1: Docker host (runs N containers)
  ├── VM 2: Docker host (runs N containers)
  ├── VM 3: Management (reverse proxy, auth, monitoring)
  └── Shared storage (Ceph/ZFS for persistent volumes)
```

**Pros:**
- Full control, no cloud markup (~3-5x cheaper than cloud)
- Can use powerful consumer/prosumer hardware
- No per-hour billing — fixed monthly cost (colocation or home lab)
- Ideal for beta with known user count

**Cons:**
- You manage everything (networking, backups, security, uptime)
- No auto-scaling across regions
- Single point of failure without redundancy

**Example Proxmox setup for beta (10-20 users):**
- 1x server: AMD Ryzen 9 / 64GB RAM / 1TB NVMe
- Each VM container: 2 cores + 2GB RAM
- Capacity: ~16 concurrent users per machine
- Cost: ~€100-150/month (Hetzner dedicated) vs ~€500-800/month on AWS

---

## 5. Cost Analysis

### Per-User Resource Cost

| Provider | 2 vCPU + 2GB RAM (per hour) | Monthly (24/7) | Monthly (8h/day) |
|----------|----------------------------|----------------|-------------------|
| AWS (t3.small) | ~€0.023/hr | ~€17 | ~€5.50 |
| Hetzner Cloud (CX22) | ~€0.008/hr | ~€5.50 | ~€1.80 |
| DigitalOcean | ~€0.018/hr | ~€13 | ~€4.30 |
| Self-hosted (Proxmox) | ~€0.003/hr* | ~€2* | ~€0.70* |

*Amortized cost of hardware + electricity + bandwidth

### Key Cost Drivers

1. **Idle containers are wasteful** — Chromium + Xorg consume ~300-500MB even idle
2. **Cold start is 15-20s** — acceptable for on-demand, but not instant
3. **Persistent storage** — plugin data needs to survive container restarts
4. **Bandwidth** — noVNC streams video frames; ~1-5 Mbps per active user

### Cost Optimization Strategies

- **Hibernate idle containers** — Stop after 10-15 min inactivity, restart on demand
- **Shared base layers** — All containers share the same Docker image (~1GB saved per instance)
- **Spot/preemptible instances** — For non-critical workloads (50-80% cheaper)
- **Right-size resources** — Many users may be fine with 1 core + 1GB for light browsing

---

## 6. What Needs to Change for Cloud Hosting

### Must-Have (Security & Multi-Tenancy)

| Change | Files | Effort |
|--------|-------|--------|
| Add authentication (JWT/OAuth2) | `bridge_ws.py`, new auth middleware | High |
| TLS everywhere (wss://, https://) | `bridge_ws.py`, `config.py`, nginx config | Medium |
| Switch from `--network host` to bridge networking | `Dockerfile`, `docker-compose.yml` | Medium |
| Reverse proxy per user (route subdomain → container) | New: nginx/Traefik config | Medium |
| Container lifecycle management (create/start/stop/destroy) | New: orchestration service | High |
| User management & billing | New: separate service | High |

### Nice-to-Have (UX & Operations)

| Change | Purpose |
|--------|---------|
| Session persistence (save/restore browser state) | Users can resume where they left off |
| Usage metering & quotas | Fair billing, prevent abuse |
| Container health monitoring | Auto-restart unhealthy instances |
| Geographic distribution | Lower latency for international users |
| Custom branding per tenant | White-label option |

---

## 7. Beta Launch Strategy

### Phase 1: Private Alpha (Proxmox / Single Server)

- **Target:** 5-10 hand-picked users (accessibility consultants, QA teams)
- **Infrastructure:** 1 Proxmox server (Hetzner dedicated, ~€100/month)
- **Auth:** Simple token-based access (no full OAuth yet)
- **Routing:** Subdomain per user: `user1.vm.inspekt.dev` → container port
- **Management:** Manual container provisioning (script-assisted)
- **Monitoring:** Basic uptime checks + resource monitoring
- **Pricing:** Free or nominal fee for feedback

### Phase 2: Closed Beta (Small Kubernetes Cluster)

- **Target:** 20-50 users with waitlist
- **Infrastructure:** 3-node K8s cluster (Hetzner Cloud or DigitalOcean)
- **Auth:** OAuth2 (GitHub/Google login)
- **Routing:** Automatic subdomain provisioning via ingress
- **Management:** API for container lifecycle (create, hibernate, destroy)
- **Monitoring:** Prometheus + Grafana
- **Pricing:** Tiered — free tier (limited hours) + paid tier

### Phase 3: Public Beta / GA

- **Target:** Open registration
- **Infrastructure:** Auto-scaling K8s with spot instances
- **Features:** Team workspaces, API access, CI/CD integration
- **Pricing:** Usage-based (per-minute or per-hour active time)

---

## 8. Recommended Beta Architecture (Proxmox)

```
┌──────────────────────────────────────────────┐
│ Proxmox Host (Hetzner Dedicated AX52)       │
│ AMD Ryzen 7 / 64GB RAM / 1TB NVMe          │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │ VM: Docker Host (56GB RAM)            │  │
│  │                                        │  │
│  │  Container 1 (user-alice)   2C/2GB    │  │
│  │  Container 2 (user-bob)     2C/2GB    │  │
│  │  Container 3 (user-carol)   2C/2GB    │  │
│  │  ...                                   │  │
│  │  Container N (max ~16 concurrent)      │  │
│  │                                        │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │ VM: Management (4GB RAM)              │  │
│  │                                        │  │
│  │  • Traefik (reverse proxy + TLS)      │  │
│  │  • Auth service (JWT validation)      │  │
│  │  • Container orchestrator (API)       │  │
│  │  • Monitoring (Prometheus/Grafana)    │  │
│  │  • Landing page / dashboard           │  │
│  │                                        │  │
│  └────────────────────────────────────────┘  │
│                                              │
└──────────────────────────────────────────────┘

DNS: *.vm.inspekt.dev → Proxmox host IP
TLS: Let's Encrypt wildcard via Traefik
```

### User Flow (Beta):

1. User signs up at `inspekt.dev` → gets invite token
2. Clicks "Launch VM" → orchestrator creates container
3. Redirected to `alice.vm.inspekt.dev` → Traefik routes to container's noVNC port
4. Uses Inspekt normally through browser (noVNC + control panel)
5. After 15 min idle → container hibernated (state saved)
6. Returns later → container resumed (~15-20s cold start)

---

## 9. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Users running crypto miners / abuse | High server cost | iptables restrictions already in place; add CPU quotas |
| Container escape | Security breach | Use gVisor or Kata containers for stronger isolation |
| noVNC latency over internet | Poor UX | Deploy in region closest to users; consider WebRTC |
| Scaling beyond single server | Growth bottleneck | Design orchestrator API to be provider-agnostic |
| Data loss on container crash | User frustration | Persist browser profile + plugin data to volumes |

---

## 10. Summary

| Question | Answer |
|----------|--------|
| Is it feasible? | Yes — the VM is already self-contained in Docker |
| What infrastructure? | Start with Proxmox (cheapest), graduate to K8s |
| Multiple users? | One container per user, ~2 cores + 2GB RAM each |
| Is it expensive? | €2-17/user/month depending on provider and usage |
| Self-hosted? | Proxmox is ideal for beta (~16 users per €100/month server) |
| Beta approach? | Private alpha on 1 server → closed beta on small K8s cluster |
| Engineering effort? | ~3-4 months for auth, multi-tenancy, orchestration, and billing |
