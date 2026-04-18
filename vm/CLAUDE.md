# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This is the **`vm/` subdirectory** — the Docker-based browser VM. The repo root has its own `CLAUDE.md` with project-wide rules (Inspekt MCP tools, CLI formatting, popover CSS build, VNC Shift+Tab fix, etc.). Read both; this file only covers what is specific to `vm/`.

---

## Working directory

Commands must run from the **repo root** (`../`), not from `vm/`. The Dockerfile uses `COPY` paths like `COPY inspekt /opt/inspekt/inspekt` that are resolved against the repo root. `docker-compose.yml` sets `context: ../..` to enforce this.

All make targets in the root `Makefile` know the right context. Prefer them over raw `docker` commands.

---

## Common commands

| Task | Command |
|------|---------|
| Daily dev (bundles on change, hot-swaps control-server) | `make dev-vm` |
| First-time / after Dockerfile change | `make vm-rebuild` (alias for `inspekt vm restart --rebuild`) |
| Start / stop / restart VM | `make vm-start` / `vm-stop` / `vm-restart` |
| Hot-restart a single service | `make vm-restart-{control,terminal,chromium,proxy}` |
| Regenerate `vm/dist/` without rebuilding | `make vm-bundle` (wraps `bun scripts/bundle-vm.mjs`) |
| List supervised services | `make vm-services` |
| Port health check | `make vm-health` |
| Shell into container | `make vm-shell` |
| Doctor (version + sync check) | `make doctor` |
| Verify host extension == VM extension | `make verify-extension-sync` |

Dev mode auto-activates when starting from the source repo (detected by `pyproject.toml`). It mounts `inspekt/`, `vm/css`, `vm/js`, `vm/control-panel.html`, `vm/servers/*.py`, and `extensions/` into the container. Python source reloads instantly; everything else needs the matching `supervisorctl restart` or a full container restart (noVNC caches static files in memory).

---

## Control panel architecture

`control-panel.html` is served at `http://127.0.0.1:6080/control.html`. It embeds **noVNC's `RFB` class directly** (no iframe) so Shift+Tab and other keyboard events reach JS; see the root CLAUDE.md for the monkey-patch details.

### CSS/JS modules and bundling

CSS files live in `vm/css/` and JS files live in `vm/js/`. `control-panel.html` references them between paired marker comments:

```html
<!-- APP_CSS_START -->
<link rel="stylesheet" href="/css/tokens.css">
...
<!-- APP_CSS_END -->

<!-- APP_JS_START -->
<script src="/js/config.js" defer></script>
...
<!-- APP_JS_END -->
```

`scripts/bundle-vm.mjs` (run via `make vm-bundle`) parses those markers, concatenates the files **in the listed order**, minifies with esbuild, and writes `vm/dist/{control.html, app.min.css, app.min.js}`. Production `control.html` in the image points at the bundled files; dev mode serves the individual source files.

**Load order matters** — many JS modules rely on globals set by earlier ones. When adding a file, insert it at the correct point between the markers; don't alphabetize.

The Docker build has a dedicated `bundle` stage (`FROM oven/bun:1-alpine AS bundle`) that runs the same script inside the image so a fresh clone can't ship stale `dist/`.

---

## Process model inside the container

`supervisord.conf` runs everything. Priority determines boot order:

| Priority | Program | Port | Purpose |
|----------|---------|------|---------|
| 100–400 | xorg, pulseaudio, x11vnc, novnc, openbox | 5900 / 6080 | Display stack |
| 350 | audio-server.py | — | WebSocket audio relay |
| 480 | mitmproxy | 8080 | Runs `proxy-scripts/master_addon.py` |
| 500 | chromium | — | Kiosk browser (via `inspekt-chromium.sh`) |
| 550 | inspekt-bridge | 8767 | Isolated bridge (NOT host's 8765) |
| 560 | inspekt-api | 80 | `uvicorn inspekt.app.api.server:app` |
| 570 | bore-server | 7835 + dynamic | Reverse tunnel for host→VM port forwarding |
| 600 | control-server.py | 8888 | Navigation, tabs, CDP proxy, screenshots, clipboard relay |
| 700 | terminal-server.py | 8889 | PTY-over-WebSocket for xterm.js |

**Host-visible ports:** 6080 (noVNC UI), 8888 (control API), 8889 (terminal WS), 7835 (bore). All four must be reachable — the CLI's `inspekt vm start` uses `--network host` so this is automatic; Docker Compose publishes them explicitly. If only 6080 is published, the UI loads but navigation, tabs, and terminal fail silently.

**Bridge URL inside the VM is always `http://localhost:8767`**, set by `INSPEKT_BRIDGE_URL` in `entrypoint.sh`. The isolated VM bridge is deliberately separate from the host's bridge on 8765.

---

## Restricted terminal user (security boundary)

The WebSocket terminal runs as the unprivileged `inspekt` user, not root. Several layers enforce this:

1. **PTY drops privileges** in `terminal-server.py` via `setgid`/`setuid` (hence the `SETUID`/`SETGID` capabilities in `docker-compose.yml`).
2. **Network restrictions** — `entrypoint.sh` applies iptables rules to the `inspekt` UID, allowing only loopback connections to ports 80, 8080, 8767, 8768, 8888. Everything else (including CDP on 9222 and the internet) is dropped. If you add a new localhost service the terminal needs to reach, **add an iptables ACCEPT rule in `entrypoint.sh`** or the call will hang.
3. **Restricted shell** — `ZDOTDIR=/etc/inspekt-shell` points zsh at a root-owned `zshrc-restricted` that the user cannot override. `PATH` is scoped to `/opt/inspekt/commands` (generated Inspekt CLI symlinks) and `/opt/inspekt/allowed-bin` (curated system utilities).
4. **Denylisted Inspekt subcommands** — the wrapper at `/opt/inspekt/commands/.wrapper` rejects `eval`, `exec`, `repl`, `plugin`, `yolo`, `domain`, `vm`, `do`, `mcp`, `autostart`. The symlinks for those are also removed in the Dockerfile. Add to both places if denylisting a new command.
5. **Interpreters non-executable to `other`** — `python3`, `npm`, `wget`, `mkcert` have `chmod o-x` applied. `node` and `env` stay executable (prettier/lightningcss need them) but are unreachable via PATH and blocked by iptables anyway.

When adding a new "safe" shell command to the VM terminal, put it in `allowed-bin` (either as a symlink or as a small wrapper script) — never expand PATH.

---

## mitmproxy script system

`proxy-scripts/master_addon.py` is the single mitmproxy entrypoint. It watches `/tmp/mitmproxy_config.json` and dynamically loads/unloads addon modules from `proxy-scripts/available/` (e.g. `strip_csp.py`, `inject_css.py`, `throttle.py`). When no scripts are enabled, it is a zero-overhead passthrough.

Adding a new proxy script:

1. Drop a file in `proxy-scripts/available/` that defines a class with one or more of `request`, `response`, `responseheaders` methods.
2. The addon is picked up on next config reload — no restart needed.
3. Default config (`proxy-scripts/default_config.json`) is copied to `/tmp/mitmproxy_config.json` on startup so changes to the default only apply to fresh containers.

---

## Assets baked into the image

The Dockerfile hand-copies files rather than `COPY vm/ /usr/share/novnc/` because noVNC serves from `/usr/share/novnc` but the VM also needs some files at other paths. When adding a new asset category (fonts, vendor libs, icons), add a matching `COPY vm/<dir> /usr/share/novnc/<dir>` line — the bundle stage doesn't handle static assets, only CSS/JS between the markers.

Vendor libraries (xterm, ninja-keys, sortable, codemirror) are **checked into `vm/vendor/`**, not pulled from npm at build time. See `vm/vendor/XTERM-VENDOR.md` and `NINJA-KEYS-PATCH.md` for the reason (local patches and version pinning).

---

## Persistent data

- Named Docker volume `inspekt-vm-data` → `/root/.config/inspekt/` (plugin data, `data.db`). Survives rebuilds. Nuke with `docker volume rm inspekt-vm-data`.
- Chromium profile caches are **cleared on every container start** by `entrypoint.sh` (for privacy and to force fresh extension loads). Don't rely on anything under `/root/.config/chromium/Default/` persisting.

---

## Variants

`variants/headless/` is an experimental pure-extension (no noVNC) variant for Chrome and Firefox. It is **not** built by the default targets. Unless you're explicitly working on that variant, changes to the main VM do not need parallel changes there.
